import json
import os

from command_mcp_tunnel_starter import cli


def test_init_writes_private_config_outside_repo(tmp_path, monkeypatch):
    path = tmp_path / "config" / "config.json"
    monkeypatch.setenv("COMMAND_MCP_CONFIG", str(path))
    client = tmp_path / "tunnel-client"
    client.touch()
    monkeypatch.setattr(cli, "ensure_ports_free", lambda _: None)
    answers = iter(["tunnel_" + "a" * 32, str(tmp_path)])
    monkeypatch.setattr("builtins.input", lambda _: next(answers))
    monkeypatch.setattr(cli.getpass, "getpass", lambda _: "sk-test-" + "x" * 30)
    cli.init_config(client_path=client)
    loaded = cli.load_config()
    assert loaded["tunnel_id"] == "tunnel_" + "a" * 32
    assert len(loaded["inbound_token"]) >= 30
    assert loaded["server_port"] == 18202
    assert loaded["tunnel_health_port"] == 18203
    assert loaded["tunnel_client_path"] == str(client)
    assert loaded["max_output_bytes"] == 31_457_280
    assert json.loads(path.read_text())["default_cwd"] == str(tmp_path)
    if os.name != "nt":
        assert path.stat().st_mode & 0o077 == 0


def test_tunnel_launcher_sets_private_local_hop(tmp_path, monkeypatch):
    settings = {
        "tunnel_id": "tunnel_" + "a" * 32,
        "runtime_api_key": "sk-test-" + "x" * 30,
        "tunnel_client_path": "tunnel-client",
        "inbound_token": "local-token-" + "y" * 40,
        "default_cwd": str(tmp_path),
        "state_dir": str(tmp_path / "state"),
        "server_port": 18102,
        "tunnel_health_port": 18103,
        "max_concurrent_commands": 2,
        "max_output_bytes": 1024,
        "max_timeout_seconds": 10,
    }
    monkeypatch.setattr(cli, "load_config", lambda: settings)
    monkeypatch.setattr(cli.argparse.ArgumentParser, "parse_args", lambda _: type("Args", (), {"action": "tunnel"})())
    captured = {}

    def fake_run(args, *, env, check):
        captured.update({"args": args, "env": env, "check": check})

    monkeypatch.setattr(cli.subprocess, "run", fake_run)
    cli.main()
    assert captured["args"] == ["tunnel-client", "run"]
    assert captured["env"]["MCP_SERVER_URL"] == "http://127.0.0.1:18102/mcp/"
    assert captured["env"]["MCP_EXTRA_HEADERS"] == "X-Command-MCP-Token: env:COMMAND_MCP_TOKEN"
    assert captured["env"]["HEALTH_LISTEN_ADDR"] == "127.0.0.1:18103"
    assert captured["env"]["CONTROL_PLANE_API_KEY"] == settings["runtime_api_key"]


def test_port_conflict():
    import socket
    import pytest
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        with pytest.raises(SystemExit, match="unavailable"):
            cli.ensure_ports_free((listener.getsockname()[1],))
