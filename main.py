#!/usr/bin/env python3
"""Local Agent — pleasant interactive CLI + one-shot commands.

Free, fully-local autonomous AI agent: web search, image/video generation,
code execution, persistent memory, skills, and projects. No API keys, no
session limits.

Examples
--------
  # Interactive chat with your local model (Ollama)
  python main.py
  LOCAL_AGENT_MODEL=llama3.1:8b python main.py

  # One-shot generators (free, no chat needed)
  python main.py image  "a red dragon on a cliff" "a quiet forest"
  python main.py video  "neon city skyline" "calm lake at dusk" --voiceover "A tour of two worlds."
  python main.py tts    "Hello from my local agent." --voice en-US-GuyNeural

  # Try without a model (deterministic mock)
  LOCAL_AGENT_LLM=mock python main.py
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys
import time

# Allow running from the project root without installation.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from local_agent.agent import Agent
from local_agent.config import load_config


# ---------------- pretty printing (no external deps) -----------------
class C:
    """ANSI colors, auto-disabled when output isn't a TTY."""
    _enabled = sys.stdout.isatty()
    RESET = "\033[0m" if _enabled else ""
    BOLD = "\033[1m" if _enabled else ""
    DIM = "\033[2m" if _enabled else ""
    CYAN = "\033[36m" if _enabled else ""
    GREEN = "\033[32m" if _enabled else ""
    YELLOW = "\033[33m" if _enabled else ""
    MAGENTA = "\033[35m" if _enabled else ""
    RED = "\033[31m" if _enabled else ""

    @classmethod
    def s(cls, *parts) -> str:
        return "".join(parts)


def banner(cfg) -> None:
    bar = C.s(C.CYAN, "─" * 64, C.RESET)
    print(bar)
    print(C.s(C.BOLD, C.CYAN, "  LOCAL AGENT", C.RESET,
              C.DIM, "  —  free · local · autonomous AI agent", C.RESET))
    print(bar)
    print(C.s(C.DIM, "  backend ", C.RESET, f"{cfg.llm_backend}",
              C.DIM, "  model ", C.RESET, f"{cfg.model}"))
    if shutil.which("ffmpeg"):
        print(C.s(C.DIM, "  video   ", C.RESET, "ffmpeg ready (offline)", C.RESET))
    else:
        print(C.s(C.YELLOW, "  video   ffmpeg NOT found — install for offline video", C.RESET))
    print(C.s(C.DIM, "  data    ", C.RESET, f"{cfg.base_dir}"))
    print(C.s(C.DIM, "  tools   ", C.RESET, ", ".join(Agent(cfg).registry.names())))
    print(bar)


SPIN = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]


def run_with_ui(agent: Agent, task: str) -> str:
    """Drive ask() while rendering live tool activity in the terminal."""
    print()
    print(C.s(C.YELLOW, "You", C.RESET, ": ", C.BOLD, task, C.RESET))
    print(C.s(C.GREEN, "Agent", C.RESET, ": "), end="", flush=True)
    line = [""]

    def activity(kind, payload):
        if kind == "thinking":
            line[0] = C.s(C.DIM, "thinking…", C.RESET)
            print("\r" + " " * 12 + line[0], end="", flush=True)
        elif kind == "tool":
            name, args = payload
            arg_s = ", ".join(f"{k}={v}" for k, v in (args or {}).items())
            if len(arg_s) > 50:
                arg_s = arg_s[:47] + "…"
            line[0] = C.s(C.MAGENTA, "▸ ", C.RESET, f"{name}({arg_s})")
            print("\r" + " " * 12 + line[0], end="", flush=True)
        elif kind == "result":
            name, obs = payload
            print("\r" + " " * 12 + C.s(C.GREEN, "✓ ", C.RESET, C.DIM, f"{name} done", C.RESET))
        elif kind == "done":
            pass

    reply = agent.ask(task, on_activity=activity)
    # Clear the transient status line, then print the final answer.
    print("\r" + " " * 70, end="")
    print("\r" + C.s(C.GREEN, "Agent", C.RESET, ": ", C.BOLD, reply, C.RESET))
    return reply


# ---------------- interactive loop -----------------
def interactive(agent: Agent) -> None:
    if agent.cfg.llm_backend != "mock" and not agent.llm.available():
        print(C.s(C.YELLOW, "\n  ⚠ I couldn't reach Ollama (your local model).", C.RESET))
        print(C.s(C.DIM, "    To use a real model: install Ollama, then run `ollama pull %s`." % agent.cfg.model, C.RESET))
        print(C.s(C.DIM, "    You can also chat right now in test mode (no model) — or set", C.RESET))
        print(C.s(C.DIM, "    LOCAL_AGENT_LLM=mock to explore the tools.", C.RESET))
    print()
    print(C.s(C.DIM, "  Just talk to me like a person. A few handy shortcuts:", C.RESET))
    print(C.s(C.DIM, "    /remember <key> <value>   /recall", C.RESET))
    print(C.s(C.DIM, "    /skills   /projects   /project <name>   /clear   /exit", C.RESET))
    print(C.s(C.CYAN, "─" * 64, C.RESET))

    while True:
        try:
            user = input(C.s(C.YELLOW, "\nYou", C.RESET, "> ")).strip()
        except (EOFError, KeyboardInterrupt):
            print(C.s(C.DIM, "\n\nCatch you later! 👋", C.RESET))
            break
        if not user:
            continue
        if user in ("/exit", "/quit", "/bye"):
            print(C.s(C.DIM, "\nCatch you later! 👋", C.RESET))
            break
        try:
            run_command_or_chat(agent, user)
        except Exception as e:  # Never show the user a raw traceback.
            print(C.s(C.RED, "\n  Oops, something went sidewise on my end:", C.RESET, str(e).splitlines()[0]))
            print(C.s(C.DIM, "  I've kept our conversation — want to try rephrasing that?", C.RESET))


def run_command_or_chat(agent: Agent, user: str) -> None:
    """Route a line: slash command, or natural chat via the agent loop."""
    if user == "/clear":
        agent.messages = [{"role": "system", "content": agent._system_context()}]
        print(C.s(C.DIM, "  Fresh start — I've cleared our chat (your memory & projects are safe).", C.RESET))
        return
    if user.startswith("/remember "):
        _, k, *rest = user.split(" ", 2)
        v = " ".join(rest)
        agent.memory.set(k, v)
        print(C.s(C.DIM, f"  Got it — I'll remember {k} = {v}", C.RESET))
        return
    if user == "/recall":
        print(agent.memory.all_kv())
        return
    if user == "/skills":
        print(agent.skills.render_for_prompt())
        return
    if user == "/projects":
        print("Projects: " + (", ".join(agent.projects.list_projects()) or "(none yet)"))
        return
    if user.startswith("/project "):
        name = user.split(" ", 1)[1].strip()
        man = agent.projects.create(name)
        print(C.s(C.DIM, f"  Started a project '{name}' — files live at {man['path']}", C.RESET))
        return
    # A bare slash the user didn't mean as a command — treat as plain text.
    if user.startswith("/") and not user.startswith("//"):
        print(C.s(C.DIM, "  I'm not sure what that slash command is. Just type what you'd like in plain words,", C.RESET))
        print(C.s(C.DIM, "  or use /help to see the shortcuts.", C.RESET))
        return
    run_with_ui(agent, user)


# ---------------- one-shot generators -----------------
def one_shot(agent: Agent, args) -> None:
    if args.cmd == "image":
        for p in args.prompts:
            t0 = time.time()
            res = agent.run_tool("image_generate", prompt=p, aspect=args.aspect)
            print(C.s(C.GREEN, "✓", C.RESET, f" {res}".replace("\n", " ")))
            print(C.s(C.DIM, f"    ({time.time()-t0:.1f}s)", C.RESET))
    elif args.cmd == "video":
        t0 = time.time()
        res = agent.run_tool("video_from_prompts", prompts=args.prompts,
                             duration=args.duration, aspect=args.aspect,
                             voiceover=args.voiceover or "")
        print(C.s(C.GREEN, "✓", C.RESET, f" {res}".replace("\n", " ")))
        print(C.s(C.DIM, f"    ({time.time()-t0:.1f}s)", C.RESET))
    elif args.cmd == "tts":
        res = agent.run_tool("text_to_speech", text=args.text, voice=args.voice)
        print(C.s(C.GREEN, "✓", C.RESET, f" {res}".replace("\n", " ")))
    elif args.cmd == "chat":
        interactive(agent)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="local-agent",
        description="Free, local, autonomous AI agent (web, images, video, code, memory).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = p.add_subparsers(dest="cmd")

    pi = sub.add_parser("image", help="generate one or more images from prompts")
    pi.add_argument("prompts", nargs="+", help="image prompts")
    pi.add_argument("--aspect", default="landscape", choices=["landscape", "square", "portrait"])

    pv = sub.add_parser("video", help="generate a video from image prompts")
    pv.add_argument("prompts", nargs="+", help="image prompts (one per scene)")
    pv.add_argument("--duration", type=float, default=3.0, help="seconds per scene")
    pv.add_argument("--aspect", default="landscape", choices=["landscape", "square", "portrait"])
    pv.add_argument("--voiceover", default="", help="optional narration script (free TTS)")

    pt = sub.add_parser("tts", help="text-to-speech (free edge-tts)")
    pt.add_argument("text", help="text to speak")
    pt.add_argument("--voice", default="en-US-AriaNeural", help="voice name")

    sub.add_parser("chat", help="interactive chat (default)")
    p.set_defaults(cmd="chat")
    return p


def main() -> None:
    try:
        args = build_parser().parse_args()
        cfg = load_config()
        agent = Agent(cfg)
        banner(cfg)
        if getattr(args, "cmd", "chat") == "chat":
            interactive(agent)
        else:
            one_shot(agent, args)
    except KeyboardInterrupt:
        print(C.s(C.DIM, "\n\nCatch you later! 👋", C.RESET))
    except Exception as e:
        print(C.s(C.RED, "\nSomething went wrong starting up:", C.RESET, str(e).splitlines()[0]))
        print(C.s(C.DIM, "Try `LOCAL_AGENT_LLM=mock python main.py` to run in test mode,", C.RESET))
        print(C.s(C.DIM, "or check that Ollama is installed if you're using a real model.", C.RESET))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
