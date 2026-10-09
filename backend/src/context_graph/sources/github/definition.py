from __future__ import annotations

from typing import Any

from pydantic import field_validator

from context_graph.config import Settings
from context_graph.domain import Source
from context_graph.sources.base import CredentialField, Normalizer, SourceDefinition, SourceOptions


class GitHubOptions(SourceOptions):
    repos: list[str] = []
    """owner/repo, or owner/* for every repo of an owner."""
    include_code: bool = True
    """Also read the code of these repos (files and functions) and link it to issues and pull requests."""

    @field_validator("repos")
    @classmethod
    def _owner_repo(cls, repos: list[str]) -> list[str]:
        for repo in repos:
            if repo.count("/") != 1:
                raise ValueError(f"Repos must look like owner/repo, got {repo!r}")
        return repos


class GitHubSource(SourceDefinition):
    id = Source.GITHUB
    label = "GitHub"
    airbyte_name = "source-github"
    streams = ("repositories", "issues", "pull_requests", "comments", "reviews", "commits")
    credentials = (
        CredentialField(
            env_key="GITHUB_TOKEN",
            label="Personal access token",
            help_url=(
                "https://github.com/settings/personal-access-tokens/new?name=Context%20Graph"
                "&expires_in=90&contents=read&issues=read&pull_requests=read&metadata=read"
            ),
            help_text="Read-only access to the repos you want in the graph.",
            placeholder="github_pat_…",
        ),
    )
    options_model = GitHubOptions
    setup_steps = (
        "Open the token page (permissions are pre-filled as read-only).",
        "Under Repository access, pick the repos to include.",
        "Generate the token and paste it here.",
    )

    def options(self, settings: Settings) -> GitHubOptions:
        return GitHubOptions.model_validate(settings.source_options(self.id))

    def is_configured(self, settings: Settings) -> bool:
        return super().is_configured(settings) and bool(self.options(settings).repos)

    def airbyte_config(self, settings: Settings) -> dict[str, Any]:
        return {
            "credentials": {
                "option_title": "PAT Credentials",
                "personal_access_token": settings.secret("GITHUB_TOKEN"),
            },
            "repositories": self.options(settings).repos,
            "start_date": self.start_date(settings),
        }

    def normalizer(self, settings: Settings) -> Normalizer:
        from context_graph.sources.github.normalizer import GitHubNormalizer

        return GitHubNormalizer()
