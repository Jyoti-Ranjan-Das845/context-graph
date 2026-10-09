"""Core domain types. Pure data: no I/O, no third-party imports."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any


class Source(StrEnum):
    GITHUB = "github"
    LINEAR = "linear"
    JIRA = "jira"
    NOTION = "notion"
    SLACK = "slack"
    GMAIL = "gmail"
    CODE = "code"
    DERIVED = "derived"


class NodeKind(StrEnum):
    PERSON = "person"
    REPOSITORY = "repository"
    ISSUE = "issue"
    PULL_REQUEST = "pull_request"
    COMMIT = "commit"
    COMMENT = "comment"
    PROJECT = "project"
    CHANNEL = "channel"
    MESSAGE = "message"
    PAGE = "page"
    EMAIL_THREAD = "email_thread"
    EMAIL = "email"
    FILE = "file"
    SYMBOL = "symbol"
    TOPIC = "topic"
    DECISION = "decision"


class EdgeKind(StrEnum):
    AUTHORED = "authored"
    ASSIGNED_TO = "assigned_to"
    PART_OF = "part_of"
    REPLY_TO = "reply_to"
    REFERENCES = "references"
    FIXES = "fixes"
    CHANGES = "changes"
    CONTAINS = "contains"
    CALLS = "calls"
    IMPORTS = "imports"
    MENTIONS = "mentions"
    DECIDES = "decides"
    ABOUT = "about"


@dataclass(frozen=True, slots=True)
class PersonRef:
    """A person as one tool refers to them (an author, an assignee, a sender)."""

    source: Source
    native_id: str | None = None
    email: str | None = None
    name: str | None = None
    handle: str | None = None

    def identity_keys(self) -> set[str]:
        keys: set[str] = set()
        if self.native_id:
            keys.add(f"{self.source}:id:{self.native_id}")
        if self.handle:
            keys.add(f"{self.source}:handle:{self.handle.lower()}")
        if self.email:
            keys.add(f"email:{self.email.strip().lower()}")
        return keys


@dataclass(slots=True)
class PersonRecord:
    """Everything one tool knows about one person (usually from a users stream)."""

    source: Source
    native_id: str
    names: set[str] = field(default_factory=set)
    emails: set[str] = field(default_factory=set)
    handles: set[str] = field(default_factory=set)

    def identity_keys(self) -> set[str]:
        keys = {f"{self.source}:id:{self.native_id}"}
        keys |= {f"{self.source}:handle:{h.lower()}" for h in self.handles if h}
        keys |= {f"email:{e.strip().lower()}" for e in self.emails if e}
        return keys


@dataclass(frozen=True, slots=True)
class Relation:
    """A structural link from an item to another item, known from the record itself."""

    kind: EdgeKind
    target: str
    props: dict[str, Any] = field(default_factory=dict, compare=False, hash=False)


@dataclass(slots=True)
class Item:
    """A normalized record from any tool: an issue, a message, a page, an email..."""

    id: str
    source: Source
    kind: NodeKind
    title: str
    body: str = ""
    url: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    keys: set[str] = field(default_factory=set)
    authors: list[PersonRef] = field(default_factory=list)
    assignees: list[PersonRef] = field(default_factory=list)
    relations: list[Relation] = field(default_factory=list)
    props: dict[str, Any] = field(default_factory=dict)
    scan_text: bool = True

    @property
    def text(self) -> str:
        return f"{self.title}\n{self.body}".strip()


@dataclass(frozen=True, slots=True)
class Node:
    id: str
    kind: NodeKind
    source: Source
    title: str
    body: str = ""
    url: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    keys: frozenset[str] = frozenset()
    props: dict[str, Any] = field(default_factory=dict, compare=False, hash=False)


@dataclass(frozen=True, slots=True)
class Edge:
    src: str
    dst: str
    kind: EdgeKind
    confidence: float = 1.0
    props: dict[str, Any] = field(default_factory=dict, compare=False, hash=False)

    @property
    def key(self) -> tuple[str, str, EdgeKind]:
        return (self.src, self.dst, self.kind)


class Graph:
    """In-memory graph used while building. Nodes are unique by id, edges by (src, dst, kind)."""

    def __init__(self) -> None:
        self._nodes: dict[str, Node] = {}
        self._edges: dict[tuple[str, str, EdgeKind], Edge] = {}

    def add_node(self, node: Node) -> None:
        self._nodes[node.id] = node

    def add_edge(self, edge: Edge) -> None:
        """Add an edge. Self-loops are ignored; on duplicates the most confident edge wins."""
        if edge.src == edge.dst:
            return
        existing = self._edges.get(edge.key)
        if existing is None or edge.confidence > existing.confidence:
            self._edges[edge.key] = edge

    def has_node(self, node_id: str) -> bool:
        return node_id in self._nodes

    def node(self, node_id: str) -> Node | None:
        return self._nodes.get(node_id)

    @property
    def nodes(self) -> list[Node]:
        return list(self._nodes.values())

    @property
    def edges(self) -> list[Edge]:
        return list(self._edges.values())

    def dangling_edges(self) -> list[Edge]:
        return [e for e in self._edges.values() if e.src not in self._nodes or e.dst not in self._nodes]

    def drop_dangling_edges(self) -> int:
        dangling = self.dangling_edges()
        for edge in dangling:
            del self._edges[edge.key]
        return len(dangling)
