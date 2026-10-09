"""Read side of the graph, shared by the UI, the CLI and agents (MCP).

Results are compact "cards" so an agent can explore without loading full documents;
full text is only returned for a single node on request.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from context_graph.domain import Edge, Node
from context_graph.graph.store import GraphStore

SNIPPET_CHARS = 220


@dataclass(frozen=True)
class NodeCard:
    id: str
    kind: str
    source: str
    title: str
    ref: str | None
    url: str | None
    updated_at: str | None
    snippet: str

    @classmethod
    def of(cls, node: Node) -> NodeCard:
        body = " ".join(node.body.split())
        return cls(
            id=node.id,
            kind=node.kind.value,
            source=node.source.value,
            title=node.title,
            ref=str(node.props["ref"]) if node.props.get("ref") else None,
            url=node.url,
            updated_at=node.updated_at.isoformat() if node.updated_at else None,
            snippet=body[:SNIPPET_CHARS] + ("…" if len(body) > SNIPPET_CHARS else ""),
        )


@dataclass(frozen=True)
class EdgeView:
    src: str
    dst: str
    kind: str
    confidence: float
    evidence: str | None = None
    via: str | None = None

    @classmethod
    def of(cls, edge: Edge) -> EdgeView:
        return cls(
            src=edge.src,
            dst=edge.dst,
            kind=edge.kind.value,
            confidence=edge.confidence,
            evidence=edge.props.get("evidence"),
            via=edge.props.get("matcher") or edge.props.get("origin"),
        )


@dataclass
class Subgraph:
    nodes: list[NodeCard] = field(default_factory=list)
    edges: list[EdgeView] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"nodes": [asdict(n) for n in self.nodes], "edges": [asdict(e) for e in self.edges]}


@dataclass
class Neighbor:
    direction: str
    edge: EdgeView
    node: NodeCard


@dataclass
class NodeDetail:
    node: dict[str, Any]
    neighbors: list[Neighbor]

    def to_dict(self) -> dict[str, Any]:
        return {"node": self.node, "neighbors": [asdict(n) for n in self.neighbors]}


class QueryService:
    def __init__(self, store: GraphStore) -> None:
        self._store = store

    def search(self, query: str, *, kinds: Sequence[str] = (), sources: Sequence[str] = (), limit: int = 20) -> list[NodeCard]:
        return [NodeCard.of(hit.node) for hit in self._store.search(query, kinds=kinds, sources=sources, limit=limit)]

    def node(self, node_id: str, *, neighbor_limit: int = 80) -> NodeDetail | None:
        node = self._store.get_node(node_id)
        if node is None:
            return None
        edges = sorted(self._store.edges_touching([node_id]), key=lambda e: -e.confidence)[:neighbor_limit]
        others = {e.dst if e.src == node_id else e.src for e in edges}
        cards = {n.id: NodeCard.of(n) for n in self._store.get_nodes(others)}
        neighbors = [
            Neighbor("out" if e.src == node_id else "in", EdgeView.of(e), cards[e.dst if e.src == node_id else e.src])
            for e in edges
            if (e.dst if e.src == node_id else e.src) in cards
        ]
        return NodeDetail(node=_node_dict(node), neighbors=neighbors)

    def neighbors(self, node_id: str, *, depth: int = 1, edge_kinds: Sequence[str] = (), limit: int = 150) -> Subgraph:
        depth = max(1, min(depth, 3))
        seen = {node_id}
        frontier = {node_id}
        edges: dict[tuple[str, str, str], Edge] = {}
        for _ in range(depth):
            found = self._store.edges_touching(frontier, kinds=edge_kinds)
            next_frontier: set[str] = set()
            for edge in found:
                edges[(edge.src, edge.dst, edge.kind.value)] = edge
                for end in (edge.src, edge.dst):
                    if end not in seen and len(seen) < limit:
                        seen.add(end)
                        next_frontier.add(end)
            frontier = next_frontier
            if not frontier:
                break
        nodes = self._store.get_nodes(seen)
        kept = {n.id for n in nodes}
        return Subgraph(
            nodes=[NodeCard.of(n) for n in nodes],
            edges=[EdgeView.of(e) for e in edges.values() if e.src in kept and e.dst in kept],
        )

    def path(self, src: str, dst: str, *, max_depth: int = 5) -> Subgraph | None:
        """Shortest connection between two nodes, ignoring edge direction."""
        if src == dst:
            node = self._store.get_node(src)
            return Subgraph(nodes=[NodeCard.of(node)]) if node else None
        parents: dict[str, tuple[str, Edge] | None] = {src: None}
        queue: deque[tuple[str, int]] = deque([(src, 0)])
        while queue:
            current, dist = queue.popleft()
            if dist >= max_depth:
                continue
            for edge in self._store.edges_touching([current]):
                other = edge.dst if edge.src == current else edge.src
                if other in parents:
                    continue
                parents[other] = (current, edge)
                if other == dst:
                    return self._trace(parents, dst)
                queue.append((other, dist + 1))
        return None

    def recent(self, *, hours: int | None = None, sources: Sequence[str] = (), limit: int = 30) -> list[NodeCard]:
        since = datetime.now(timezone.utc) - timedelta(hours=hours) if hours else None
        return [NodeCard.of(n) for n in self._store.recent(since=since, sources=sources, limit=limit)]

    def context(self, question: str, *, limit: int = 6, links_per_result: int = 8) -> dict[str, Any]:
        """A compact, citation-ready bundle for agents: the best matches plus what they connect to."""
        results = []
        for card in self.search(question, limit=limit):
            detail = self.node(card.id, neighbor_limit=links_per_result)
            links = [_describe_link(n) for n in detail.neighbors] if detail else []
            results.append({**asdict(card), "links": links})
        return {"question": question, "results": results}

    def view(self, *, kinds: Sequence[str] = (), sources: Sequence[str] = (), limit: int = 3000) -> Subgraph:
        nodes = self._store.all_nodes(kinds=kinds, sources=sources, limit=limit)
        ids = {n.id for n in nodes}
        edges = [e for e in self._store.all_edges() if e.src in ids and e.dst in ids]
        return Subgraph(nodes=[NodeCard.of(n) for n in nodes], edges=[EdgeView.of(e) for e in edges])

    def stats(self) -> dict[str, Any]:
        return {**self._store.stats(), "meta": self._store.meta()}

    def _trace(self, parents: dict[str, tuple[str, Edge] | None], end: str) -> Subgraph:
        chain_nodes, chain_edges = [end], []
        while (step := parents[chain_nodes[-1]]) is not None:
            previous, edge = step
            chain_edges.append(edge)
            chain_nodes.append(previous)
        chain_nodes.reverse()
        chain_edges.reverse()
        by_id = {n.id: n for n in self._store.get_nodes(chain_nodes)}
        return Subgraph(
            nodes=[NodeCard.of(by_id[i]) for i in chain_nodes if i in by_id],
            edges=[EdgeView.of(e) for e in chain_edges],
        )


def _describe_link(neighbor: Neighbor) -> str:
    """One line per link, e.g. `→ references issue ENG-5 Duplicate charges… [linear:issue:ENG-5]`."""
    arrow = "→" if neighbor.direction == "out" else "←"
    ref = f"{neighbor.node.ref} " if neighbor.node.ref else ""
    return f"{arrow} {neighbor.edge.kind} {neighbor.node.kind} {ref}{neighbor.node.title} [{neighbor.node.id}]"


def _node_dict(node: Node) -> dict[str, Any]:
    return {
        "id": node.id,
        "kind": node.kind.value,
        "source": node.source.value,
        "title": node.title,
        "body": node.body,
        "url": node.url,
        "created_at": node.created_at.isoformat() if node.created_at else None,
        "updated_at": node.updated_at.isoformat() if node.updated_at else None,
        "keys": sorted(node.keys),
        "props": node.props,
    }
