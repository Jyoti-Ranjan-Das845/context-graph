"""Matchers find reference keys in free text (strategy pattern).

Each matcher looks for one kind of mention and returns the keys it stands for. The
linker looks those keys up in the `ReferenceIndex`. Add a matcher to support a new
kind of mention; nothing else changes.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Protocol

from context_graph.domain import keys


@dataclass(frozen=True)
class MatchContext:
    """What a matcher may need to know about the text's own item."""

    source: str
    repo: str | None = None
    """`owner/repo` when the text belongs to a GitHub item."""
    only_repo: str | None = None
    """`owner/repo` when the graph contains exactly one repository."""


@dataclass(frozen=True)
class Hit:
    keys: frozenset[str]
    start: int
    end: int
    matcher: str
    confidence: float = 1.0


class Matcher(Protocol):
    name: str

    def find(self, text: str, context: MatchContext) -> Iterator[Hit]: ...


class IssueKeyMatcher:
    name = "issue_key"
    _pattern = re.compile(r"(?<![A-Za-z0-9/-])([A-Z][A-Z0-9]{1,9}-\d{1,6})(?![A-Za-z0-9-])")

    def find(self, text: str, context: MatchContext) -> Iterator[Hit]:
        for m in self._pattern.finditer(text):
            yield Hit(frozenset({keys.issue(m[1])}), m.start(1), m.end(1), self.name)


class UrlMatcher:
    name = "url"
    _pattern = re.compile(r"https?://[^\s<>()\[\]{}\"'|]+")

    def find(self, text: str, context: MatchContext) -> Iterator[Hit]:
        for m in self._pattern.finditer(text):
            yield Hit(frozenset(keys.url_keys(m[0])), m.start(), m.end(), self.name)


class GitHubNumberMatcher:
    """`owner/repo#12`, `repo#12`, `#12 of repo`, bare `#12` inside a GitHub item,
    and `GitHub issue #12` when only one repository is connected."""

    name = "github_number"
    _qualified = re.compile(r"(?<![\w/.-])([\w.-]+)/([\w.-]+)#(\d+)\b")
    _short = re.compile(r"(?<![\w/#.-])([A-Za-z][\w.-]*)#(\d+)\b")
    _of_repo = re.compile(r"#(\d+)\s+(?:of|in|on)\s+([A-Za-z][\w.-]*)", re.IGNORECASE)
    _github_phrase = re.compile(r"\bgithub\s+(?:issue|pr|pull request)\s+#(\d+)\b", re.IGNORECASE)
    _bare = re.compile(r"(?<![\w&#/])#(\d+)\b")

    def find(self, text: str, context: MatchContext) -> Iterator[Hit]:
        for m in self._qualified.finditer(text):
            yield Hit(frozenset({keys.github_number(m[1], m[2], m[3])}), m.start(), m.end(), self.name)
        for m in self._short.finditer(text):
            yield Hit(frozenset({keys.github_repo_number(m[1], m[2])}), m.start(), m.end(), self.name)
        for m in self._of_repo.finditer(text):
            yield Hit(frozenset({keys.github_repo_number(m[2], m[1])}), m.start(), m.end(), self.name)
        if context.only_repo:
            owner, repo = context.only_repo.split("/", 1)
            for m in self._github_phrase.finditer(text):
                yield Hit(frozenset({keys.github_number(owner, repo, m[1])}), m.start(), m.end(), self.name, 0.8)
        if context.repo:
            owner, repo = context.repo.split("/", 1)
            for m in self._bare.finditer(text):
                yield Hit(frozenset({keys.github_number(owner, repo, m[1])}), m.start(), m.end(), self.name)


class ChannelMatcher:
    name = "channel"
    _pattern = re.compile(r"(?<![\w&/#])#([a-z][a-z0-9_-]{1,79})\b")

    def find(self, text: str, context: MatchContext) -> Iterator[Hit]:
        for m in self._pattern.finditer(text):
            yield Hit(frozenset({keys.channel(m[1])}), m.start(), m.end(), self.name)


class QuotedTitleMatcher:
    """Text in quotes that equals another item's title, e.g. the Notion page "Payments retry design"."""

    name = "quoted_title"
    _pattern = re.compile(r"[\"“]([^\"”\n]{6,200})[\"”]")

    def find(self, text: str, context: MatchContext) -> Iterator[Hit]:
        for m in self._pattern.finditer(text):
            if len(m[1].split()) >= 3:
                yield Hit(frozenset({keys.title(m[1])}), m.start(1), m.end(1), self.name, 0.9)


class PathMatcher:
    """Repo file paths like `payments/retry.py`. The look-behind skips paths inside URLs."""

    name = "path"
    _pattern = re.compile(r"(?<![\w/.:-])((?:[\w.-]+/)+[\w.-]+\.[A-Za-z0-9]{1,8})(?![\w/])")

    def find(self, text: str, context: MatchContext) -> Iterator[Hit]:
        for m in self._pattern.finditer(text):
            yield Hit(frozenset({keys.path(m[1])}), m.start(1), m.end(1), self.name)


class SymbolMatcher:
    """Code identifiers that look deliberate: snake_case or camelCase, 4+ characters."""

    name = "symbol"
    _pattern = re.compile(r"(?<![\w./])([A-Za-z_][A-Za-z0-9_]{3,})(?:\(\))?(?![\w/])")

    def find(self, text: str, context: MatchContext) -> Iterator[Hit]:
        for m in self._pattern.finditer(text):
            name = m[1]
            if "_" in name.strip("_") or re.search(r"[a-z][A-Z]", name):
                yield Hit(frozenset({keys.symbol(name)}), m.start(1), m.end(1), self.name, 0.9)


def default_matchers() -> list[Matcher]:
    return [
        IssueKeyMatcher(),
        UrlMatcher(),
        GitHubNumberMatcher(),
        ChannelMatcher(),
        QuotedTitleMatcher(),
        PathMatcher(),
        SymbolMatcher(),
    ]
