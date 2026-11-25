"""Read allowlisted service-manager fields; never emit logs or arguments."""
import json
import os
import subprocess
from pathlib import Path

UNITS = ("command-mcp-v2.service", "command-mcp-v2-tunnel.service")
FIELDS = ("LoadState", "ActiveState", "SubState", "UnitFileState", "Result", "ExecMainStatus", "NRestarts")
ALLOWED = set(FIELDS)


def parse_systemd(stdout):
    result = {}
    for line in stdout.splitlines():
        key, sep, value = line.partition("=")
        if sep and key in ALLOWED:
            result[key] = value[:80]
    return result


def linux_status():
    result = {"manager": "systemd-user", "available": False, "services": [], "linger": "unknown"}
    for name in UNITS:
        try:
            p = subprocess.run(["systemctl", "--user", "show", name, *[f"--property={x}" for x in FIELDS]],
                               capture_output=True, text=True, timeout=8, check=False)
            if p.returncode == 0:
                result["available"] = True
            result["services"].append({"name": name, **parse_systemd(p.stdout)})
        except (OSError, subprocess.TimeoutExpired):
            result["services"].append({"name": name})
    try:
        p = subprocess.run(["loginctl", "show-user", str(os.getuid()), "--property=Linger", "--value"],
                           capture_output=True, text=True, timeout=8, check=False)
        val = p.stdout.strip()
        if p.returncode == 0 and val in {"yes", "no"}:
            result["linger"] = val
    except (OSError, subprocess.TimeoutExpired):
        pass
    return result


def windows_status():
    result = {"manager": "task-scheduler", "available": False, "services": []}
    path = Path(__file__).resolve().parents[2] / "scripts" / "windows-service.ps1"
    try:
        p = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-File", str(path),
                            "-Action", "diagnostics", "-Python", "unused", "-Repo", "unused"],
                           capture_output=True, text=True, timeout=20, check=False)
        if p.returncode == 0:
            items = json.loads(p.stdout)
            if isinstance(items, list):
                result["available"] = True
                allowed = {"role", "state", "enabled", "logon_type", "last_result", "boot_trigger", "owned"}
                for row in items:
                    if isinstance(row, dict):
                        result["services"].append({k: v for k, v in row.items() if k in allowed})
    except (OSError, subprocess.TimeoutExpired, ValueError):
        pass
    return result


def service_status():
    return windows_status() if os.name == "nt" else linux_status()
