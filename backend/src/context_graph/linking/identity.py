"""Merge the many records of one person across tools into a single person node.

Union-find over identity keys: a tool's user id, its handle, emails, and (optionally)
the exact full name. Anything two records share joins them into one person.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass

from context_graph.domain import Node, NodeKind, PersonRecord, PersonRef, Source

_SPACES = re.compile(r"\s+")


class _UnionFind:
    def __init__(self) -> None:
        self._parent: dict[str, str] = {}

    def add(self, key: str) -> None:
        self._parent.setdefault(key, key)

    def find(self, key: str) -> str:
        root = key
        while self._parent[root] != root:
            root = self._parent[root]
        while self._parent[key] != root:  # path compression
            self._parent[key], key = root, self._parent[key]
        return root

    def union(self, a: str, b: str) -> None:
        self.add(a)
        self.add(b)
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self._parent[max(ra, rb)] = min(ra, rb)

    def keys(self) -> Iterable[str]:
        return self._parent.keys()


@dataclass(frozen=True)
class IdentityResult:
    people: list[Node]
    _node_by_key: dict[str, str]

    def node_for(self, ref: PersonRef) -> str | None:
        for key in ref.identity_keys():
            if node_id := self._node_by_key.get(key):
                return node_id
        return None


class IdentityResolver:
    def __init__(self, merge_by_name: bool = True) -> None:
        self._merge_by_name = merge_by_name

    def resolve(self, records: Iterable[PersonRecord], refs: Iterable[PersonRef]) -> IdentityResult:
        uf = _UnionFind()
        names: dict[str, Counter[str]] = defaultdict(Counter)
        emails: dict[str, set[str]] = defaultdict(set)
        sources: dict[str, set[Source]] = defaultdict(set)
        handles: dict[str, set[str]] = defaultdict(set)

        def register(keys: set[str], person_names: Iterable[str], source: Source, person_emails: Iterable[str], person_handles: Iterable[str]) -> None:
            keys = set(keys)
            if self._merge_by_name:
                keys |= {k for n in person_names if (k := _name_key(n))}
            if not keys:
                return
            anchor = next(iter(keys))
            for key in keys:
                uf.union(anchor, key)
            names[anchor].update(n.strip() for n in person_names if n and n.strip())
            emails[anchor].update(e.lower() for e in person_emails if e)
            sources[anchor].add(source)
            handles[anchor].update(f"{source}:{h}" for h in person_handles if h)

        for record in records:
            register(record.identity_keys(), record.names, record.source, record.emails, record.handles)
        for ref in refs:
            register(ref.identity_keys(), [ref.name] if ref.name else [], ref.source, [ref.email] if ref.email else [], [ref.handle] if ref.handle else [])

        # gather per component
        members: dict[str, set[str]] = defaultdict(set)
        for key in list(uf.keys()):
            members[uf.find(key)].add(key)
        comp_names: dict[str, Counter[str]] = defaultdict(Counter)
        comp_emails: dict[str, set[str]] = defaultdict(set)
        comp_sources: dict[str, set[Source]] = defaultdict(set)
        comp_handles: dict[str, set[str]] = defaultdict(set)
        for anchor in names.keys() | emails.keys() | sources.keys():
            root = uf.find(anchor)
            comp_names[root].update(names[anchor])
            comp_emails[root] |= emails[anchor]
            comp_sources[root] |= sources[anchor]
            comp_handles[root] |= handles[anchor]

        people: list[Node] = []
        node_by_key: dict[str, str] = {}
        for root, keys in members.items():
            node_id = f"person:{_canonical_key(keys, comp_emails[root])}"
            for key in keys:
                node_by_key[key] = node_id
            people.append(
                Node(
                    id=node_id,
                    kind=NodeKind.PERSON,
                    source=Source.DERIVED,
                    title=_best_name(comp_names[root], comp_emails[root], keys),
                    keys=frozenset(f"email:{e}" for e in comp_emails[root]),
                    props={
                        "emails": sorted(comp_emails[root]),
                        "sources": sorted(s.value for s in comp_sources[root]),
                        "handles": sorted(comp_handles[root]),
                    },
                )
            )
        return IdentityResult(people=people, _node_by_key=node_by_key)


def _name_key(name: str | None) -> str | None:
    """Full names with at least two words merge people; single words are too ambiguous."""
    if not name:
        return None
    normalized = _SPACES.sub(" ", name.strip().lower())
    return f"name:{normalized}" if len(normalized.split(" ")) >= 2 else None


def _canonical_key(keys: set[str], emails: set[str]) -> str:
    if emails:
        return min(emails)
    return min(keys).replace("name:", "").replace(" ", "-")


def _best_name(names: Counter[str], emails: set[str], keys: set[str]) -> str:
    full = [n for n, _ in names.most_common() if " " in n.strip()]
    if full:
        return full[0]
    if names:
        return names.most_common(1)[0][0]
    if emails:
        return min(emails)
    return min(keys)
