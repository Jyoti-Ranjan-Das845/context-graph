"""Reference keys: the aliases a node publishes so text in other tools can point at it.

Matchers in `linking` produce the same keys from free text, so both sides must use
these functions. Keys are plain strings with a type prefix, e.g. ``issue:ENG-5``.
"""

from __future__ import annotations

import re
from urllib.parse import urlsplit

_SPACES = re.compile(r"\s+")
_EDGE_PUNCT = " \t\r\n\"'“”‘’.,;:!?()[]{}<>"


def node_id(source: str, kind: str, native_id: str) -> str:
    return f"{source}:{kind}:{native_id}"


def issue(key: str) -> str:
    return f"issue:{key.strip().upper()}"


def github_number(owner: str, repo: str, number: int | str) -> str:
    return f"gh:{owner.lower()}/{repo.lower()}#{number}"


def github_repo(owner: str, repo: str) -> str:
    return f"ghrepo:{owner.lower()}/{repo.lower()}"


def github_repo_name(repo: str) -> str:
    """Short repo name, used to resolve `#12 of my-repo` style mentions."""
    return f"ghreponame:{repo.lower()}"


def github_repo_number(repo: str, number: int | str) -> str:
    """`my-repo#12`: an issue or PR addressed by short repo name and number."""
    return f"ghreponum:{repo.lower()}#{number}"


def notion_page(page_id: str) -> str:
    return f"notion:{page_id.replace('-', '').lower()}"


def channel(name: str) -> str:
    return f"channel:{name.strip().lstrip('#').lower()}"


def slack_message(channel_id: str, ts: str) -> str:
    return f"slack:{channel_id}:{ts}"


def title(text: str) -> str:
    return f"title:{normalize_title(text)}"


def path(file_path: str) -> str:
    return f"path:{file_path.strip().strip('/').lower()}"


def symbol(name: str) -> str:
    return f"symbol:{name.strip()}"


def url(raw_url: str) -> str:
    return f"url:{normalize_url(raw_url)}"


def normalize_title(text: str) -> str:
    return _SPACES.sub(" ", text.strip(_EDGE_PUNCT).lower())


def normalize_url(raw_url: str) -> str:
    """Lower-case host, drop scheme, www, query, fragment and trailing slash."""
    parts = urlsplit(raw_url.strip().rstrip(".,;:)>]\"'"))
    host = parts.netloc.lower().removeprefix("www.")
    return f"{host}{parts.path}".rstrip("/")


_NOTION_ID = re.compile(r"([0-9a-f]{32})(?:$|[/?#])", re.IGNORECASE)
_GITHUB_NUMBER = re.compile(r"^github\.com/([^/]+)/([^/]+)/(?:pull|issues)/(\d+)", re.IGNORECASE)
_GITHUB_REPO = re.compile(r"^github\.com/([^/]+)/([^/]+)$", re.IGNORECASE)
_LINEAR_ISSUE = re.compile(r"^linear\.app/[^/]+/issue/([A-Z][A-Z0-9]{1,9}-\d+)", re.IGNORECASE)
_JIRA_ISSUE = re.compile(r"/browse/([A-Z][A-Z0-9]{1,9}-\d+)", re.IGNORECASE)
_SLACK_MESSAGE = re.compile(r"/archives/([A-Z0-9]+)/p(\d{10})(\d{6})")


def url_keys(raw_url: str) -> set[str]:
    """All keys a URL can stand for: the URL itself plus the item it identifies."""
    normalized = normalize_url(raw_url)
    keys = {f"url:{normalized}"}
    if m := _GITHUB_NUMBER.match(normalized):
        keys.add(github_number(m[1], m[2], m[3]))
    if m := _GITHUB_REPO.match(normalized):
        keys.add(github_repo(m[1], m[2]))
    if m := _LINEAR_ISSUE.match(normalized):
        keys.add(issue(m[1]))
    if ".atlassian.net" in normalized and (m := _JIRA_ISSUE.search(normalized)):
        keys.add(issue(m[1]))
    if "notion." in normalized and (m := _NOTION_ID.search(normalized + "/")):
        keys.add(notion_page(m[1]))
    if "slack.com" in normalized and (m := _SLACK_MESSAGE.search(normalized)):
        keys.add(slack_message(m[1], f"{m[2]}.{m[3]}"))
    return keys
