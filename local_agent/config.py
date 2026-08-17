"""Configuration & state for the Local Agent.

Everything is stored under a base directory (default ~/local_agent_data)
so the agent is fully portable and self-contained.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_BASE = Path(os.environ.get("LOCAL_AGENT_HOME", Path.home() / "local_agent_data"))


def _env_flag(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class Config:
    base_dir: Path = DEFAULT_BASE
    # LLM backend: "ollama" (default, free, local) or "mock" (no model needed for tests)
    llm_backend: str = field(default_factory=lambda: os.environ.get("LOCAL_AGENT_LLM", "ollama"))
    model: str = field(default_factory=lambda: os.environ.get("LOCAL_AGENT_MODEL", "llama3.1:8b"))
    ollama_host: str = field(default_factory=lambda: os.environ.get("OLLAMA_HOST", "http://localhost:11434"))
    allow_execution: bool = field(default_factory=lambda: _env_flag("LOCAL_AGENT_ALLOW_EXECUTION"))
    # Cap on tool-call iterations per user turn (safety, not a session limit)
    max_iterations: int = 40
    max_tool_output_chars: int = 12000

    def __post_init__(self):
        self.base_dir = Path(self.base_dir).expanduser().resolve()

    @property
    def db_path(self) -> Path:
        return self.base_dir / "memory.db"

    @property
    def skills_dir(self) -> Path:
        return self.base_dir / "skills"

    @property
    def projects_dir(self) -> Path:
        return self.base_dir / "projects"

    @property
    def outputs_dir(self) -> Path:
        return self.base_dir / "outputs"

    @property
    def workspace_dir(self) -> Path:
        return self.base_dir / "workspace"

    def workspace_path(self, path: str | Path) -> Path:
        """Resolve a user path inside the managed workspace.

        Absolute paths and traversal outside the workspace are rejected. This
        keeps model-generated file operations away from unrelated user files.
        """
        candidate = Path(path).expanduser()
        if candidate.is_absolute():
            raise ValueError("absolute paths are not allowed; use a workspace-relative path")
        resolved = (self.workspace_dir / candidate).resolve()
        if resolved != self.workspace_dir and self.workspace_dir not in resolved.parents:
            raise ValueError("path escapes the managed workspace")
        return resolved

    def ensure_dirs(self) -> None:
        for d in (self.base_dir, self.skills_dir, self.projects_dir, self.outputs_dir, self.workspace_dir):
            d.mkdir(parents=True, exist_ok=True)


def load_config() -> Config:
    cfg = Config()
    cfg.ensure_dirs()
    return cfg
