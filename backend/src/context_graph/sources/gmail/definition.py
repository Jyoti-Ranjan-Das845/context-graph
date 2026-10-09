from __future__ import annotations

from typing import Any

from context_graph.config import Settings
from context_graph.domain import Source
from context_graph.sources.base import CredentialField, Normalizer, SourceDefinition, SourceOptions

DEFAULT_SKIP_LABELS = (
    "CATEGORY_PROMOTIONS",
    "CATEGORY_SOCIAL",
    "CATEGORY_UPDATES",
    "CATEGORY_FORUMS",
    "SPAM",
    "TRASH",
)


class GmailOptions(SourceOptions):
    skip_labels: list[str] = list(DEFAULT_SKIP_LABELS)
    """Emails with any of these labels are left out of the graph."""


class GmailSource(SourceDefinition):
    id = Source.GMAIL
    label = "Gmail"
    airbyte_name = "source-gmail"
    streams = ("messages_details",)
    credentials = (
        CredentialField(
            env_key="GMAIL_CLIENT_ID",
            label="OAuth client ID",
            secret=False,
            help_url="https://console.cloud.google.com/auth/clients",
            help_text="A Desktop app client in your Google Cloud project (Gmail API enabled).",
        ),
        CredentialField(env_key="GMAIL_CLIENT_SECRET", label="OAuth client secret"),
        CredentialField(
            env_key="GMAIL_REFRESH_TOKEN",
            label="Google sign-in",
            managed_by="google_signin",
            help_text="Filled automatically by 'Sign in with Google'. Expires after 7 days while the app is in Testing.",
        ),
    )
    options_model = GmailOptions
    setup_steps = (
        "Create a Google Cloud project and turn on the Gmail API.",
        "Set up the sign-in screen (External, add yourself as a test user).",
        "Create a Desktop app client and paste its ID and secret here.",
        "Click 'Sign in with Google'.",
    )

    def options(self, settings: Settings) -> GmailOptions:
        return GmailOptions.model_validate(settings.source_options(self.id))

    def airbyte_config(self, settings: Settings) -> dict[str, Any]:
        return {
            "credentials": {
                "auth_type": "Client",
                "client_id": settings.secret("GMAIL_CLIENT_ID"),
                "client_secret": settings.secret("GMAIL_CLIENT_SECRET"),
                "client_refresh_token": settings.secret("GMAIL_REFRESH_TOKEN"),
            },
            "start_date": self.start_date(settings),
            "include_spam_and_trash": False,
        }

    def normalizer(self, settings: Settings) -> Normalizer:
        from context_graph.sources.gmail.normalizer import GmailNormalizer

        return GmailNormalizer(skip_labels=set(self.options(settings).skip_labels))
