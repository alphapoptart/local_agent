#!/usr/bin/env python3
"""Real live run: drives the agent with a local Ollama model.

Usage:
    ollama pull llama3.1:8b
    python live_run.py "your task here"
"""
from __future__ import annotations
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

# Use the real local Ollama backend. Override model via env if you like.
os.environ.setdefault("LOCAL_AGENT_LLM", "ollama")
os.environ.setdefault("LOCAL_AGENT_MODEL", "llama3.1:8b")

from local_agent.agent import Agent
from local_agent.config import load_config


def main() -> None:
    cfg = load_config()
    agent = Agent(cfg)
    print(f"Backend: {cfg.llm_backend} | Model: {cfg.model} | Ollama reachable: {agent.llm.available()}")
    print("=" * 60)

    task = (sys.argv[1] if len(sys.argv) > 1 else
           "Search the web for 'best practices for local AI agents', then remember that "
           "the user's name is Sean (key user_name), and create a project called "
           "'agent_research' with a task to summarize findings.")
    print("USER:", task)
    print("-" * 60)

    reply = agent.ask(task)
    print("\nAGENT:\n", reply)
    print("=" * 60)
    print("Memory:", agent.memory.all_kv())
    print("Projects:", agent.projects.list_projects())


if __name__ == "__main__":
    main()
