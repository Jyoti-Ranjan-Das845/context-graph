import json
import stat

import pytest
from pydantic import ValidationError

from context_graph.config import EnvFile, mask
from context_graph.sources.github.definition import GitHubOptions
from context_graph.sources.registry import UnknownSourceError, default_registry


def test_settings_load_secrets_and_source_options(settings_repo):
    settings = settings_repo.load()
    assert settings.secret("LINEAR_API_KEY") == "lin_api_secretvalue1234"
    assert settings.secret("MISSING") is None
    assert settings.source_options("github") == {"repos": ["acme/payments"]}
    assert settings.options.sync.interval_minutes == 30


def test_env_file_updates_one_key_and_keeps_the_rest(tmp_path):
    env = tmp_path / ".env"
    env.write_text("# comment\nA=1\nB=2\n")
    EnvFile(env).set("B", "3")
    EnvFile(env).set("C", "4")
    assert env.read_text() == "# comment\nA=1\nB=3\nC=4\n"
    assert stat.S_IMODE(env.stat().st_mode) == 0o600
    with pytest.raises(ValueError):
        EnvFile(env).set("bad key", "x")


def test_mask_shows_only_last_four():
    assert mask("lin_api_secretvalue1234") == "••••1234"
    assert mask(None) is None


def test_update_source_options_persists(settings_repo, project_root):
    settings_repo.update_source_options("slack", {"join_channels": False})
    saved = json.loads((project_root / "settings.json").read_text())
    assert saved["sources"]["slack"] == {"join_channels": False}
    assert saved["sources"]["github"] == {"repos": ["acme/payments"]}


def test_github_repo_format_is_validated():
    with pytest.raises(ValidationError):
        GitHubOptions(repos=["not-a-repo"])


def test_registry_lists_six_tools_and_rejects_unknown():
    registry = default_registry()
    assert [d.id.value for d in registry.all()] == ["github", "linear", "jira", "notion", "slack", "gmail"]
    with pytest.raises(UnknownSourceError):
        registry.get("trello")


def test_configured_state_follows_credentials(settings_repo):
    settings = settings_repo.load()
    registry = default_registry()
    assert registry.get("linear").is_configured(settings)
    jira = registry.get("jira")
    assert jira.missing_credentials(settings) == ["JIRA_EMAIL", "JIRA_API_TOKEN"]
    config = jira.airbyte_config(settings)
    assert config["domain"] == "acme.atlassian.net" and config["projects"] == ["DEMO"]


def test_linear_reads_reference_streams_without_a_start_date(settings_repo):
    plans = default_registry().get("linear").read_plans(settings_repo.load())
    assert [p.streams for p in plans] == [("issues", "comments"), ("users", "projects")]
    assert plans[1].config["start_date"].startswith("2000-")


def test_data_lives_in_the_home_folder_unless_overridden(monkeypatch, tmp_path):
    from context_graph.config import discover_root

    monkeypatch.delenv("CONTEXT_GRAPH_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    assert discover_root() == tmp_path / ".context-graph"
    monkeypatch.setenv("CONTEXT_GRAPH_HOME", str(tmp_path / "elsewhere"))
    assert discover_root() == (tmp_path / "elsewhere").resolve()


def test_first_use_fixes_the_start_date_30_days_back(tmp_path):
    import json
    from datetime import datetime, timedelta, timezone

    from context_graph.config import AppPaths, SettingsRepository

    repo = SettingsRepository(AppPaths(tmp_path))
    first = repo.load().options.sync.start_date
    expected = (datetime.now(timezone.utc) - timedelta(days=30)).date().isoformat()
    assert first == f"{expected}T00:00:00Z"
    assert json.loads((tmp_path / "settings.json").read_text())["sync"]["start_date"] == first  # saved, so it never moves
