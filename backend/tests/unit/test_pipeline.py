"""The sync pipeline with fake I/O: fault isolation and keeping a good graph."""

from typing import Any

from context_graph.domain import Graph, Node, NodeKind, Source
from context_graph.graph.store import SQLiteGraphStore
from context_graph.ingest.raw_store import RawStoreError
from context_graph.pipeline.status import SyncStatusWriter
from context_graph.pipeline.sync import PipelineDeps, SyncPipeline, SyncRequest
from context_graph.sources.registry import default_registry

LINEAR_ISSUE = {"id": "u-1", "identifier": "ENG-5", "title": "Dup charges", "description": "see DEMO-1", "creatorid": "p1"}


class FakeRawStore:
    def __init__(self, records: dict[str, dict[str, list[Any]]] | None = None, error: Exception | None = None) -> None:
        self.records = records or {}
        self.error = error

    def read(self, schema: str, streams: tuple[str, ...]) -> dict[str, list[Any]]:
        if self.error:
            raise self.error
        return {stream: self.records.get(schema, {}).get(stream, []) for stream in streams}


def pipeline(tmp_path, settings_repo, raw: FakeRawStore) -> tuple[SyncPipeline, SQLiteGraphStore, SyncStatusWriter]:
    store = SQLiteGraphStore(tmp_path / "graph.sqlite")
    status = SyncStatusWriter(tmp_path / "status.json")
    deps = PipelineDeps(
        settings=settings_repo,
        registry=default_registry(),
        runner=None,  # never used: these runs do not pull
        raw=raw,
        store=store,
        status=status,
        lock_path=tmp_path / "sync.lock",
        code_service=lambda settings: None,
        enricher=lambda settings: None,
    )
    return SyncPipeline(deps), store, status


def test_one_broken_tool_does_not_stop_the_others(tmp_path, settings_repo):
    raw = FakeRawStore({"linear": {"issues": [LINEAR_ISSUE]}, "gmail": {"messages_details": [None]}})
    sync, store, status = pipeline(tmp_path, settings_repo, raw)

    report = sync.run(SyncRequest(pull=False))

    assert report.ok
    assert store.get_node("linear:issue:ENG-5") is not None
    assert "normalize_error" in status.read()["sources"]["gmail"]


def test_unreadable_local_data_keeps_the_current_graph(tmp_path, settings_repo):
    sync, store, status = pipeline(tmp_path, settings_repo, FakeRawStore(error=RawStoreError("Could not read airbyte.duckdb: locked")))
    previous = Graph()
    previous.add_node(Node(id="linear:issue:ENG-5", kind=NodeKind.ISSUE, source=Source.LINEAR, title="Dup charges"))
    store.replace(previous, {"built_at": "before"})

    report = sync.run(SyncRequest(pull=False))

    assert not report.ok and "locked" in report.error
    assert status.read()["state"] == "failed"
    assert store.meta() == {"built_at": "before"} and store.get_node("linear:issue:ENG-5") is not None
