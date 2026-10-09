from __future__ import annotations

from typing import Any

from context_graph.config import Settings
from context_graph.domain import Source
from context_graph.sources.base import CredentialField, Normalizer, SourceDefinition, SourceOptions


class JiraOptions(SourceOptions):
    projects: list[str] = []
    """Project keys to include. Empty means every project the account can see."""


class JiraSource(SourceDefinition):
    id = Source.JIRA
    label = "Jira"
    airbyte_name = "source-jira"
    streams = ("projects", "issues", "issue_comments", "users")
    credentials = (
        CredentialField(
            env_key="JIRA_DOMAIN",
            label="Site",
            secret=False,
            help_text="Your Jira address without https://",
            placeholder="your-site.atlassian.net",
        ),
        CredentialField(
            env_key="JIRA_EMAIL",
            label="Account email",
            secret=False,
            placeholder="you@example.com",
        ),
        CredentialField(
            env_key="JIRA_API_TOKEN",
            label="API token",
            help_url="https://id.atlassian.com/manage-profile/security/api-tokens",
            help_text="Create an API token for your Atlassian account.",
        ),
    )
    options_model = JiraOptions
    setup_steps = ("Open Atlassian's API token page.", "Create a token and paste it here with your site and email.")

    def options(self, settings: Settings) -> JiraOptions:
        return JiraOptions.model_validate(settings.source_options(self.id))

    def airbyte_config(self, settings: Settings) -> dict[str, Any]:
        domain = (settings.secret("JIRA_DOMAIN") or "").removeprefix("https://").strip("/")
        return {
            "credentials": {
                "auth_type": "API Token",
                "api_token": settings.secret("JIRA_API_TOKEN"),
                "email": settings.secret("JIRA_EMAIL"),
            },
            "domain": domain,
            "projects": self.options(settings).projects,
            "start_date": self.start_date(settings),
        }

    def normalizer(self, settings: Settings) -> Normalizer:
        from context_graph.sources.jira.normalizer import JiraNormalizer

        domain = (settings.secret("JIRA_DOMAIN") or "").removeprefix("https://").strip("/")
        return JiraNormalizer(domain=domain)
