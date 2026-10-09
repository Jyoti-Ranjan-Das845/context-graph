"""Runs PyAirbyte connectors: connection checks and incremental reads into DuckDB."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from context_graph.config import Settings

if TYPE_CHECKING:
    from context_graph.sources.base import SourceDefinition

log = logging.getLogger(__name__)


def configure_airbyte_environment(work_dir: Path) -> None:
    """Must run before `airbyte` is imported.

    - Several official connectors ship small custom Python components; PyAirbyte
      only runs them when this flag is set.
    - Telemetry is turned off.
    - PyAirbyte's own files go to `work_dir` instead of the folder `cg` was started from.
    """
    os.environ.setdefault("AIRBYTE_ENABLE_UNSAFE_CODE", "true")
    os.environ.setdefault("DO_NOT_TRACK", "1")
    work_dir.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("AIRBYTE_PROJECT_DIR", str(work_dir))


@dataclass(frozen=True)
class CheckResult:
    ok: bool
    message: str = ""


@dataclass(frozen=True)
class ReadResult:
    ok: bool
    records_by_stream: dict[str, int] = field(default_factory=dict)
    message: str = ""


class AirbyteRunner:
    def __init__(self, raw_db: Path, work_dir: Path) -> None:
        self._raw_db = raw_db
        self._work_dir = work_dir
        configure_airbyte_environment(work_dir)

    def check(self, definition: SourceDefinition, settings: Settings) -> CheckResult:
        missing = definition.missing_credentials(settings)
        if missing:
            return CheckResult(ok=False, message=f"Missing: {', '.join(missing)}")
        try:
            self._source(definition, settings).check()
            return CheckResult(ok=True, message="Connected")
        except Exception as exc:  # connector errors come in many shapes
            return CheckResult(ok=False, message=_describe(exc))

    def read(self, definition: SourceDefinition, settings: Settings) -> ReadResult:
        """Incrementally read every stream of every read plan into this tool's DuckDB schema.

        The cache is closed afterwards, which releases DuckDB's file lock for other processes.
        """
        try:
            from airbyte.caches import DuckDBCache

            counts: dict[str, int] = {}
            with DuckDBCache(db_path=self._raw_db, schema_name=definition.id.value, cache_dir=self._work_dir) as cache:
                for plan in definition.read_plans(settings):
                    source = self._get_source(definition.airbyte_name, plan.config)
                    source.select_streams(list(plan.streams))
                    result = source.read(cache=cache)
                    counts.update({name: _count(dataset) for name, dataset in result.streams.items()})
            return ReadResult(ok=True, records_by_stream=counts)
        except Exception as exc:
            log.exception("Read failed for %s", definition.id)
            return ReadResult(ok=False, message=_describe(exc))

    def available_streams(self, definition: SourceDefinition, settings: Settings) -> list[str]:
        source = self._get_source(definition.airbyte_name, definition.airbyte_config(settings))
        return list(source.get_available_streams())

    def _source(self, definition: SourceDefinition, settings: Settings):
        source = self._get_source(definition.airbyte_name, definition.airbyte_config(settings))
        source.select_streams(list(definition.streams))
        return source

    @staticmethod
    def _get_source(airbyte_name: str, config: dict):
        import airbyte as ab

        return ab.get_source(airbyte_name, config=config, install_if_missing=True)


def _count(dataset) -> int:
    try:
        return len(dataset)
    except Exception:
        return -1


def _describe(exc: Exception) -> str:
    """A short, secret-free description of a connector failure."""
    original = getattr(exc, "original_exception", None)
    text = str(original or exc).splitlines()[0] if str(original or exc) else type(exc).__name__
    return text[:300]
