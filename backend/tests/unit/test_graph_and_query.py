from datetime import datetime, timezone

import pytest

from context_graph.domain import EdgeKind, Item, NodeKind, PersonRecord, PersonRef, Relation, Source
from context_graph.domain import keys
from context_graph.graph.builder import GraphBuilder
from context_graph.graph.store import SQLiteGraphStore
from context_graph.linking.identity import IdentityResolver
from context_graph.query.service import QueryService

T = datetime(2026, 10, 8, 19, 0, tzinfo=timezone.utc)


def story_items() -> list[Item]:
    dev = PersonRef(Source.LINEAR, native_id="p1")
    return [
        Item(id="linear:issue:ENG-5", source=Source.LINEAR, kind=NodeKind.ISSUE, title="Duplicate charges on retry",
             body="charge_with_retry has no idempotency key. Reported in DEMO-1.", keys={keys.issue("ENG-5")},
             authors=[dev], updated_at=T, props={"ref": "ENG-5"}),
        Item(id="jira:issue:DEMO-1", source=Source.JIRA, kind=NodeKind.ISSUE, title="Customer charged twice",
             body="Escalated by email", keys={keys.issue("DEMO-1")}, updated_at=T, props={"ref": "DEMO-1"}),
        Item(id="slack:channel:C1", source=Source.SLACK, kind=NodeKind.CHANNEL, title="#payments", keys={keys.channel("payments")}, scan_text=False),
        Item(id="slack:message:C1:1", source=Source.SLACK, kind=NodeKind.MESSAGE, title="Root cause",
             body="Root cause for ENG-5 discussed here", relations=[Relation(EdgeKind.PART_OF, "slack:channel:C1"),
             Relation(EdgeKind.PART_OF, "slack:channel:GONE")], updated_at=T),
    ]


@pytest.fixture
def store(tmp_path) -> SQLiteGraphStore:
    items = story_items()
    identity = IdentityResolver().resolve([PersonRecord(Source.LINEAR, "p1", names={"Dev One"}, emails={"dev@acme.io"})],
                                          [r for i in items for r in i.authors])
    graph = GraphBuilder().build(items, identity)
    store = SQLiteGraphStore(tmp_path / "graph.sqlite")
    store.replace(graph, {"built_at": "now"})
    return store


def test_builder_adds_structural_reference_and_person_edges(store):
    edges = {(e.src, e.dst, e.kind) for e in store.all_edges()}
    assert ("linear:issue:ENG-5", "jira:issue:DEMO-1", EdgeKind.REFERENCES) in edges
    assert ("slack:message:C1:1", "linear:issue:ENG-5", EdgeKind.REFERENCES) in edges
    assert ("person:dev@acme.io", "linear:issue:ENG-5", EdgeKind.AUTHORED) in edges
    assert not any(dst == "slack:channel:GONE" for _, dst, _ in edges)  # dangling edges are dropped


def test_store_search_finds_by_key_word_and_alias(store):
    assert store.search("ENG-5")[0].node.id == "linear:issue:ENG-5"
    assert {h.node.id for h in store.search("idempotency")} == {"linear:issue:ENG-5"}
    assert store.search("payments", kinds=["channel"])[0].node.id == "slack:channel:C1"
    assert store.search("") == []


def test_store_stats_and_meta(store):
    stats = store.stats()
    assert stats["nodes"] == 5 and stats["by_kind"]["person"] == 1
    assert store.meta() == {"built_at": "now"}


def test_query_node_detail_path_and_context(store):
    query = QueryService(store)
    detail = query.node("linear:issue:ENG-5")
    directions = {(n.direction, n.edge.kind, n.node.id) for n in detail.neighbors}
    assert ("out", "references", "jira:issue:DEMO-1") in directions
    assert ("in", "authored", "person:dev@acme.io") in directions

    path = query.path("slack:message:C1:1", "jira:issue:DEMO-1")
    assert [n.id for n in path.nodes] == ["slack:message:C1:1", "linear:issue:ENG-5", "jira:issue:DEMO-1"]
    assert query.path("slack:channel:C1", "missing") is None

    bundle = query.context("duplicate charges")
    assert bundle["results"][0]["id"] == "linear:issue:ENG-5"
    assert any("DEMO-1" in link for link in bundle["results"][0]["links"])


def test_query_neighbors_respects_depth(store):
    query = QueryService(store)
    one = {n.id for n in query.neighbors("jira:issue:DEMO-1", depth=1).nodes}
    two = {n.id for n in query.neighbors("jira:issue:DEMO-1", depth=2).nodes}
    assert one == {"jira:issue:DEMO-1", "linear:issue:ENG-5"}
    assert "slack:message:C1:1" in two and "person:dev@acme.io" in two


def test_replace_is_atomic_and_overwrites(store, tmp_path):
    from context_graph.domain import Graph

    store.replace(Graph(), {"built_at": "later"})
    assert store.stats()["nodes"] == 0 and store.meta()["built_at"] == "later"
    assert not (tmp_path / "graph.sqlite.tmp").exists()


def test_sync_status_keeps_the_last_pull_of_each_tool(tmp_path):
    from context_graph.pipeline.status import SyncStatusWriter

    status = SyncStatusWriter(tmp_path / "status.json")
    status.start("manual")
    status.source("linear", pull="ok", records={"issues": 5}, finished_at="2026-10-09T10:00:00+00:00")
    status.source("linear", items=6)
    status.source("gmail", pull="running")
    status.finish()

    status.start("build")  # a run that does not pull
    status.source("linear", items=7)
    status.finish()

    sources = status.read()["sources"]
    assert sources["linear"] == {"pull": "ok", "records": {"issues": 5}, "finished_at": "2026-10-09T10:00:00+00:00", "items": 7}
    assert "gmail" not in sources  # an interrupted pull is not reported as a result


def test_search_ranks_items_with_every_content_word_first(tmp_path):
    from context_graph.domain import Graph, Node
    from context_graph.graph.fulltext import search_terms

    graph = Graph()
    graph.add_node(Node(id="decision:1", kind=NodeKind.DECISION, source=Source.DERIVED, title="Cap payment retries at 5."))
    graph.add_node(Node(id="decision:2", kind=NodeKind.DECISION, source=Source.DERIVED, title="Ship dark mode in November."))
    graph.add_node(Node(id="slack:channel:C9", kind=NodeKind.CHANNEL, source=Source.SLACK, title="#all-acme",
                        body="Which plans were made about the offsite? Anything about lunch."))
    graph.add_node(Node(id="linear:issue:ENG-9", kind=NodeKind.ISSUE, source=Source.LINEAR, title="Payment page copy", props={"ref": "ENG-9"}))
    store = SQLiteGraphStore(tmp_path / "graph.sqlite")
    store.replace(graph, {})

    assert search_terms("Which decisions were made about payment retries?") == ["decisions", "payment", "retries"]
    hits = [h.node.id for h in store.search("Which decisions were made about payment retries?")]
    assert hits[0] == "decision:1"  # every content word, and "decisions" matches the node kind
    assert set(hits[1:]) == {"decision:2", "linear:issue:ENG-9"}  # partial matches follow
    assert "slack:channel:C9" not in hits  # filler words alone never match
    assert [h.node.id for h in store.search("which")] == ["slack:channel:C9"]  # a query of only filler words still works
    assert store.search("ENG-9")[0].node.id == "linear:issue:ENG-9"
