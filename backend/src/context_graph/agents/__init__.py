"""Teach coding agents (Claude Code, Codex) to query the graph with the `cg` commands.

The guide text lives once, in `guide.md`. Claude Code receives it as a personal skill; Codex
receives it as a marked block in its global `AGENTS.md`, so the rest of that file is never
touched. Each agent is an `AgentTarget`, so supporting another agent means adding one class.
"""

from context_graph.agents.targets import (
    AgentIntegrations,
    AgentStatus,
    AgentTarget,
    ClaudeCodeSkill,
    CodexInstructions,
    default_integrations,
    guide,
)

__all__ = [
    "AgentIntegrations",
    "AgentStatus",
    "AgentTarget",
    "ClaudeCodeSkill",
    "CodexInstructions",
    "default_integrations",
    "guide",
]
