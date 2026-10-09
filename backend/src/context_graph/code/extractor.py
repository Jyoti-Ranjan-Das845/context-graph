"""Code structure → graph fragment.

`CodeExtractor` is the port. `GraphifyCodeExtractor` uses Graphify's tree-sitter AST pass
(30+ languages, no LLM) and maps its output onto our file / symbol nodes.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Protocol

from context_graph.domain import Edge, EdgeKind, Graph, Node, NodeKind, Source
from context_graph.domain import keys
from context_graph.sources.github.normalizer import repository_id

log = logging.getLogger(__name__)

_RELATIONS = {
    "contains": EdgeKind.CONTAINS,
    "calls": EdgeKind.CALLS,
    "imports": EdgeKind.IMPORTS,
    "imports_from": EdgeKind.IMPORTS,
}
_DISTINCTIVE = re.compile(r"_|[a-z][A-Z]")


def file_id(full_name: str, path: str) -> str:
    return keys.node_id(Source.CODE, NodeKind.FILE, f"{full_name.lower()}:{path}")


def symbol_id(full_name: str, path: str, name: str) -> str:
    return keys.node_id(Source.CODE, NodeKind.SYMBOL, f"{full_name.lower()}:{path}::{name}")


class CodeExtractor(Protocol):
    def extract(self, full_name: str, root: Path) -> Graph: ...


class GraphifyCodeExtractor:
    def __init__(self, cache_dir: Path) -> None:
        self._cache_dir = cache_dir

    def extract(self, full_name: str, root: Path) -> Graph:
        from graphify.detect import _SKIP_DIRS, CODE_EXTENSIONS
        from graphify.extract import extract

        files = [
            p
            for p in root.rglob("*")
            if p.is_file() and p.suffix in CODE_EXTENSIONS and not (set(p.relative_to(root).parts) & set(_SKIP_DIRS))
        ]
        if not files:
            return Graph()
        result = extract(files, cache_root=self._cache_dir / full_name, root=root, parallel=False)
        return self._map(full_name, root, result)

    def _map(self, full_name: str, root: Path, result: dict[str, Any]) -> Graph:
        graph = Graph()
        local_to_ours: dict[str, str] = {}
        docstrings: dict[str, str] = {}
        rationale_nodes = {n["id"]: n for n in result.get("nodes", []) if n.get("file_type") == "rationale"}

        for edge in result.get("edges", []):
            if edge.get("relation") == "rationale_for" and edge["source"] in rationale_nodes:
                docstrings[edge["target"]] = rationale_nodes[edge["source"]].get("label", "")

        for node in result.get("nodes", []):
            if node.get("file_type") != "code" or not node.get("source_file"):
                continue
            path = node["source_file"]
            label = str(node.get("label", ""))
            if label == Path(path).name:
                ours = self._file_node(full_name, root, path)
            else:
                ours = self._symbol_node(full_name, path, label, node, docstrings.get(node["id"], ""))
            local_to_ours[node["id"]] = ours.id
            graph.add_node(ours)
            if ours.kind is NodeKind.FILE:
                graph.add_edge(Edge(ours.id, repository_id(full_name), EdgeKind.PART_OF, props={"origin": "code"}))

        for edge in result.get("edges", []):
            kind = _RELATIONS.get(edge.get("relation", ""))
            src, dst = local_to_ours.get(edge["source"]), local_to_ours.get(edge["target"])
            if kind and src and dst:
                graph.add_edge(Edge(src, dst, kind, props={"origin": "code", "line": edge.get("source_location")}))
        log.info("Code graph for %s: %d nodes, %d edges", full_name, len(graph.nodes), len(graph.edges))
        return graph

    @staticmethod
    def _file_node(full_name: str, root: Path, path: str) -> Node:
        url = f"https://github.com/{full_name}/blob/HEAD/{path}"
        return Node(
            id=file_id(full_name, path),
            kind=NodeKind.FILE,
            source=Source.CODE,
            title=path,
            body=_head(root / path),
            url=url,
            keys=frozenset({keys.path(path), *keys.url_keys(url)}),
            props={"repo": full_name, "path": path, "ref": path},
        )

    @staticmethod
    def _symbol_node(full_name: str, path: str, label: str, node: dict[str, Any], docstring: str) -> Node:
        name = label.removesuffix("()").split(".")[-1]
        line = str(node.get("source_location") or "").lstrip("L")
        node_keys = {keys.symbol(name)} if _DISTINCTIVE.search(name) else set()
        return Node(
            id=symbol_id(full_name, path, label.removesuffix("()")),
            kind=NodeKind.SYMBOL,
            source=Source.CODE,
            title=label,
            body=docstring,
            url=f"https://github.com/{full_name}/blob/HEAD/{path}#L{line}" if line else None,
            keys=frozenset(node_keys),
            props={"repo": full_name, "path": path, "line": line, "callable": bool(node.get("_callable")), "ref": f"{path}:{line}"},
        )


def _head(path: Path, limit: int = 4000) -> str:
    """The start of a file, so file nodes are searchable by their content."""
    try:
        return path.read_text(errors="replace")[:limit]
    except OSError:
        return ""
