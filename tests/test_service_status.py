from command_mcp_tunnel_starter import service_status as s


def test_systemd_allowlist():
    result = s.parse_systemd("ActiveState=active\nExecMainStatus=0\nEnvironment=private-secret\nExecStart=private-arguments\n")
    assert result == {"ActiveState": "active", "ExecMainStatus": "0"}
