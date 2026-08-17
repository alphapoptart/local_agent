"""LLM backends.

Two backends are supported:

1. ``ollama`` — free, fully local. Requires Ollama installed and a model pulled.
   Install:  https://ollama.com  (then ``ollama pull llama3.1:8b``)
2. ``mock``  — deterministic fake model used for testing when no model is
   available. It parses tool-call requests from a scripted instruction and
   echoes, so the whole framework can be exercised without a GPU.

The interface is intentionally tiny so you can plug in *any* backend
(LocalAI, LM Studio OpenAI-compatible server, vLLM, llama.cpp server, etc.)
by implementing ``chat()``.
"""
from __future__ import annotations

import json
import re
from typing import Any

import requests

from .config import Config

SYSTEM_PROMPT = """You are Local Agent — a friendly, capable assistant running privately on this \
user's own computer. You talk like a helpful person: natural, concise, and warm. \
You can actually DO things through tools, not just talk about them.

How to use tools (keep it easy and natural):
- When you need to do something (search, generate an image, save a file, remember a \
fact, start a project, etc.), include a tool call in your reply. You can write a short \
friendly sentence AND a tool call together — that's great.
- Tool call format — a small JSON block. Either style is fine:
    {"tool": "name", "args": {"arg": "value"}}
  or the shorter:
    {"name": {"arg": "value"}}
- You may call several tools in one reply if that's efficient.
- After a tool reports back, just keep going: call another tool, or reply to the user \
normally when you're done.
- If a tool fails, don't panic — read the note, then try a different approach or ask the \
user a quick clarifying question. You don't need to mention internal errors verbatim.

Just be yourself: chat naturally, and reach for a tool whenever it helps get the user's \
task done. No special markers or rigid formatting required."""


class LLM:
    """Model-agnostic chat interface."""

    def __init__(self, cfg: Config):
        self.cfg = cfg

    def chat(self, messages: list[dict], tools: list[dict] | None = None) -> str:
        """Return the model's next message (may be a tool-call JSON or text)."""
        raise NotImplementedError

    def available(self) -> bool:
        return True


class OllamaLLM(LLM):
    def chat(self, messages: list[dict], tools: list[dict] | None = None) -> str:
        payload: dict[str, Any] = {
            "model": self.cfg.model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": 0.5},
        }
        try:
            r = requests.post(f"{self.cfg.ollama_host}/api/chat", json=payload, timeout=300)
            r.raise_for_status()
            return r.json()["message"]["content"]
        except requests.exceptions.ConnectionError:
            raise RuntimeError(
                "Could not reach Ollama at %s. Install Ollama (https://ollama.com) "
                "and run `ollama pull %s`, or set LOCAL_AGENT_LLM=mock for a test run."
                % (self.cfg.ollama_host, self.cfg.model)
            )

    def available(self) -> bool:
        try:
            r = requests.get(f"{self.cfg.ollama_host}/api/tags", timeout=5)
            return r.status_code == 200
        except Exception:
            return False


class MockLLM(LLM):
    """Deterministic backend so the framework is testable with zero dependencies.

    It inspects the user's latest request and emits a matching tool-call JSON
    (or a final echo). It remembers what it already did this conversation, so it
    stops after acting once — just like a real conversational model would. This
    drives a realistic multi-step tool loop without a model, so the framework is
    exercisable in CI / offline.
    """

    def __init__(self, cfg: Config):
        self.cfg = cfg

    def chat(self, messages: list[dict], tools: list[dict] | None = None) -> str:
        user_last = ""
        for m in reversed(messages):
            if m.get("role") == "user" and not str(m.get("content", "")).startswith("tool_result:"):
                user_last = m["content"]
                break

        low = user_last.lower()
        current_turn_start = max(
            i
            for i, message in enumerate(messages)
            if message.get("role") == "user"
            and not str(message.get("content", "")).startswith("tool_result:")
        )

        def did_tool(name: str) -> bool:
            return any(
                m.get("role") == "assistant" and f'"{name}"' in str(m.get("content", ""))
                for m in messages[current_turn_start + 1 :]
            )

        web_done = any("web_search" in str(m.get("content", "")) for m in messages
                       if m.get("role") == "assistant")

        # Web search: call once, then answer in prose.
        if "search" in low:
            if not web_done:
                return json.dumps({"tool": "web_search", "args": {"query": "open source local AI agent framework"}})
            return "Here are the web search results I found for your query. (mock agent demo)"

        # Remember: once per conversation.
        if "remember" in low:
            if did_tool("remember"):
                return "Saved that to local memory."
            natural = re.search(r"remember\s+(?:that\s+)?(?:my\s+)?(.+?)\s+is\s+(.+?)[.!]?\s*$", user_last, re.I)
            if natural:
                key = re.sub(r"[^a-z0-9]+", "_", natural.group(1).lower()).strip("_")
                value = natural.group(2).strip().rstrip(".!")
                return json.dumps({"tool": "remember", "args": {"key": key, "value": value}})
            if "with key" in low:
                val_part, key_part = user_last.split("with key", 1)
                val = val_part.replace("remember", "", 1).strip().split()[-1] if val_part.strip() else "Sean"
                key = key_part.strip().strip(".,")
                return json.dumps({"tool": "remember", "args": {"key": key, "value": val}})
            if " as " in low:
                key_part, val_part = user_last.split(" as ", 1)
                key = key_part.replace("remember", "", 1).strip().split()[-1]
                val = val_part.strip().strip(".,")
                return json.dumps({"tool": "remember", "args": {"key": key, "value": val}})
            return "Try a phrase like: remember my preferred language is Python."

        # Skill: once.
        if "skill" in low and not did_tool("save_skill"):
            return json.dumps({
                "tool": "save_skill",
                "args": {
                    "name": "hello_world",
                    "description": "Prints a friendly hello.",
                    "content": "def run():\n    return 'Hello from a saved skill!'",
                },
            })
        if "skill" in low and did_tool("save_skill"):
            return "Saved the reusable skill locally."

        # Project: once.
        if "project" in low and not did_tool("project_create"):
            project_match = re.search(r"project\s+(?:called|named)\s+([a-z0-9_-]+)", user_last, re.I)
            project_name = project_match.group(1) if project_match else "demo_project"
            return json.dumps({
                "tool": "project_create",
                "args": {"name": project_name},
            })
        if "project" in low and did_tool("project_create"):
            return "Created the project workspace."

        # Default: answer like a person would.
        return f"Sure! I noted your request: \"{user_last}\". (mock agent — no model loaded)"


def build_llm(cfg: Config) -> LLM:
    if cfg.llm_backend == "mock":
        return MockLLM(cfg)
    return OllamaLLM(cfg)
