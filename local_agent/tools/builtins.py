"""Built-in tool implementations.

All tools are FREE and require NO API keys by default:
  * Web search / fetch  -> DuckDuckGo (keyless, via HTML endpoint) + requests
  * Image generation    -> Pollinations.ai (keyless, free) OR a local ComfyUI /
                           Automatic1111 SD API if you set STABLE_DIFFUSION_API
  * Audio narration      -> edge-tts (keyless, free) muxed into video via ffmpeg
  * Video generation    -> local ffmpeg slideshow from generated images (free,
                           offline) OR a remote provider via VIDEO_API
  * Code / terminal     -> local subprocess execution (sandboxed by timeout)
  * File ops            -> local filesystem
  * Memory / skills /   -> the agent's own persistence layer
    projects

To swap in a different backend, set the relevant env var; everything else is
identical. Nothing here phones home for a paid key.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.parse import quote

import requests

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; LocalAgent/0.1)"}
TIMEOUT = 30


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n...[truncated to {limit} chars]"


def build_tools(agent) -> object:
    """Register every builtin tool onto agent.registry."""
    reg = agent.registry
    cfg = agent.cfg
    # ---------------- WEB ----------------
    @reg.decorator("web_search", "Search the web (keyless DuckDuckGo). Args: query (str).", {"query": "search terms"})
    def web_search(query: str) -> str:
        try:
            r = requests.post(
                "https://lite.duckduckgo.com/lite/",
                data={"q": query},
                headers=HEADERS,
                timeout=TIMEOUT,
            )
            r.raise_for_status()
            # Pull result titles + urls from the lite HTML.
            links = re.findall(r'<a[^>]+href="([^"]+)"[^>]*class="result-link"[^>]*>(.*?)</a>', r.text, re.S)
            if not links:
                links = re.findall(r'<a[^>]+href="(https?://[^"]+)"[^>]*>(.*?)</a>', r.text, re.S)
            out = []
            for url, title in links[:8]:
                title = re.sub(r"<.*?>", "", title).strip()
                out.append(f"- {title}\n  {url}")
            if not out:
                return f"No results parsed for '{query}'. (page returned {len(r.text)} bytes)"
            return _truncate("\n".join(out), cfg.max_tool_output_chars)
        except Exception as e:
            return f"web_search failed: {e}. Trying fallback..."

    @reg.decorator("web_fetch", "Fetch a URL and return its readable text. Args: url (str).", {"url": "web page URL"})
    def web_fetch(url: str) -> str:
        try:
            r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
            r.raise_for_status()
            text = re.sub(r"<script.*?</script>", "", r.text, flags=re.S)
            text = re.sub(r"<style.*?</style>", "", text, flags=re.S)
            text = re.sub(r"<[^>]+>", " ", text)
            text = re.sub(r"\s+", " ", text).strip()
            return _truncate(text, cfg.max_tool_output_chars)
        except Exception as e:
            return f"web_fetch failed: {e}"

    # ---------------- IMAGE ----------------
    @reg.decorator(
        "image_generate",
        "Generate an image from a text prompt. Free by default (Pollinations). "
        "Args: prompt (str), aspect (optional 'landscape'|'square'|'portrait').",
        {"prompt": "image description", "aspect": "landscape|square|portrait"},
    )
    def image_generate(prompt: str, aspect: str = "landscape") -> str:
        sd_api = os.environ.get("STABLE_DIFFUSION_API")
        out_dir = cfg.outputs_dir / "images"
        out_dir.mkdir(parents=True, exist_ok=True)
        fname = f"img_{int(time.time())}.png"
        out_path = out_dir / fname
        if sd_api:
            # Local ComfyUI / Automatic1111 compatible JSON endpoint.
            try:
                r = requests.post(sd_api, json={"prompt": prompt, "steps": 20}, timeout=300)
                r.raise_for_status()
                data = r.json()
                url = data.get("images", [{}])[0].get("url") or data.get("url")
                if url:
                    img = requests.get(url, timeout=300).content
                    out_path.write_bytes(img)
                    return f"Image saved (local SD): {out_path}"
            except Exception as e:
                return f"Local SD API failed: {e}; falling back to Pollinations."
        # Default free keyless generator.
        try:
            width = {"landscape": 1024, "square": 1024, "portrait": 768}.get(aspect, 1024)
            height = {"landscape": 576, "square": 1024, "portrait": 1024}.get(aspect, 576)
            url = f"https://image.pollinations.ai/prompt/{quote(prompt)}?width={width}&height={height}&nologo=true"
            img = requests.get(url, headers=HEADERS, timeout=120).content
            if len(img) < 2000:
                return f"Image generation returned suspicious data ({len(img)} bytes)."
            # Pick extension from magic bytes so the file is valid.
            if img[:3] == b"\xff\xd8\xff":
                suffix = ".jpg"
            elif img[:8] == b"\x89PNG\r\n\x1a\n":
                suffix = ".png"
            else:
                suffix = ".bin"
            out_path = out_path.with_suffix(suffix)
            out_path.write_bytes(img)
            return f"Image generated and saved: {out_path}\n(prompt: {prompt})"
        except Exception as e:
            return f"image_generate failed: {e}"

    # ---------------- AUDIO (free, local / keyless) ----------------
    @reg.decorator(
        "text_to_speech",
        "Convert text to speech and save an audio file — FREE via edge-tts (no API key). "
        "Args: text (str), voice (optional, e.g. 'en-US-AriaNeural'), out (optional path).",
        {"text": "text to speak", "voice": "voice name", "out": "output mp3 path"},
    )
    def text_to_speech(text: str, voice: str = "en-US-AriaNeural", out: str = "") -> str:
        out_path = Path(out) if out else (cfg.outputs_dir / "audio" / f"tts_{int(time.time())}.mp3")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            import asyncio

            import edge_tts
            async def _synth():
                comm = edge_tts.Communicate(text, voice)
                await comm.save(str(out_path))
            asyncio.run(_synth())
            if not out_path.exists() or out_path.stat().st_size < 100:
                return f"TTS produced no audio at {out_path}"
            return f"Audio saved: {out_path}"
        except ImportError:
            return ("edge-tts not installed. Free install: pip install edge-tts "
                    "(no API key needed). Skipped audio.")
        except Exception as e:
            return f"text_to_speech failed: {e}"

    def _mux_audio(video_path: Path, audio_path: Path, out_path: Path) -> str:
        """Add a narration track to a video (ffmpeg). Returns the output path."""
        out_path.parent.mkdir(parents=True, exist_ok=True)
        cmd = [
            "ffmpeg", "-y", "-i", str(video_path), "-i", str(audio_path),
            "-c:v", "copy", "-c:a", "aac", "-map", "0:v:0", "-map", "1:a:0",
            "-shortest", str(out_path),
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if res.returncode != 0:
            return f"audio mux failed ({res.returncode}): {res.stderr[-400:]}"
        return str(out_path)

    # ---------------- VIDEO ----------------
    @reg.decorator(
        "video_from_images",
        "Build a real video from local image paths using OFFLINE ffmpeg "
        "(Ken Burns zoom + crossfades, no network). Args: images (list[str]), "
        "out (optional str), duration (optional sec per image), fps (optional).",
        {"images": "list of image file paths", "out": "output mp4 path",
         "duration": "seconds per image", "fps": "frames per second"},
    )
    def video_from_images(images: list, out: str = "", duration: float = 3.0,
                          fps: int = 25) -> str:
        if not images:
            return "No images provided."
        imgs = [str(Path(p).resolve()) for p in images]
        missing = [p for p in imgs if not Path(p).exists()]
        if missing:
            return f"Missing images: {missing}"
        out_path = Path(out) if out else (cfg.outputs_dir / "videos" / f"vid_{int(time.time())}.mp4")
        out_path.parent.mkdir(parents=True, exist_ok=True)

        remote = os.environ.get("VIDEO_API")
        if remote:
            try:
                r = requests.post(remote, json={"images": imgs, "duration": duration}, timeout=600)
                r.raise_for_status()
                url = r.json().get("url") or r.json().get("video")
                if url:
                    out_path.write_bytes(requests.get(url, timeout=600).content)
                    return f"Video created (remote): {out_path}"
            except Exception as e:
                return f"Remote VIDEO_API failed: {e}; falling back to offline ffmpeg."

        # Offline path: verify ffmpeg exists, then build a Ken Burns + crossfade clip.
        if subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True).returncode != 0:
            return ("ffmpeg not found. Install ffmpeg (https://ffmpeg.org) for free offline "
                    "video generation, or set VIDEO_API to a remote provider.")
        try:
            fade = min(0.5, duration / 2.0)
            step = duration - fade
            zoom = "z='min(zoom+0.0008,1.06)'"
            parts = []
            for i, _im in enumerate(imgs):
                parts.append(
                    f"[{i}:v]scale=1600:900,setsar=1,crop=1280:720,"
                    f"zoompan={zoom}:d={int(duration*fps)}:s=1280x720:fps={fps},"
                    f"trim=duration={duration},format=yuv420p[v{i}]"
                )
            # Chain crossfades: input of step k is v0 (k==1), then x / x{k-1}.
            for k in range(1, len(imgs)):
                in_prev = "v0" if k == 1 else ("x" if k == 2 else f"x{k-1}")
                out_cur = "x" if k == 1 else f"x{k}"
                parts.append(
                    f"[{in_prev}][v{k}]xfade=transition=fade:"
                    f"duration={fade}:offset={k*step:.3f}[{out_cur}]"
                )
            last_label = "x" if len(imgs) == 2 else f"x{len(imgs)-1}"
            filter_complex = ";".join(parts)
            inputs = []
            for im in imgs:
                inputs += ["-loop", "1", "-t", str(duration), "-i", im]
            cmd = [
                "ffmpeg", "-y", *inputs,
                "-filter_complex", filter_complex,
                "-map", f"[{last_label}]", "-r", str(fps),
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
                str(out_path),
            ]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            if res.returncode != 0:
                return f"ffmpeg failed ({res.returncode}): {res.stderr[-800:]}"
            return f"Video created (offline ffmpeg, {len(imgs)} imgs, {duration}s each): {out_path}"
        except Exception as e:
            return f"video_from_images failed: {e}"

    @reg.decorator(
        "video_from_prompts",
        "Generate images from prompts, then assemble them into a video — fully "
        "offline & free. Args: prompts (list[str]), out (optional str), "
        "duration (optional sec per image), aspect (optional), "
        "voiceover (optional str: a narration script; uses FREE edge-tts).",
        {"prompts": "list of image prompts", "out": "output mp4 path",
         "duration": "seconds per image", "aspect": "landscape|square|portrait",
         "voiceover": "optional narration text (free TTS)"},
    )
    def video_from_prompts(prompts: list, out: str = "", duration: float = 3.0,
                           aspect: str = "landscape", voiceover: str = "") -> str:
        if not prompts:
            return "No prompts provided."
        generated = []
        for p in prompts:
            res = image_generate(p, aspect=aspect)
            if "saved" not in res and "generated" not in res:
                return f"Image generation step failed: {res}"
            # Extract the saved path from the result string.
            path = res.split("saved: ")[-1].split("\n")[0] if "saved:" in res else \
                   res.split("saved: ")[-1].split("\n")[0]
            generated.append(path)
        silent = Path(out).with_suffix(".silent.mp4") if out else \
                 (cfg.outputs_dir / "videos" / f"vid_{int(time.time())}.silent.mp4")
        vres = video_from_images(generated, out=str(silent), duration=duration)
        if "Video created" not in vres:
            return vres
        final_path = Path(out) if out else \
                     (cfg.outputs_dir / "videos" / f"vid_{int(time.time())}.mp4")

        # Optional free narration track (edge-tts).
        if voiceover:
            if shutil.which("ffmpeg") is None:
                return f"Video created (no audio, ffmpeg missing): {silent}"
            tts = text_to_speech(voiceover)
            if "Audio saved" in tts:
                audio_path = Path(tts.split("saved: ")[-1].strip())
                muxed = _mux_audio(silent, audio_path, final_path)
                if Path(muxed).exists():
                    try:
                        silent.unlink()
                    except OSError:
                        pass
                    return f"Video created with narration (offline ffmpeg + free TTS): {final_path}"
                return f"Video created but audio mux failed: {muxed}\nSilent video: {silent}"
            return f"Video created (silent; TTS unavailable): {silent}\nTTS note: {tts}"
        return vres.replace(str(silent), str(final_path))

    # ---------------- CODE / TERMINAL ----------------
    @reg.decorator(
        "run_code",
        "Execute Python code locally and return stdout. Args: code (str), timeout (optional sec).",
        {"code": "python source", "timeout": "max seconds"},
    )
    def run_code(code: str, timeout: int = 30) -> str:
        if not cfg.allow_execution:
            return ("run_code is disabled by default. Set "
                    "LOCAL_AGENT_ALLOW_EXECUTION=1 to enable local execution.")
        timeout = max(1, min(int(timeout), 120))
        with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
            f.write(code)
            tmp = f.name
        try:
            res = subprocess.run([sys.executable, tmp], capture_output=True, text=True, timeout=timeout)
            out = (res.stdout or "") + (res.stderr or "")
            return _truncate(f"exit={res.returncode}\n{out}", cfg.max_tool_output_chars)
        except subprocess.TimeoutExpired:
            return f"run_code timed out after {timeout}s"
        except Exception as e:
            return f"run_code error: {e}"
        finally:
            os.unlink(tmp)

    @reg.decorator(
        "terminal",
        "Run a shell command locally and return output. Args: command (str), timeout (optional sec).",
        {"command": "shell command", "timeout": "max seconds"},
    )
    def terminal(command: str, timeout: int = 60) -> str:
        if not cfg.allow_execution:
            return ("terminal is disabled by default. Set "
                    "LOCAL_AGENT_ALLOW_EXECUTION=1 to enable shell commands.")
        timeout = max(1, min(int(timeout), 120))
        try:
            res = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=timeout)
            out = (res.stdout or "") + (res.stderr or "")
            return _truncate(f"exit={res.returncode}\n{out}", cfg.max_tool_output_chars)
        except subprocess.TimeoutExpired:
            return f"terminal timed out after {timeout}s"
        except Exception as e:
            return f"terminal error: {e}"

    # ---------------- FILES ----------------
    @reg.decorator("write_file", "Write text to a file (creating dirs). Args: path (str), content (str).",
                   {"path": "file path", "content": "file contents"})
    def write_file(path: str, content: str) -> str:
        p = cfg.workspace_path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return f"Wrote {len(content)} chars to {p.resolve()}"

    @reg.decorator("read_file", "Read a text file. Args: path (str), limit (optional lines).",
                   {"path": "file path", "limit": "max lines"})
    def read_file(path: str, limit: int = 500) -> str:
        p = cfg.workspace_path(path)
        if not p.exists():
            return f"File not found: {p}"
        lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
        return _truncate("\n".join(lines[:limit]), cfg.max_tool_output_chars)

    # ---------------- MEMORY ----------------
    @reg.decorator("remember", "Store a fact in long-term memory. Args: key (str, the fact's NAME like 'user_name'), value (any, the fact's VALUE like 'Sean').",
                   {"key": "fact name, e.g. 'user_name'", "value": "fact value, e.g. 'Sean'"})
    def remember(key: str, value) -> str:
        agent.memory.set(key, value)
        return f"Remembered '{key}' = {value!r}"

    @reg.decorator("recall", "Recall a stored fact or list all memory. Args: key (optional str).",
                   {"key": "memory key (omit to list all)"})
    def recall(key: str = "") -> str:
        if not key:
            return f"Memory:\n{agent.memory.all_kv()}"
        return f"{key} = {agent.memory.get(key)}"

    # ---------------- SKILLS ----------------
    @reg.decorator(
        "save_skill",
        "Save a reusable skill (instructions + code). Args: name, description, content, trigger(optional).",
        {"name": "skill name", "description": "what it does", "content": "instructions/code", "trigger": "when to use"},
    )
    def save_skill(name: str, description: str, content: str, trigger: str = "") -> str:
        s = agent.skills.save(name, description, content, trigger)
        return f"Saved skill '{s['name']}' to {agent.cfg.skills_dir / name}"

    @reg.decorator("list_skills", "List saved skills. No args.", {})
    def list_skills() -> str:
        skills = agent.skills.list_skills()
        if not skills:
            return "No skills saved yet."
        return "\n".join(f"- {s['name']}: {s.get('description','')}" for s in skills)

    @reg.decorator("delete_skill", "Delete a saved skill. Args: name (str).", {"name": "skill name"})
    def delete_skill(name: str) -> str:
        ok = agent.skills.delete(name)
        return f"Deleted '{name}'" if ok else f"Skill '{name}' not found."

    # ---------------- PROJECTS ----------------
    @reg.decorator("project_create", "Create a project workspace. Args: name (str, the project's NAME like 'website_builder'), path (optional folder, usually omit).",
                   {"name": "project name, e.g. 'website_builder'", "path": "omit unless user specifies a folder"})
    def project_create(name: str, path: str = "") -> str:
        man = agent.projects.create(name, path or None)
        return f"Created project '{name}' at {man['path']}"

    @reg.decorator("project_plan", "Add tasks to a project. Args: name (str), tasks (list[str]).",
                   {"name": "project name", "tasks": "list of task strings"})
    def project_plan(name: str, tasks: list) -> str:
        for t in tasks[:12]:  # cap to keep plans actionable
            agent.projects.add_task(name, t)
        n = min(len(tasks), 12)
        extra = f" ({len(tasks)-n} omitted)" if len(tasks) > n else ""
        return f"Added {n} tasks to project '{name}'{extra}."

    @reg.decorator("project_status", "Show a project's goal and task list. Args: name (str).",
                   {"name": "project name"})
    def project_status(name: str) -> str:
        man = agent.projects.get(name)
        if not man:
            return f"Project '{name}' not found."
        tasks = man.get("tasks", [])
        lines = [f"Project: {name}  (status: {man.get('status')})", f"Goal: {man.get('goal','')}", "Tasks:"]
        for i, t in enumerate(tasks):
            lines.append(f"  [{t.get('status','?')[:1].upper()}] {i}. {t.get('task')}")
        return "\n".join(lines)

    return reg
