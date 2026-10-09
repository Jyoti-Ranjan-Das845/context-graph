import base64

from context_graph.domain import keys
from context_graph.sources import text


class TestUrlKeys:
    def test_github_pull_and_issue_share_number_space(self):
        assert keys.github_number("Acme", "Pay", 2) in keys.url_keys("https://github.com/Acme/Pay/pull/2")
        assert keys.github_number("acme", "pay", 1) in keys.url_keys("https://github.com/acme/pay/issues/1/")

    def test_linear_and_jira_urls_yield_issue_keys(self):
        assert keys.issue("ENG-5") in keys.url_keys("https://linear.app/ws/issue/ENG-5/some-title")
        assert keys.issue("DEMO-1") in keys.url_keys("https://acme.atlassian.net/browse/DEMO-1")

    def test_notion_url_yields_page_key(self):
        url = "https://app.notion.com/p/Payments-retry-design-0123456789abcdef0123456789abcdef"
        assert keys.notion_page("01234567-89ab-cdef-0123-456789abcdef") in keys.url_keys(url)

    def test_slack_permalink_yields_message_key(self):
        url = "https://acme.slack.com/archives/C0123456789/p1700000000123456"
        assert keys.slack_message("C0123456789", "1700000000.123456") in keys.url_keys(url)

    def test_normalize_url_drops_noise(self):
        assert keys.normalize_url("HTTPS://www.Example.com/a/b/?x=1#frag") == "example.com/a/b"


class TestText:
    def test_adf_to_text_flattens_blocks_and_links(self):
        adf = {
            "type": "doc",
            "content": [
                {"type": "paragraph", "content": [{"type": "text", "text": "See "}, {"type": "inlineCard", "attrs": {"url": "https://x.io/1"}}]},
                {"type": "paragraph", "content": [{"type": "text", "text": "done", "marks": [{"type": "link", "attrs": {"href": "https://y.io"}}]}]},
            ],
        }
        assert text.adf_to_text(adf).splitlines() == ["See https://x.io/1", "done (https://y.io)"]

    def test_slack_to_text_resolves_users_channels_and_links(self):
        raw = "Hi <@U1>, see <https://a.io|the doc> in <#C9|payments>"
        assert text.slack_to_text(raw, {"U1": "Priya Shah"}, {}) == "Hi @Priya Shah, see the doc (https://a.io) in #payments"

    def test_gmail_body_prefers_plain_text_and_strips_quotes(self):
        body = "New reply\n\nOn Fri, 9 Oct 2026 at 00:37, Maya <m@x.io> wrote:\n> old text"
        data = base64.urlsafe_b64encode(body.encode()).decode().rstrip("=")
        payload = {"mimeType": "multipart/alternative", "parts": [{"mimeType": "text/plain", "body": {"data": data}}]}
        assert text.gmail_body(payload) == "New reply"

    def test_clean_subject(self):
        assert text.clean_subject("Re: Fwd: RE: Customers charged twice") == "Customers charged twice"

    def test_parse_datetime_handles_epoch_ms_seconds_and_iso(self):
        assert text.parse_datetime("1700000000.123456").year == 2023  # epoch seconds, as Slack sends them
        assert text.parse_datetime(1791487357000).year == 2026
        assert text.parse_datetime("2026-10-08T19:05:53Z").tzinfo is not None
        assert text.parse_datetime("") is None
