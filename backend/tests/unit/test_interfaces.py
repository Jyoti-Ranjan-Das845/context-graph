import asyncio

import pytest
from fastapi.testclient import TestClient

from context_graph.domain import Graph, Node, NodeKind, Source
from context_graph.interfaces.api import create_api
from context_graph.interfaces.mcp_server import build_server
from context_graph.pipeline.scheduler import ScheduleStatus


class FakeScheduler:
    """Stands in for launchd so tests never install a real LaunchAgent."""

    def __init__(self, minutes: int | None = None) -> None:
        self.minutes = minutes

    def status(self) -> ScheduleStatus:
        return ScheduleStatus(self.minutes is not None, self.minutes, "fake.plist")

    def install(self, interval_minutes: int) -> ScheduleStatus:
        self.minutes = interval_minutes
        return self.status()

    def uninstall(self) -> None:
        self.minutes = None


@pytest.fixture
def client(app):
    graph = Graph()
    graph.add_node(Node(id="linear:issue:ENG-5", kind=NodeKind.ISSUE, source=Source.LINEAR, title="Duplicate charges", body="retry bug", props={"ref": "ENG-5"}))
    app.store.replace(graph, {"built_at": "now"})
    return TestClient(create_api(app))


def test_sources_never_expose_full_secrets(client):
    sources = {s["id"]: s for s in client.get("/api/sources").json()}
    linear = sources["linear"]
    assert linear["configured"] is True
    field = linear["credentials"][0]
    assert field["is_set"] and field["display"] == "••••1234"
    assert "secretvalue" not in client.get("/api/sources").text
    assert sources["jira"]["credentials"][0]["display"] == "acme.atlassian.net"  # non-secret fields are shown


def test_credentials_update_rejects_other_tools_keys(client, app):
    response = client.put("/api/sources/linear/credentials", json={"values": {"GITHUB_TOKEN": "x"}})
    assert response.status_code == 400
    ok = client.put("/api/sources/notion/credentials", json={"values": {"NOTION_TOKEN": "ntn_abcdefgh1234"}})
    assert ok.status_code == 200 and app.settings().secret("NOTION_TOKEN") == "ntn_abcdefgh1234"


def test_options_are_validated(client):
    assert client.put("/api/sources/github/options", json={"values": {"repos": ["bad"]}}).status_code == 422
    good = client.put("/api/sources/github/options", json={"values": {"repos": ["acme/web"], "include_code": False}})
    assert good.json()["options"]["repos"] == ["acme/web"]


def test_settings_are_validated_and_saved(client, app):
    app.scheduler = FakeScheduler()
    assert client.put("/api/settings", json={"sync": {"interval_minutes": 1}}).status_code == 422
    saved = client.put("/api/settings", json={"sync": {"interval_minutes": 45}, "enrichment": {"enabled": False}}).json()
    assert saved["sync"]["interval_minutes"] == 45 and saved["enrichment"]["enabled"] is False
    assert app.scheduler.minutes is None  # saving settings never turns background sync on


def test_installed_schedule_follows_saved_interval(client, app):
    app.scheduler = FakeScheduler(minutes=30)
    client.put("/api/settings", json={"sync": {"interval_minutes": 15}})
    assert app.scheduler.minutes == 15
    assert client.put("/api/schedule", json={"enabled": False}).json()["installed"] is False


def test_graph_queries(client):
    assert client.get("/api/search", params={"q": "ENG-5"}).json()[0]["ref"] == "ENG-5"
    assert client.get("/api/nodes/linear:issue:ENG-5").json()["node"]["title"] == "Duplicate charges"
    assert client.get("/api/nodes/missing").status_code == 404
    assert client.get("/api/graph").json()["nodes"][0]["id"] == "linear:issue:ENG-5"
    assert client.get("/api/stats").json()["nodes"] == 1


def test_untrusted_hosts_are_rejected(client):
    assert client.get("/api/stats", headers={"host": "evil.example"}).status_code == 400


def test_mcp_server_exposes_query_tools(app):
    tools = asyncio.run(build_server(app).list_tools())
    assert {t.name for t in tools} == {
        "retrieve_context", "search", "get_node", "neighbors", "find_path", "recent_activity", "graph_stats",
    }


def test_starting_a_sync_while_another_process_syncs_is_refused(client, app):
    from context_graph.pipeline.status import sync_lock

    with sync_lock(app.paths.state_dir / "sync.lock"):  # e.g. a scheduled sync in another process
        response = client.post("/api/sync", json={"pull": False})
    assert response.status_code == 409


def test_ui_explains_a_port_taken_by_another_program():
    import socket

    from typer.testing import CliRunner

    from context_graph.interfaces.cli import app as cli

    with socket.socket() as other:  # listens but is not Context Graph
        other.bind(("127.0.0.1", 0))
        other.listen()
        port = other.getsockname()[1]
        result = CliRunner().invoke(cli, ["ui", "--port", str(port), "--no-browser"])
    assert result.exit_code == 1
    assert f"Port {port} is used by another program" in result.output


def test_agent_endpoints_add_and_remove_the_skill(client, app, tmp_path):
    from context_graph.agents import default_integrations

    app.agents = default_integrations(tmp_path / "home")
    assert [a["id"] for a in client.get("/api/agents").json()] == ["claude-code", "codex"]
    added = client.put("/api/agents/claude-code", json={"installed": True}).json()
    assert added["installed"] and (tmp_path / "home/.claude/skills/context-graph/SKILL.md").exists()
    assert client.put("/api/agents/claude-code", json={"installed": False}).json()["installed"] is False
    assert client.put("/api/agents/cursor", json={"installed": True}).status_code == 404


def test_the_built_web_app_is_served_for_every_page(app, tmp_path):
    web = tmp_path / "web"
    (web / "assets").mkdir(parents=True)
    (web / "index.html").write_text("<html>app</html>")
    (web / "assets" / "app.js").write_text("console.log(1)")
    web_client = TestClient(create_api(app, web_dir=web))
    assert web_client.get("/").text == "<html>app</html>"
    assert web_client.get("/setup").text == "<html>app</html>"  # client-side routes fall back to the app
    assert web_client.get("/assets/app.js").text == "console.log(1)"
    assert web_client.get("/api/stats").json()["nodes"] == 0
