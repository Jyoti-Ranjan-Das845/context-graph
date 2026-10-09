"""Plain-text views of query results, written for people and agents reading a terminal.

Every view prints item ids exactly as the other commands expect them, so an agent can pass
them straight to `cg show`, `cg neighbors` or `cg path`.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from context_graph.overview import Overview
from context_graph.query.service import NodeCard, NodeDetail, Subgraph

BODY_LIMIT = 6000


def time_ago(iso: str | None) -> str:
    if not iso:
        return "never"
    then = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    if then.tzinfo is None:
        then = then.replace(tzinfo=timezone.utc)
    seconds = max(0.0, (datetime.now(timezone.utc) - then).total_seconds())
    if seconds < 60:
        return "just now"
    for size, unit in ((86400, "d"), (3600, "h"), (60, "min")):
        if seconds >= size:
            return f"{round(seconds / size)} {unit} ago"
    return "just now"


def _title(ref: str | None, title: str) -> str:
    return f"{ref} {title}" if ref and not title.startswith(ref) else title


def _card(card: NodeCard, number: int) -> list[str]:
    lines = [
        f"{number}. {_title(card.ref, card.title)}",
        f"   {card.source} · {card.kind}" + (f" · updated {time_ago(card.updated_at)}" if card.updated_at else ""),
        f"   id:  {card.id}",
    ]
    if card.url:
        lines.append(f"   url: {card.url}")
    if card.snippet:
        lines.append(f"   {card.snippet}")
    return lines


def _plural(count: int, noun: str) -> str:
    return f"{count} {noun}{'' if count == 1 else 's'}"


def render_cards(cards: list[NodeCard], query: str) -> str:
    if not cards:
        return f'No matches for "{query}". Try other words, an issue key, a file or function name, or --kind / --source.'
    out: list[str] = []
    for number, card in enumerate(cards, start=1):
        out += [*_card(card, number), ""]
    return "\n".join(out).rstrip()


def render_context(bundle: dict[str, Any], synced_at: str | None) -> str:
    results = bundle["results"]
    header = f'"{bundle["question"]}" · {_plural(len(results), "result")} · graph synced {time_ago(synced_at)}'
    if not results:
        return (
            f"{header}\n\nNo matches. Try the words the people involved would use, an issue key (ENG-5), "
            'a file or function name, or `cg search "<words>" --kind <kind>`.'
        )
    out = [header, ""]
    for number, result in enumerate(results, start=1):
        card = NodeCard(**{k: result[k] for k in NodeCard.__dataclass_fields__})
        out += _card(card, number)
        if result["links"]:
            out.append("   links:")
            out += [f"     {link}" for link in result["links"]]
        out.append("")
    out.append("Next: `cg show <id>` for an item's full text and all its links; `cg neighbors <id>` for what is around it.")
    return "\n".join(out)


def render_node(detail: NodeDetail) -> str:
    node = detail.node
    ref = node["props"].get("ref")
    dates = " · ".join(
        f"{label} {time_ago(node[key])}" for label, key in (("created", "created_at"), ("updated", "updated_at")) if node[key]
    )
    out = [_title(str(ref) if ref else None, node["title"]), f"{node['source']} · {node['kind']}" + (f" · {dates}" if dates else "")]
    out.append(f"id:  {node['id']}")
    if node["url"]:
        out.append(f"url: {node['url']}")
    body = node["body"] or ""
    if body:
        out += ["", body[:BODY_LIMIT]]
        if len(body) > BODY_LIMIT:
            out.append(f"[… {len(body) - BODY_LIMIT:,} more characters; use --json for the full text]")
    fields = {k: v for k, v in node["props"].items() if k != "ref" and v not in (None, "", [], {})}
    if fields:
        out += ["", "Fields: " + "; ".join(f"{k}: {', '.join(map(str, v)) if isinstance(v, list) else v}" for k, v in fields.items())]
    out += ["", f"Links ({len(detail.neighbors)}):"]
    for neighbor in detail.neighbors:
        arrow = "→" if neighbor.direction == "out" else "←"
        confidence = f"  {round(neighbor.edge.confidence * 100)}%" if neighbor.edge.confidence < 1 else ""
        other = neighbor.node
        out.append(f"  {arrow} {neighbor.edge.kind:12s} {other.kind:12s} {_title(other.ref, other.title)}  [{other.id}]{confidence}")
        if neighbor.edge.evidence:
            out.append(f"      “{' '.join(neighbor.edge.evidence.split())}”")
    return "\n".join(out)


def render_neighbors(sub: Subgraph, start: str, depth: int) -> str:
    if not sub.nodes:
        return f"No item with id {start}."
    titles = {n.id: _title(n.ref, n.title) for n in sub.nodes}
    out = [f"{len(sub.nodes) - 1} items within {depth} link{'s' if depth > 1 else ''} of {titles.get(start, start)}:", ""]
    out += [f"  {n.source:7s} {n.kind:12s} {titles[n.id]}  [{n.id}]" for n in sub.nodes if n.id != start]
    out += ["", f"Links ({len(sub.edges)}):"]
    out += [f"  {titles.get(e.src, e.src)} —{e.kind}→ {titles.get(e.dst, e.dst)}" for e in sub.edges]
    return "\n".join(out)


def render_path(sub: Subgraph) -> str:
    out: list[str] = []
    for i, node in enumerate(sub.nodes):
        out.append(f"{_title(node.ref, node.title)}  [{node.id}]")
        if i < len(sub.edges):
            edge = sub.edges[i]
            out.append(f"   ↓ {edge.kind}" if edge.src == node.id else f"   ↑ {edge.kind} (points back to the item above)")
    return "\n".join(out)


def render_overview(o: Overview) -> str:
    sync = o.sync
    if sync["state"] == "running":
        last = f"running now ({sync['step']})"
    elif sync["state"] == "failed":
        last = f"failed: {sync['error']}"
    elif sync["state"] in (None, "never_run"):
        last = "never"
    else:
        last = time_ago(sync["last_success_at"])
    background = f"every {o.background_sync['interval_minutes']} min" if o.background_sync["on"] else "off"
    out = [
        f"Context Graph · data in {o.home}",
        f"Last sync: {last} · {o.graph['nodes']} items, {o.graph['edges']} links · background sync: {background}",
        "",
        "Tools",
    ]
    for tool in o.tools:
        state = {"ready": "ready", "needs_setup": "needs setup", "off": "off"}[tool.state]
        out.append(f"  {tool.label:8s} {state:12s} {_last_pull(tool.last_pull) if tool.state == 'ready' else ''}".rstrip())
    out += ["", "Agents"]
    for agent in o.agents:
        if agent.installed:
            out.append(f"  {agent.label:12s} skill added  {agent.location}")
        else:
            out.append(f"  {agent.label:12s} {'not added (cg agent install)' if agent.detected else 'not found on this computer'}")
    if o.is_empty:
        out += ["", "The graph is empty. Run `cg setup` to connect your tools, then sync."]
    return "\n".join(out)


def _last_pull(run: dict[str, Any]) -> str:
    if run.get("pull") == "error":
        return f"last pull failed: {run.get('message') or 'unknown error'}"
    if run.get("normalize_error"):
        return f"could not read pulled data: {run['normalize_error']}"
    if run.get("pull") == "ok":
        items = f" · {_plural(run['items'], 'item')}" if run.get("items") is not None else ""
        return f"pulled {time_ago(run.get('finished_at'))}{items}"
    return "not pulled yet"
