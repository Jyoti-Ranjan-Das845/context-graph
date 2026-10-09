from __future__ import annotations

from typing import Any

from context_graph.config import Settings
from context_graph.domain import Source
from context_graph.sources.base import CredentialField, Normalizer, ReadPlan, SourceDefinition

REFERENCE_START_DATE = "2000-01-01T00:00:00.000Z"
"""Users and projects are reference data: they must be read regardless of the sync start date."""
REFERENCE_STREAMS = ("users", "projects")


class LinearSource(SourceDefinition):
    id = Source.LINEAR
    label = "Linear"
    airbyte_name = "source-linear"
    streams = ("issues", "comments", "users", "projects")
    credentials = (
        CredentialField(
            env_key="LINEAR_API_KEY",
            label="Personal API key",
            help_url="https://linear.app/settings/account/security",
            help_text="Settings → Security & access → Personal API keys → New key.",
            placeholder="lin_api_…",
        ),
    )
    setup_steps = ("Open Linear's security settings.", "Create a personal API key and paste it here.")

    def airbyte_config(self, settings: Settings) -> dict[str, Any]:
        return {
            "credentials": {"auth_type": "API Key", "api_key": settings.secret("LINEAR_API_KEY")},
            "start_date": _linear_date(self.start_date(settings)),
        }

    def read_plans(self, settings: Settings) -> list[ReadPlan]:
        activity = tuple(s for s in self.streams if s not in REFERENCE_STREAMS)
        reference_config = {**self.airbyte_config(settings), "start_date": REFERENCE_START_DATE}
        return [
            ReadPlan(activity, self.airbyte_config(settings)),
            ReadPlan(REFERENCE_STREAMS, reference_config),
        ]

    def normalizer(self, settings: Settings) -> Normalizer:
        from context_graph.sources.linear.normalizer import LinearNormalizer

        return LinearNormalizer()


def _linear_date(iso: str) -> str:
    """Linear's connector expects milliseconds: 2020-01-01T00:00:00.000Z."""
    return iso if "." in iso else iso.replace("Z", ".000Z")
