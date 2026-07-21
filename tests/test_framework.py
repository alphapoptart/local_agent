#!/usr/bin/env python3
"""Permanent test suite for the Local Agent framework.

Run:  pip install pytest && pytest -q

All tests use the keyless `mock` backend (set via env) so they need no model,
no network, and no GPU. A live Ollama run is covered separately by live_run.py.
"""
from __future__ import annotations

import os
import sys
import tempfile

import pytest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

os.environ["LOCAL_AGENT_LLM"] = "mock"

from local_agent.agent import Agent
from local_agent.config import Config


@pytest.fixture
def agent():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        cfg = Config(base_dir=os.path.join(tmp, "data"))
        a = Agent(cfg)
        yield a
        a.memory.close()


# ---------------- parser robustness ----------------
def test_canonical_schema():
    out = Agent._parse_tool_calls('{"tool": "remember", "args": {"key": "x", "value": 1}}')
    assert out == [{"tool": "remember", "args": {"key": "x", "value": 1}}]


def test_shorthand_schema():
    out = Agent._parse_tool_calls('{"project_create": {"name": "p"}}')
    assert out == [{"tool": "project_create", "args": {"name": "p"}}]


def test_multiple_calls_per_reply():
    out = Agent._parse_tool_calls(
        '{"remember": {"key": "a", "value": 1}} {"project_create": {"name": "p"}}'
    )
    assert {c["tool"] for c in out} == {"remember", "project_create"}


def test_sloppy_windows_path_escapes():
    out = Agent._parse_tool_calls(r'{"write_file": {"path": "c:\Users\x.md", "content": "hi\n"}}')
    assert out and out[0]["tool"] == "write_file"
    assert out[0]["args"]["path"].endswith("x.md")


def test_no_tool_call_returns_empty():
    assert Agent._parse_tool_calls("just some plain text") == []


# ---------------- tool behaviours (mock backend) ----------------
def test_run_code(agent):
    out = agent.run_tool("run_code", code="print(6*7)")
    assert "42" in out


def test_file_roundtrip(agent, tmp_path):
    p = str(tmp_path / "note.txt")
    agent.run_tool("write_file", path=p, content="hello persistence")
    assert "hello persistence" in agent.run_tool("read_file", path=p)


def test_image_generate_registered(agent):
    assert agent.registry.get("image_generate") is not None


def test_remember_and_recall(agent):
    agent.run_tool("remember", key="user_name", value="Sean")
    assert "Sean" in agent.run_tool("recall", key="user_name")


def test_project_lifecycle(agent):
    agent.run_tool("project_create", name="demo")
    agent.run_tool("project_plan", name="demo", tasks=["a", "b", "c"])
    status = agent.run_tool("project_status", name="demo")
    assert "a" in status and "demo" in status


# ---------------- mock end-to-end multi-step ----------------
def test_web_search_loop(agent):
    reply = agent.ask("please search the web for me")
    assert "web search results" in reply.lower() or "duckduckgo" in reply.lower()


def test_memory_persists(agent):
    agent.ask("remember the user name Sean with key user_name")
    cfg = agent.cfg
    a2 = Agent(cfg)
    try:
        assert a2.memory.get("user_name") == "Sean"
    finally:
        a2.memory.close()


def test_save_skill_roundtrip(agent):
    agent.ask("save a skill called hello_world that prints a friendly hello")
    assert any(s["name"] == "hello_world" for s in agent.skills.list_skills())


def test_activity_callback_fires(agent):
    events = []
    agent.ask("remember the user name Sean with key user_name",
              on_activity=lambda k, p: events.append(k))
    assert "tool" in events and "result" in events
