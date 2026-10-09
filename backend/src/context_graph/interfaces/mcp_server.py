"""MCP server (stdio) so agents like Claude Code and Codex can query the graph."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from mcp.server.fastmcp import FastMCP

from context_graph.bootstrap import App

MAX_BODY_CHARS = 6000

INSTRUCTIONS = """A personal context graph of the user's work tools: GitHub (issues, PRs, commits, code),
Linear, Jira, Notion, Slack and Gmail, linked across tools (issue keys, URLs, titles, file paths,
function names) with one node per person, plus topics and decisions extracted from text.

How to use it:
1. Start with `retrieve_context` for a question: the best matches plus what each links to.
2. Use `get_node` for full text and every link of one node; `neighbors` to walk further.
3. Use `find_path` to see how two things are connected, `recent_activity` for what changed.
Node ids look like `linear:issue:ENG-5`, `github:pull_request:owner/repo#2`, `slack:message:C123:1700000000.1`.
The graph is refreshed on a schedule; before acting on an item's current state, confirm it in the tool itself
(`graph_stats` shows when the graph was last built)."""


def build_server(app: App) -> FastMCP:
    server = FastMCP("context-graph", instructions=INSTRUCTIONS)
    query = app.query

    @server.tool()
    def retrieve_context(question: str, limit: int = 6) -> dict[str, Any]:
        """Best-matching nodes for a question, each with a one-line summary of what it links to."""
        return query.context(question, limit=min(limit, 15))

    @server.tool()
    def search(query_text: str, kinds: list[str] | None = None, sources: list[str] | None = None, limit: int = 10) -> list[dict[str, Any]]:
        """Keyword search. kinds: issue, pull_request, commit, comment, message, page, email, email_thread,
        channel, project, repository, file, symbol, person, topic, decision. sources: github, linear, jira,
        notion, slack, gmail, code, derived."""
        return [asdict(c) for c in query.search(query_text, kinds=kinds or (), sources=sources or (), limit=min(limit, 50))]

    @server.tool()
    def get_node(node_id: str) -> dict[str, Any]:
        """Full text, properties and every link of one node."""
        detail = query.node(node_id)
        if detail is None:
            return {"error": f"No node {node_id}"}
        data = detail.to_dict()
        body = data["node"]["body"]
        if len(body) > MAX_BODY_CHARS:
            data["node"]["body"] = body[:MAX_BODY_CHARS] + "…"
        return data

    @server.tool()
    def neighbors(node_id: str, depth: int = 1, edge_kinds: list[str] | None = None, limit: int = 60) -> dict[str, Any]:
        """Nodes within 1-3 hops. edge_kinds: authored, assigned_to, part_of, reply_to, references, fixes,
        changes, contains, calls, imports, mentions, decides, about."""
        return query.neighbors(node_id, depth=depth, edge_kinds=edge_kinds or (), limit=min(limit, 200)).to_dict()

    @server.tool()
    def find_path(source_id: str, target_id: str) -> dict[str, Any]:
        """The shortest chain of links between two nodes."""
        result = query.path(source_id, target_id)
        return result.to_dict() if result else {"error": "No connection within 5 hops"}

    @server.tool()
    def recent_activity(hours: int = 24, sources: list[str] | None = None, limit: int = 20) -> list[dict[str, Any]]:
        """Items updated in the last N hours."""
        return [asdict(c) for c in query.recent(hours=hours, sources=sources or (), limit=min(limit, 100))]

    @server.tool()
    def graph_stats() -> dict[str, Any]:
        """Node and edge counts, and when the graph was last built."""
        return query.stats()

    return server
