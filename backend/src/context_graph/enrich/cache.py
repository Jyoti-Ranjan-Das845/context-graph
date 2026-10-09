"""A persistent cache so unchanged text is never sent to the LLM twice."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class LLMCache:
    def __init__(self, path: Path) -> None:
        self._path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as con:
            con.execute(
                "create table if not exists results (key text primary key, value text not null, created_at text not null)"
            )

    @staticmethod
    def key(*parts: str) -> str:
        return hashlib.sha256("\x1f".join(parts).encode()).hexdigest()

    def get_many(self, keys: list[str]) -> dict[str, Any]:
        found: dict[str, Any] = {}
        with self._connect() as con:
            for i in range(0, len(keys), 400):
                chunk = keys[i : i + 400]
                rows = con.execute(
                    f"select key, value from results where key in ({','.join('?' * len(chunk))})", chunk
                ).fetchall()
                found.update({k: json.loads(v) for k, v in rows})
        return found

    def put(self, key: str, value: Any) -> None:
        with self._connect() as con:
            con.execute(
                "insert or replace into results values (?,?,?)",
                (key, json.dumps(value), datetime.now(timezone.utc).isoformat()),
            )

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        con = sqlite3.connect(self._path)
        try:
            yield con
            con.commit()
        finally:
            con.close()
