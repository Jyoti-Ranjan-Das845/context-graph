"""Sync progress, written to a JSON file so the UI and CLI can show it while a sync runs."""

from __future__ import annotations

import fcntl
import json
import os
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator


PULL_FIELDS = ("pull", "records", "message", "missing", "started_at", "finished_at")
"""Per-tool fields that describe the latest pull. They are kept when a run does not pull (e.g. `cg sync --no-pull`)."""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class SyncStatusWriter:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._status: dict[str, Any] = {}

    def start(self, trigger: str) -> None:
        previous = self.read()
        last_pulls = {
            source_id: {k: v for k, v in run.items() if k in PULL_FIELDS}
            for source_id, run in previous.get("sources", {}).items()
            if run.get("pull") not in (None, "running")
        }
        self._status = {
            "state": "running",
            "trigger": trigger,
            "started_at": now(),
            "finished_at": None,
            "step": "starting",
            "sources": last_pulls,
            "code": {},
            "graph": {},
            "enrichment": {},
            "error": None,
            "last_success_at": previous.get("last_success_at"),
        }
        self._write()

    def step(self, name: str) -> None:
        self._status["step"] = name
        self._write()

    def source(self, source_id: str, **fields: Any) -> None:
        self._status["sources"].setdefault(source_id, {}).update(fields)
        self._write()

    def section(self, name: str, value: dict[str, Any]) -> None:
        self._status[name] = value
        self._write()

    def finish(self, error: str | None = None) -> None:
        self._status.update(state="failed" if error else "idle", step="done", finished_at=now(), error=error)
        if not error:
            self._status["last_success_at"] = self._status["finished_at"]
        self._write()

    def read(self) -> dict[str, Any]:
        if not self._path.exists():
            return {"state": "never_run"}
        try:
            return json.loads(self._path.read_text())
        except json.JSONDecodeError:
            return {"state": "unknown"}

    def _write(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._status, indent=2, default=str))
        os.replace(tmp, self._path)


class SyncAlreadyRunning(RuntimeError):
    pass


@contextmanager
def sync_lock(path: Path) -> Iterator[None]:
    """An exclusive, non-blocking file lock: only one sync at a time, across processes."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise SyncAlreadyRunning("A sync is already running") from exc
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)
