"""Real loopback service and process checks, without a real tunnel or credentials."""
import json
import os
import socket
import subprocess
import sys
import time
from urllib.error import URLError

from command_mcp_tunnel_starter import cli


def unused_port():
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


def test_supervised_server_lifecycle(tmp_path):
    port = unused_port()
    health_port = unused_port()
    while health_port == port:
        health_port = unused_port()
    token = "dummy-" + "x" * 40
    config = {
        "tunnel_id": "tunnel_" + "a" * 32,
        "runtime_api_key": "dummy-" + "x" * 40,
        "tunnel_client_path": sys.executable,
        "inbound_token": token,
        "default_cwd": str(tmp_path),
        "state_dir": str(tmp_path / "state"),
        "server_port": port,
        "tunnel_health_port": health_port,
        "max_concurrent_commands": 2,
        "max_output_bytes": 1024,
        "max_timeout_seconds": 30,
    }
    path = tmp_path / "config.json"
    path.write_text(json.dumps(config))
    if os.name != "nt":
        path.chmod(0o600)
    env = dict(os.environ, COMMAND_MCP_CONFIG=str(path))
    url = f"http://127.0.0.1:{port}/healthz"
    with (tmp_path / "supervisor.log").open("w+b") as log:
        proc = subprocess.Popen(
            [sys.executable, "-m", "command_mcp_tunnel_starter.supervisor", "serve"],
            env=env, stdin=subprocess.DEVNULL, stdout=log, stderr=log,
        )
        try:
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                if proc.poll() is not None:
                    log.seek(0)
                    raise AssertionError(f"Supervisor exited: {log.read().decode(errors='replace')}")
                try:
                    if cli._get(url, token)[0] == 200:
                        break
                except (URLError, OSError):
                    pass
                time.sleep(0.2)
            else:
                raise AssertionError("Supervised server did not become ready")
            assert cli._get(url)[0] == 401
            assert cli._get(url, token)[0] == 200
        finally:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=10)
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            try:
                cli._get(url, token)
            except (URLError, OSError):
                break
            time.sleep(0.2)
        else:
            raise AssertionError("Server child still listening after supervisor stopped")
