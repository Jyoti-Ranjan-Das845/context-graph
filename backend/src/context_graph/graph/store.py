"""Graph persistence.

`GraphStore` is the port; `SQLiteGraphStore` is the default adapter: one file with
nodes, edges and an FTS5 full-text index. A sync writes a complete new graph to a
temporary file and swaps it in atomically, so readers never see a half-built graph.
"""

from __future__ import annotations

import json
import os
import sqlite3
from collections.abc import Iterable, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol

from context_graph.domain import Edge, EdgeKind, Graph, Node, NodeKind, Source
from context_graph.graph.fulltext import aliases, match_levels, search_terms

SCHEMA = """
create table nodes (
    id text primary key, kind text not null, source text not null, title text not null,
    body text not null default '', url text, created_at text, updated_at text,
    keys text not null default '[]', props text not null default '{}'
);
create index nodes_kind on nodes(kind);
create index nodes_source on nodes(source);
create index nodes_updated on nodes(updated_at);
create table edges (
    src text not null, dst text not null, kind text not null,
    confidence real not null default 1.0, props text not null default '{}',
    primary key (src, dst, kind)
);
create index edges_dst on edges(dst);
create virtual table nodes_fts using fts5(id unindexed, title, body, aliases, tokenize = 'porter unicode61');
create table meta (key text primary key, value text not null);
"""

@dataclass(frozen=True)
class SearchHit:
    node: Node
    score: float


class GraphStore(Protocol):
    def replace(self, graph: Graph, meta: dict[str, Any]) -> None: ...
    def get_node(self, node_id: str) -> Node | None: ...
    def get_nodes(self, node_ids: Iterable[str]) -> list[Node]: ...
    def search(self, query: str, *, kinds: Sequence[str] = (), sources: Sequence[str] = (), limit: int = 20) -> list[SearchHit]: ...
    def edges_touching(self, node_ids: Iterable[str], *, kinds: Sequence[str] = ()) -> list[Edge]: ...
    def all_nodes(self, *, kinds: Sequence[str] = (), sources: Sequence[str] = (), limit: int | None = None) -> list[Node]: ...
    def all_edges(self) -> list[Edge]: ...
    def recent(self, *, since: datetime | None = None, sources: Sequence[str] = (), limit: int = 30) -> list[Node]: ...
    def stats(self) -> dict[str, Any]: ...
    def meta(self) -> dict[str, Any]: ...


class SQLiteGraphStore:
    def __init__(self, path: Path) -> None:
        self._path = path

    @property
    def exists(self) -> bool:
        return self._path.exists()

    # ------------------------------------------------------------ writes

    def replace(self, graph: Graph, meta: dict[str, Any]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(".sqlite.tmp")
        tmp.unlink(missing_ok=True)
        con = sqlite3.connect(tmp)
        try:
            con.executescript(SCHEMA)
            con.executemany(
                "insert into nodes values (?,?,?,?,?,?,?,?,?,?)",
                [_node_row(n) for n in graph.nodes],
            )
            con.executemany(
                "insert into nodes_fts (id, title, body, aliases) values (?,?,?,?)",
                [(n.id, n.title, n.body, aliases(n)) for n in graph.nodes],
            )
            con.executemany(
                "insert into edges values (?,?,?,?,?)",
                [(e.src, e.dst, e.kind.value, e.confidence, json.dumps(e.props)) for e in graph.edges],
            )
            con.executemany("insert into meta values (?,?)", [(k, json.dumps(v, default=str)) for k, v in meta.items()])
            con.commit()
        finally:
            con.close()
        os.replace(tmp, self._path)

    # ------------------------------------------------------------ reads

    def get_node(self, node_id: str) -> Node | None:
        nodes = self.get_nodes([node_id])
        return nodes[0] if nodes else None

    def get_nodes(self, node_ids: Iterable[str]) -> list[Node]:
        ids = list(dict.fromkeys(node_ids))
        if not ids or not self.exists:
            return []
        with self._read() as con:
            rows = _chunked_query(con, "select * from nodes where id in ({})", ids)
        by_id = {row["id"]: _row_node(row) for row in rows}
        return [by_id[i] for i in ids if i in by_id]

    def search(self, query: str, *, kinds: Sequence[str] = (), sources: Sequence[str] = (), limit: int = 20) -> list[SearchHit]:
        """Best matches first; `fulltext.match_levels` explains the ranking."""
        levels = match_levels(search_terms(query))
        if not levels or not self.exists:
            return []
        found: dict[str, SearchHit] = {}
        with self._read() as con:
            for expressions in levels:
                level: dict[str, SearchHit] = {}
                for expression in expressions:
                    for hit in _match(con, expression, kinds, sources, limit):
                        best = level.get(hit.node.id)
                        if hit.node.id not in found and (best is None or hit.score > best.score):
                            level[hit.node.id] = hit
                found.update((hit.node.id, hit) for hit in sorted(level.values(), key=lambda h: -h.score))
                if len(found) >= limit:
                    break
        return list(found.values())[:limit]

    def edges_touching(self, node_ids: Iterable[str], *, kinds: Sequence[str] = ()) -> list[Edge]:
        ids = list(dict.fromkeys(node_ids))
        if not ids or not self.exists:
            return []
        with self._read() as con:
            out = _chunked_query(con, "select * from edges where src in ({0}) or dst in ({0})", ids, repeat=2)
        edges = [_row_edge(r) for r in out]
        return [e for e in edges if not kinds or e.kind.value in kinds]

    def all_nodes(self, *, kinds: Sequence[str] = (), sources: Sequence[str] = (), limit: int | None = None) -> list[Node]:
        if not self.exists:
            return []
        sql, params = _filter("select * from nodes where 1=1", [], kinds, sources)
        if limit:
            sql += " limit ?"
            params.append(limit)
        with self._read() as con:
            return [_row_node(r) for r in con.execute(sql, params).fetchall()]

    def all_edges(self) -> list[Edge]:
        if not self.exists:
            return []
        with self._read() as con:
            return [_row_edge(r) for r in con.execute("select * from edges").fetchall()]

    def recent(self, *, since: datetime | None = None, sources: Sequence[str] = (), limit: int = 30) -> list[Node]:
        if not self.exists:
            return []
        sql = "select * from nodes where updated_at is not null and kind not in ('person','topic','decision','file','symbol')"
        params: list[Any] = []
        if since:
            sql += " and updated_at >= ?"
            params.append(since.isoformat())
        sql, params = _filter(sql, params, (), sources)
        sql += " order by updated_at desc limit ?"
        params.append(limit)
        with self._read() as con:
            return [_row_node(r) for r in con.execute(sql, params).fetchall()]

    def stats(self) -> dict[str, Any]:
        if not self.exists:
            return {"nodes": 0, "edges": 0, "by_kind": {}, "by_source": {}, "by_edge_kind": {}}
        with self._read() as con:
            return {
                "nodes": con.execute("select count(*) from nodes").fetchone()[0],
                "edges": con.execute("select count(*) from edges").fetchone()[0],
                "by_kind": dict(con.execute("select kind, count(*) from nodes group by kind").fetchall()),
                "by_source": dict(con.execute("select source, count(*) from nodes group by source").fetchall()),
                "by_edge_kind": dict(con.execute("select kind, count(*) from edges group by kind").fetchall()),
            }

    def meta(self) -> dict[str, Any]:
        if not self.exists:
            return {}
        with self._read() as con:
            return {k: json.loads(v) for k, v in con.execute("select key, value from meta").fetchall()}

    @contextmanager
    def _read(self):
        con = sqlite3.connect(f"file:{self._path}?mode=ro", uri=True)
        con.row_factory = sqlite3.Row
        try:
            yield con
        finally:
            con.close()


# ---------------------------------------------------------------- row mapping


def _node_row(node: Node) -> tuple[Any, ...]:
    return (
        node.id,
        node.kind.value,
        node.source.value,
        node.title,
        node.body,
        node.url,
        node.created_at.isoformat() if node.created_at else None,
        node.updated_at.isoformat() if node.updated_at else None,
        json.dumps(sorted(node.keys)),
        json.dumps(node.props, default=str),
    )


def _row_node(row: sqlite3.Row) -> Node:
    return Node(
        id=row["id"],
        kind=NodeKind(row["kind"]),
        source=Source(row["source"]),
        title=row["title"],
        body=row["body"],
        url=row["url"],
        created_at=datetime.fromisoformat(row["created_at"]) if row["created_at"] else None,
        updated_at=datetime.fromisoformat(row["updated_at"]) if row["updated_at"] else None,
        keys=frozenset(json.loads(row["keys"])),
        props=json.loads(row["props"]),
    )


def _row_edge(row: sqlite3.Row) -> Edge:
    return Edge(row["src"], row["dst"], EdgeKind(row["kind"]), row["confidence"], json.loads(row["props"]))


def _match(con: sqlite3.Connection, expression: str, kinds: Sequence[str], sources: Sequence[str], limit: int) -> list[SearchHit]:
    """One FTS5 query; BM25 weights title 4, body 1, aliases 6."""
    sql = (
        "select n.*, bm25(nodes_fts, 0.0, 4.0, 1.0, 6.0) as score from nodes_fts "
        "join nodes n on n.id = nodes_fts.id where nodes_fts match ?"
    )
    sql, params = _filter(sql, [expression], kinds, sources, prefix="n.")
    rows = con.execute(sql + " order by score limit ?", [*params, limit]).fetchall()
    return [SearchHit(_row_node(r), -float(r["score"])) for r in rows]


def _filter(sql: str, params: list[Any], kinds: Sequence[str], sources: Sequence[str], prefix: str = "") -> tuple[str, list[Any]]:
    if kinds:
        sql += f" and {prefix}kind in ({','.join('?' * len(kinds))})"
        params.extend(kinds)
    if sources:
        sql += f" and {prefix}source in ({','.join('?' * len(sources))})"
        params.extend(sources)
    return sql, params


def _chunked_query(con: sqlite3.Connection, template: str, ids: list[str], repeat: int = 1, size: int = 400) -> list[sqlite3.Row]:
    rows: list[sqlite3.Row] = []
    for i in range(0, len(ids), size):
        chunk = ids[i : i + size]
        placeholders = ",".join("?" * len(chunk))
        rows.extend(con.execute(template.format(placeholders), chunk * repeat).fetchall())
    return rows
