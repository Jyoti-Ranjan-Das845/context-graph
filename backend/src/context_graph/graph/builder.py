"""Builds the graph from normalized items: nodes, structural edges, people, code and references."""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from context_graph.domain import Edge, EdgeKind, Graph, Item, Node
from context_graph.linking.identity import IdentityResult
from context_graph.linking.references import ReferenceIndex, ReferenceLinker


def item_to_node(item: Item) -> Node:
    return Node(
        id=item.id,
        kind=item.kind,
        source=item.source,
        title=item.title,
        body=item.body,
        url=item.url,
        created_at=item.created_at,
        updated_at=item.updated_at,
        keys=frozenset(item.keys),
        props=dict(item.props),
    )


class GraphBuilder:
    def __init__(self, linker: ReferenceLinker | None = None) -> None:
        self._linker = linker or ReferenceLinker()

    def build(self, items: Sequence[Item], identity: IdentityResult, fragments: Iterable[Graph] = ()) -> Graph:
        graph = Graph()
        for person in identity.people:
            graph.add_node(person)
        for item in items:
            graph.add_node(item_to_node(item))
        for item in items:
            for edge in self._structural_edges(item, identity):
                graph.add_edge(edge)
        for fragment in fragments:
            for node in fragment.nodes:
                graph.add_node(node)
            for edge in fragment.edges:
                graph.add_edge(edge)

        index = ReferenceIndex(graph.nodes)
        for edge in self._linker.link(items, index):
            graph.add_edge(edge)
        graph.drop_dangling_edges()
        return graph

    @staticmethod
    def _structural_edges(item: Item, identity: IdentityResult) -> Iterable[Edge]:
        for relation in item.relations:
            yield Edge(item.id, relation.target, relation.kind, props={"origin": "record", **relation.props})
        for ref in item.authors:
            if person := identity.node_for(ref):
                yield Edge(person, item.id, EdgeKind.AUTHORED, props={"origin": "record"})
        for ref in item.assignees:
            if person := identity.node_for(ref):
                yield Edge(item.id, person, EdgeKind.ASSIGNED_TO, props={"origin": "record"})
