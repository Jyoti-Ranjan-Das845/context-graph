"""Local REST API for the web UI. Listens on 127.0.0.1 only; secrets are never returned in full."""

from __future__ import annotations

import threading
import urllib.parse
from dataclasses import asdict
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ValidationError

from context_graph.bootstrap import App
from context_graph.config import AppOptions, mask
from context_graph.domain import Source
from context_graph.pipeline.status import SyncAlreadyRunning
from context_graph.pipeline.sync import SyncRequest
from context_graph.sources.base import SourceDefinition
from context_graph.sources.slack.definition import manifest as slack_manifest


class CredentialsUpdate(BaseModel):
    values: dict[str, str]


class OptionsUpdate(BaseModel):
    values: dict[str, Any]


class SyncStart(BaseModel):
    pull: bool = True
    enrich: bool | None = None
    sources: list[str] = []


class ScheduleUpdate(BaseModel):
    enabled: bool
    interval_minutes: int | None = None


class SettingsUpdate(BaseModel):
    sync: dict[str, Any] | None = None
    enrichment: dict[str, Any] | None = None
    identity: dict[str, Any] | None = None


class AgentUpdate(BaseModel):
    installed: bool


WEB_DIR = Path(__file__).resolve().parents[1] / "web"
"""The built web app (`npm run build` in `ui/` writes it here), shipped inside the package."""


class _BackgroundSync:
    """Runs one sync at a time on a worker thread.

    `start` returns once the run has begun (its status says "running"), so a client that
    polls the status right after never sees the previous state. It raises `SyncAlreadyRunning`
    when a sync is already going, here or in another process (the CLI, the schedule).
    """

    START_TIMEOUT_SECONDS = 10

    def __init__(self, app: App) -> None:
        self._app = app
        self._thread: threading.Thread | None = None

    def start(self, request: SyncRequest) -> None:
        if self._thread and self._thread.is_alive():
            raise SyncAlreadyRunning("A sync is already running")
        began = threading.Event()
        refused: list[SyncAlreadyRunning] = []

        def work() -> None:
            try:
                self._app.pipeline.run(request, on_started=began.set)
            except SyncAlreadyRunning as exc:
                refused.append(exc)
                began.set()

        self._thread = threading.Thread(target=work, daemon=True)
        self._thread.start()
        began.wait(self.START_TIMEOUT_SECONDS)
        if refused:
            raise refused[0]


def create_api(app: App, web_dir: Path = WEB_DIR) -> FastAPI:
    api = FastAPI(title="Context Graph", version="0.1.0")
    api.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "testserver"])
    background = _BackgroundSync(app)

    def definition(source_id: str) -> SourceDefinition:
        try:
            return app.registry.get(source_id)
        except KeyError:
            raise HTTPException(404, f"Unknown source {source_id}") from None

    def describe(d: SourceDefinition) -> dict[str, Any]:
        settings = app.settings()
        pull_status = app.status.read().get("sources", {}).get(d.id.value, {})
        return {
            "id": d.id.value,
            "label": d.label,
            "configured": d.is_configured(settings),
            "enabled": d.is_enabled(settings),
            "missing": d.missing_credentials(settings),
            "setup_steps": list(d.setup_steps),
            "credentials": [
                {
                    **asdict(f),
                    "is_set": bool(settings.secret(f.env_key)),
                    "display": mask(settings.secret(f.env_key)) if f.secret else settings.secret(f.env_key),
                }
                for f in d.credentials
            ],
            "options": d.options(settings).model_dump(),
            "options_schema": d.options_model.model_json_schema(),
            "last_pull": pull_status,
        }

    # ------------------------------------------------------------ sources & settings

    @api.get("/api/sources")
    def list_sources() -> list[dict[str, Any]]:
        return [describe(d) for d in app.registry.all()]

    @api.post("/api/sources/{source_id}/check")
    def check_source(source_id: str) -> dict[str, Any]:
        result = app.runner.check(definition(source_id), app.settings())
        return {"ok": result.ok, "message": result.message}

    @api.put("/api/sources/{source_id}/credentials")
    def update_credentials(source_id: str, body: CredentialsUpdate) -> dict[str, Any]:
        d = definition(source_id)
        allowed = {f.env_key for f in d.credentials if not f.managed_by}
        unknown = set(body.values) - allowed
        if unknown:
            raise HTTPException(400, f"Not a credential of {d.label}: {', '.join(sorted(unknown))}")
        for key, value in body.values.items():
            if value.strip():
                app.settings_repo.set_secret(key, value.strip())
        return describe(d)

    @api.put("/api/sources/{source_id}/options")
    def update_options(source_id: str, body: OptionsUpdate) -> dict[str, Any]:
        d = definition(source_id)
        try:
            validated = d.options_model.model_validate(body.values)
        except ValidationError as exc:
            raise HTTPException(422, exc.errors(include_url=False, include_context=False)) from None
        app.settings_repo.update_source_options(d.id.value, validated.model_dump())
        return describe(d)

    @api.post("/api/sources/gmail/signin")
    def gmail_signin() -> dict[str, Any]:
        from context_graph.auth.google import GoogleSignInError, sign_in_gmail

        try:
            sign_in_gmail(app.settings_repo)
        except GoogleSignInError as exc:
            raise HTTPException(400, str(exc)) from None
        return describe(definition(Source.GMAIL.value))

    @api.get("/api/sources/slack/create-app-url")
    def slack_create_app_url() -> dict[str, str]:
        import json

        encoded = urllib.parse.quote(json.dumps(slack_manifest(), separators=(",", ":")))
        return {"url": f"https://api.slack.com/apps?new_app=1&manifest_json={encoded}"}

    @api.get("/api/settings")
    def get_settings() -> dict[str, Any]:
        options = app.settings().options
        return {"sync": options.sync.model_dump(), "enrichment": options.enrichment.model_dump(), "identity": options.identity.model_dump()}

    @api.put("/api/settings")
    def update_settings(body: SettingsUpdate) -> dict[str, Any]:
        current = app.settings().options.model_dump()
        for section in ("sync", "enrichment", "identity"):
            if (patch := getattr(body, section)) is not None:
                current[section] = {**current[section], **patch}
        try:
            options = AppOptions.model_validate(current)
        except ValidationError as exc:
            raise HTTPException(422, exc.errors(include_url=False, include_context=False)) from None
        app.settings_repo.save_options(options)
        # An installed background sync follows the saved interval.
        schedule = app.scheduler.status()
        if schedule.installed and schedule.interval_minutes != options.sync.interval_minutes:
            app.scheduler.install(options.sync.interval_minutes)
        return get_settings()

    # ------------------------------------------------------------ sync & schedule

    @api.post("/api/sync", status_code=202)
    def start_sync(body: SyncStart) -> dict[str, Any]:
        try:
            background.start(SyncRequest(trigger="ui", pull=body.pull, enrich=body.enrich, sources=tuple(body.sources)))
        except SyncAlreadyRunning:
            raise HTTPException(409, "A sync is already running") from None
        return {"started": True}

    @api.get("/api/sync/status")
    def sync_status() -> dict[str, Any]:
        return app.status.read()

    @api.get("/api/schedule")
    def get_schedule() -> dict[str, Any]:
        return asdict(app.scheduler.status())

    @api.put("/api/schedule")
    def update_schedule(body: ScheduleUpdate) -> dict[str, Any]:
        if body.enabled:
            minutes = body.interval_minutes or app.settings().options.sync.interval_minutes
            return asdict(app.scheduler.install(minutes))
        app.scheduler.uninstall()
        return asdict(app.scheduler.status())

    # ------------------------------------------------------------ agents

    @api.get("/api/agents")
    def list_agents() -> list[dict[str, Any]]:
        return [asdict(s) for s in app.agents.statuses()]

    @api.put("/api/agents/{agent_id}")
    def update_agent(agent_id: str, body: AgentUpdate) -> dict[str, Any]:
        try:
            result = app.agents.install(agent_id) if body.installed else app.agents.remove(agent_id)
        except KeyError as exc:
            raise HTTPException(404, str(exc.args[0])) from None
        return asdict(result)

    # ------------------------------------------------------------ graph queries

    @api.get("/api/graph")
    def graph(kinds: list[str] = Query(default=[]), sources: list[str] = Query(default=[]), limit: int = 3000) -> dict[str, Any]:
        return app.query.view(kinds=kinds, sources=sources, limit=limit).to_dict()

    @api.get("/api/search")
    def search(q: str, kinds: list[str] = Query(default=[]), sources: list[str] = Query(default=[]), limit: int = 20) -> list[dict[str, Any]]:
        return [asdict(c) for c in app.query.search(q, kinds=kinds, sources=sources, limit=limit)]

    @api.get("/api/nodes/{node_id:path}/neighbors")
    def neighbors(node_id: str, depth: int = 1) -> dict[str, Any]:
        return app.query.neighbors(node_id, depth=depth).to_dict()

    @api.get("/api/nodes/{node_id:path}")
    def node(node_id: str) -> dict[str, Any]:
        detail = app.query.node(node_id)
        if detail is None:
            raise HTTPException(404, "Node not found")
        return detail.to_dict()

    @api.get("/api/path")
    def path(src: str, dst: str) -> dict[str, Any]:
        result = app.query.path(src, dst)
        if result is None:
            raise HTTPException(404, "No connection found")
        return result.to_dict()

    @api.get("/api/recent")
    def recent(hours: int | None = None, limit: int = 30) -> list[dict[str, Any]]:
        return [asdict(c) for c in app.query.recent(hours=hours, limit=limit)]

    @api.get("/api/context")
    def context(q: str, limit: int = 6) -> dict[str, Any]:
        return app.query.context(q, limit=limit)

    @api.get("/api/stats")
    def stats() -> dict[str, Any]:
        return app.query.stats()

    # ------------------------------------------------------------ web UI

    if (web_dir / "index.html").exists():
        api.mount("/assets", StaticFiles(directory=web_dir / "assets"), name="assets")

        @api.get("/{full_path:path}", include_in_schema=False)
        def spa(full_path: str) -> FileResponse:
            candidate = web_dir / full_path
            if full_path and candidate.is_file() and web_dir.resolve() in candidate.resolve().parents:
                return FileResponse(candidate)
            return FileResponse(web_dir / "index.html")

    return api
