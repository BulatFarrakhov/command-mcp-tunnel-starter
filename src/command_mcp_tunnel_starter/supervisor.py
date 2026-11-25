"""Monitor one local component; the OS manager controls restart budgets."""
import argparse
import os
import signal
import subprocess
import sys
import threading
import time

from . import cli
from .diagnostics import endpoint_status

START_GRACE = 45
CHECK_INTERVAL = 10
FAILURE_LIMIT = 3


def probe(role, settings):
    if role == "serve":
        url = f"http://127.0.0.1:{settings['server_port']}/healthz"
        anon = endpoint_status(url)
        auth = endpoint_status(url, settings["inbound_token"])
        if anon["http_status"] == 401 and auth["http_status"] == 200:
            return "healthy"
        if anon["reachable"] and anon["http_status"] != 401:
            return "auth_contract_failure"
        if auth["reachable"] and auth["http_status"] in (401, 403):
            return "auth_contract_failure"
        return "unresponsive"
    result = endpoint_status(f"http://127.0.0.1:{settings['tunnel_health_port']}/readyz")
    if result["reachable"]:
        return "healthy" if result["http_status"] == 200 else "remote_not_ready"
    return "unresponsive"


def command(role, settings):
    if role == "serve":
        return [sys.executable, "-m", "command_mcp_tunnel_starter", "serve"], os.environ.copy()
    return [settings["tunnel_client_path"], "run"], cli.tunnel_environment(settings)


def stop_child(child):
    if child.poll() is not None:
        return
    if os.name == "nt":
        try:
            subprocess.run(["taskkill", "/PID", str(child.pid), "/T", "/F"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           check=False, timeout=15)
        except (OSError, subprocess.TimeoutExpired):
            child.terminate()
    else:
        child.terminate()
    try:
        child.wait(timeout=12)
    except subprocess.TimeoutExpired:
        child.kill()
        child.wait(timeout=5)


def monitor(role, settings, child, stop, clock=time.monotonic, interval=CHECK_INTERVAL,
            grace=START_GRACE, limit=FAILURE_LIMIT):
    deadline = clock() + grace
    failures = 0
    while not stop.is_set():
        if child.poll() is not None:
            print(f"{role}: component exited", flush=True)
            return 1
        if clock() >= deadline:
            state = probe(role, settings)
            if state == "auth_contract_failure":
                print(f"{role}: local authentication contract failed; inspect listeners", flush=True)
                return 2
            if state == "unresponsive":
                failures += 1
                if failures >= limit:
                    print(f"{role}: repeated local health failure", flush=True)
                    return 1
            else:
                failures = 0
        stop.wait(interval)
    return 0


def supervise(role):
    settings = cli.load_config()
    if os.name == "nt":
        from .windows_job import contain_current_process
        try:
            job_handle = contain_current_process()
        except OSError:
            print("Unable to contain Windows process tree; not starting component", flush=True)
            return 2
    stop = threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stop.set())
    args, env = command(role, settings)
    # Third-party logs can include sensitive data.
    kwargs = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL} if role == "tunnel" else {}
    child = subprocess.Popen(args, env=env, stdin=subprocess.DEVNULL, **kwargs)
    try:
        return monitor(role, settings, child, stop)
    finally:
        stop_child(child)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("role", choices=("serve", "tunnel"))
    return supervise(parser.parse_args().role)


if __name__ == "__main__":
    sys.exit(main())
