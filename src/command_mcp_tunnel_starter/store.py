"""Durable, idempotent command job records."""

import hashlib
import json
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path


ACTIVE = ("queued", "running", "cancel_requested")


class Store:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY, request_id TEXT NOT NULL UNIQUE,
                fingerprint TEXT NOT NULL, command TEXT NOT NULL, cwd TEXT NOT NULL,
                timeout_seconds INTEGER NOT NULL, status TEXT NOT NULL,
                pid INTEGER, exit_code INTEGER, output_limit_reached INTEGER NOT NULL DEFAULT 0,
                error TEXT, created_at REAL NOT NULL, updated_at REAL NOT NULL
            )""")
            # An orphaned command can have changed files. Never silently replay it.
            db.execute("UPDATE jobs SET status='interrupted', error='Service restarted; inspect effects before retrying', updated_at=? WHERE status IN ('queued','running','cancel_requested')", (time.time(),))

    @contextmanager
    def _connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def submit(self, request_id: str, command: str, cwd: str, timeout_seconds: int,
               max_active: int) -> tuple[dict, bool]:
        uuid.UUID(request_id)
        fingerprint = hashlib.sha256(json.dumps(
            [command, cwd, timeout_seconds], separators=(",", ":")
        ).encode()).hexdigest()
        now = time.time()
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            existing = db.execute("SELECT * FROM jobs WHERE request_id=?", (request_id,)).fetchone()
            if existing:
                if existing["fingerprint"] != fingerprint:
                    raise ValueError("request_id was already used for a different command")
                return dict(existing), False
            count = db.execute("SELECT count(*) FROM jobs WHERE status IN ('queued','running','cancel_requested')").fetchone()[0]
            if count >= max_active:
                raise ValueError("Command slots are busy; try again later")
            job_id = str(uuid.uuid4())
            db.execute("INSERT INTO jobs (id,request_id,fingerprint,command,cwd,timeout_seconds,status,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
                       (job_id, request_id, fingerprint, command, cwd, timeout_seconds, "queued", now, now))
            return self.get(job_id, db), True

    def get(self, job_id: str, db=None) -> dict | None:
        uuid.UUID(job_id)
        if db is None:
            with self._connect() as connection:
                row = connection.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        else:
            row = db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        return dict(row) if row else None

    def set_status(self, job_id: str, status: str, *, pid: int | None = None,
                   exit_code: int | None = None, output_limit_reached: bool | None = None,
                   error: str | None = None) -> None:
        with self._connect() as db:
            cursor = db.execute("UPDATE jobs SET status=?, pid=COALESCE(?,pid), exit_code=COALESCE(?,exit_code), output_limit_reached=COALESCE(?,output_limit_reached), error=?, updated_at=? WHERE id=?",
                                (status, pid, exit_code, int(output_limit_reached) if output_limit_reached is not None else None,
                                 error, time.time(), job_id))
            if cursor.rowcount != 1:
                raise ValueError("Unknown job_id")
