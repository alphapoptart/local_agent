"""The agent core: maintains context, runs the tool-calling loop, and persists
memory/skills/projects. Model-agnostic — works with any LLM backend.
"""
from __future__ import annotations

import inspect
import json
from typing import Any

from .config import Config, load_config
from .llm import SYSTEM_PROMPT, build_llm
from .memory import Memory
from .projects import ProjectManager
from .skills import SkillManager
from .tools import ToolRegistry
from .tools.builtins import build_tools


class Agent:
    def __init__(self, cfg: Config | None = None):
        self.cfg = cfg or load_config()
        self.llm = build_llm(self.cfg)
        self.memory = Memory(self.cfg.db_path)
        self.skills = SkillManager(self.cfg.skills_dir)
        self.projects = ProjectManager(self.cfg.projects_dir)
        self.registry = ToolRegistry()
        build_tools(self)
        self.messages: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]

    # ---------- conversation helpers ----------
    def _toolblock(self) -> str:
        specs = self.registry.specs()
        lines = ["You have these tools. Call one with JSON when you need it:"]
        for s in specs:
            lines.append(f"- {s['name']}: {s['description']}  args={s['args']}")
        return "\n".join(lines)

    def _system_context(self) -> str:
        return (
            SYSTEM_PROMPT + "\n\n" + self._toolblock() + "\n\n"
            + "Saved skills:\n" + self.skills.render_for_prompt()
        )

    # ---------- core loop ----------
    def ask(self, user_text: str, on_activity=None) -> str:
        """Run one user turn, looping tool calls until the model answers naturally.

        on_activity(kind, payload) is an optional callback fired during the loop:
          ("thinking", None)        -> model is generating
          ("tool",  (name, args))   -> about to run a tool
          ("result", (name, obs))   -> tool finished
        """
        # Refresh dynamic context while preserving the current conversation.
        self.messages[0] = {"role": "system", "content": self._system_context()}
        if len(self.messages) > 40:
            self.messages = [self.messages[0], *self.messages[-39:]]
        self.messages.append({"role": "user", "content": user_text})
        self.memory.log("user", user_text)

        last_results: list[str] = []
        for _ in range(self.cfg.max_iterations):
            if on_activity:
                on_activity("thinking", None)
            reply = self.llm.chat(self.messages, self.registry.specs())

            # Conversational model: only treat as "done" when there's real prose
            # and no tool calls (or a bare acknowledgement). Strip the old marker
            # if a model still emits it.
            reply_clean = reply.replace("<<<DONE>>>", "").strip()
            calls = self._parse_tool_calls(reply)
            if not calls:
                if reply_clean:
                    if on_activity:
                        on_activity("done", reply_clean)
                    self.memory.log("assistant", reply_clean)
                    return reply_clean
                # Empty reply (model stalled) — nudge it to respond like a person.
                if last_results:
                    summary = "; ".join(r for r in last_results if not r.startswith("Unknown"))
                    final = f"Done. I completed {len(last_results)} action(s): {summary}."
                    if on_activity:
                        on_activity("done", final)
                    self.memory.log("assistant", final)
                    return final
                self.messages.append({"role": "assistant", "content": reply})
                self.messages.append({
                    "role": "user",
                    "content": "Please reply to me in plain language, or include a tool call if you need to do something.",
                })
                continue

            # Execute every tool call the model emitted this turn.
            results = []
            for call in calls:
                name = call.get("tool")
                args = call.get("args", {}) or {}
                if on_activity:
                    on_activity("tool", (name, args))
                tool = self.registry.get(name)
                if not tool:
                    obs = (f"I don't have a tool called '{name}'. The tools I can use are: "
                           f"{', '.join(self.registry.names())}. Try one of those, or just tell "
                           f"me what you'd like in plain words.")
                else:
                    obs = self._run_tool_safely(tool, name, args)
                if on_activity:
                    on_activity("result", (name, obs))
                results.append(f"{name}: {obs}")
            last_results.extend(results)
            self.messages.append({"role": "assistant", "content": reply})
            self.messages.append({"role": "user", "content": "tool_result: " + json.dumps(results, default=str)})
        # Loop ended (hit cap). If we did real work, report it like a person would.
        if last_results:
            summary = "; ".join(r for r in last_results if not r.startswith("Unknown"))
            return f"I finished the work — here's what I did: {summary}"
        return "I wasn't able to complete that. Could you rephrase what you'd like me to do?"

    def _run_tool_safely(self, tool, name: str, args: dict) -> str:
        """Run a tool, turning failures into friendly, recoverable messages.

        Also coerces obviously-wrong arg types (e.g. a comma-string where the
        tool wants a list) so a small model slip doesn't become a hard error.
        """
        try:
            sig = inspect.signature(tool.fn)
            clean = {}
            for pname, pval in (args or {}).items():
                ann = sig.parameters.get(pname)
                want_list = ann is not None and ann.annotation in (list, "list", "list[str]")
                if want_list and isinstance(pval, str):
                    # "a, b, c" or "['a','b']" -> ["a","b","c"]
                    s = pval.strip()
                    if s.startswith("[") and s.endswith("]"):
                        try:
                            pval = json.loads(s)
                        except json.JSONDecodeError:
                            pval = [x.strip().strip("'\"") for x in s[1:-1].split(",") if x.strip()]
                    else:
                        pval = [x.strip().strip("'\"") for x in pval.split(",") if x.strip()]
                clean[pname] = pval
            return tool.run(**clean)
        except Exception as e:  # The agent's "smart workaround" hook.
            kind = type(e).__name__
            msg = str(e).splitlines()[0] if str(e) else kind
            # Friendly note that invites a natural retry instead of an error code.
            return (f"That didn't work ({kind}: {msg}). No worries — try a different approach, "
                    f"adjust the inputs, or tell me what you'd like and I'll figure it out.")


    @staticmethod
    def _parse_tool_calls(text: str) -> list[dict]:
        """Extract every valid tool call the model emitted this turn.

        Accepts both schemas the model may use:
          - canonical:  {"tool": "name", "args": {...}}
          - shorthand:  {"name": {...args...}}   (action-as-key)
        """
        out = []
        for c in Agent._extract_json_objects(text):
            obj = Agent._loose_json(c)
            if obj is None:
                continue
            if not isinstance(obj, dict):
                continue
            if "tool" in obj and "args" in obj:
                out.append({"tool": obj["tool"], "args": obj.get("args", {}) or {}})
            elif len(obj) == 1:
                # shorthand: single key = tool name, value = args
                name, args = next(iter(obj.items()))
                if isinstance(args, dict):
                    out.append({"tool": name, "args": args})
        return out

    @staticmethod
    def _loose_json(s: str):
        """json.loads that tolerates the sloppy escapes free models emit
        (e.g. Windows paths like c:\\Users with a lone backslash)."""
        try:
            return json.loads(s)
        except json.JSONDecodeError:
            pass
        # Repair: any backslash NOT followed by a valid JSON escape -> double it.
        import re as _re
        valid = set('"\\/bfnrt')
        def _fix(m):
            nxt = m.group(2)
            return m.group(0) if nxt in valid else "\\" + m.group(0)
        repaired = _re.sub(r"(\\)(.)", _fix, s)
        try:
            return json.loads(repaired)
        except json.JSONDecodeError:
            return None

    @staticmethod
    def _extract_json_objects(text: str) -> list[str]:
        """Return all balanced-brace JSON object substrings (handles nesting)."""
        out: list[str] = []
        depth = 0
        start = -1
        in_str = False
        esc = False
        for i, ch in enumerate(text):
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch == "{":
                if depth == 0:
                    start = i
                depth += 1
            elif ch == "}":
                if depth > 0:
                    depth -= 1
                    if depth == 0 and start != -1:
                        out.append(text[start : i + 1])
                        start = -1
        return out

    # ---------- convenience for scripts/tests ----------
    def run_tool(self, tool_name: str, **kwargs) -> Any:
        tool = self.registry.get(tool_name)
        if not tool:
            raise KeyError(tool_name)
        return tool.run(**kwargs)
