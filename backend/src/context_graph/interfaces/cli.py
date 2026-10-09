"""`cg`: the command line. Thin layer over `App`; no business logic lives here.

For you: setup, ui, sync, status, check, agent install / remove.
For agents (and you): ask, search, show, neighbors, path, recent.
Every query command prints readable text, or JSON with --json.
"""

from __future__ import annotations

import json
import threading
import time
import urllib.request
import webbrowser
from dataclasses import asdict
from typing import Annotated, Optional

import typer

from context_graph.bootstrap import App, configure_logging, create_app
from context_graph.interfaces import text
from context_graph.overview import collect
from context_graph.pipeline.status import SyncAlreadyRunning
from context_graph.pipeline.sync import SyncRequest

app = typer.Typer(help="Personal context graph: your work tools in one local graph.", no_args_is_help=True, add_completion=False)
agent_app = typer.Typer(help="Teach Claude Code and Codex to use `cg`.", no_args_is_help=True)
app.add_typer(agent_app, name="agent")

JsonOption = Annotated[bool, typer.Option("--json", help="Print JSON.")]
PortOption = Annotated[int, typer.Option(help="Port for the web app.")]
LOCAL_HOST = "127.0.0.1"
"""The web app never listens beyond this machine."""
DEFAULT_PORT = 8765


def _app(verbose: bool = False) -> App:
    application = create_app()
    configure_logging(application, verbose)
    return application


def _print_json(data: object) -> None:
    typer.echo(json.dumps(data, indent=2, default=str))


def _require_graph(application: App) -> None:
    if not application.store.stats()["nodes"]:
        typer.echo("The graph is empty: nothing has been synced yet. Run `cg setup` to connect your tools, then sync.")
        raise typer.Exit(1)


# ---------------------------------------------------------------- web app


@app.command()
def setup(port: PortOption = DEFAULT_PORT, browser: Annotated[bool, typer.Option(help="Open the browser.")] = True) -> None:
    """Open the Setup page: connect tools, choose what to sync, add the agent skill."""
    _run_web_app("setup", port, browser)


@app.command()
def ui(port: PortOption = DEFAULT_PORT, browser: Annotated[bool, typer.Option(help="Open the browser.")] = True) -> None:
    """Open the web app on the graph."""
    _run_web_app("graph", port, browser)


def _run_web_app(view: str, port: int, open_browser: bool) -> None:
    import uvicorn

    from context_graph.interfaces.api import WEB_DIR, create_api

    url = f"http://{LOCAL_HOST}:{port}/#/{view}"
    if not _port_is_free(LOCAL_HOST, port):
        if not _is_context_graph(port):
            typer.echo(f"Port {port} is used by another program. Choose another: cg {view if view == 'setup' else 'ui'} --port {port + 1}", err=True)
            raise typer.Exit(1)
        typer.echo(f"Context Graph is already running: {url}")
        if open_browser:
            webbrowser.open(url)
        return
    if not (WEB_DIR / "index.html").exists():
        typer.echo("The web app is not built. Run ./install.sh from the project folder.", err=True)
        raise typer.Exit(1)
    application = _app()
    typer.echo(f"Context Graph: {url}\nKeep this window open while you use it; press Ctrl+C to stop.")
    if open_browser:
        threading.Thread(target=_open_when_listening, args=(url, port), daemon=True).start()
    uvicorn.run(create_api(application), host=LOCAL_HOST, port=port, log_level="warning", access_log=False)


def _port_is_free(host: str, port: int) -> bool:
    """True if nothing listens on `host:port`. SO_REUSEADDR matches uvicorn, so a just-closed port counts as free."""
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            probe.bind((host, port))
        except OSError:
            return False
    return True


def _is_context_graph(port: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://{LOCAL_HOST}:{port}/api/stats", timeout=2) as response:
            return "nodes" in json.loads(response.read())
    except (OSError, ValueError):
        return False


def _open_when_listening(url: str, port: int, timeout: float = 15.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline and _port_is_free(LOCAL_HOST, port):
        time.sleep(0.2)
    webbrowser.open(url)


# ---------------------------------------------------------------- sync & status


@app.command()
def sync(
    source: Annotated[list[str], typer.Option("--source", "-s", help="Only pull these tools.")] = [],
    pull: Annotated[bool, typer.Option(help="Pull from the tools. --no-pull rebuilds from local data.")] = True,
    code: Annotated[bool, typer.Option(help="Read repository code.")] = True,
    enrich: Annotated[Optional[bool], typer.Option("--enrich/--no-enrich", help="Override the Setup choice.")] = None,
    trigger: Annotated[str, typer.Option(hidden=True)] = "manual",
    verbose: Annotated[bool, typer.Option("--verbose", "-v")] = False,
) -> None:
    """Pull what changed, rebuild the graph and add topics and decisions for new text."""
    application = _app(verbose)
    request = SyncRequest(trigger=trigger, pull=pull, sources=tuple(source), code=code, enrich=enrich)
    try:
        report = application.pipeline.run(request)
    except SyncAlreadyRunning:
        typer.echo("A sync is already running.")
        raise typer.Exit(2)
    typer.echo(text.render_overview(collect(application)))
    if not report.ok:
        typer.echo(f"\n✗ Sync failed: {report.error}")
        raise typer.Exit(1)
    typer.echo(f"\n✓ Graph ready: {report.nodes} items, {report.edges} links ({report.seconds}s)")


@app.command()
def status(as_json: JsonOption = False) -> None:
    """Connected tools, last sync, graph size, background sync and agents."""
    overview = collect(_app())
    if as_json:
        return _print_json(asdict(overview))
    typer.echo(text.render_overview(overview))


@app.command()
def check(source: Annotated[Optional[str], typer.Argument(help="One tool, e.g. slack.")] = None) -> None:
    """Test the connection to each tool."""
    application = _app()
    settings = application.settings()
    definitions = [application.registry.get(source)] if source else application.registry.all()
    failed = False
    for definition in definitions:
        result = application.runner.check(definition, settings)
        failed |= not result.ok
        typer.echo(f"{'✓' if result.ok else '✗'} {definition.label:7s} {result.message}")
    raise typer.Exit(1 if failed else 0)


# ---------------------------------------------------------------- queries


@app.command()
def ask(question: str, limit: Annotated[int, typer.Option(help="How many items.")] = 6, as_json: JsonOption = False) -> None:
    """Best matches for a question, each with its links. Start here."""
    application = _app()
    _require_graph(application)
    bundle = application.query.context(question, limit=limit)
    synced_at = application.status.read().get("last_success_at") or application.store.meta().get("built_at")
    if as_json:
        return _print_json({**bundle, "synced_at": synced_at})
    typer.echo(text.render_context(bundle, synced_at))


@app.command()
def search(
    query: str,
    kind: Annotated[list[str], typer.Option("--kind", "-k", help="Only this kind, e.g. issue. Repeatable.")] = [],
    source: Annotated[list[str], typer.Option("--source", "-s", help="Only this tool, e.g. slack. Repeatable.")] = [],
    limit: Annotated[int, typer.Option(help="How many items.")] = 15,
    as_json: JsonOption = False,
) -> None:
    """Matching items, without their links."""
    application = _app()
    _require_graph(application)
    cards = application.query.search(query, kinds=kind, sources=source, limit=limit)
    if as_json:
        return _print_json([asdict(c) for c in cards])
    typer.echo(text.render_cards(cards, query))


@app.command()
def show(node_id: Annotated[str, typer.Argument(help="An item id, e.g. linear:issue:ENG-5.")], as_json: JsonOption = False) -> None:
    """One item in full, with all its links and the evidence for each."""
    detail = _app().query.node(node_id)
    if detail is None:
        typer.echo(f"No item with id {node_id}. Ids are printed by `cg ask` and `cg search`.")
        raise typer.Exit(1)
    if as_json:
        return _print_json(detail.to_dict())
    typer.echo(text.render_node(detail))


@app.command()
def neighbors(
    node_id: str,
    depth: Annotated[int, typer.Option(min=1, max=3, help="How many links away.")] = 1,
    as_json: JsonOption = False,
) -> None:
    """The items around an item."""
    sub = _app().query.neighbors(node_id, depth=depth)
    if as_json:
        return _print_json(sub.to_dict())
    typer.echo(text.render_neighbors(sub, node_id, depth))


@app.command()
def path(from_id: str, to_id: str, as_json: JsonOption = False) -> None:
    """The shortest chain of links between two items."""
    sub = _app().query.path(from_id, to_id)
    if sub is None:
        typer.echo("No connection found within 5 links.")
        raise typer.Exit(1)
    if as_json:
        return _print_json(sub.to_dict())
    typer.echo(text.render_path(sub))


@app.command()
def recent(
    hours: Annotated[Optional[int], typer.Option(help="Only items updated in the last N hours.")] = None,
    source: Annotated[list[str], typer.Option("--source", "-s", help="Only this tool. Repeatable.")] = [],
    limit: Annotated[int, typer.Option(help="How many items.")] = 20,
    as_json: JsonOption = False,
) -> None:
    """The most recently updated items."""
    cards = _app().query.recent(hours=hours, sources=source, limit=limit)
    if as_json:
        return _print_json([asdict(c) for c in cards])
    typer.echo(text.render_cards(cards, "recent activity") if cards else "Nothing updated in that window.")


# ---------------------------------------------------------------- agents


@agent_app.command("install")
def agent_install(
    agent: Annotated[list[str], typer.Option("--agent", "-a", help="claude-code or codex. Default: every agent found.")] = [],
) -> None:
    """Add the context-graph skill to Claude Code and Codex, so they know how to use `cg`."""
    application = _app()
    overview = collect(application)
    if overview.is_empty:
        typer.echo("Note: nothing is synced yet. The skill works as soon as you connect tools in `cg setup` and sync.\n")
    else:
        ready = [t.label for t in overview.tools if t.state == "ready"]
        missing = [t.label for t in overview.tools if t.state == "needs_setup"]
        typer.echo(f"Connected: {', '.join(ready) or 'none'}" + (f". Not set up: {', '.join(missing)}." if missing else ".") + "\n")
    targets = agent or [a.id for a in overview.agents if a.detected]
    if not targets:
        typer.echo("Found neither Claude Code nor Codex on this computer. Install one, or choose with --agent.")
        raise typer.Exit(1)
    for agent_id in targets:
        try:
            result = application.agents.install(agent_id)
        except KeyError as exc:
            typer.echo(str(exc.args[0]), err=True)
            raise typer.Exit(1)
        typer.echo(f"✓ {result.label}: skill added at {result.location}")


@agent_app.command("remove")
def agent_remove(
    agent: Annotated[list[str], typer.Option("--agent", "-a", help="claude-code or codex. Default: every agent that has it.")] = [],
) -> None:
    """Remove the skill again."""
    application = _app()
    targets = agent or [a.id for a in application.agents.statuses() if a.installed]
    if not targets:
        typer.echo("The skill is not added to any agent.")
        return
    for agent_id in targets:
        result = application.agents.remove(agent_id)
        typer.echo(f"✓ {result.label}: skill removed")


# ---------------------------------------------------------------- MCP


@app.command()
def mcp() -> None:
    """Run the MCP server on stdio, for agents that prefer MCP over the command line."""
    from context_graph.interfaces.mcp_server import build_server

    build_server(_app()).run()


if __name__ == "__main__":
    app()
