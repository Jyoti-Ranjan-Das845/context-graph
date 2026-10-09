"""The sync pipeline: pull → code → normalize → identity → build → enrich → persist."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from context_graph.code.service import CodeService
from context_graph.config import Settings, SettingsRepository
from context_graph.domain import Graph, Item, Source
from context_graph.enrich.enricher import SemanticEnricher
from context_graph.graph.builder import GraphBuilder
from context_graph.graph.store import GraphStore
from context_graph.ingest.airbyte_runner import AirbyteRunner
from context_graph.ingest.raw_store import RawStore
from context_graph.linking.identity import IdentityResolver
from context_graph.pipeline.status import SyncStatusWriter, now, sync_lock
from context_graph.sources.base import NormalizedBatch
from context_graph.sources.registry import SourceRegistry

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class SyncRequest:
    trigger: str = "manual"
    pull: bool = True
    sources: tuple[str, ...] = ()
    """Limit pulling to these tools. Empty means every enabled, configured tool."""
    code: bool = True
    enrich: bool | None = None
    """None follows `settings.json`."""


@dataclass
class SyncReport:
    ok: bool = True
    pulled: dict[str, Any] = field(default_factory=dict)
    nodes: int = 0
    edges: int = 0
    seconds: float = 0.0
    error: str | None = None


@dataclass
class PipelineDeps:
    settings: SettingsRepository
    registry: SourceRegistry
    runner: AirbyteRunner
    raw: RawStore
    store: GraphStore
    status: SyncStatusWriter
    lock_path: Any
    code_service: Callable[[Settings], CodeService | None]
    enricher: Callable[[Settings], SemanticEnricher | None]


class SyncPipeline:
    def __init__(self, deps: PipelineDeps) -> None:
        self._d = deps

    def run(self, request: SyncRequest = SyncRequest(), on_started: Callable[[], None] | None = None) -> SyncReport:
        """Run one sync. Raises `SyncAlreadyRunning` if another process or thread is syncing.

        `on_started` is called once the run holds the lock and its status says "running".
        """
        report = SyncReport()
        started = time.monotonic()
        with sync_lock(self._d.lock_path):
            self._d.status.start(request.trigger)
            if on_started:
                on_started()
            try:
                settings = self._d.settings.load()
                if request.pull:
                    self._pull(settings, request, report)
                items, people = self._normalize(settings)
                code_fragment = self._code(settings, request, items)
                self._d.status.step("building graph")
                identity = IdentityResolver(settings.options.identity.merge_by_name).resolve(
                    people, [ref for item in items for ref in (*item.authors, *item.assignees)]
                )
                graph = GraphBuilder().build(items, identity, [code_fragment])
                self._enrich(settings, request, items, graph)
                self._d.status.step("saving")
                self._d.store.replace(graph, {"built_at": now(), "trigger": request.trigger})
                report.nodes, report.edges = len(graph.nodes), len(graph.edges)
                self._d.status.section("graph", {"nodes": report.nodes, "edges": report.edges})
                self._d.status.finish()
            except Exception as exc:
                log.exception("Sync failed")
                report.ok, report.error = False, str(exc)[:300]
                self._d.status.finish(error=report.error)
        report.seconds = round(time.monotonic() - started, 1)
        return report

    # ------------------------------------------------------------ steps

    def _pull(self, settings: Settings, request: SyncRequest, report: SyncReport) -> None:
        for definition in self._d.registry.all():
            sid = definition.id.value
            if request.sources and sid not in request.sources:
                continue
            if not definition.is_enabled(settings):
                self._d.status.source(sid, pull="disabled")
                continue
            if not definition.is_configured(settings):
                self._d.status.source(sid, pull="not_configured", missing=definition.missing_credentials(settings))
                continue
            self._d.status.step(f"pulling {definition.label}")
            self._d.status.source(sid, pull="running", started_at=now())
            result = self._d.runner.read(definition, settings)
            self._d.status.source(
                sid,
                pull="ok" if result.ok else "error",
                records=result.records_by_stream,
                message=result.message,
                finished_at=now(),
            )
            report.pulled[sid] = result.records_by_stream if result.ok else result.message

    def _normalize(self, settings: Settings) -> tuple[list[Item], list[Any]]:
        """Raw records → items. A tool whose records cannot be normalized is skipped; if the local
        raw data cannot be read at all, `RawStoreError` stops the run so the current graph is kept."""
        self._d.status.step("normalizing")
        combined = NormalizedBatch()
        for definition in self._d.registry.all():
            if not definition.is_enabled(settings):
                continue
            sid = definition.id.value
            records = self._d.raw.read(sid, definition.streams)
            try:
                batch = definition.normalizer(settings).normalize(records)
                combined.extend(batch)
                self._d.status.source(sid, items=len(batch.items), people=len(batch.people))
            except Exception as exc:  # one broken tool must not stop the others
                log.exception("Normalizing %s failed", sid)
                self._d.status.source(sid, normalize_error=str(exc)[:200])
        return combined.items, combined.people

    def _code(self, settings: Settings, request: SyncRequest, items: list[Item]) -> Graph:
        service = self._d.code_service(settings) if request.code else None
        if service is None:
            return Graph()
        self._d.status.step("reading code")
        github = self._d.registry.get(Source.GITHUB)
        fragment, code_report = service.build(github.options(settings).repos, [i for i in items if i.source is Source.GITHUB])
        self._d.status.section("code", {"repos": code_report.repos, "errors": code_report.errors})
        return fragment

    def _enrich(self, settings: Settings, request: SyncRequest, items: list[Item], graph: Graph) -> None:
        wanted = settings.options.enrichment.enabled if request.enrich is None else request.enrich
        enricher = self._d.enricher(settings) if wanted else None
        if enricher is None:
            self._d.status.section("enrichment", {"state": "off"})
            return
        self._d.status.step("enriching with Claude Code")
        fragment, report = enricher.enrich(items)
        for node in fragment.nodes:
            graph.add_node(node)
        for edge in fragment.edges:
            graph.add_edge(edge)
        graph.drop_dangling_edges()
        self._d.status.section("enrichment", {"state": "done", **report.__dict__})
