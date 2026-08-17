"""Standard-library test suite for Local Agent.

Run with: python -m unittest discover -s tests -v
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from local_agent.agent import Agent
from local_agent.config import Config


class AgentTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.cfg = Config(base_dir=Path(self.temp_dir.name) / "data", llm_backend="mock")
        self.cfg.ensure_dirs()
        self.agent = Agent(self.cfg)

    def tearDown(self) -> None:
        self.agent.memory.close()
        self.temp_dir.cleanup()

    def test_canonical_tool_schema(self):
        parsed = Agent._parse_tool_calls('{"tool":"remember","args":{"key":"x","value":1}}')
        self.assertEqual(parsed, [{"tool": "remember", "args": {"key": "x", "value": 1}}])

    def test_shorthand_tool_schema(self):
        parsed = Agent._parse_tool_calls('{"project_create":{"name":"demo"}}')
        self.assertEqual(parsed[0]["tool"], "project_create")

    def test_multiple_tool_calls(self):
        parsed = Agent._parse_tool_calls(
            '{"remember":{"key":"a","value":1}} {"project_create":{"name":"demo"}}'
        )
        self.assertEqual({item["tool"] for item in parsed}, {"remember", "project_create"})

    def test_plain_text_is_not_a_tool_call(self):
        self.assertEqual(Agent._parse_tool_calls("ordinary response"), [])

    def test_sloppy_windows_escape_is_repaired(self):
        parsed = Agent._parse_tool_calls(r'{"write_file":{"path":"c:\Users\x.md","content":"hi"}}')
        self.assertTrue(parsed[0]["args"]["path"].endswith("x.md"))

    def test_memory_round_trip(self):
        self.agent.run_tool("remember", key="preferred_editor", value="VS Code")
        self.assertIn("VS Code", self.agent.run_tool("recall", key="preferred_editor"))

    def test_memory_persists_between_instances(self):
        self.agent.run_tool("remember", key="theme", value="dark")
        other = Agent(self.cfg)
        try:
            self.assertEqual(other.memory.get("theme"), "dark")
        finally:
            other.memory.close()

    def test_skill_round_trip(self):
        self.agent.run_tool("save_skill", name="hello", description="demo", content="Say hello")
        self.assertIn("hello", self.agent.run_tool("list_skills"))

    def test_project_lifecycle(self):
        self.agent.run_tool("project_create", name="demo")
        self.agent.run_tool("project_plan", name="demo", tasks=["plan", "build", "test"])
        self.assertIn("build", self.agent.run_tool("project_status", name="demo"))

    def test_project_names_reject_traversal(self):
        with self.assertRaises(ValueError):
            self.agent.projects.create("../outside")

    def test_workspace_file_round_trip(self):
        self.agent.run_tool("write_file", path="notes/demo.txt", content="portfolio ready")
        self.assertIn("portfolio ready", self.agent.run_tool("read_file", path="notes/demo.txt"))

    def test_workspace_rejects_traversal(self):
        with self.assertRaises(ValueError):
            self.cfg.workspace_path("../../private.txt")

    def test_workspace_rejects_absolute_paths(self):
        with self.assertRaises(ValueError):
            self.cfg.workspace_path("/tmp/private.txt")

    def test_execution_is_disabled_by_default(self):
        self.assertIn("disabled by default", self.agent.run_tool("run_code", code="print(42)"))

    def test_execution_can_be_enabled_explicitly(self):
        self.cfg.allow_execution = True
        self.assertIn("42", self.agent.run_tool("run_code", code="print(6 * 7)"))

    def test_mock_agent_completes_tool_loop(self):
        reply = self.agent.ask("remember theme as dark")
        self.assertTrue(reply)
        self.assertEqual(self.agent.memory.get("theme"), "dark")

    def test_activity_callback_reports_tool_work(self):
        events = []
        self.agent.ask("remember language as Python", on_activity=lambda kind, payload: events.append(kind))
        self.assertIn("tool", events)
        self.assertIn("result", events)

    def test_registry_exposes_expected_tools(self):
        expected = {"remember", "recall", "write_file", "read_file", "run_code", "terminal"}
        self.assertTrue(expected.issubset(set(self.agent.registry.names())))


if __name__ == "__main__":
    unittest.main()
