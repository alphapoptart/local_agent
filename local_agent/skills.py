"""Skills — reusable, agent-authored procedures.

A skill is a folder under <base>/skills/<name>/ containing:
  - SKILL.md  : frontmatter (name, description, trigger) + instructions
  - (optional) scripts/ : helper scripts the skill can call

The agent can SAVE new skills from experience and LOAD them on demand, so it
gets smarter over time and across sessions. No cloud, no limits.
"""
from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import Any

_FRONT = re.compile(r"^---\n(.*?)\n---\n?(.*)$", re.DOTALL)


class SkillManager:
    def __init__(self, skills_dir: Path):
        self.dir = Path(skills_dir)
        self.dir.mkdir(parents=True, exist_ok=True)

    def list_skills(self) -> list[dict]:
        out = []
        for p in sorted(self.dir.iterdir()):
            if p.is_dir():
                md = p / "SKILL.md"
                if md.exists():
                    out.append(self._parse(md))
        return out

    def get(self, name: str) -> dict | None:
        md = self.dir / name / "SKILL.md"
        if not md.exists():
            return None
        return self._parse(md)

    def _parse(self, md: Path) -> dict:
        text = md.read_text(encoding="utf-8")
        m = _FRONT.match(text)
        meta: dict[str, Any] = {"name": md.parent.name}
        body = text
        if m:
            import yaml  # type: ignore
            try:
                meta.update(yaml.safe_load(m.group(1)) or {})
            except Exception:
                pass
            body = m.group(2)
        meta["name"] = meta.get("name") or md.parent.name
        meta["body"] = body.strip()
        return meta

    def save(self, name: str, description: str, content: str, trigger: str = "") -> dict:
        """Persist a skill. `content` may be markdown instructions and/or code."""
        folder = self.dir / name
        folder.mkdir(parents=True, exist_ok=True)
        front = f"---\nname: {name}\ndescription: {description}\n"
        if trigger:
            front += f"trigger: {trigger}\n"
        front += "---\n\n"
        (folder / "SKILL.md").write_text(front + content.strip() + "\n", encoding="utf-8")
        return self._parse(folder / "SKILL.md")

    def delete(self, name: str) -> bool:
        folder = self.dir / name
        if folder.exists():
            shutil.rmtree(folder)
            return True
        return False

    def render_for_prompt(self) -> str:
        skills = self.list_skills()
        if not skills:
            return "No skills saved yet."
        lines = []
        for s in skills:
            lines.append(f"- {s['name']}: {s.get('description','')}")
        return "Available skills:\n" + "\n".join(lines)

