from __future__ import annotations

import json
from pathlib import Path

import pytest

from context_graph.bootstrap import App
from context_graph.config import AppPaths, SettingsRepository


@pytest.fixture
def project_root(tmp_path: Path) -> Path:
    """A throwaway project folder with a minimal .env and settings.json."""
    (tmp_path / ".env").write_text("LINEAR_API_KEY=lin_api_secretvalue1234\nJIRA_DOMAIN=acme.atlassian.net\n")
    (tmp_path / "settings.json").write_text(
        json.dumps({"sources": {"github": {"repos": ["acme/payments"]}, "jira": {"projects": ["DEMO"]}}})
    )
    return tmp_path


@pytest.fixture
def settings_repo(project_root: Path) -> SettingsRepository:
    paths = AppPaths(project_root)
    paths.ensure()
    return SettingsRepository(paths)


@pytest.fixture
def app(project_root: Path) -> App:
    return App(project_root)
