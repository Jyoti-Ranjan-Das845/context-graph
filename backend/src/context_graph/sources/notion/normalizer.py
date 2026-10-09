"""Notion raw records → page items (with their block text) and people."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from context_graph.domain import EdgeKind, Item, NodeKind, PersonRecord, PersonRef, Relation, Source
from context_graph.domain import keys
from context_graph.sources.base import NormalizedBatch, RawRecords
from context_graph.sources.text import notion_block_text, notion_title, parse_datetime


def page_id(native_id: str) -> str:
    return keys.node_id(Source.NOTION, NodeKind.PAGE, native_id.replace("-", "").lower())


class NotionNormalizer:
    def normalize(self, records: RawRecords) -> NormalizedBatch:
        batch = NormalizedBatch()
        children = _children_by_parent(records.get("blocks", []))
        for page in records.get("pages", []):
            if page.get("archived") or page.get("in_trash"):
                continue
            batch.items.append(self._page(page, children))
        for user in records.get("users", []):
            if user.get("type") != "person":
                continue
            email = ((user.get("person") or {}).get("email") or "").lower()
            batch.people.append(
                PersonRecord(Source.NOTION, native_id=user["id"], names={user.get("name") or ""} - {""}, emails={email} - {""})
            )
        return batch

    @staticmethod
    def _page(record: dict[str, Any], children: dict[str, list[dict[str, Any]]]) -> Item:
        native = record["id"]
        title = notion_title(record.get("properties")) or "Untitled"
        url = record.get("url") or ""
        body = "\n".join(_page_lines(native, children))
        relations = []
        parent = record.get("parent") or {}
        if parent.get("type") == "page_id" and parent.get("page_id"):
            relations.append(Relation(EdgeKind.PART_OF, page_id(parent["page_id"])))
        author = (record.get("created_by") or {}).get("id")
        return Item(
            id=page_id(native),
            source=Source.NOTION,
            kind=NodeKind.PAGE,
            title=title,
            body=body,
            url=url,
            created_at=parse_datetime(record.get("created_time")),
            updated_at=parse_datetime(record.get("last_edited_time")),
            keys={keys.notion_page(native), keys.title(title), *keys.url_keys(url)},
            authors=[PersonRef(Source.NOTION, native_id=author)] if author else [],
            relations=relations,
        )


def _children_by_parent(blocks: Any) -> dict[str, list[dict[str, Any]]]:
    """Blocks grouped by parent id (page or block), in document order."""
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for block in blocks:
        if block.get("archived") or block.get("in_trash"):
            continue
        parent = block.get("parent") or {}
        parent_id = parent.get("page_id") or parent.get("block_id")
        if parent_id:
            grouped[parent_id].append(block)
    for siblings in grouped.values():
        siblings.sort(key=lambda b: ((b.get("parent") or {}).get("sequence_number", 0), b.get("created_time") or ""))
    return grouped


def _page_lines(parent_id: str, children: dict[str, list[dict[str, Any]]], depth: int = 0) -> list[str]:
    lines: list[str] = []
    for block in children.get(parent_id, []):
        if text := notion_block_text(block).strip():
            lines.append(("  " * depth) + text)
        if block.get("has_children") and depth < 8:
            lines.extend(_page_lines(block["id"], children, depth + 1))
    return lines
