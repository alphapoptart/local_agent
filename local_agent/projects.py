"""Projects — group larger multi-step tasks into a named workspace.

A project is a folder under <base>/projects/<name>/ that holds its own files,
a manifest (goal, created date, status) and a task list so the agent can track
progress on big jobs (e.g. "build a website", "research a topic").
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


class ProjectManager:
    def __init__(self, projects_dir: Path):
        self.dir = Path(projects_dir)
        self.dir.mkdir(parents=True, exist_ok=True)

    def create(self, name: str, path: str | None = None) -> dict:
        safe_name = "".join(ch for ch in name.strip() if ch.isalnum() or ch in {"-", "_"})
        if not safe_name or safe_name != name.strip():
            raise ValueError("project names may contain only letters, numbers, '-' and '_'")
        if path:
            raise ValueError("custom project paths are disabled; projects stay in managed storage")
        folder = (self.dir / safe_name).resolve()
        if self.dir.resolve() not in folder.parents:
            raise ValueError("project path escapes managed storage")
        folder.mkdir(parents=True, exist_ok=True)
        manifest = {
            "name": name,
            "path": str(folder),
            "created": datetime.now(timezone.utc).isoformat(),
            "status": "active",
            "goal": "",
            "tasks": [],
        }
        self._write_manifest(folder, manifest)
        return manifest

    def get(self, name: str) -> dict | None:
        folder = self.dir / name
        m = folder / "manifest.json"
        if not m.exists():
            return None
        return json.loads(m.read_text(encoding="utf-8"))

    def list_projects(self) -> list[str]:
        return sorted(p.name for p in self.dir.iterdir() if (p / "manifest.json").exists())

    def set_goal(self, name: str, goal: str) -> dict | None:
        man = self._edit(name, lambda m: m.update(goal=goal))
        return man

    def add_task(self, name: str, task: str) -> dict | None:
        def edit(m):
            m.setdefault("tasks", []).append({"task": task, "status": "pending"})
        return self._edit(name, edit)

    def complete_task(self, name: str, idx: int) -> dict | None:
        def edit(m):
            try:
                m["tasks"][idx]["status"] = "done"
            except (IndexError, KeyError):
                pass
        return self._edit(name, edit)

    def _edit(self, name, fn):
        man = self.get(name)
        if man is None:
            return None
        fn(man)
        self._write_manifest(Path(man["path"]), man)
        return man

    def _write_manifest(self, folder: Path, manifest: dict) -> None:
        (folder / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
