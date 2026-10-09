"""Helpers that turn each tool's rich-text formats into plain text, plus small parsing utilities."""

from __future__ import annotations

import base64
import html
import re
from datetime import datetime, timezone
from email.utils import getaddresses, parsedate_to_datetime
from typing import Any

# ---------------------------------------------------------------- dates


def parse_datetime(value: Any) -> datetime | None:
    """Parse ISO strings, epoch seconds/milliseconds and RFC 2822 dates. Always returns UTC-aware."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, (int, float)) or (isinstance(value, str) and re.fullmatch(r"\d+(\.\d+)?", value)):
        number = float(value)
        dt = datetime.fromtimestamp(number / 1000 if number > 1e11 else number, tz=timezone.utc)
    else:
        text = str(value).strip()
        try:
            dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            try:
                dt = parsedate_to_datetime(text)
            except (TypeError, ValueError):
                return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def first_line(text: str, limit: int = 120) -> str:
    line = next((ln.strip() for ln in text.splitlines() if ln.strip()), "")
    return line if len(line) <= limit else line[: limit - 1].rstrip() + "…"


# ---------------------------------------------------------------- Atlassian Document Format (Jira)

_ADF_BLOCKS = {"paragraph", "heading", "listItem", "blockquote", "codeBlock", "rule", "tableRow", "panel"}


def adf_to_text(node: Any) -> str:
    """Flatten Atlassian Document Format into plain text, one block per line."""
    if node is None:
        return ""
    if isinstance(node, str):
        return node
    if isinstance(node, list):
        return "".join(adf_to_text(child) for child in node)
    kind = node.get("type")
    if kind == "text":
        text = node.get("text", "")
        for mark in node.get("marks", []) or []:
            if mark.get("type") == "link" and (href := (mark.get("attrs") or {}).get("href")) and href not in text:
                text = f"{text} ({href})"
        return text
    if kind == "hardBreak":
        return "\n"
    if kind in {"mention", "emoji", "status", "date"}:
        attrs = node.get("attrs") or {}
        return str(attrs.get("text") or attrs.get("shortName") or "")
    if kind in {"inlineCard", "blockCard", "embedCard"}:
        return str((node.get("attrs") or {}).get("url", ""))
    inner = adf_to_text(node.get("content") or [])
    return f"{inner}\n" if kind in _ADF_BLOCKS else inner


# ---------------------------------------------------------------- Notion


def notion_rich_text(rich_text: Any) -> str:
    if not isinstance(rich_text, list):
        return ""
    parts = []
    for span in rich_text:
        text = span.get("plain_text") or (span.get("text") or {}).get("content", "")
        href = span.get("href") or ((span.get("text") or {}).get("link") or {}).get("url")
        parts.append(f"{text} ({href})" if href and href not in text else text)
    return "".join(parts)


def notion_block_text(block: dict[str, Any]) -> str:
    kind = block.get("type") or ""
    payload = block.get(kind) or {}
    if not isinstance(payload, dict):
        return ""
    text = notion_rich_text(payload.get("rich_text"))
    if kind.startswith("heading_"):
        return f"{'#' * int(kind[-1])} {text}"
    if kind in {"bulleted_list_item", "to_do"}:
        return f"- {text}"
    if kind == "numbered_list_item":
        return f"1. {text}"
    if kind == "code":
        return f"```\n{text}\n```"
    if kind in {"bookmark", "embed", "link_preview"}:
        return str(payload.get("url", ""))
    if kind == "child_page":
        return str(payload.get("title", ""))
    return text


def notion_title(properties: Any) -> str:
    """Page title from Notion properties (Airbyte stores them as a list of {name, value})."""
    entries = properties if isinstance(properties, list) else [{"value": v} for v in (properties or {}).values()]
    for entry in entries:
        value = entry.get("value") or {}
        if value.get("type") == "title":
            return notion_rich_text(value.get("title"))
    return ""


# ---------------------------------------------------------------- Slack

_SLACK_LINK = re.compile(r"<(https?://[^|>]+)(?:\|([^>]+))?>")
_SLACK_USER = re.compile(r"<@([UW][A-Z0-9]+)(?:\|[^>]+)?>")
_SLACK_CHANNEL = re.compile(r"<#([CG][A-Z0-9]+)(?:\|([^>]*))?>")


def slack_to_text(text: str, user_names: dict[str, str], channel_names: dict[str, str]) -> str:
    def link(m: re.Match[str]) -> str:
        url, label = m[1], m[2]
        return f"{label} ({url})" if label and label != url else url

    text = _SLACK_LINK.sub(link, text or "")
    text = _SLACK_USER.sub(lambda m: f"@{user_names.get(m[1], m[1])}", text)
    text = _SLACK_CHANNEL.sub(lambda m: f"#{m[2] or channel_names.get(m[1], m[1])}", text)
    return html.unescape(text)


# ---------------------------------------------------------------- Email

_TAG = re.compile(r"<[^>]+>")
_QUOTE_HEADER = re.compile(r"^On .{5,200}wrote:\s*$", re.MULTILINE)


def gmail_headers(payload: dict[str, Any]) -> dict[str, str]:
    return {h.get("name", "").lower(): h.get("value", "") for h in payload.get("headers", []) or []}


def gmail_body(payload: dict[str, Any]) -> str:
    """Plain-text body of a Gmail message, without quoted replies."""
    plain, rich = _collect_parts(payload)
    text = plain or _html_to_text(rich)
    return strip_quoted_reply(text)


def _collect_parts(part: dict[str, Any]) -> tuple[str, str]:
    mime = part.get("mimeType", "")
    data = (part.get("body") or {}).get("data")
    if data and mime == "text/plain":
        return _b64(data), ""
    if data and mime == "text/html":
        return "", _b64(data)
    plain, rich = "", ""
    for child in part.get("parts") or []:
        p, r = _collect_parts(child)
        plain, rich = plain or p, rich or r
    return plain, rich


def _b64(data: str) -> str:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4)).decode("utf-8", errors="replace")


def _html_to_text(markup: str) -> str:
    markup = re.sub(r"(?is)<(script|style).*?</\1>", "", markup)
    markup = re.sub(r"(?i)<br\s*/?>|</p>|</div>", "\n", markup)
    return html.unescape(_TAG.sub("", markup))


def strip_quoted_reply(text: str) -> str:
    if m := _QUOTE_HEADER.search(text):
        text = text[: m.start()]
    lines = [ln for ln in text.splitlines() if not ln.lstrip().startswith(">")]
    return "\n".join(lines).strip()


def parse_addresses(value: str) -> list[tuple[str, str]]:
    """[(name, email)] from an address header, emails lower-cased."""
    return [(name.strip(), email.strip().lower()) for name, email in getaddresses([value or ""]) if email]


def clean_subject(subject: str) -> str:
    return re.sub(r"^(\s*(re|fw|fwd)\s*:\s*)+", "", subject or "", flags=re.IGNORECASE).strip()
