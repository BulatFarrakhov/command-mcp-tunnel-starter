"""Operator commands for Windows and Linux."""

import argparse
import getpass
import json
import os
import re
import secrets
import shutil
import socket
import subprocess
import warnings
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, ProxyHandler, HTTPRedirectHandler, build_opener


def config_path() -> Path:
    override = os.environ.get("COMMAND_MCP_CONFIG")
    if override:
        return Path(override).expanduser()
    if os.name == "nt":
        return Path(os.environ["APPDATA"]) / "command-mcp-v2" / "config.json"
    return Path.home() / ".config" / "command-mcp-v2" / "config.json"


def _secure_windows_file(path: Path) -> None:
    identity = subprocess.check_output(["whoami"], text=True).strip()
    subprocess.run(["icacls", str(path), "/grant:r", f"{identity}:" + ("(OI)(CI)(F)" if path.is_dir() else "(F)")], check=True, capture_output=True)
    subprocess.run(["icacls", str(path), "/inheritance:r"], check=True, capture_output=True)


DEFAULT_SERVER_PORT = 18202
DEFAULT_HEALTH_PORT = 18203


def ensure_ports_free(ports: tuple[int, ...]) -> None:
    for port in ports:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
            try:
                listener.bind(("127.0.0.1", port))
            except OSError as exc:
                raise SystemExit(f"Local port {port} is unavailable. Inspect existing listeners before installing.") from exc


def init_config(client_path: Path | None = None) -> None:
    path = config_path()
    if path.exists():
        raise SystemExit(f"Configuration already exists: {path}. Move it aside to reinitialize.")
    ensure_ports_free((DEFAULT_SERVER_PORT, DEFAULT_HEALTH_PORT))
    print("Create a tunnel in OpenAI Platform and obtain a runtime API key first.")
    tunnel_id = input("Tunnel ID (tunnel_...): ").strip()
    with warnings.catch_warnings():
        warnings.simplefilter("error", getpass.GetPassWarning)
        try:
            api_key = getpass.getpass("Runtime API key (hidden): ").strip()
        except getpass.GetPassWarning:
            raise SystemExit("A private interactive terminal is required for credential entry.") from None
    if client_path is not None:
        client = str(client_path)
    else:
        suggested = shutil.which("tunnel-client") or ""
        client = input(f"Absolute path to tunnel-client [{suggested}]: ").strip() or suggested
    if not Path(client).is_absolute() or not Path(client).is_file():
        raise SystemExit("Tunnel client must be an existing absolute executable path.")
    cwd = input(f"Default command directory [{Path.home()}]: ").strip() or str(Path.home())
    state = (Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "command-mcp-v2"
             if os.name == "nt" else Path.home() / ".local" / "state" / "command-mcp-v2")
    settings = {
        "tunnel_id": tunnel_id,
        "runtime_api_key": api_key,
        "tunnel_client_path": client,
        "inbound_token": secrets.token_urlsafe(48),
        "default_cwd": cwd,
        "state_dir": str(state),
        "server_port": DEFAULT_SERVER_PORT,
        "tunnel_health_port": DEFAULT_HEALTH_PORT,
        "max_concurrent_commands": 4,
        "max_output_bytes": 31_457_280,
        "max_timeout_seconds": 86_400,
    }
    validate(settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    if os.name != "nt":
        os.chmod(path.parent, 0o700)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(settings, handle, indent=2)
            handle.write("\n")
    else:
        _secure_windows_file(path.parent)
        with path.open("x", encoding="utf-8") as handle:
            json.dump(settings, handle, indent=2)
            handle.write("\n")
        _secure_windows_file(path)
    print(f"Saved private configuration at {path}")


def validate(settings: dict) -> None:
    required = ("tunnel_id", "runtime_api_key", "tunnel_client_path", "inbound_token", "default_cwd", "state_dir",
                "server_port", "tunnel_health_port", "max_concurrent_commands", "max_output_bytes", "max_timeout_seconds")
    missing = [key for key in required if key not in settings]
    if missing:
        raise ValueError(f"Missing config keys: {', '.join(missing)}")
    if not re.fullmatch(r"tunnel_[0-9a-f]{32}", settings["tunnel_id"]):
        raise ValueError("Invalid tunnel_id")
    if len(settings["runtime_api_key"]) < 20 or len(settings["inbound_token"]) < 30:
        raise ValueError("Runtime key or local token is missing")
    if not Path(settings["default_cwd"]).is_absolute() or not Path(settings["default_cwd"]).is_dir():
        raise ValueError("default_cwd must be an existing absolute directory")
    if not Path(settings["state_dir"]).is_absolute():
        raise ValueError("state_dir must be absolute")
    for key in ("server_port", "tunnel_health_port"):
        if not 1 <= settings[key] <= 65535:
            raise ValueError(f"Invalid {key}")
    if settings["server_port"] == settings["tunnel_health_port"]:
        raise ValueError("Server and tunnel health ports must differ")
    for key in ("max_concurrent_commands", "max_output_bytes", "max_timeout_seconds"):
        if settings[key] < 1:
            raise ValueError(f"Invalid {key}")


def load_config() -> dict:
    path = config_path()
    if not path.is_file():
        raise SystemExit(f"No config at {path}. Run: uv run command-mcp init")
    if os.name != "nt" and path.stat().st_mode & 0o077:
        raise SystemExit(f"Config is accessible to other users: {path}. Run chmod 600 on it.")
    settings = json.loads(path.read_text(encoding="utf-8"))
    validate(settings)
    return settings


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _get(url: str, token: str | None = None) -> tuple[int, str]:
    headers = {"X-Command-MCP-Token": token} if token else {}
    request = Request(url, headers=headers)
    try:
        with build_opener(ProxyHandler({}), NoRedirect()).open(request, timeout=5) as response:
            return response.status, ""
    except HTTPError as exc:
        return exc.code, ""


def check(settings: dict) -> None:
    base = f"http://127.0.0.1:{settings['server_port']}"
    try:
        anonymous, _ = _get(base + "/healthz")
        authenticated, payload = _get(base + "/healthz", settings["inbound_token"])
    except URLError as exc:
        raise SystemExit(f"MCP server unreachable on localhost: {exc.reason}") from exc
    if anonymous != 401 or authenticated != 200:
        raise SystemExit(f"MCP server auth check failed: anonymous={anonymous}, authenticated={authenticated}")
    print("MCP server: healthy, authenticated")
    try:
        ready, _ = _get(f"http://127.0.0.1:{settings['tunnel_health_port']}/readyz")
    except URLError as exc:
        raise SystemExit(f"Tunnel client unreachable on localhost: {exc.reason}") from exc
    if ready != 200:
        raise SystemExit(f"Tunnel client not ready (HTTP {ready})")
    print("Tunnel client: ready")


def tunnel_environment(settings):
    env = os.environ.copy()
    env.update({
        "CONTROL_PLANE_API_KEY": settings["runtime_api_key"],
        "CONTROL_PLANE_TUNNEL_ID": settings["tunnel_id"],
        "COMMAND_MCP_TOKEN": settings["inbound_token"],
        "MCP_SERVER_URL": f"http://127.0.0.1:{settings['server_port']}/mcp/",
        "MCP_EXTRA_HEADERS": "X-Command-MCP-Token: env:COMMAND_MCP_TOKEN",
        "HEALTH_LISTEN_ADDR": f"127.0.0.1:{settings['tunnel_health_port']}",
    })
    return env


def main() -> None:
    parser = argparse.ArgumentParser(description="Standalone private command MCP tunnel")
    parser.add_argument("action", choices=("init", "serve", "tunnel", "check"))
    action = parser.parse_args().action
    if action == "init":
        init_config()
        return
    settings = load_config()
    if action == "serve":
        import uvicorn
        from .server import create_app

        app, _, _ = create_app(settings)
        uvicorn.run(app, host="127.0.0.1", port=settings["server_port"], access_log=False)
    elif action == "tunnel":
        env = tunnel_environment(settings)
        subprocess.run([settings["tunnel_client_path"], "run"], env=env, check=True)
    else:
        check(settings)


if __name__ == "__main__":
    main()
