"""Safe, machine-readable local checks. No credentials or response bodies."""
import json
import os
from pathlib import Path
from urllib.error import URLError

from . import cli


def endpoint_status(url, token=None):
    try:
        status, _ = cli._get(url, token)
        return {"http_status": status, "reachable": True}
    except (URLError, OSError, TimeoutError, ValueError):
        return {"http_status": None, "reachable": False}


def diagnose():
    result = {
        "schema_version": 1,
        "configuration": "missing",
        "client_installed": False,
        "local_mcp": None,
        "local_tunnel": None,
        "chatgpt_end_to_end": "not_tested",
        "ready": False,
        "next_action": "install",
    }
    try:
        if not cli.config_path().is_file():
            return result
        settings = cli.load_config()
    except (SystemExit, OSError, ValueError, TypeError, KeyError):
        result.update(configuration="invalid_or_inaccessible", next_action="inspect_private_config")
        return result
    result["configuration"] = "valid"
    client = Path(settings["tunnel_client_path"])
    result["client_installed"] = client.is_absolute() and client.is_file() and (os.name == "nt" or os.access(client, os.X_OK))
    base = f"http://127.0.0.1:{settings['server_port']}/healthz"
    anonymous = endpoint_status(base)
    authenticated = endpoint_status(base, settings["inbound_token"])
    local_ok = anonymous["http_status"] == 401 and authenticated["http_status"] == 200
    result["local_mcp"] = {
        "anonymous": anonymous,
        "authenticated": authenticated,
        "healthy": local_ok,
    }
    tunnel = endpoint_status(f"http://127.0.0.1:{settings['tunnel_health_port']}/readyz")
    tunnel["ready"] = tunnel["http_status"] == 200
    result["local_tunnel"] = tunnel
    result["ready"] = result["client_installed"] and local_ok and tunnel["ready"]
    if not result["client_installed"]:
        result["next_action"] = "inspect_tunnel_client"
    elif not local_ok:
        result["next_action"] = "inspect_local_mcp_service"
    elif not tunnel["ready"]:
        result["next_action"] = "inspect_tunnel_service_or_network"
    else:
        result["next_action"] = "verify_command_in_chatgpt"
    return result


def print_diagnostics():
    result = diagnose()
    print(json.dumps(result, sort_keys=True))
    return 0 if result["ready"] else 1
