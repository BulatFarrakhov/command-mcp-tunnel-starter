"""Command-only MCP server; no Codex agent or gateway dependency."""

import asyncio
import hmac
import logging
import os
import signal
import subprocess
from contextlib import asynccontextmanager
from pathlib import Path

from mcp import types
from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel
from starlette.applications import Starlette
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route

from .store import Store


logger = logging.getLogger(__name__)
OUTPUT_CHUNK = 24_000


class CommandInfo(BaseModel):
    job_id: str
    request_id: str
    cwd: str
    status: str
    pid: int | None
    exit_code: int | None
    output: str
    output_offset: int
    next_offset: int
    output_total_bytes: int
    output_limit_reached: bool
    error: str | None


class Engine:
    def __init__(self, settings: dict):
        self.settings = settings
        self.state_dir = Path(settings["state_dir"])
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.output_dir = self.state_dir / "output"
        self.output_dir.mkdir(exist_ok=True)
        if os.name == "nt":
            identity = subprocess.check_output(["whoami"], text=True).strip()
            for path in (self.state_dir, self.output_dir):
                subprocess.run(["icacls", str(path), "/grant:r", f"{identity}:(F)"], check=True, capture_output=True)
                subprocess.run(["icacls", str(path), "/inheritance:r"], check=True, capture_output=True)
        else:
            os.chmod(self.state_dir, 0o700)
            os.chmod(self.output_dir, 0o700)
        self.store = Store(self.state_dir / "jobs.sqlite3")
        self.tasks: dict[str, asyncio.Task] = {}

    def output_path(self, job_id: str) -> Path:
        return self.output_dir / f"{job_id}.log"

    def public(self, job: dict, offset: int = 0) -> CommandInfo:
        path = self.output_path(job["id"])
        size = path.stat().st_size if path.exists() else 0
        if not 0 <= offset <= size:
            raise ValueError("offset is outside command output bounds")
        data = b""
        if path.exists():
            with path.open("rb") as handle:
                handle.seek(offset)
                data = handle.read(OUTPUT_CHUNK)
        return CommandInfo(
            job_id=job["id"], request_id=job["request_id"], cwd=job["cwd"],
            status=job["status"], pid=job["pid"], exit_code=job["exit_code"],
            output=data.decode("utf-8", errors="replace"), output_offset=offset,
            next_offset=offset + len(data), output_total_bytes=size,
            output_limit_reached=bool(job["output_limit_reached"]), error=job["error"],
        )

    async def stop_process(self, process: asyncio.subprocess.Process) -> None:
        if os.name == "nt":
            killer = await asyncio.create_subprocess_exec(
                "taskkill", "/PID", str(process.pid), "/T", "/F",
                stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
            )
            await killer.wait()
        else:
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                await asyncio.wait_for(process.wait(), timeout=3)
            except asyncio.TimeoutError:
                pass
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        await process.wait()

    async def drain(self, stream: asyncio.StreamReader, handle) -> bool:
        saved = 0
        reached = False
        cap = self.settings["max_output_bytes"]
        while chunk := await stream.read(65536):
            remaining = max(0, cap - saved)
            if remaining:
                part = chunk[:remaining]
                handle.write(part)
                handle.flush()
                saved += len(part)
            if len(chunk) > remaining:
                reached = True
        return reached

    async def finish_reader(self, reader: asyncio.Task | None,
                            process: asyncio.subprocess.Process | None) -> bool:
        if reader is None:
            return False
        try:
            return await asyncio.wait_for(asyncio.shield(reader), timeout=3)
        except asyncio.TimeoutError:
            if process is not None:
                await self.stop_process(process)
            reader.cancel()
            await asyncio.gather(reader, return_exceptions=True)
            return False

    async def run_job(self, job_id: str) -> None:
        job = self.store.get(job_id)
        process = None
        spawn = None
        reader = None
        handle = None
        try:
            path = self.output_path(job_id)
            handle = path.open("xb")
            if os.name != "nt":
                os.chmod(path, 0o600)
            env = os.environ.copy()
            # The child gets ordinary operator environment, never tunnel credentials.
            for name in ("CONTROL_PLANE_API_KEY", "CONTROL_PLANE_TUNNEL_ID", "COMMAND_MCP_TOKEN", "MCP_EXTRA_HEADERS"):
                env.pop(name, None)
            if os.name == "nt":
                args = ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", job["command"]]
                spawn_options = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW}
            else:
                args = ["/bin/bash", "-c", job["command"]]
                spawn_options = {"start_new_session": True}
            spawn = asyncio.create_task(asyncio.create_subprocess_exec(
                *args, cwd=job["cwd"], env=env, stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
                **spawn_options,
            ))
            process = await asyncio.shield(spawn)
            self.store.set_status(job_id, "running", pid=process.pid)
            reader = asyncio.create_task(self.drain(process.stdout, handle))
            try:
                await asyncio.wait_for(process.wait(), timeout=job["timeout_seconds"])
                status = "completed" if process.returncode == 0 else "failed"
                error = None
            except asyncio.TimeoutError:
                await self.stop_process(process)
                status = "timed_out"
                error = f"Command exceeded {job['timeout_seconds']} seconds"
            reached = await self.finish_reader(reader, process)
            self.store.set_status(job_id, status, exit_code=process.returncode,
                                  output_limit_reached=reached, error=error)
            logger.info("command_finished job_id=%s status=%s exit_code=%s", job_id, status, process.returncode)
        except asyncio.CancelledError:
            if process is None and spawn is not None:
                try:
                    process = await spawn
                except Exception:
                    pass
            if process is not None:
                await self.stop_process(process)
            await self.finish_reader(reader, process)
            self.store.set_status(job_id, "cancelled", exit_code=process.returncode if process else None,
                                  error="Command cancelled; earlier effects may remain")
            raise
        except Exception as exc:
            if process is not None:
                await self.stop_process(process)
            await self.finish_reader(reader, process)
            self.store.set_status(job_id, "failed", exit_code=process.returncode if process else None,
                                  error=f"Command could not run: {type(exc).__name__}: {str(exc)[:300]}")
            logger.warning("command_failed job_id=%s error_type=%s", job_id, type(exc).__name__)
        finally:
            if handle is not None:
                handle.close()
            self.tasks.pop(job_id, None)

    async def start(self, command: str, request_id: str, cwd: str | None = None,
                    timeout_seconds: int = 7200) -> CommandInfo:
        """Start a shell command without blocking; retry with the same UUID request_id."""
        cwd = cwd or self.settings["default_cwd"]
        if not command.strip() or len(command) > 8000:
            raise ValueError("command must be 1-8000 characters")
        if len(cwd) > 500 or not Path(cwd).is_absolute() or not Path(cwd).is_dir():
            raise ValueError("cwd must be an existing absolute directory")
        if not 1 <= timeout_seconds <= self.settings["max_timeout_seconds"]:
            raise ValueError("timeout_seconds outside configured range")
        job, created = self.store.submit(request_id, command, cwd, timeout_seconds,
                                         self.settings["max_concurrent_commands"])
        if created:
            task = asyncio.create_task(self.run_job(job["id"]))
            self.tasks[job["id"]] = task
            task.add_done_callback(lambda _: self.tasks.pop(job["id"], None))
        return self.public(job)

    async def get(self, job_id: str, offset: int = 0) -> CommandInfo:
        """Get job status, exit code, and the next output chunk. Reuse next_offset."""
        job = self.store.get(job_id)
        if not job:
            raise ValueError("Unknown command job_id")
        return self.public(job, offset)

    async def cancel(self, job_id: str) -> CommandInfo:
        """Stop the process tree. Effects from before cancellation remain."""
        job = self.store.get(job_id)
        if not job:
            raise ValueError("Unknown command job_id")
        task = self.tasks.get(job_id)
        if task and not task.done():
            task.cancel()
            if job["status"] == "queued":
                self.store.set_status(job_id, "cancelled", error="Command cancelled before it started")
            elif job["status"] == "running":
                self.store.set_status(job_id, "cancel_requested")
        return self.public(self.store.get(job_id))

    async def shutdown(self) -> None:
        tasks = list(self.tasks.values())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)


class TokenMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, token: str):
        super().__init__(app)
        self.token = token

    async def dispatch(self, request: Request, call_next):
        supplied = request.headers.get("X-Command-MCP-Token", "")
        if not hmac.compare_digest(supplied, self.token):
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        return await call_next(request)


def create_app(settings: dict) -> tuple[Starlette, FastMCP, Engine]:
    engine = Engine(settings)
    mcp = FastMCP(
        "Private Commands",
        instructions=(
            "Run direct shell commands on this computer with start_command. It returns a job ID quickly. "
            "Poll get_command with next_offset for status, exit code, and new output. "
            "Several commands may run concurrently. cancel_command stops a running process tree. "
            "Use the same request_id UUID when retrying an uncertain submission. "
            "Commands run with the host permissions of the configured service account."
        ),
        streamable_http_path="/", stateless_http=True, json_response=True,
    )

    async def start_command(command: str, request_id: str, cwd: str | None = None,
                            timeout_seconds: int = 7200) -> CommandInfo:
        """Start a direct command; return immediately with its job ID."""
        return await engine.start(command, request_id, cwd, timeout_seconds)

    async def get_command(job_id: str, offset: int = 0) -> CommandInfo:
        """Poll a command; pass next_offset on the next poll to read new output."""
        return await engine.get(job_id, offset)

    async def cancel_command(job_id: str) -> CommandInfo:
        """Stop a command process tree; earlier effects are not rolled back."""
        return await engine.cancel(job_id)

    mcp.tool(annotations=types.ToolAnnotations(readOnlyHint=False, destructiveHint=True, openWorldHint=True), structured_output=True)(start_command)
    mcp.tool(annotations=types.ToolAnnotations(readOnlyHint=True, openWorldHint=False), structured_output=True)(get_command)
    mcp.tool(annotations=types.ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=False), structured_output=True)(cancel_command)

    async def health(_: Request):
        return JSONResponse({"status": "ok", "tools": 3})

    @asynccontextmanager
    async def lifespan(_: Starlette):
        async with mcp.session_manager.run():
            try:
                yield
            finally:
                await engine.shutdown()

    app = Starlette(routes=[Route("/healthz", health), Mount("/mcp", app=mcp.streamable_http_app())], lifespan=lifespan)
    app.add_middleware(TokenMiddleware, token=settings["inbound_token"])
    return app, mcp, engine
