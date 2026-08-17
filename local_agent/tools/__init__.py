"""Tool registry and the agent's tool set.

A Tool is a plain function with metadata. Tools can call back into the agent
context (memory, skills, projects) because they receive the agent instance.
Each tool returns a JSON-serializable result (string or dict) that is fed back
to the model as an observation.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any


class Tool:
    def __init__(self, name: str, description: str, fn: Callable, args: dict):
        self.name = name
        self.description = description
        self.fn = fn
        self.args = args  # {"arg": "description"}

    def spec(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "args": self.args,
        }

    def run(self, **kwargs) -> Any:
        return self.fn(**kwargs)


class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, Tool] = {}

    def register(self, name: str, description: str, args: dict, fn: Callable) -> None:
        self._tools[name] = Tool(name, description, fn, args)

    def decorator(self, name: str, description: str, args: dict):
        def deco(fn: Callable):
            self.register(name, description, args, fn)
            return fn
        return deco

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def specs(self) -> list[dict]:
        return [t.spec() for t in self._tools.values()]

    def names(self) -> list[str]:
        return list(self._tools)
