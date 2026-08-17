#!/usr/bin/env python3
"""Offline smoke test for a fresh Local Agent installation."""
from __future__ import annotations

import tempfile
from pathlib import Path

from local_agent.agent import Agent
from local_agent.config import Config


def main() -> None:
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp_dir:
        cfg = Config(base_dir=Path(temp_dir) / "data", llm_backend="mock")
        cfg.ensure_dirs()
        agent = Agent(cfg)
        try:
            checks = []
            agent.run_tool("remember", key="demo", value="ready")
            checks.append(("persistent memory", agent.memory.get("demo") == "ready"))
            agent.run_tool("write_file", path="demo/note.txt", content="hello workspace")
            checks.append(("workspace files", "hello workspace" in agent.run_tool("read_file", path="demo/note.txt")))
            agent.run_tool("project_create", name="portfolio_demo")
            agent.run_tool("project_plan", name="portfolio_demo", tasks=["plan", "build", "test"])
            checks.append(("project tracking", "build" in agent.run_tool("project_status", name="portfolio_demo")))
            agent.run_tool("save_skill", name="greeting", description="Demo skill", content="Say hello clearly")
            checks.append(("reusable skills", "greeting" in agent.run_tool("list_skills")))
            checks.append(("safe execution default", "disabled by default" in agent.run_tool("run_code", code="print(42)")))
            for name, passed in checks:
                print(f"[{'PASS' if passed else 'FAIL'}] {name}")
            if not all(passed for _, passed in checks):
                raise SystemExit(1)
            print(f"\nAll {len(checks)} offline checks passed.")
        finally:
            agent.memory.close()


if __name__ == "__main__":
    main()
