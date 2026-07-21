"""Configuration & state for the Local Agent.

Everything is stored under a base directory (default ~/local_agent_data)
so the agent is fully portable and self-contained.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_BASE = Path(os.environ.get("LOCAL_AGENT_HOME", Path.home() / "local_agent_data"))


@dataclass
class Config:
    base_dir: Path = DEFAULT_BASE
    # LLM backend: "ollama" (default, free, local) or "mock" (no model needed for tests)
    llm_backend: str = field(default_factory=lambda: os.environ.get("LOCAL_AGENT_LLM", "ollama"))
    model: str = field(default_factory=lambda: os.environ.get("LOCAL_AGENT_MODEL", "llama3.1:8b"))
    ollama_host: str = field(default_factory=lambda: os.environ.get("OLLAMA_HOST", "http://localhost:11434"))
    # Cap on tool-call iterations per user turn (safety, not a session limit)
    max_iterations: int = 40
    max_tool_output_chars: int = 12000

    def __post_init__(self):
        self.base_dir = Path(self.base_dir)

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

    def ensure_dirs(self) -> None:
        for d in (self.base_dir, self.skills_dir, self.projects_dir, self.outputs_dir):
            d.mkdir(parents=True, exist_ok=True)


def load_config() -> Config:
    cfg = Config()
    cfg.ensure_dirs()
    return cfg
