"""One-time Google sign-in for Gmail: runs the OAuth consent in the browser and stores the
refresh token in `.env`. The token is never printed."""

from __future__ import annotations

from context_graph.config import SettingsRepository

GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


class GoogleSignInError(RuntimeError):
    pass


def sign_in_gmail(settings: SettingsRepository, open_browser: bool = True) -> None:
    from google_auth_oauthlib.flow import InstalledAppFlow

    current = settings.load()
    client_id, client_secret = current.secret("GMAIL_CLIENT_ID"), current.secret("GMAIL_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise GoogleSignInError("Set GMAIL_CLIENT_ID and GMAIL_CLIENT_SECRET first.")
    flow = InstalledAppFlow.from_client_config(
        {
            "installed": {
                "client_id": client_id,
                "client_secret": client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": ["http://localhost"],
            }
        },
        scopes=GMAIL_SCOPES,
    )
    credentials = flow.run_local_server(port=0, prompt="consent", access_type="offline", open_browser=open_browser)
    if not credentials.refresh_token:
        raise GoogleSignInError("Google did not return a refresh token. Try again.")
    settings.set_secret("GMAIL_REFRESH_TOKEN", credentials.refresh_token)
