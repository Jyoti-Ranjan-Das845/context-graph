"""The list of supported tools. Register a new `SourceDefinition` here to add a tool."""

from __future__ import annotations

from collections.abc import Iterable

from context_graph.domain import Source
from context_graph.sources.base import SourceDefinition


class UnknownSourceError(KeyError):
    pass


class SourceRegistry:
    def __init__(self, definitions: Iterable[SourceDefinition]) -> None:
        self._by_id: dict[Source, SourceDefinition] = {}
        for definition in definitions:
            if definition.id in self._by_id:
                raise ValueError(f"Duplicate source definition: {definition.id}")
            self._by_id[definition.id] = definition

    def get(self, source_id: str | Source) -> SourceDefinition:
        try:
            return self._by_id[Source(source_id)]
        except (KeyError, ValueError) as exc:
            raise UnknownSourceError(str(source_id)) from exc

    def all(self) -> list[SourceDefinition]:
        return list(self._by_id.values())


def default_registry() -> SourceRegistry:
    from context_graph.sources.github.definition import GitHubSource
    from context_graph.sources.gmail.definition import GmailSource
    from context_graph.sources.jira.definition import JiraSource
    from context_graph.sources.linear.definition import LinearSource
    from context_graph.sources.notion.definition import NotionSource
    from context_graph.sources.slack.definition import SlackSource

    return SourceRegistry(
        [GitHubSource(), LinearSource(), JiraSource(), NotionSource(), SlackSource(), GmailSource()]
    )
