"""Typed settings.

Two files, two jobs:
- `.env` holds credentials and connection identity (never written to logs).
- `settings.json` holds what to sync and how (safe to show and edit in the UI).
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Annotated, Any, Literal, Mapping

from pydantic import AfterValidator, BaseModel, Field

from context_graph.config.env_file import EnvFile

HOME_ENV_VAR = "CONTEXT_GRAPH_HOME"
DEFAULT_HOME_NAME = ".context-graph"
FIRST_PULL_DAYS = 30
"""How far back the first pull goes when nothing is configured yet. Changeable in Setup."""


def normalize_start_date(value: str) -> str:
    """Accept an ISO date or time ("2026-10-01", "2026-10-01T09:30:00+02:00") and return UTC `YYYY-MM-DDTHH:MM:SSZ`,
    the format every connector accepts."""
    parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


StartDate = Annotated[str, AfterValidator(normalize_start_date)]


def default_start_date() -> str:
    """Midnight UTC, `FIRST_PULL_DAYS` days ago. Saved on first use so it never moves afterwards."""
    day = (datetime.now(timezone.utc) - timedelta(days=FIRST_PULL_DAYS)).date()
    return f"{day.isoformat()}T00:00:00Z"


class SyncOptions(BaseModel):
    interval_minutes: int = Field(default=30, ge=5, le=24 * 60)
    start_date: StartDate = Field(default_factory=default_start_date)


class EnrichmentOptions(BaseModel):
    enabled: bool = True
    provider: Literal["claude-cli", "none"] = "claude-cli"
    model: str | None = None
    batch_size: int = Field(default=8, ge=1, le=25)
    max_items_per_sync: int = Field(default=150, ge=0)
    timeout_seconds: int = Field(default=240, ge=30)


class IdentityOptions(BaseModel):
    merge_by_name: bool = True


class AppOptions(BaseModel):
    sync: SyncOptions = Field(default_factory=SyncOptions)
    enrichment: EnrichmentOptions = Field(default_factory=EnrichmentOptions)
    identity: IdentityOptions = Field(default_factory=IdentityOptions)
    sources: dict[str, dict[str, Any]] = Field(default_factory=dict)


@dataclass(frozen=True)
class AppPaths:
    root: Path

    @property
    def env_file(self) -> Path:
        return self.root / ".env"

    @property
    def settings_file(self) -> Path:
        return self.root / "settings.json"

    @property
    def data_dir(self) -> Path:
        return self.root / "data"

    @property
    def raw_db(self) -> Path:
        return self.data_dir / "raw" / "airbyte.duckdb"

    @property
    def graph_db(self) -> Path:
        return self.data_dir / "graph" / "graph.sqlite"

    @property
    def llm_cache(self) -> Path:
        return self.data_dir / "cache" / "llm.sqlite"

    @property
    def code_dir(self) -> Path:
        return self.data_dir / "code"

    @property
    def state_dir(self) -> Path:
        return self.data_dir / "state"

    @property
    def logs_dir(self) -> Path:
        return self.data_dir / "logs"

    @property
    def airbyte_dir(self) -> Path:
        """PyAirbyte's own working files (connector installs, temp files)."""
        return self.data_dir / "raw" / "airbyte"

    def ensure(self) -> None:
        for directory in (
            self.raw_db.parent,
            self.airbyte_dir,
            self.graph_db.parent,
            self.llm_cache.parent,
            self.code_dir,
            self.state_dir,
            self.logs_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)


@dataclass(frozen=True)
class Settings:
    paths: AppPaths
    options: AppOptions
    env: Mapping[str, str]

    def secret(self, key: str) -> str | None:
        value = self.env.get(key, "").strip()
        return value or None

    def source_options(self, source_id: str) -> dict[str, Any]:
        return dict(self.options.sources.get(source_id, {}))


class SettingsRepository:
    """Loads and saves settings. The only class that touches `.env` and `settings.json`."""

    def __init__(self, paths: AppPaths) -> None:
        self._paths = paths
        self._env = EnvFile(paths.env_file)

    @property
    def paths(self) -> AppPaths:
        return self._paths

    def load(self) -> Settings:
        return Settings(paths=self._paths, options=self._load_options(), env=self._env.read())

    def save_options(self, options: AppOptions) -> None:
        self._paths.settings_file.write_text(json.dumps(options.model_dump(), indent=2) + "\n")

    def update_source_options(self, source_id: str, values: dict[str, Any]) -> AppOptions:
        options = self._load_options()
        options.sources[source_id] = values
        self.save_options(options)
        return options

    def set_secret(self, key: str, value: str) -> None:
        self._env.set(key, value)

    def _load_options(self) -> AppOptions:
        file = self._paths.settings_file
        raw = json.loads(file.read_text()) if file.exists() else {}
        options = AppOptions.model_validate(raw)
        if "start_date" not in raw.get("sync", {}):
            self.save_options(options)  # fix the default start date on first use
        return options


def discover_root() -> Path:
    """The data folder: $CONTEXT_GRAPH_HOME, else ~/.context-graph. Code and data are kept apart."""
    if home := os.environ.get(HOME_ENV_VAR):
        return Path(home).expanduser().resolve()
    return Path.home() / DEFAULT_HOME_NAME
