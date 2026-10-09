"""LLM port and the Claude Code CLI adapter."""

from __future__ import annotations

import json
import shutil
import subprocess
from typing import Any, Protocol


class LLMError(RuntimeError):
    pass


class LLMClient(Protocol):
    def complete_json(self, *, system: str, prompt: str, schema: dict[str, Any]) -> dict[str, Any]:
        """Return an object that matches `schema`."""
        ...


class ClaudeCodeClient:
    """Runs `claude -p` non-interactively: no tools, no MCP servers, no saved session.

    Uses the person's Claude Code subscription, so no API key is needed.
    """

    def __init__(self, model: str | None = None, timeout_seconds: int = 240, executable: str = "claude") -> None:
        self._model = model
        self._timeout = timeout_seconds
        self._executable = executable

    def available(self) -> bool:
        return shutil.which(self._executable) is not None

    def complete_json(self, *, system: str, prompt: str, schema: dict[str, Any]) -> dict[str, Any]:
        command = [
            self._executable,
            "-p",
            "--output-format", "json",
            "--tools", "",
            "--strict-mcp-config",
            "--no-session-persistence",
            "--json-schema", json.dumps(schema),
            "--system-prompt", system,
        ]
        if self._model:
            command += ["--model", self._model]
        try:
            completed = subprocess.run(
                command, input=prompt, capture_output=True, text=True, timeout=self._timeout, check=False
            )
        except FileNotFoundError as exc:
            raise LLMError("Claude Code CLI not found on PATH") from exc
        except subprocess.TimeoutExpired as exc:
            raise LLMError(f"Claude Code did not answer within {self._timeout}s") from exc
        if completed.returncode != 0:
            raise LLMError(f"Claude Code exited with {completed.returncode}: {completed.stderr.strip()[:200]}")
        try:
            envelope = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            raise LLMError("Claude Code returned non-JSON output") from exc
        if envelope.get("is_error"):
            raise LLMError(f"Claude Code error: {str(envelope.get('result'))[:200]}")
        output = envelope.get("structured_output")
        if output is None:
            try:
                output = json.loads(envelope.get("result") or "")
            except json.JSONDecodeError as exc:
                raise LLMError("Claude Code returned no structured output") from exc
        return output
