from __future__ import annotations

from typing import Any

from pydantic import Field

from context_graph.config import Settings
from context_graph.domain import Source
from context_graph.sources.base import CredentialField, Normalizer, SourceDefinition, SourceOptions

BOT_SCOPES = (
    "channels:history",
    "channels:join",
    "channels:read",
    "files:read",
    "groups:read",
    "links:read",
    "reactions:read",
    "remote_files:read",
    "team:read",
    "usergroups:read",
    "users:read",
    "users:read.email",
    "users.profile:read",
)


class SlackOptions(SourceOptions):
    join_channels: bool = True
    """Let the bot join every public channel so their messages can be read."""
    channels: list[str] = []
    """Channel names to include. Empty means every channel the bot can read."""
    include_private: bool = False
    """Also read private channels the bot has been invited to."""
    thread_lookback_days: int = Field(default=7, ge=0, le=90)
    """How many days back each sync re-checks threads for new replies."""


class SlackSource(SourceDefinition):
    id = Source.SLACK
    label = "Slack"
    airbyte_name = "source-slack"
    streams = ("channels", "channel_messages", "threads", "users")
    credentials = (
        CredentialField(
            env_key="SLACK_BOT_TOKEN",
            label="Bot token",
            help_url="https://api.slack.com/apps?new_app=1",
            help_text="Create the app from our manifest, install it, then copy the Bot User OAuth Token.",
            placeholder="xoxb-…",
        ),
    )
    options_model = SlackOptions
    setup_steps = (
        "Create the Slack app from the pre-filled manifest and pick your workspace.",
        "Install it to the workspace.",
        "Copy the Bot User OAuth Token (xoxb-…) from OAuth & Permissions.",
    )

    def options(self, settings: Settings) -> SlackOptions:
        return SlackOptions.model_validate(settings.source_options(self.id))

    def airbyte_config(self, settings: Settings) -> dict[str, Any]:
        options = self.options(settings)
        return {
            "credentials": {"option_title": "API Token Credentials", "api_token": settings.secret("SLACK_BOT_TOKEN")},
            "start_date": self.start_date(settings),
            "lookback_window": options.thread_lookback_days,
            "join_channels": options.join_channels,
            "channel_filter": options.channels,
            "include_private_channels": options.include_private,
        }

    def normalizer(self, settings: Settings) -> Normalizer:
        from context_graph.sources.slack.normalizer import SlackNormalizer

        return SlackNormalizer()


def manifest(app_name: str = "Context Graph") -> dict[str, Any]:
    """The Slack app manifest used by the setup screen's "Create app" link."""
    return {
        "display_information": {"name": app_name},
        "features": {"bot_user": {"display_name": app_name, "always_online": False}},
        "oauth_config": {"scopes": {"bot": list(BOT_SCOPES)}},
        "settings": {"org_deploy_enabled": False, "socket_mode_enabled": False, "token_rotation_enabled": False},
    }
