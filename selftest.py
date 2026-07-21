#!/usr/bin/env python3
"""Self-test: proves the framework works with the keyless `mock` backend.

It drives a REAL multi-step tool loop (no model needed) covering:
  - web search tool call -> result fed back
  - persistent memory (survives across a fresh Agent)
  - saving a skill
  - creating a project + planning tasks
  - file write/read round-trip
  - code execution

Run:  LOCAL_AGENT_LLM=mock python selftest.py
"""
from __future__ import annotations

import os
import sys
import tempfile
import shutil

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

os.environ["LOCAL_AGENT_LLM"] = "mock"

from local_agent.agent import Agent
from local_agent.config import Config


def check(name: str, cond: bool, detail: str = "") -> None:
    status = "PASS" if cond else "FAIL"
    print(f"[{status}] {name}" + (f" — {detail}" if detail else ""))
    if not cond:
        raise SystemExit(f"Self-test failed at: {name}")


def main() -> None:
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        cfg = Config(base_dir=os.path.join(tmp, "data"))
        a = Agent(cfg)

        # 1) Tool loop with web search -> result returned & loop completes.
        r1 = a.ask("please search the web for me")
        check("web_search tool loop", "web search results" in r1.lower() or "duckduckgo" in r1.lower(), r1[:60])

        # 2) Memory persists across a fresh Agent instance (separate process simulation).
        a.ask("remember the user name Sean with key user_name")
        a2 = Agent(cfg)
        check("memory persistence across instances", a2.memory.get("user_name") == "Sean",
               str(a2.memory.get("user_name")))

        # 3) Save a skill and confirm it lists.
        a.ask("save a skill called hello_world that prints a friendly hello")
        skills = a.skills.list_skills()
        check("save_skill", any(s["name"] == "hello_world" for s in skills), str([s["name"] for s in skills]))

        # 4) Create project + add tasks + status.
        a.ask("create a project called website_builder")
        a.run_tool("project_plan", name="website_builder",
                   tasks=["scaffold HTML", "add CSS", "deploy"])
        status = a.run_tool("project_status", name="website_builder")
        check("project plan/status", "scaffold HTML" in status and "deploy" in status, status.splitlines()[0])

        # 5) File write + read round-trip.
        fpath = os.path.join(tmp, "note.txt")
        a.run_tool("write_file", path=fpath, content="hello persistence")
        content = a.run_tool("read_file", path=fpath)
        check("file write/read", "hello persistence" in content, content[:40])

        # 6) Code execution tool.
        out = a.run_tool("run_code", code="print(6*7)")
        check("run_code", "42" in out, out)

        # 7) image_generate fallback path (mock backend, no network) — ensure no crash.
        # (skipped network call; we just confirm the tool is registered)
        check("image_generate registered", a.registry.get("image_generate") is not None)

        # 8) Video generation: offline ffmpeg if available and we have images.
        d = a.cfg.outputs_dir / "images"
        d.mkdir(parents=True, exist_ok=True)
        sample = [str(d / f) for f in sorted(os.listdir(d)) if f.endswith(".jpg")][:2]
        if not sample:
            # No fixtures yet — generate 2 images into the agent's own outputs dir.
            for p in ("test red square", "test blue square"):
                r = a.run_tool("image_generate", prompt=p)
                if "saved" in r or "generated" in r:
                    sample.append(r.split("saved: ")[-1].split("\n")[0])
        if sample and shutil.which("ffmpeg"):
            v = a.run_tool("video_from_images", images=sample, duration=2.0)
            ok_vid = "Video created" in v and os.path.exists(v.split(": ")[-1].strip())
            check("video_from_images (offline ffmpeg)", ok_vid, v[:60])
        else:
            note = "skipped (no images / no ffmpeg)" if not sample else "ffmpeg not found"
            print(f"[NOTE] video_from_images {note}")

        print("\nALL CHECKS PASSED — Local Agent framework is functional.")
        print("Tools available:", ", ".join(a.registry.names()))
        a.memory.close()
        a2.memory.close()


if __name__ == "__main__":
    main()
