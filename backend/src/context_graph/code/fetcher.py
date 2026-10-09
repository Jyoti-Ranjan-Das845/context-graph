"""Keeps a local snapshot of each repo's default branch, and the list of files each PR changes.

Snapshots are re-downloaded only when the branch head moves; PR file lists only when
the PR was updated. State lives in a small JSON file.
"""

from __future__ import annotations

import io
import json
import shutil
import tarfile
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from context_graph.code.github_client import GitHubClient


@dataclass(frozen=True)
class RepoSnapshot:
    full_name: str
    path: Path
    sha: str
    branch: str
    changed: bool


class GitHubCodeFetcher:
    def __init__(self, client: GitHubClient, code_dir: Path, state_file: Path) -> None:
        self._client = client
        self._code_dir = code_dir
        self._state_file = state_file
        self._state: dict[str, Any] = json.loads(state_file.read_text()) if state_file.exists() else {}

    def expand(self, patterns: list[str]) -> list[str]:
        """Resolve `owner/*` into every repo of that owner the token can see."""
        explicit = [p for p in patterns if not p.endswith("/*")]
        owners = {p.split("/", 1)[0].lower() for p in patterns if p.endswith("/*")}
        if owners:
            repos = self._client.get_paginated("/user/repos")
            explicit += [r["full_name"] for r in repos if r["owner"]["login"].lower() in owners]
        return sorted(set(explicit), key=str.lower)

    def snapshot(self, full_name: str) -> RepoSnapshot:
        info = self._client.get_json(f"/repos/{full_name}")
        branch = info["default_branch"]
        sha = self._client.get_json(f"/repos/{full_name}/commits/{branch}")["sha"]
        target = self._code_dir / full_name
        known = self._state.setdefault("repos", {}).get(full_name, {})
        if known.get("sha") == sha and target.exists():
            return RepoSnapshot(full_name, target, sha, branch, changed=False)

        archive = self._client.download(f"/repos/{full_name}/tarball/{sha}")
        self._extract(archive, target)
        self._state["repos"][full_name] = {"sha": sha, "branch": branch}
        self._save()
        return RepoSnapshot(full_name, target, sha, branch, changed=True)

    def pr_files(self, full_name: str, number: int, updated_at: str | None) -> list[str]:
        key = f"{full_name}#{number}"
        cache = self._state.setdefault("pr_files", {})
        if (entry := cache.get(key)) and entry.get("updated_at") == updated_at:
            return entry["files"]
        files = [f["filename"] for f in self._client.get_paginated(f"/repos/{full_name}/pulls/{number}/files")]
        cache[key] = {"updated_at": updated_at, "files": files}
        self._save()
        return files

    def _extract(self, archive: bytes, target: Path) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=target.parent) as tmp:
            with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as tar:
                tar.extractall(tmp, filter="data")
            (top,) = [p for p in Path(tmp).iterdir() if p.is_dir()]
            staged = target.with_name(target.name + ".new")
            shutil.rmtree(staged, ignore_errors=True)
            top.rename(staged)
            shutil.rmtree(target, ignore_errors=True)
            staged.rename(target)

    def _save(self) -> None:
        self._state_file.parent.mkdir(parents=True, exist_ok=True)
        self._state_file.write_text(json.dumps(self._state, indent=2))
