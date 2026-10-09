"""Contract: the config each SourceDefinition builds must satisfy its connector's own JSON schema.

Uses the connectors' published specs (downloaded once by PyAirbyte). Skipped when unavailable.
"""

from __future__ import annotations

import pytest

from context_graph.config import AppOptions, AppPaths, Settings
from context_graph.ingest.airbyte_runner import configure_airbyte_environment
from context_graph.sources.registry import default_registry

pytestmark = pytest.mark.contract

FAKE_ENV = {
    "GITHUB_TOKEN": "github_pat_x",
    "LINEAR_API_KEY": "lin_api_x",
    "JIRA_DOMAIN": "acme.atlassian.net",
    "JIRA_EMAIL": "dev@acme.io",
    "JIRA_API_TOKEN": "x",
    "NOTION_TOKEN": "ntn_x",
    "SLACK_BOT_TOKEN": "xoxb-x",
    "GMAIL_CLIENT_ID": "id",
    "GMAIL_CLIENT_SECRET": "secret",
    "GMAIL_REFRESH_TOKEN": "refresh",
}


@pytest.fixture(scope="module")
def settings(tmp_path_factory) -> Settings:
    options = AppOptions.model_validate({"sources": {"github": {"repos": ["acme/pay"]}, "jira": {"projects": ["DEMO"]}}})
    return Settings(paths=AppPaths(tmp_path_factory.mktemp("root")), options=options, env=FAKE_ENV)


@pytest.mark.parametrize("definition", default_registry().all(), ids=lambda d: d.id.value)
def test_config_matches_connector_spec(definition, settings):
    configure_airbyte_environment(settings.paths.airbyte_dir)
    jsonschema = pytest.importorskip("jsonschema")
    ab = pytest.importorskip("airbyte")
    try:
        spec = ab.get_source(definition.airbyte_name, install_if_missing=True).config_spec
    except Exception as exc:  # offline or registry unavailable
        pytest.skip(f"spec unavailable: {exc}")
    for plan in definition.read_plans(settings):
        jsonschema.validate(plan.config, spec)
