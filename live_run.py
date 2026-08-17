#!/usr/bin/env python3
"""Real live run: drives the agent with a local Ollama model.

Usage:
    ollama pull llama3.1:8b
    python live_run.py "your task here"
"""
from __future__ import annotations

import os
import sys

from local_agent.agent import Agent
from local_agent.config import load_config


def main() -> None:
    # Use the real local Ollama backend. Environment values still take precedence.
    os.environ.setdefault("LOCAL_AGENT_LLM", "ollama")
    os.environ.setdefault("LOCAL_AGENT_MODEL", "llama3.1:8b")
    cfg = load_config()
    agent = Agent(cfg)
    print(f"Backend: {cfg.llm_backend} | Model: {cfg.model} | Ollama reachable: {agent.llm.available()}")
    print("=" * 60)

    task = (
        sys.argv[1]
        if len(sys.argv) > 1
        else "Research local AI agent best practices and create a project named agent_research."
    )
    print("USER:", task)
    print("-" * 60)

    reply = agent.ask(task)
    print("\nAGENT:\n", reply)
    print("=" * 60)
    print("Memory:", agent.memory.all_kv())
    print("Projects:", agent.projects.list_projects())


if __name__ == "__main__":
    main()
