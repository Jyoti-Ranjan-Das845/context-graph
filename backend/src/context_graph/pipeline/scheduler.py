"""Runs `cg sync` on an interval with macOS launchd (a per-user LaunchAgent)."""

from __future__ import annotations

import os
import plistlib
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

LABEL = "com.contextgraph.sync"


@dataclass(frozen=True)
class ScheduleStatus:
    installed: bool
    interval_minutes: int | None
    plist: str


class LaunchdScheduler:
    def __init__(self, home: Path, logs_dir: Path, agents_dir: Path | None = None) -> None:
        self._home = home
        self._logs = logs_dir
        self._plist = (agents_dir or Path.home() / "Library" / "LaunchAgents") / f"{LABEL}.plist"

    def install(self, interval_minutes: int) -> ScheduleStatus:
        cg = Path(sys.executable).with_name("cg")
        path_entries = [str(cg.parent), "/usr/local/bin", "/opt/homebrew/bin", "/usr/bin", "/bin"]
        if claude := shutil.which("claude"):
            path_entries.insert(0, str(Path(claude).parent))
        self._logs.mkdir(parents=True, exist_ok=True)
        self._plist.parent.mkdir(parents=True, exist_ok=True)
        definition = {
            "Label": LABEL,
            "ProgramArguments": [str(cg), "sync", "--trigger", "schedule"],
            "StartInterval": interval_minutes * 60,
            "RunAtLoad": False,
            "EnvironmentVariables": {"CONTEXT_GRAPH_HOME": str(self._home), "PATH": ":".join(path_entries)},
            "StandardOutPath": str(self._logs / "scheduled-sync.log"),
            "StandardErrorPath": str(self._logs / "scheduled-sync.log"),
        }
        self.uninstall()
        self._plist.write_bytes(plistlib.dumps(definition))
        subprocess.run(["launchctl", "bootstrap", f"gui/{os.getuid()}", str(self._plist)], check=True)
        return self.status()

    def uninstall(self) -> None:
        if self._plist.exists():
            subprocess.run(["launchctl", "bootout", f"gui/{os.getuid()}", str(self._plist)], check=False, capture_output=True)
            self._plist.unlink()

    def status(self) -> ScheduleStatus:
        if not self._plist.exists():
            return ScheduleStatus(False, None, str(self._plist))
        definition = plistlib.loads(self._plist.read_bytes())
        return ScheduleStatus(True, int(definition.get("StartInterval", 0)) // 60, str(self._plist))
