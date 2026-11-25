"""Agent-operated native installation and lifecycle."""
import argparse
import hashlib
import json
import os
import platform
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import urllib.request
import zipfile
from pathlib import Path
from command_mcp_tunnel_starter.cli import config_path, init_config, load_config
from command_mcp_tunnel_starter.diagnostics import print_diagnostics

ROOT = Path(__file__).resolve().parents[1]
VERSION = "v0.0.16"
HASHES = {
    ("linux", "amd64"): "d60cdba019bce451bcc3a15478cc5b9cb11270b049f5b56ea39a80b517f8b117",
    ("linux", "arm64"): "963d0384aaa7c798778479c45673f9051a4039dd891aef8f8978d2a1a628b74f",
    ("windows", "amd64"): "edef7241b0c647fcb30f1a80ff376b6b25c51927960f257a3f01e21b17c2aba6",
    ("windows", "arm64"): "ecd748288b9bd9cc8f5a963855eb143f4788b831475156703d0bafdcd2dcb149",
}
UNITS = ("command-mcp-v2.service", "command-mcp-v2-tunnel.service")


def run(*args, check=True, **kwargs):
    return subprocess.run([str(x) for x in args], check=check, **kwargs)


def target():
    os_name = platform.system().lower()
    arch = {"x86_64": "amd64", "amd64": "amd64", "aarch64": "arm64", "arm64": "arm64"}.get(platform.machine().lower())
    if (os_name, arch) not in HASHES:
        raise SystemExit("Unsupported OS/architecture; see manual documentation.")
    return os_name, arch


def executable_names(os_name):
    suffix = ".exe" if os_name == "windows" else ""
    return {"tunnel-client" + suffix, "cloudflared" + suffix, "cloudflared-manifest.json"}


def extract_verified(archive, destination, digest, os_name):
    if hashlib.sha256(archive.read_bytes()).hexdigest() != digest:
        raise ValueError("Official release SHA-256 mismatch")
    with zipfile.ZipFile(archive) as bundle:
        entries = bundle.infolist()
        names = [entry.filename for entry in entries]
        if len(names) != len(set(names)) or not executable_names(os_name).issubset(names):
            raise ValueError("Incomplete or duplicate release archive")
        for entry in entries:
            name = entry.filename
            if (not name or name in {".", ".."} or "/" in name or "\\" in name or ":" in name
                    or entry.is_dir() or stat.S_ISLNK(entry.external_attr >> 16)):
                raise ValueError("Unsafe release archive member")
        destination.mkdir(mode=0o700)
        for entry in entries:
            path = destination / entry.filename
            with path.open("xb") as out:
                out.write(bundle.read(entry))
            if os_name == "linux":
                path.chmod(0o700 if entry.filename in {"tunnel-client", "cloudflared"} else 0o600)


def install_client():
    os_name, arch = target()
    private = config_path().parent
    private.mkdir(parents=True, exist_ok=True, mode=0o700)
    if os.name != "nt":
        private.chmod(0o700)
    base = private / "bin"
    base.mkdir(parents=True, exist_ok=True, mode=0o700)
    dest = base / f"tunnel-client-{VERSION}-{os_name}-{arch}"
    exe = dest / ("tunnel-client.exe" if os_name == "windows" else "tunnel-client")
    if dest.exists():
        if not all((dest / name).is_file() for name in executable_names(os_name)):
            raise SystemExit("Existing tunnel installation incomplete; inspect before retrying.")
        return exe
    name = f"tunnel-client-{VERSION}-{os_name}-{arch}.zip"
    url = f"https://github.com/openai/tunnel-client/releases/download/{VERSION}/{name}"
    with tempfile.TemporaryDirectory(dir=base) as temp:
        archive = Path(temp) / name
        with urllib.request.urlopen(url, timeout=120) as src, archive.open("wb") as out:
            shutil.copyfileobj(src, out)
        stage = Path(temp) / "verified"
        extract_verified(archive, stage, HASHES[(os_name, arch)], os_name)
        stage.rename(dest)
    return exe


def systemd_quote(value, *, exec_arg=False):
    value = str(value)
    if any(c in value for c in "\r\n\0"):
        raise ValueError("Invalid service path")
    value = value.replace("\\", "\\\\").replace('"', '\\"').replace("%", "%%")
    if exec_arg:
        value = value.replace("$", "$$")
    return '"' + value + '"'


def unit_text(action, python, root):
    # WorkingDirectory is parsed as one path, not as a command-line argument.
    root = str(root)
    if any(c in root for c in "\r\n\0") or root != root.strip():
        raise ValueError("Invalid working directory")
    working = root.replace("%", "%%")
    ordering = "After=command-mcp-v2.service\nWants=command-mcp-v2.service\n" if action == "tunnel" else ""
    return (
        "[Unit]\nDescription=Private command MCP " + action + "\nStartLimitIntervalSec=120\nStartLimitBurst=5\n" + ordering +
        "[Service]\nType=simple\n"
        f"WorkingDirectory={working}\n"
        f"ExecStart={systemd_quote(python, exec_arg=True)} -m command_mcp_tunnel_starter {action}\n"
        "Restart=always\nRestartSec=10\nUMask=0077\n"
        "KillMode=control-group\n[Install]\nWantedBy=default.target\n"
    )


def systemctl(*args, check=True):
    return run("systemctl", "--user", *args, check=check)


def linux(action):
    directory = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))) / "systemd/user"
    if action != "status":
        for unit, mode in zip(UNITS, ("serve", "tunnel")):
            path = directory / unit
            if path.exists() and path.read_text() != unit_text(mode, sys.executable, ROOT):
                raise SystemExit(f"Existing different unit: {path}. Inspect/migrate explicitly.")
    if action == "install":
        run("systemctl", "--user", "show-environment", stdout=subprocess.DEVNULL)
        directory.mkdir(parents=True, exist_ok=True)
        for unit, mode in zip(UNITS, ("serve", "tunnel")):
            (directory / unit).write_text(unit_text(mode, sys.executable, ROOT))
        systemctl("daemon-reload")
        systemctl("enable", *UNITS)
        systemctl("reset-failed", *UNITS, check=False)
        systemctl("start", *UNITS)
    elif action == "uninstall":
        if not all((directory / unit).is_file() for unit in UNITS):
            raise SystemExit("Expected managed user units not found; inspect partial setup manually.")
        systemctl("disable", "--now", *reversed(UNITS))
        for unit in UNITS:
            (directory / unit).unlink()
        systemctl("daemon-reload")
    elif action == "status":
        systemctl("status", "--no-pager", *UNITS, check=False)
    else:
        if not all((directory / unit).is_file() for unit in UNITS):
            raise SystemExit("Managed units not found; run install first.")
        if action == "restart":
            systemctl("stop", *reversed(UNITS))
            systemctl("reset-failed", *UNITS, check=False)
            systemctl("start", *UNITS)
        else:
            if action == "start":
                systemctl("reset-failed", *UNITS, check=False)
            systemctl(action, *(reversed(UNITS) if action == "stop" else UNITS))


def windows(action):
    run("powershell.exe", "-NoProfile", "-NonInteractive", "-File",
        ROOT / "scripts/windows-service.ps1", "-Action", action, "-Python", sys.executable, "-Repo", ROOT)


def health(wait=False):
    attempts = 12 if wait else 1
    for i in range(attempts):
        result = run(sys.executable, "-m", "command_mcp_tunnel_starter", "check", check=False)
        if result.returncode == 0:
            print("Local checks passed. Verify a command from a new ChatGPT chat separately.")
            return 0
        if i < attempts - 1:
            time.sleep(5)
    return result.returncode


def install():
    if not config_path().exists():
        if not sys.stdin.isatty():
            raise SystemExit("First setup requires a local terminal for the hidden API-key prompt.")
        client = install_client()
        init_config(client_path=client)
    settings = load_config()
    client = Path(settings["tunnel_client_path"])
    if not client.is_absolute() or not client.is_file():
        raise SystemExit("Configure an existing absolute tunnel-client executable path before installing services.")


def preflight():
    os_name, arch = target()
    config = config_path()
    report = {
        "schema_version": 1, "platform": os_name, "architecture": arch,
        "python": platform.python_version(), "interactive_terminal": sys.stdin.isatty(),
        "existing_v2_config": config.is_file(),
        "service_manager_available": False, "service_manager": "systemd-user" if os_name == "linux" else "task-scheduler",
        "chatgpt_end_to_end": "not_tested",
    }
    if os_name == "linux":
        if shutil.which("systemctl"):
            try:
                report["service_manager_available"] = run("systemctl", "--user", "show-environment",
                    check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=8).returncode == 0
            except (OSError, subprocess.TimeoutExpired):
                pass
    else:
        try:
            report["service_manager_available"] = run("powershell.exe", "-NoProfile", "-NonInteractive",
                "-Command", "if (Get-Command Register-ScheduledTask -ErrorAction SilentlyContinue) { exit 0 }; exit 1",
                check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15).returncode == 0
        except (OSError, subprocess.TimeoutExpired):
            pass
    print(json.dumps(report, sort_keys=True))
    return 0 if report["service_manager_available"] else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("install", "preflight", "diagnostics", "start", "stop", "restart", "status", "check", "uninstall"))
    args = parser.parse_args()
    os_name, _ = target()
    if os.environ.get("COMMAND_MCP_CONFIG"):
        raise SystemExit("Native service setup currently supports the default private config only.")
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        raise SystemExit("Run under the intended non-root execution account.")
    if args.action == "preflight":
        return preflight()
    if args.action == "diagnostics":
        return print_diagnostics()
    if args.action == "check":
        return health()
    if args.action == "install":
        install()
    if args.action in {"install", "start", "restart"}:
        load_config()
    (linux if os_name == "linux" else windows)(args.action)
    if args.action in {"install", "start", "restart", "status"}:
        return health(wait=args.action != "status")
    return 0


if __name__ == "__main__":
    sys.exit(main())
