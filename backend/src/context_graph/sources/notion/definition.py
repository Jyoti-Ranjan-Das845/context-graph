from __future__ import annotations

from typing import Any

from context_graph.config import Settings
from context_graph.domain import Source
from context_graph.sources.base import CredentialField, Normalizer, SourceDefinition


class NotionSource(SourceDefinition):
    id = Source.NOTION
    label = "Notion"
    airbyte_name = "source-notion"
    streams = ("pages", "blocks", "users")
    credentials = (
        CredentialField(
            env_key="NOTION_TOKEN",
            label="Integration token",
            help_url="https://www.notion.so/profile/integrations",
            help_text="Create an internal connection, then share the pages you want with it (••• → Connections).",
            placeholder="ntn_…",
        ),
    )
    setup_steps = (
        "Create an internal connection in Notion's developer tools.",
        "Paste its token here.",
        "In Notion, open each page to include: ••• → Connections → add the connection.",
    )

    def airbyte_config(self, settings: Settings) -> dict[str, Any]:
        return {
            "credentials": {"auth_type": "token", "token": settings.secret("NOTION_TOKEN")},
            "start_date": _notion_date(self.start_date(settings)),
        }

    def normalizer(self, settings: Settings) -> Normalizer:
        from context_graph.sources.notion.normalizer import NotionNormalizer

        return NotionNormalizer()


def _notion_date(iso: str) -> str:
    """Notion's connector expects milliseconds: 2020-11-16T00:00:00.000Z."""
    return iso if "." in iso else iso.replace("Z", ".000Z")
