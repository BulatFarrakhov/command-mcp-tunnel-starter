import json
from urllib.error import URLError

from command_mcp_tunnel_starter import diagnostics as d


def configured(tmp_path, monkeypatch):
    path = tmp_path / "private.json"
    path.touch()
    client = tmp_path / "client"
    client.touch()
    client.chmod(0o700)
    monkeypatch.setattr(d.cli, "config_path", lambda: path)
    monkeypatch.setattr(d.cli, "load_config", lambda: {
        "tunnel_client_path": str(client), "server_port": 18202,
        "tunnel_health_port": 18203, "inbound_token": "private-test-token",
        "runtime_api_key": "private-test-key",
    })


def test_missing_config(tmp_path, monkeypatch):
    monkeypatch.setattr(d.cli, "config_path", lambda: tmp_path / "missing")
    result = d.diagnose()
    assert result["configuration"] == "missing"
    assert result["next_action"] == "install"
    assert not result["ready"]


def test_invalid_config_redacted(tmp_path, monkeypatch):
    configured(tmp_path, monkeypatch)
    def fail():
        raise ValueError("private-test-key")
    monkeypatch.setattr(d.cli, "load_config", fail)
    result = d.diagnose()
    assert result["configuration"] == "invalid_or_inaccessible"
    assert "private-test-key" not in json.dumps(result)


def test_ready_is_not_remote_verification(tmp_path, monkeypatch, capsys):
    configured(tmp_path, monkeypatch)
    def get(url, token):
        return (200 if token or url.endswith("readyz") else 401, "private response")
    monkeypatch.setattr(d.cli, "_get", get)
    assert d.print_diagnostics() == 0
    raw = capsys.readouterr().out
    assert "private" not in raw
    result = json.loads(raw)
    assert result["ready"]
    assert result["chatgpt_end_to_end"] == "not_tested"


def test_unprotected_server_is_not_ready(tmp_path, monkeypatch):
    configured(tmp_path, monkeypatch)
    monkeypatch.setattr(d.cli, "_get", lambda *a: (200, ""))
    result = d.diagnose()
    assert not result["ready"]
    assert result["next_action"] == "inspect_local_mcp_service"


def test_tunnel_unreachable(tmp_path, monkeypatch):
    configured(tmp_path, monkeypatch)
    def get(url, token):
        if url.endswith("readyz"):
            raise URLError("private error")
        return (200 if token else 401, "")
    monkeypatch.setattr(d.cli, "_get", get)
    result = d.diagnose()
    assert result["local_mcp"]["healthy"]
    assert not result["local_tunnel"]["reachable"]
    assert result["next_action"] == "inspect_tunnel_service_or_network"
    assert "private error" not in json.dumps(result)
