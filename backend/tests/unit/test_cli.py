"""The `cg` commands as an agent uses them, against a temporary data folder."""

import json

import pytest
from typer.testing import CliRunner

from context_graph.config import AppPaths
from context_graph.domain import Edge, EdgeKind, Graph, Node, NodeKind, Source
from context_graph.graph.store import SQLiteGraphStore
from context_graph.interfaces.cli import app as cli

run = CliRunner().invoke


@pytest.fixture
def home(tmp_path, monkeypatch):
    """A data folder and a home folder of our own, so nothing real is touched."""
    root, user_home = tmp_path / "data-home", tmp_path / "home"
    user_home.mkdir()
    monkeypatch.setenv("CONTEXT_GRAPH_HOME", str(root))
    monkeypatch.setenv("HOME", str(user_home))
    monkeypatch.setattr("context_graph.agents.targets.shutil.which", lambda name: None)
    return root, user_home


@pytest.fixture
def graph(home):
    root, _ = home
    g = Graph()
    g.add_node(Node(id="linear:issue:ENG-5", kind=NodeKind.ISSUE, source=Source.LINEAR, title="Duplicate charges on retry",
                    body="Customers are charged twice when a payment times out.", url="https://linear.app/x/issue/ENG-5",
                    props={"ref": "ENG-5"}))
    g.add_node(Node(id="jira:issue:DEMO-1", kind=NodeKind.ISSUE, source=Source.JIRA, title="Customer reports duplicate charges",
                    props={"ref": "DEMO-1"}))
    g.add_edge(Edge("linear:issue:ENG-5", "jira:issue:DEMO-1", EdgeKind.REFERENCES, 1.0, {"evidence": "Reported in DEMO-1"}))
    paths = AppPaths(root)
    paths.ensure()
    SQLiteGraphStore(paths.graph_db).replace(g, {"built_at": "2026-10-09T10:00:00+00:00"})
    return g


def test_ask_on_an_empty_graph_says_how_to_fix_it(home):
    result = run(cli, ["ask", "anything"])
    assert result.exit_code == 1 and "cg setup" in result.output


def test_ask_returns_matches_with_ids_and_links(graph):
    result = run(cli, ["ask", "why are customers charged twice"])
    assert result.exit_code == 0, result.output
    assert "1. ENG-5 Duplicate charges on retry" in result.output
    assert "id:  linear:issue:ENG-5" in result.output
    assert "→ references issue DEMO-1 Customer reports duplicate charges [jira:issue:DEMO-1]" in result.output
    as_json = json.loads(run(cli, ["ask", "duplicate charges", "--json"]).output)
    assert as_json["results"][0]["links"] and "synced_at" in as_json


def test_show_search_and_path_print_ids_the_other_commands_accept(graph):
    shown = run(cli, ["show", "linear:issue:ENG-5"]).output
    assert "Links (1):" in shown and "[jira:issue:DEMO-1]" in shown and "“Reported in DEMO-1”" in shown
    assert run(cli, ["show", "nope"]).exit_code == 1
    found = json.loads(run(cli, ["search", "duplicate", "--kind", "issue", "--json"]).output)
    assert {c["id"] for c in found} == {"linear:issue:ENG-5", "jira:issue:DEMO-1"}
    path = run(cli, ["path", "jira:issue:DEMO-1", "linear:issue:ENG-5"]).output
    assert "↑ references (points back to the item above)" in path


def test_status_lists_tools_and_agents(home):
    output = run(cli, ["status"]).output
    assert "Tools" in output and "GitHub" in output and "needs setup" in output
    assert "not found on this computer" in output and "The graph is empty" in output


def test_agent_install_and_remove(home):
    _, user_home = home
    assert run(cli, ["agent", "install"]).exit_code == 1  # no agent found yet

    (user_home / ".claude").mkdir()
    result = run(cli, ["agent", "install"])
    assert result.exit_code == 0 and "nothing is synced yet" in result.output
    assert (user_home / ".claude/skills/context-graph/SKILL.md").exists()

    assert "skill removed" in run(cli, ["agent", "remove"]).output
    assert not (user_home / ".claude/skills/context-graph").exists()
