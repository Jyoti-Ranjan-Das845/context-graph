"""Composition root: the only place that chooses concrete implementations.

Every interface (CLI, REST, MCP) gets its objects from `App`, so swapping an adapter
(another graph store, another LLM) is a change in this file only.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path

from context_graph.agents import AgentIntegrations, default_integrations
from context_graph.code.extractor import GraphifyCodeExtractor
from context_graph.code.fetcher import GitHubCodeFetcher
from context_graph.code.github_client import GitHubClient
from context_graph.code.service import CodeService
from context_graph.config import AppPaths, Settings, SettingsRepository, discover_root
from context_graph.domain import Source
from context_graph.enrich.cache import LLMCache
from context_graph.enrich.concepts import ConceptMerger, ConceptRegistry
from context_graph.enrich.enricher import SemanticEnricher
from context_graph.enrich.llm import ClaudeCodeClient
from context_graph.graph.store import SQLiteGraphStore
from context_graph.ingest.airbyte_runner import AirbyteRunner
from context_graph.ingest.raw_store import RawStore
from context_graph.pipeline.scheduler import LaunchdScheduler
from context_graph.pipeline.status import SyncStatusWriter
from context_graph.pipeline.sync import PipelineDeps, SyncPipeline
from context_graph.query.service import QueryService
from context_graph.sources.registry import SourceRegistry, default_registry


@dataclass
class App:
    root: Path

    @cached_property
    def paths(self) -> AppPaths:
        paths = AppPaths(self.root)
        paths.ensure()
        return paths

    @cached_property
    def settings_repo(self) -> SettingsRepository:
        return SettingsRepository(self.paths)

    @cached_property
    def registry(self) -> SourceRegistry:
        return default_registry()

    @cached_property
    def runner(self) -> AirbyteRunner:
        return AirbyteRunner(self.paths.raw_db, self.paths.airbyte_dir)

    @cached_property
    def store(self) -> SQLiteGraphStore:
        return SQLiteGraphStore(self.paths.graph_db)

    @cached_property
    def status(self) -> SyncStatusWriter:
        return SyncStatusWriter(self.paths.state_dir / "sync_status.json")

    @cached_property
    def query(self) -> QueryService:
        return QueryService(self.store)

    @cached_property
    def scheduler(self) -> LaunchdScheduler:
        return LaunchdScheduler(self.root, self.paths.logs_dir)

    @cached_property
    def agents(self) -> AgentIntegrations:
        return default_integrations()

    @cached_property
    def pipeline(self) -> SyncPipeline:
        return SyncPipeline(
            PipelineDeps(
                settings=self.settings_repo,
                registry=self.registry,
                runner=self.runner,
                raw=RawStore(self.paths.raw_db, self.paths.airbyte_dir),
                store=self.store,
                status=self.status,
                lock_path=self.paths.state_dir / "sync.lock",
                code_service=self._code_service,
                enricher=self._enricher,
            )
        )

    def settings(self) -> Settings:
        return self.settings_repo.load()

    # ------------------------------------------------------------ factories that depend on settings

    def _code_service(self, settings: Settings) -> CodeService | None:
        github = self.registry.get(Source.GITHUB)
        token = settings.secret("GITHUB_TOKEN")
        if not token or not github.is_enabled(settings) or not github.options(settings).include_code:
            return None
        fetcher = GitHubCodeFetcher(GitHubClient(token), self.paths.code_dir, self.paths.state_dir / "code_state.json")
        return CodeService(fetcher, GraphifyCodeExtractor(self.paths.data_dir / "cache" / "graphify"))

    def _enricher(self, settings: Settings) -> SemanticEnricher | None:
        options = settings.options.enrichment
        if options.provider != "claude-cli":
            return None
        client = ClaudeCodeClient(model=options.model, timeout_seconds=options.timeout_seconds)
        if not client.available():
            logging.getLogger(__name__).warning("Claude Code CLI not found; skipping enrichment")
            return None
        merger = ConceptMerger(client, ConceptRegistry(self.paths.llm_cache))
        return SemanticEnricher(
            client, LLMCache(self.paths.llm_cache), options.batch_size, options.max_items_per_sync, merger=merger
        )


def create_app(root: Path | None = None) -> App:
    return App(root or discover_root())


def configure_logging(app: App, verbose: bool = False) -> None:
    handlers: list[logging.Handler] = [logging.FileHandler(app.paths.logs_dir / "context-graph.log")]
    if verbose:
        handlers.append(logging.StreamHandler())
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=handlers,
        force=True,
    )
