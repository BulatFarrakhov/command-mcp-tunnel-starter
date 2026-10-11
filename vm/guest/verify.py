"""Local authenticated smoke check. Does not display tokens or API responses."""

import json
import subprocess
import time
import uuid
from urllib.request import Request, urlopen

from command_mcp_tunnel_starter.cli import check, load_config


def check_listeners(settings: dict) -> None:
    for port in (settings["server_port"], settings["tunnel_health_port"]):
        result = subprocess.run(
            ["ss", "-H", "-ltn", f"sport = :{port}"],
            check=True, text=True, capture_output=True,
        )
        addresses = [line.split()[3] for line in result.stdout.splitlines()]
        if addresses != [f"127.0.0.1:{port}"]:
            raise RuntimeError("Expected exactly one loopback-only service listener")


def verify(settings: dict) -> None:
    check(settings)
    check_listeners(settings)

    def rpc(method: str, params: dict) -> dict:
        request = Request(
            f"http://127.0.0.1:{settings['server_port']}/mcp/",
            data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode(),
            headers={"X-Command-MCP-Token": settings["inbound_token"],
                     "Accept": "application/json, text/event-stream", "Content-Type": "application/json"},
        )
        with urlopen(request, timeout=10) as response:
            result = json.load(response)
        if "error" in result or result.get("result", {}).get("isError"):
            raise RuntimeError("Local MCP smoke call failed; response omitted to protect private data")
        return result["result"]

    tools = rpc("tools/list", {})["tools"]
    if {tool["name"] for tool in tools} != {"start_command", "get_command", "cancel_command"}:
        raise RuntimeError("Unexpected MCP tool list")
    arguments = {
        "command": "test \"$(pwd)\" = /workspace && test \"$(id -un)\" = agent && sudo -n true && printf 'guest-smoke-ok\\n'",
        "request_id": str(uuid.uuid4()),
        "timeout_seconds": 10,
    }
    first = rpc("tools/call", {"name": "start_command", "arguments": arguments})["structuredContent"]
    second = rpc("tools/call", {"name": "start_command", "arguments": arguments})["structuredContent"]
    if first["job_id"] != second["job_id"]:
        raise RuntimeError("Submission idempotency check failed")
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        info = rpc("tools/call", {"name": "get_command", "arguments": {"job_id": first["job_id"]}})["structuredContent"]
        if info["status"] == "completed":
            if info["exit_code"] != 0 or info["output"].strip() != "guest-smoke-ok":
                raise RuntimeError("Unexpected guest command result")
            print("Verified three MCP tools, request idempotency, /workspace, agent, and guest sudo.")
            return
        if info["status"] not in {"queued", "running"}:
            raise RuntimeError("Guest smoke command failed")
        time.sleep(0.2)
    raise RuntimeError("Guest smoke command did not finish")


if __name__ == "__main__":
    verify(load_config())
