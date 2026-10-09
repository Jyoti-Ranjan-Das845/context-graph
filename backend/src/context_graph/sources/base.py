"""Contracts every tool integration implements.

A tool is described by a `SourceDefinition` (how to connect and what to pull) and a
`Normalizer` (how its raw records become domain `Item`s and `PersonRecord`s).
Adding a tool means adding one module; nothing else changes (open/closed).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any, ClassVar, Protocol

from pydantic import BaseModel, ConfigDict

from context_graph.config import Settings, StartDate
from context_graph.domain import Item, PersonRecord, Source

RawRecords = Mapping[str, Iterable[dict[str, Any]]]
"""Raw records grouped by stream name."""


@dataclass(frozen=True)
class CredentialField:
    env_key: str
    label: str
    secret: bool = True
    help_url: str | None = None
    help_text: str = ""
    placeholder: str = ""
    managed_by: str | None = None
    """Set when the value is produced by an action (e.g. Google sign-in) instead of typed."""


@dataclass
class NormalizedBatch:
    items: list[Item] = field(default_factory=list)
    people: list[PersonRecord] = field(default_factory=list)

    def extend(self, other: NormalizedBatch) -> None:
        self.items.extend(other.items)
        self.people.extend(other.people)


class Normalizer(Protocol):
    def normalize(self, records: RawRecords) -> NormalizedBatch: ...


@dataclass(frozen=True)
class ReadPlan:
    """One connector read: a set of streams with the config to read them with."""

    streams: tuple[str, ...]
    config: dict[str, Any]


class SourceOptions(BaseModel):
    """Options shared by every tool. Tools subclass this to add their own.

    Field docstrings become descriptions in the JSON schema, which the setup UI shows as help text.
    """

    model_config = ConfigDict(use_attribute_docstrings=True)

    enabled: bool = True
    """Include this tool when syncing."""
    start_date: StartDate | None = None
    """Pull from this date instead of the global "Pull data since" (e.g. 2026-10-01)."""


class SourceDefinition(ABC):
    id: ClassVar[Source]
    label: ClassVar[str]
    airbyte_name: ClassVar[str]
    streams: ClassVar[tuple[str, ...]]
    credentials: ClassVar[tuple[CredentialField, ...]]
    options_model: ClassVar[type[SourceOptions]] = SourceOptions
    setup_steps: ClassVar[tuple[str, ...]] = ()

    def options(self, settings: Settings) -> SourceOptions:
        return self.options_model.model_validate(settings.source_options(self.id))

    def start_date(self, settings: Settings) -> str:
        return self.options(settings).start_date or settings.options.sync.start_date

    def missing_credentials(self, settings: Settings) -> list[str]:
        return [f.env_key for f in self.credentials if not settings.secret(f.env_key)]

    def is_configured(self, settings: Settings) -> bool:
        return not self.missing_credentials(settings)

    def is_enabled(self, settings: Settings) -> bool:
        return self.options(settings).enabled

    @abstractmethod
    def airbyte_config(self, settings: Settings) -> dict[str, Any]:
        """The connector config, built from `.env` secrets and `settings.json` options."""

    def read_plans(self, settings: Settings) -> list[ReadPlan]:
        """How to pull this tool. One read by default; override to split streams that
        need a different config (e.g. reference data that must ignore the start date)."""
        return [ReadPlan(self.streams, self.airbyte_config(settings))]

    @abstractmethod
    def normalizer(self, settings: Settings) -> Normalizer:
        """A normalizer for this tool's raw records."""
