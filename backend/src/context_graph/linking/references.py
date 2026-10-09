"""Cross-tool reference linking.

1. `ReferenceIndex` maps every key a node publishes (e.g. ``issue:ENG-5``) to node ids.
2. `ReferenceLinker` runs the matchers over each item's text, looks the keys up, and
   emits `references` edges, or `fixes` edges when a PR/commit says "Fixes X".
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterable, Sequence

from context_graph.domain import Edge, EdgeKind, Item, Node, NodeKind, Source
from context_graph.linking.matchers import Matcher, MatchContext, default_matchers

_FIX_VERB = re.compile(r"\b(fix(?:es|ed)?|close[sd]?|resolve[sd]?)\b[\s:]*(?:[^\s.;,]+[\s,]+){0,2}$", re.IGNORECASE)
_FIX_SOURCES = {NodeKind.PULL_REQUEST, NodeKind.COMMIT}
_MIN_TITLE_WORDS = 3
_EVIDENCE_RADIUS = 70


class ReferenceIndex:
    def __init__(self, nodes: Iterable[Node]) -> None:
        self._targets: dict[str, set[str]] = defaultdict(set)
        repos: list[str] = []
        for node in nodes:
            for key in node.keys:
                if key.startswith("title:") and len(key.split(" ")) < _MIN_TITLE_WORDS:
                    continue  # short titles ("Problem") are too ambiguous to link on
                self._targets[key].add(node.id)
            if node.kind is NodeKind.REPOSITORY and node.source is Source.GITHUB:
                repos.append(str(node.props.get("owner", "")) + "/" + str(node.props.get("name", "")))
        self.only_repo = repos[0] if len(repos) == 1 else None

    def lookup(self, key: str) -> set[str]:
        return self._targets.get(key, set())


class ReferenceLinker:
    def __init__(self, matchers: Sequence[Matcher] | None = None) -> None:
        self._matchers = list(matchers) if matchers is not None else default_matchers()

    def link(self, items: Iterable[Item], index: ReferenceIndex) -> list[Edge]:
        edges: list[Edge] = []
        for item in items:
            if item.scan_text:
                edges.extend(self._link_item(item, index))
        return edges

    def _link_item(self, item: Item, index: ReferenceIndex) -> list[Edge]:
        text = item.text
        context = MatchContext(
            source=item.source.value,
            repo=item.props.get("repo") if item.source is Source.GITHUB else None,
            only_repo=index.only_repo,
        )
        found: dict[tuple[str, EdgeKind], Edge] = {}
        for matcher in self._matchers:
            for hit in matcher.find(text, context):
                targets = set().union(*(index.lookup(k) for k in hit.keys)) - {item.id}
                if not targets:
                    continue
                confidence = hit.confidence if len(targets) == 1 else hit.confidence * 0.6
                kind = self._edge_kind(item, text, hit.start)
                for target in targets:
                    edge = Edge(
                        src=item.id,
                        dst=target,
                        kind=kind,
                        confidence=round(confidence, 3),
                        props={"matcher": hit.matcher, "evidence": _evidence(text, hit.start, hit.end)},
                    )
                    current = found.get((target, kind))
                    if current is None or edge.confidence > current.confidence:
                        found[(target, kind)] = edge
        return list(found.values())

    @staticmethod
    def _edge_kind(item: Item, text: str, start: int) -> EdgeKind:
        if item.kind in _FIX_SOURCES and _FIX_VERB.search(text[max(0, start - 40) : start]):
            return EdgeKind.FIXES
        return EdgeKind.REFERENCES


def _evidence(text: str, start: int, end: int) -> str:
    left = max(0, start - _EVIDENCE_RADIUS)
    right = min(len(text), end + _EVIDENCE_RADIUS)
    snippet = " ".join(text[left:right].split())
    return ("…" if left else "") + snippet + ("…" if right < len(text) else "")
