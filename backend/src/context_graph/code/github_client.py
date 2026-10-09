"""A minimal GitHub REST client for the code module (repo snapshots and PR file lists)."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

API = "https://api.github.com"


class GitHubError(RuntimeError):
    pass


class GitHubClient:
    def __init__(self, token: str, timeout: float = 60.0) -> None:
        self._token = token
        self._timeout = timeout

    def get_json(self, path: str, params: dict[str, Any] | None = None) -> Any:
        query = ("?" + "&".join(f"{k}={v}" for k, v in params.items())) if params else ""
        return json.loads(self._get(f"{API}{path}{query}", accept="application/vnd.github+json"))

    def get_paginated(self, path: str, per_page: int = 100, max_pages: int = 10) -> list[Any]:
        items: list[Any] = []
        for page in range(1, max_pages + 1):
            batch = self.get_json(path, {"per_page": per_page, "page": page})
            items.extend(batch)
            if len(batch) < per_page:
                break
        return items

    def download(self, path: str) -> bytes:
        return self._get(f"{API}{path}", accept="application/vnd.github+json")

    def _get(self, url: str, accept: str) -> bytes:
        request = urllib.request.Request(
            url,
            headers={
                "Authorization": f"Bearer {self._token}",
                "Accept": accept,
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "context-graph",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            raise GitHubError(f"GitHub {exc.code} for {url.removeprefix(API)}") from None
