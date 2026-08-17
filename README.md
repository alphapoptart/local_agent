# Local Agent

A privacy-first Python workbench for running an AI agent with local language models. Local Agent combines a transparent tool-calling loop, persistent SQLite memory, reusable skills, managed project workspaces, and optional media tools without requiring a hosted LLM account.

> Portfolio release: the core workflow runs locally, the complete offline test suite needs no model or API key, and potentially dangerous execution tools are disabled by default.

## What it demonstrates

- A model-agnostic agent loop that parses tool calls, executes them, returns observations, and stops safely
- Persistent facts and conversation history backed by SQLite
- Reusable Markdown/YAML skills loaded into the model context
- Project manifests with goals, tasks, status, and isolated storage
- Workspace-confined file operations with traversal protection
- Ollama integration for local open-weight models
- A deterministic mock backend for testing without a GPU, network, or model download
- Optional web research, image generation, text-to-speech, and video assembly
- Cross-platform Python packaging and automated CI on Python 3.10–3.12

## Safety model

Local Agent is intentionally conservative by default:

- File tools can access only the managed workspace under `LOCAL_AGENT_HOME`.
- Absolute paths and `..` traversal outside that workspace are rejected.
- Project names are validated and projects remain inside managed storage.
- Python and shell execution are disabled unless the operator explicitly sets `LOCAL_AGENT_ALLOW_EXECUTION=1`.
- Tool loops, output size, and execution time have hard limits.
- Runtime memory, workspaces, media, logs, and local configuration are excluded from Git.

Local execution remains powerful after it is enabled. Review generated commands and use a dedicated workspace for important tasks. See [SECURITY.md](SECURITY.md).

## Quick start

Requirements: Python 3.10+ and, for real-model chat, [Ollama](https://ollama.com/).

```bash
git clone https://github.com/alphapoptart/local_agent.git
cd local_agent
python -m venv .venv

# macOS/Linux
source .venv/bin/activate

# Windows PowerShell
# .venv\Scripts\Activate.ps1

python -m pip install -e .
python selftest.py
```

The smoke test proves memory, managed files, projects, skills, and the safe execution default without downloading a model.

## Try the interface without a model

```bash
LOCAL_AGENT_LLM=mock local-agent
```

Windows PowerShell:

```powershell
$env:LOCAL_AGENT_LLM = "mock"
local-agent
```

The mock backend is deterministic and intended for evaluation, demos, and CI—not general conversation.

## Use a real local model

```bash
ollama pull llama3.1:8b
local-agent
```

Choose another installed model with `LOCAL_AGENT_MODEL`, or point `OLLAMA_HOST` at another Ollama-compatible endpoint.

## Commands and tools

Chat normally, or use the optional shortcuts:

```text
/remember <key> <value>
/recall
/skills
/projects
/project <name>
/clear
/exit
```

Core tools include:

| Area | Tools | Default behavior |
|---|---|---|
| Memory | `remember`, `recall` | Stored locally in SQLite |
| Files | `write_file`, `read_file` | Confined to the managed workspace |
| Projects | `project_create`, `project_plan`, `project_status` | Confined to managed project storage |
| Skills | `save_skill`, `list_skills`, `delete_skill` | Stored locally |
| Research | `web_search`, `web_fetch` | Uses network access when invoked |
| Media | image, TTS, and video tools | Optional local or keyless services |
| Execution | `run_code`, `terminal` | Disabled until explicitly enabled |

## Enable local execution

Only enable execution in an environment where you are comfortable running model-generated code:

```bash
LOCAL_AGENT_ALLOW_EXECUTION=1 local-agent
```

Execution calls are still time-limited and output-limited, but this is not an operating-system sandbox.

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `LOCAL_AGENT_LLM` | `ollama` | `ollama` or deterministic `mock` backend |
| `LOCAL_AGENT_MODEL` | `llama3.1:8b` | Ollama model name |
| `OLLAMA_HOST` | `http://localhost:11434` | Ollama endpoint |
| `LOCAL_AGENT_HOME` | `~/local_agent_data` | Memory, projects, outputs, skills, and workspace |
| `LOCAL_AGENT_ALLOW_EXECUTION` | disabled | Explicitly enables Python and shell tools |
| `STABLE_DIFFUSION_API` | unset | Optional local image-generation endpoint |
| `EDGE_TTS_VOICE` | `en-US-AriaNeural` | Optional narration voice |

## Architecture

```text
User request
    │
    ▼
Agent loop ─────► Model backend (Ollama or deterministic mock)
    │                         │
    │       tool call ◄───────┘
    ▼
Tool registry
    ├── memory ──────────────► SQLite
    ├── skills ──────────────► managed skill files
    ├── projects ────────────► managed project manifests
    ├── files ───────────────► confined workspace
    ├── research/media ──────► optional network/local services
    └── execution ───────────► explicit opt-in only
```

The implementation is deliberately small enough to audit:

```text
local_agent/
├── agent.py          tool-calling loop and result feedback
├── config.py         environment configuration and workspace policy
├── llm.py            Ollama and deterministic mock backends
├── memory.py         SQLite persistence
├── projects.py       project manifests and task tracking
├── skills.py         reusable skill storage
└── tools/
    ├── __init__.py   registry and tool metadata
    └── builtins.py   research, media, execution, file, and state tools
```

## Verification

Run the complete standard-library suite:

```bash
python -m unittest discover -s tests -v
python selftest.py
```

The suite covers both accepted tool schemas, malformed Windows-style escapes, multiple tool calls, memory persistence, skills, project lifecycle, workspace file isolation, path traversal rejection, safe execution defaults, explicit execution opt-in, callbacks, and an end-to-end mock tool loop.

GitHub Actions runs the same checks on Python 3.10, 3.11, and 3.12.

## Scope and limitations

- Model quality and tool-selection reliability depend on the local model.
- The JSON tool protocol is intentionally simple and educational rather than a replacement for a production agent SDK.
- Optional keyless media providers can change or become unavailable; local backends are preferable for repeatability and privacy.
- Shell execution is intentionally opt-in and is not an OS-level sandbox.
- The project is a local CLI workbench; it does not expose an authenticated multi-user service.

## License

[MIT](LICENSE)
