# Local Agent 🤖

A **free, fully-local, session-unlimited** AI agent framework. Run any open
model as an autonomous agent that can search the web, generate images/video,
write and run code, manage persistent memory, save reusable skills, and organize
work into projects.

> No API keys required. No per-session limits. No cloud lock-in. Your data
> lives under `~/local_agent_data`.

---

## What it can do (like Hermes / Claude)

| Capability | Tool | Free backend |
|---|---|---|
| Web search | `web_search` | DuckDuckGo (keyless) |
| Fetch web pages | `web_fetch` | requests |
| Generate images | `image_generate` | Pollinations.ai (keyless) or your local Stable Diffusion |
| Generate video | `video_from_images`, `video_from_prompts` | local `ffmpeg` (offline Ken Burns + crossfades) or remote provider |
| Audio narration | `text_to_speech` | edge-tts (keyless, free) muxed into video |
| Write/run code | `run_code`, `terminal` | local Python / shell |
| Files | `write_file`, `read_file` | local filesystem |
| Long-term memory | `remember`, `recall` | SQLite (persists forever) |
| Reusable skills | `save_skill`, `list_skills`, `delete_skill` | local files |
| Projects | `project_create`, `project_plan`, `project_status` | local folders |

The agent talks like a person. You chat normally; when a task needs doing it
reaches for a tool, observes the result, and either does the next step or
replies — retrying with a smart workaround (in plain language, never a raw
error code) if something fails. No special syntax or rigid formatting required.

---

## Quick start (free, no GPU required to try)

```bash
# 1. Install deps
pip install -r requirements.txt

# 2. Try it instantly with the keyless mock backend (no model download)
LOCAL_AGENT_LLM=mock python main.py        # interactive
LOCAL_AGENT_LLM=mock python selftest.py    # proves every feature works

# 3. For a REAL model, install Ollama (https://ollama.com) and pull one:
ollama pull llama3.1:8b
python main.py                              # interactive chat with the model
```

### One-shot generators (no chat needed)

```bash
python main.py image "a red dragon" "a quiet forest" --aspect square
python main.py video "neon skyline" "calm lake" --duration 2.5 --voiceover "A tour of two worlds."
python main.py tts "Hello from my local agent." --voice en-US-GuyNeural
```

On **Windows** use `set` instead of `export`:
```cmd
set LOCAL_AGENT_LLM=mock
python main.py
```

---

## Using a real local model

Ollama (recommended — free, one command):

```bash
ollama pull llama3.1:8b
python main.py
```

Other OpenAI-compatible local servers (LocalAI, LM Studio, llama.cpp server,
vLLM) work too — point `OllamaLLM` at them or implement `.chat()` in
`local_agent/llm.py`. The interface is three lines; everything else is identical.

---

## CLI commands

## Talking to it

Just chat. No rigid format — mix a sentence with a tool call if you like:

```
You> hey, can you search for free local AI models and remember my name is Sean?
Agent> Sure — searching now…  (calls web_search, then remember)
       Done! I found several options and saved your name as Sean.
```

Slash shortcuts are optional power-user moves; plain English also works for most
things (e.g. "remember that my name is Sean" triggers memory just as well). If a
tool fails, the agent tells you in plain words and tries another way — you'll
never see a raw stack trace or error code in the chat.

Interactive chat (`python main.py`):
```
You> <any task>
You> /remember user_name Sean     # store a fact
You> /skills                     # list saved skills
You> /projects                   # list projects
You> /project website_builder    # create a project
You> /clear                      # reset conversation (keeps memory/projects)
You> /exit
```

---

## Architecture

```
local_agent/
├── config.py        # paths, model choice, env overrides
├── llm.py           # model-agnostic backend (Ollama / mock) — plug in any!
├── agent.py         # the tool-calling loop + context assembly
├── memory.py        # SQLite key/value + conversation history (persistent)
├── skills.py        # save / load / delete reusable skills
├── projects.py      # project workspaces + task lists
├── tools/
│   ├── __init__.py  # Tool + ToolRegistry
│   └── builtins.py  # all built-in tools (free, keyless)
└── __init__.py
main.py              # interactive CLI
selftest.py          # zero-dep proof it works
```

### The agent loop (`agent.py`)
1. Assemble system prompt + tool list + saved skills.
2. Ask the model. If it returns `{"tool": name, "args": {...}}` → run it.
3. Feed the result back and loop (up to `max_iterations`, a safety cap — **not**
   a session limit).
4. When the model replies in plain text, return the answer.

### Adding your own tool
```python
@reg.decorator("my_tool", "Does X. Args: a (str).", {"a": "description"})
def my_tool(a: str) -> str:
    return do_work(a)
```
Register it in `local_agent/tools/builtins.py`. The model can call it
immediately.

### Adding a model backend
Implement `chat(messages, tools) -> str` in `local_agent/llm.py` and select it
via `LOCAL_AGENT_LLM`.

---

## Environment variables

| Var | Default | Meaning |
|---|---|---|
| `LOCAL_AGENT_LLM` | `ollama` | `ollama` or `mock` |
| `LOCAL_AGENT_MODEL` | `llama3.1:8b` | model name |
| `OLLAMA_HOST` | `http://localhost:11434` | Ollama endpoint |
| `LOCAL_AGENT_HOME` | `~/local_agent_data` | data directory |
| `STABLE_DIFFUSION_API` | _(unset)_ | local SD/ComfyUI endpoint for images |
| `VIDEO_API` | _(unset)_ | remote video provider endpoint |
| `EDGE_TTS_VOICE` | `en-US-AriaNeural` | default narration voice |

---

## Testing

A permanent `pytest` suite covers the parser, every tool, and a mock
multi-step run (all keyless — no model, no network):

```bash
pip install pytest
pytest -q            # 14 tests
LOCAL_AGENT_LLM=mock python selftest.py   # zero-dep alternative
```

A real-Ollama run is exercised by `live_run.py` (with `ollama` installed):

```bash
python live_run.py "search the web for local AI best practices, then make a project"
```

## Limitations & honest notes
- **Free image/video**: defaults to keyless web APIs (Pollinations) and offline
  `ffmpeg`. For private/local generation set `STABLE_DIFFUSION_API` to your own
  SD/ComfyUI server.
- **Model quality** depends on the local model you choose. An 8B model reasons
  about tools well; bigger models are better at long multi-step plans.
- This is a from-scratch framework, not a wrapper around a paid service — so it
  is yours to extend, audit, and run forever at zero cost.

## License
MIT — do whatever you want with it.
