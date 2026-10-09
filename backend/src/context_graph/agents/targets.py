"""Where each agent reads its instructions, and how the guide is added and removed."""

from __future__ import annotations

import json
import re
import shutil
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

GUIDE_FILE = Path(__file__).with_name("guide.md")
SKILL_NAME = "context-graph"
SKILL_DESCRIPTION = (
    "Look up the user's own work context from their local context graph: issues, pull requests, code, "
    "Slack threads, emails, Notion pages, decisions and who did what, across GitHub, Linear, Jira, Notion, "
    "Slack and Gmail. Use it when the user asks about their projects, tickets, discussions, decisions, "
    "or why something changed."
)


def guide() -> str:
    return GUIDE_FILE.read_text(encoding="utf-8")


@dataclass(frozen=True)
class AgentStatus:
    id: str
    label: str
    detected: bool
    """The agent seems to be installed on this computer."""
    installed: bool
    """Our guide is in place."""
    location: str


class AgentTarget(Protocol):
    id: str
    label: str

    def status(self) -> AgentStatus: ...
    def install(self, guide_text: str) -> AgentStatus: ...
    def remove(self) -> AgentStatus: ...


class ClaudeCodeSkill:
    """A personal skill: `~/.claude/skills/context-graph/SKILL.md`, available in every project."""

    id = "claude-code"
    label = "Claude Code"

    def __init__(self, home: Path) -> None:
        self._config_dir = home / ".claude"
        self._skill_dir = self._config_dir / "skills" / SKILL_NAME
        self._file = self._skill_dir / "SKILL.md"

    def status(self) -> AgentStatus:
        detected = self._config_dir.exists() or shutil.which("claude") is not None
        return AgentStatus(self.id, self.label, detected, self._file.exists(), str(self._file))

    def install(self, guide_text: str) -> AgentStatus:
        self._skill_dir.mkdir(parents=True, exist_ok=True)
        # A JSON string is a valid YAML scalar, so the description can safely contain colons.
        frontmatter = f"---\nname: {SKILL_NAME}\ndescription: {json.dumps(SKILL_DESCRIPTION)}\n---\n\n"
        self._file.write_text(frontmatter + guide_text, encoding="utf-8")
        return self.status()

    def remove(self) -> AgentStatus:
        if self._skill_dir.exists():
            shutil.rmtree(self._skill_dir)
        return self.status()


class CodexInstructions:
    """A marked block in `~/.codex/AGENTS.md`, which Codex reads at the start of every session."""

    id = "codex"
    label = "Codex"
    START = "<!-- context-graph:start (added by `cg agent install`, removed by `cg agent remove`) -->"
    END = "<!-- context-graph:end -->"
    _BLOCK = re.compile(r"\n*<!-- context-graph:start.*?<!-- context-graph:end -->\n*", re.DOTALL)

    def __init__(self, home: Path) -> None:
        self._config_dir = home / ".codex"
        self._file = self._config_dir / "AGENTS.md"

    def status(self) -> AgentStatus:
        detected = self._config_dir.exists() or shutil.which("codex") is not None
        installed = self._file.exists() and self.START in self._file.read_text(encoding="utf-8")
        return AgentStatus(self.id, self.label, detected, installed, str(self._file))

    def install(self, guide_text: str) -> AgentStatus:
        others = self._without_block()
        block = f"{self.START}\n{guide_text.strip()}\n{self.END}\n"
        self._config_dir.mkdir(parents=True, exist_ok=True)
        self._file.write_text((others + "\n\n" if others else "") + block, encoding="utf-8")
        return self.status()

    def remove(self) -> AgentStatus:
        if self._file.exists():
            others = self._without_block()
            if others:
                self._file.write_text(others + "\n", encoding="utf-8")
            else:
                self._file.unlink()
        return self.status()

    def _without_block(self) -> str:
        """The file's own content, without our block."""
        if not self._file.exists():
            return ""
        return self._BLOCK.sub("\n\n", self._file.read_text(encoding="utf-8")).strip()


class AgentIntegrations:
    def __init__(self, targets: Sequence[AgentTarget], guide_text: str) -> None:
        self._targets = {t.id: t for t in targets}
        self._guide = guide_text

    def statuses(self) -> list[AgentStatus]:
        return [t.status() for t in self._targets.values()]

    def install(self, agent_id: str) -> AgentStatus:
        return self._target(agent_id).install(self._guide)

    def remove(self, agent_id: str) -> AgentStatus:
        return self._target(agent_id).remove()

    def _target(self, agent_id: str) -> AgentTarget:
        try:
            return self._targets[agent_id]
        except KeyError:
            raise KeyError(f"Unknown agent {agent_id!r}; choose from {', '.join(self._targets)}") from None


def default_integrations(home: Path | None = None) -> AgentIntegrations:
    home = home or Path.home()
    return AgentIntegrations([ClaudeCodeSkill(home), CodexInstructions(home)], guide())
