"""Read access to the raw records PyAirbyte wrote to DuckDB (one schema per tool).

DuckDB locks its file for as long as any connection is open, and only one process can hold
the lock. Every read therefore opens the file through PyAirbyte's own cache (the same
configuration the pulls use) and closes it right after, so the web app, the CLI and the
scheduled sync can take turns.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Connection

from context_graph.ingest.airbyte_runner import configure_airbyte_environment


class RawStoreError(RuntimeError):
    """The local raw data could not be read (e.g. another process holds the DuckDB lock)."""


class RawStore:
    def __init__(self, db_path: Path, work_dir: Path) -> None:
        self._db_path = db_path
        self._work_dir = work_dir

    def read(self, schema: str, streams: tuple[str, ...]) -> dict[str, list[dict[str, Any]]]:
        """All records of the given streams of one tool. Missing streams come back empty."""
        if not self._db_path.exists():
            return {stream: [] for stream in streams}
        with self._connect() as con:
            present = _tables(con, schema)
            return {stream: _records(con, schema, stream) if stream in present else [] for stream in streams}

    @contextmanager
    def _connect(self) -> Iterator[Connection]:
        configure_airbyte_environment(self._work_dir)
        from airbyte.caches import DuckDBCache

        try:
            cache = DuckDBCache(db_path=self._db_path, schema_name="main", cache_dir=self._work_dir)
            with cache, cache.get_sql_engine().connect() as con:
                yield con
        except RawStoreError:
            raise
        except Exception as exc:  # DuckDB raises IOException for locks, SQLAlchemy wraps it
            raise RawStoreError(f"Could not read {self._db_path.name}: {str(exc).splitlines()[0][:200]}") from exc


def _tables(con: Connection, schema: str) -> set[str]:
    rows = con.execute(
        text(
            "select table_name from information_schema.tables "
            "where table_schema = :schema and table_name not like '\\_airbyte%' escape '\\'"
        ),
        {"schema": schema},
    ).fetchall()
    return {r[0] for r in rows}


def _records(con: Connection, schema: str, stream: str) -> list[dict[str, Any]]:
    json_columns = {
        name
        for name, data_type in con.execute(
            text(
                "select column_name, data_type from information_schema.columns "
                "where table_schema = :schema and table_name = :table"
            ),
            {"schema": schema, "table": stream},
        ).fetchall()
        if data_type == "JSON"
    }
    result = con.execute(text(f'select * from "{schema}"."{stream}"'))
    names = list(result.keys())
    return [
        {name: _decode(value, name in json_columns) for name, value in zip(names, row) if not name.startswith("_airbyte")}
        for row in result.fetchall()
    ]


def _decode(value: Any, is_json: bool) -> Any:
    if is_json and isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value
