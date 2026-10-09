"""One snapshot of the whole app: connected tools, last sync, graph size, background sync and agents.

`cg status` prints it for people and agents; the web app shows the same facts on its own screens.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

from context_graph.agents import AgentStatus

if TYPE_CHECKING:
    from context_graph.bootstrap import App

ToolState = Literal["ready", "needs_setup", "off"]


@dataclass(frozen=True)
class ToolOverview:
    id: str
    label: str
    state: ToolState
    last_pull: dict[str, Any] = field(default_factory=dict)
    """The latest pull result from the sync status: `pull`, `finished_at`, `items`, `message`, ..."""


@dataclass(frozen=True)
class Overview:
    home: str
    sync: dict[str, Any]
    """`state`, `step`, `last_success_at`, `error` of the latest sync."""
    graph: dict[str, Any]
    """`nodes`, `edges`, `built_at`."""
    background_sync: dict[str, Any]
    """`on` and `interval_minutes`."""
    tools: list[ToolOverview]
    agents: list[AgentStatus]

    @property
    def is_empty(self) -> bool:
        return not self.graph["nodes"]


def collect(app: App) -> Overview:
    settings = app.settings()
    status = app.status.read()
    runs = status.get("sources", {})
    stats = app.store.stats()
    schedule = app.scheduler.status()

    def tool_state(definition) -> ToolState:
        if not definition.is_enabled(settings):
            return "off"
        return "ready" if definition.is_configured(settings) else "needs_setup"

    return Overview(
        home=str(app.root),
        sync={k: status.get(k) for k in ("state", "step", "last_success_at", "error")},
        graph={"nodes": stats["nodes"], "edges": stats["edges"], "built_at": app.store.meta().get("built_at")},
        background_sync={"on": schedule.installed, "interval_minutes": schedule.interval_minutes},
        tools=[ToolOverview(d.id.value, d.label, tool_state(d), runs.get(d.id.value, {})) for d in app.registry.all()],
        agents=app.agents.statuses(),
    )
