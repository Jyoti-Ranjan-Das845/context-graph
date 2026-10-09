"""Read and update a `.env` file without disturbing comments or other keys."""

from __future__ import annotations

import re
from pathlib import Path

from dotenv import dotenv_values


class EnvFile:
    def __init__(self, path: Path) -> None:
        self._path = path

    @property
    def path(self) -> Path:
        return self._path

    def read(self) -> dict[str, str]:
        if not self._path.exists():
            return {}
        return {k: (v or "") for k, v in dotenv_values(self._path).items()}

    def set(self, key: str, value: str) -> None:
        if not re.fullmatch(r"[A-Z][A-Z0-9_]*", key):
            raise ValueError(f"Invalid env key: {key!r}")
        if "\n" in value:
            raise ValueError("Env values must be a single line")
        text = self._path.read_text() if self._path.exists() else ""
        line = f"{key}={value}"
        pattern = re.compile(rf"^{re.escape(key)}=.*$", re.MULTILINE)
        if pattern.search(text):
            text = pattern.sub(lambda _: line, text)
        else:
            text = text.rstrip("\n") + ("\n" if text else "") + line + "\n"
        self._path.write_text(text)
        self._path.chmod(0o600)


def mask(value: str | None) -> str | None:
    """Show only the last 4 characters of a secret."""
    if not value:
        return None
    return f"••••{value[-4:]}" if len(value) > 8 else "••••"
