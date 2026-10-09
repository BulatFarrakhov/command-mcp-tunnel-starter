import asyncio
import os
import sys
import time
import uuid

import pytest
from starlette.testclient import TestClient

from command_mcp_tunnel_starter.server import create_app
from command_mcp_tunnel_starter.store import Store


def settings(tmp_path):
    return {
        "inbound_token": "test-token-with-sufficient-length-123456789",
        "state_dir": str(tmp_path / "state"),
        "default_cwd": str(tmp_path),
        "max_concurrent_commands": 2,
        "max_output_bytes": 10_485_760,
        "max_timeout_seconds": 86_400,
    }


def python_command(source):
    executable = f'& "{sys.executable}"' if os.name == "nt" else f"'{sys.executable}'"
    return f'{executable} -c "{source}"'


def test_exact_tools_and_http_auth(tmp_path):
    config = settings(tmp_path)
    app, mcp, _ = create_app(config)

    async def names():
        return {tool.name for tool in await mcp.list_tools()}

    assert asyncio.run(names()) == {"start_command", "get_command", "cancel_command"}
    with TestClient(app, base_url="http://127.0.0.1:18102") as client:
        assert client.get("/healthz").status_code == 401
        good = client.get("/healthz", headers={"X-Command-MCP-Token": config["inbound_token"]})
        assert good.status_code == 200
        assert good.json()["tools"] == 3
        headers = {"X-Command-MCP-Token": config["inbound_token"],
                   "Accept": "application/json, text/event-stream", "Content-Type": "application/json"}
        response = client.post("/mcp/", headers=headers, json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}})
        assert response.status_code == 200
        assert {tool["name"] for tool in response.json()["result"]["tools"]} == {"start_command", "get_command", "cancel_command"}
        call = client.post("/mcp/", headers=headers, json={"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                                                   "params": {"name": "start_command", "arguments": {
                                                       "command": python_command("print('transport')"),
                                                       "request_id": str(uuid.uuid4()), "cwd": str(tmp_path), "timeout_seconds": 10}}})
        assert call.status_code == 200
        job_id = call.json()["result"]["structuredContent"]["job_id"]
        for _ in range(60):
            polled = client.post("/mcp/", headers=headers, json={"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                                                          "params": {"name": "get_command", "arguments": {"job_id": job_id}}})
            result = polled.json()["result"]["structuredContent"]
            if result["status"] == "completed":
                assert result["exit_code"] == 0
                assert result["output"].splitlines() == ["transport"]
                break
            time.sleep(0.1)
        else:
            pytest.fail("MCP transport command did not complete")


def test_concurrency_idempotency_and_incremental_output(tmp_path):
    config = settings(tmp_path)
    _, _, engine = create_app(config)

    async def scenario():
        command = python_command("import time; print('first', flush=True); time.sleep(1); print('last', flush=True)")
        request_id = str(uuid.uuid4())
        first = await engine.start(command, request_id)
        same = await engine.start(command, request_id)
        assert same.job_id == first.job_id
        second = await engine.start(python_command("print('other')"), str(uuid.uuid4()))
        assert second.job_id != first.job_id
        with pytest.raises(ValueError, match="slots are busy"):
            await engine.start(python_command("print('third')"), str(uuid.uuid4()))
        for _ in range(30):
            partial = await engine.get(first.job_id)
            if partial.output:
                break
            await asyncio.sleep(0.1)
        assert partial.status == "running"
        assert partial.output.splitlines() == ["first"]
        await asyncio.gather(*list(engine.tasks.values()))
        rest = await engine.get(first.job_id, partial.next_offset)
        assert rest.status == "completed"
        assert rest.exit_code == 0
        assert rest.output.splitlines() == ["last"]
        assert (await engine.get(second.job_id)).output.splitlines() == ["other"]
        with pytest.raises(ValueError, match="different command"):
            await engine.start(python_command("print('changed')"), request_id)

    asyncio.run(scenario())


def test_cancel_and_output_cap(tmp_path):
    config = settings(tmp_path)
    config["max_output_bytes"] = 4
    _, _, engine = create_app(config)

    async def scenario():
        capped = await engine.start(python_command("print('abcdef')"), str(uuid.uuid4()))
        slow = await engine.start(python_command("import time; time.sleep(30)"), str(uuid.uuid4()))
        await asyncio.sleep(0.3)
        await engine.cancel(slow.job_id)
        await asyncio.gather(*list(engine.tasks.values()), return_exceptions=True)
        result = await engine.get(slow.job_id)
        assert result.status == "cancelled"
        assert "earlier effects" in result.error
        cap = await engine.get(capped.job_id)
        assert cap.output == "abcd"
        assert cap.output_limit_reached

    asyncio.run(scenario())


def test_restart_does_not_replay_job(tmp_path):
    path = tmp_path / "jobs.sqlite3"
    store = Store(path)
    request_id = str(uuid.uuid4())
    job, created = store.submit(request_id, "some command", str(tmp_path), 10, 2)
    assert created
    restarted = Store(path)
    assert restarted.get(job["id"])["status"] == "interrupted"
    retried, created = restarted.submit(request_id, "some command", str(tmp_path), 10, 2)
    assert not created
    assert retried["id"] == job["id"]


def test_timeout_records_terminal_state(tmp_path):
    config = settings(tmp_path)
    _, _, engine = create_app(config)

    async def scenario():
        job = await engine.start(python_command("import time; time.sleep(5)"), str(uuid.uuid4()), timeout_seconds=1)
        await asyncio.gather(*list(engine.tasks.values()))
        result = await engine.get(job.job_id)
        assert result.status == "timed_out"
        assert result.exit_code is not None
        assert "exceeded" in result.error

    asyncio.run(scenario())
