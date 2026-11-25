from types import SimpleNamespace
from command_mcp_tunnel_starter import supervisor as s

SETTINGS = {"server_port": 18202, "tunnel_health_port": 18203, "inbound_token": "test"}


def test_tunnel_not_ready_is_not_a_hang(monkeypatch):
    monkeypatch.setattr(s, "endpoint_status", lambda *a: {"reachable": True, "http_status": 503})
    assert s.probe("tunnel", SETTINGS) == "remote_not_ready"


def test_auth_mismatch(monkeypatch):
    monkeypatch.setattr(s, "endpoint_status", lambda *a: {"reachable": True, "http_status": 200})
    assert s.probe("serve", SETTINGS) == "auth_contract_failure"


class Stop:
    def __init__(self, max_ticks):
        self.ticks = 0
        self.max_ticks = max_ticks
    def is_set(self):
        return self.ticks >= self.max_ticks
    def wait(self, _):
        self.ticks += 1


def test_repeated_local_failure_exits(monkeypatch):
    monkeypatch.setattr(s, "probe", lambda *a: "unresponsive")
    stop = Stop(10)
    child = SimpleNamespace(poll=lambda: None)
    assert s.monitor("serve", SETTINGS, child, stop, clock=lambda: 0, grace=0) == 1
    assert stop.ticks == 2


def test_remote_unready_does_not_trigger_restarts(monkeypatch):
    monkeypatch.setattr(s, "probe", lambda *a: "remote_not_ready")
    stop = Stop(10)
    assert s.monitor("tunnel", SETTINGS, SimpleNamespace(poll=lambda: None), stop,
                     clock=lambda: 0, grace=0) == 0
    assert stop.ticks == 10


def test_exited_child():
    assert s.monitor("serve", SETTINGS, SimpleNamespace(poll=lambda: 0), Stop(10)) == 1


def test_transient_failure_resets_budget(monkeypatch):
    states = iter(["unresponsive", "unresponsive", "healthy", "unresponsive", "healthy"])
    monkeypatch.setattr(s, "probe", lambda *a: next(states))
    assert s.monitor("serve", SETTINGS, SimpleNamespace(poll=lambda: None), Stop(5),
                     clock=lambda: 0, grace=0) == 0
