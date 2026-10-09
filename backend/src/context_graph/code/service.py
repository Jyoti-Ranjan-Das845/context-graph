"""Builds the code fragment of the graph: repo snapshots → files/symbols, and PR → changed files."""

from __future__ import annotations

import logging
from collections.abc import Iterable
from dataclasses import dataclass, field

from context_graph.code.extractor import CodeExtractor, file_id
from context_graph.code.fetcher import GitHubCodeFetcher
from context_graph.domain import Edge, EdgeKind, Graph, Item, NodeKind

log = logging.getLogger(__name__)


@dataclass
class CodeSyncReport:
    repos: dict[str, str] = field(default_factory=dict)
    errors: dict[str, str] = field(default_factory=dict)


class CodeService:
    def __init__(self, fetcher: GitHubCodeFetcher, extractor: CodeExtractor) -> None:
        self._fetcher = fetcher
        self._extractor = extractor

    def build(self, repo_patterns: list[str], github_items: Iterable[Item]) -> tuple[Graph, CodeSyncReport]:
        report = CodeSyncReport()
        fragment = Graph()
        for full_name in self._fetcher.expand(repo_patterns):
            try:
                snapshot = self._fetcher.snapshot(full_name)
                code = self._extractor.extract(full_name, snapshot.path)
                for node in code.nodes:
                    fragment.add_node(node)
                for edge in code.edges:
                    fragment.add_edge(edge)
                report.repos[full_name] = f"{snapshot.sha[:7]} ({'updated' if snapshot.changed else 'unchanged'})"
            except Exception as exc:
                log.exception("Code sync failed for %s", full_name)
                report.errors[full_name] = str(exc)[:200]

        for item in github_items:
            if item.kind is not NodeKind.PULL_REQUEST:
                continue
            repo, number = item.props["repo"], item.props["number"]
            try:
                updated = item.updated_at.isoformat() if item.updated_at else None
                for path in self._fetcher.pr_files(repo, number, updated):
                    fragment.add_edge(Edge(item.id, file_id(repo, path), EdgeKind.CHANGES, props={"origin": "github"}))
            except Exception as exc:
                report.errors[f"{repo}#{number}"] = str(exc)[:200]
        return fragment, report
