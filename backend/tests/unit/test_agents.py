import yaml

from context_graph.agents import ClaudeCodeSkill, CodexInstructions, default_integrations, guide
from context_graph.agents.targets import SKILL_DESCRIPTION


def test_claude_code_gets_a_personal_skill_that_can_be_removed(tmp_path):
    (tmp_path / ".claude").mkdir()
    skill = ClaudeCodeSkill(tmp_path)
    assert skill.status().detected and not skill.status().installed

    status = skill.install(guide())
    text = (tmp_path / ".claude/skills/context-graph/SKILL.md").read_text()
    header = yaml.safe_load(text.split("---")[1])  # what Claude Code reads to decide when to use the skill
    assert status.installed and header == {"name": "context-graph", "description": SKILL_DESCRIPTION}
    assert "cg ask" in text and "cg show" in text

    assert not skill.remove().installed
    assert not (tmp_path / ".claude/skills/context-graph").exists() and (tmp_path / ".claude").exists()


def test_codex_block_keeps_the_rest_of_agents_md(tmp_path):
    agents_md = tmp_path / ".codex/AGENTS.md"
    agents_md.parent.mkdir()
    agents_md.write_text("# My rules\nAlways write tests.\n")
    codex = CodexInstructions(tmp_path)

    codex.install(guide())
    codex.install(guide())  # installing again replaces the block instead of adding a second one
    text = agents_md.read_text()
    assert text.startswith("# My rules\nAlways write tests.") and text.count(CodexInstructions.START) == 1
    assert codex.status().installed

    codex.remove()
    assert agents_md.read_text() == "# My rules\nAlways write tests.\n"


def test_codex_file_created_only_for_the_guide_is_removed_with_it(tmp_path):
    codex = CodexInstructions(tmp_path)
    codex.install(guide())
    assert (tmp_path / ".codex/AGENTS.md").exists()
    codex.remove()
    assert not (tmp_path / ".codex/AGENTS.md").exists()


def test_integrations_report_every_agent_and_reject_unknown_ones(tmp_path):
    integrations = default_integrations(tmp_path)
    assert [s.id for s in integrations.statuses()] == ["claude-code", "codex"]
    assert integrations.install("codex").installed
    try:
        integrations.install("cursor")
    except KeyError as exc:
        assert "claude-code, codex" in str(exc)
    else:
        raise AssertionError("unknown agent accepted")
