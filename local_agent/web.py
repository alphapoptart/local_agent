"""Local web interface for Local Agent.

The server binds to loopback by default and uses only the Python standard
library. It intentionally exposes no remote-access mode.
"""
from __future__ import annotations

import json
import threading
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from .agent import Agent

APP_HTML = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <meta name="color-scheme" content="dark">
  <title>Local Agent</title>
  <style>
    :root{--bg:#090d14;--panel:#111824;--panel2:#172130;--line:#263349;--text:#eef4ff;
      --muted:#95a7bf;--accent:#76e4c4;--blue:#77a8ff;--warn:#ffc977;--shadow:0 24px 70px #0008}
    *{box-sizing:border-box}body{margin:0;background:radial-gradient(circle at 15% -10%,#18364a 0,
      transparent 36%),var(--bg);color:var(--text);font:15px/1.5 Inter,ui-sans-serif,system-ui,sans-serif}
    button,textarea{font:inherit}.shell{min-height:100vh;display:grid;grid-template-columns:280px 1fr}
    aside{border-right:1px solid var(--line);background:#0c121cdd;padding:26px 20px;display:flex;
      flex-direction:column;gap:26px}.brand{display:flex;align-items:center;gap:12px}.mark{width:42px;height:42px;
      border-radius:14px;background:linear-gradient(135deg,var(--accent),var(--blue));box-shadow:0 8px 30px #76e4c444}
    h1{font-size:18px;margin:0}.eyebrow{font-size:11px;letter-spacing:.14em;text-transform:uppercase;color:var(--accent)}
    .status{display:flex;align-items:center;gap:8px;color:var(--muted)}.dot{width:8px;height:8px;border-radius:50%;
      background:var(--accent);box-shadow:0 0 14px var(--accent)}.card{background:var(--panel);border:1px solid var(--line);
      border-radius:16px;padding:16px}.card h2{font-size:12px;text-transform:uppercase;letter-spacing:.1em;
      color:var(--muted);margin:0 0 12px}.facts{display:grid;gap:10px}.fact{display:flex;justify-content:space-between;
      gap:12px}.fact span:last-child{color:var(--muted);text-align:right}.safe{color:var(--accent)!important}
    .side-list{display:grid;gap:8px;color:var(--muted)}.side-list div{padding:8px 10px;border-radius:9px;
      background:#ffffff05}.spacer{flex:1}.small{font-size:12px;color:var(--muted)}
    main{min-width:0;display:flex;flex-direction:column;max-height:100vh}.top{padding:24px 34px;border-bottom:1px solid var(--line);
      display:flex;justify-content:space-between;align-items:center;background:#090d1499;backdrop-filter:blur(16px)}
    .top h2{font-size:16px;margin:0}.badge{border:1px solid var(--line);padding:6px 10px;border-radius:999px;color:var(--muted);
      font-size:12px}.chat{flex:1;overflow:auto;padding:34px;display:flex;flex-direction:column;gap:18px}
    .welcome{max-width:720px;margin:auto;text-align:center;padding:32px}.welcome h3{font-size:32px;line-height:1.15;margin:0 0 14px}
    .welcome p{color:var(--muted);margin:0 auto 24px;max-width:590px}.suggestions{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}
    .suggestion{color:var(--text);background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:14px;
      cursor:pointer;text-align:left}.suggestion:hover{border-color:#76e4c477;transform:translateY(-1px)}
    .message{max-width:780px;width:fit-content;border:1px solid var(--line);border-radius:18px;padding:14px 16px;
      white-space:pre-wrap;box-shadow:0 10px 24px #0002}.user{align-self:flex-end;background:#1b3154}.assistant{background:var(--panel)}
    .meta{font-size:11px;text-transform:uppercase;letter-spacing:.08em;color:var(--muted);margin-bottom:6px}
    .activity{align-self:flex-start;color:var(--muted);font-size:13px;padding:0 8px}.composer{padding:18px 34px 28px;
      background:linear-gradient(transparent,#090d14 24%)}.compose-box{max-width:900px;margin:auto;background:var(--panel);
      border:1px solid var(--line);border-radius:20px;padding:12px;display:flex;gap:12px;box-shadow:var(--shadow)}
    textarea{flex:1;resize:none;min-height:48px;max-height:150px;background:transparent;border:0;outline:0;color:var(--text);
      padding:12px}.send{align-self:flex-end;border:0;background:linear-gradient(135deg,var(--accent),#5ab8ef);color:#07131a;
      font-weight:750;border-radius:13px;padding:12px 18px;cursor:pointer}.send:disabled{opacity:.45;cursor:wait}
    @media(max-width:800px){.shell{grid-template-columns:1fr}aside{display:none}.top,.chat{padding-left:20px;padding-right:20px}
      .composer{padding:14px}.suggestions{grid-template-columns:1fr}.welcome h3{font-size:26px}}
  </style>
</head>
<body>
<div class="shell">
  <aside>
    <div class="brand"><div class="mark"></div><div><div class="eyebrow">Private by design</div><h1>Local Agent</h1></div></div>
    <div class="status"><span class="dot"></span><span id="statusText">Starting…</span></div>
    <section class="card"><h2>Runtime</h2><div class="facts">
      <div class="fact"><span>Backend</span><span id="backend">—</span></div>
      <div class="fact"><span>Model</span><span id="model">—</span></div>
      <div class="fact"><span>Execution</span><span id="execution" class="safe">—</span></div>
    </div></section>
    <section class="card"><h2>Memory</h2><div id="memory" class="side-list"><div>No saved facts</div></div></section>
    <section class="card"><h2>Projects</h2><div id="projects" class="side-list"><div>No projects yet</div></div></section>
    <div class="spacer"></div><div class="small">Files stay inside the managed workspace. The server listens only on this computer.</div>
  </aside>
  <main>
    <header class="top"><div><div class="eyebrow">Agent workbench</div><h2>Conversation</h2></div><span class="badge">Local session</span></header>
    <section id="chat" class="chat">
      <div id="welcome" class="welcome"><h3>What should we work on?</h3>
        <p>Test the tool loop, persistent memory, project tracking, and safety controls without sending your conversation to a hosted model.</p>
        <div class="suggestions">
          <button class="suggestion">Remember my preferred language is Python</button>
          <button class="suggestion">Create a project called portfolio_demo</button>
          <button class="suggestion">Run code that prints 42</button>
        </div>
      </div>
    </section>
    <footer class="composer"><div class="compose-box"><textarea id="input" rows="1" placeholder="Message Local Agent…"></textarea>
      <button id="send" class="send">Send</button></div></footer>
  </main>
</div>
<script>
const chat=document.querySelector('#chat'),input=document.querySelector('#input'),send=document.querySelector('#send');
function esc(s){return String(s).replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]))}
function message(role,text){document.querySelector('#welcome')?.remove();const el=document.createElement('div');
  el.className='message '+role;el.innerHTML=`<div class="meta">${role==='user'?'You':'Local Agent'}</div>${esc(text)}`;
  chat.appendChild(el);chat.scrollTop=chat.scrollHeight}
async function refresh(){const r=await fetch('/api/status'),s=await r.json();
  document.querySelector('#statusText').textContent=s.ready?'Ready':'Unavailable';document.querySelector('#backend').textContent=s.backend;
  document.querySelector('#model').textContent=s.model;document.querySelector('#execution').textContent=s.execution?'Enabled':'Safely disabled';
  const mem=document.querySelector('#memory');mem.innerHTML=s.memory.length?s.memory.map(([k,v])=>`<div>${esc(k)}: ${esc(v)}</div>`).join(''):'<div>No saved facts</div>';
  const projects=document.querySelector('#projects');projects.innerHTML=s.projects.length?s.projects.map(p=>`<div>${esc(p)}</div>`).join(''):'<div>No projects yet</div>'}
async function submit(text=input.value.trim()){if(!text||send.disabled)return;input.value='';message('user',text);send.disabled=true;
  const act=document.createElement('div');act.className='activity';act.textContent='Thinking locally…';chat.appendChild(act);
  try{const r=await fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({message:text})});
    const data=await r.json();act.remove();if(!r.ok)throw new Error(data.error||'Request failed');message('assistant',data.reply);await refresh()}
  catch(e){act.remove();message('assistant','I could not complete that request: '+e.message)}finally{send.disabled=false;input.focus()}}
send.addEventListener('click',()=>submit());input.addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();submit()}});
document.querySelectorAll('.suggestion').forEach(b=>b.addEventListener('click',()=>submit(b.textContent)));refresh();input.focus();
</script>
</body></html>"""


class LocalAgentHandler(BaseHTTPRequestHandler):
    agent: Agent
    agent_lock: threading.Lock

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _json(self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, default=str).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path == "/":
            body = APP_HTML.encode()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'unsafe-inline'; script-src 'unsafe-inline'")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path == "/api/status":
            with self.agent_lock:
                payload = {
                    "ready": True,
                    "backend": self.agent.cfg.llm_backend,
                    "model": self.agent.cfg.model,
                    "execution": self.agent.cfg.allow_execution,
                    "memory": list(self.agent.memory.all_kv().items()),
                    "projects": self.agent.projects.list_projects(),
                }
            self._json(payload)
            return
        self._json({"error": "Not found"}, HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        if self.path != "/api/chat":
            self._json({"error": "Not found"}, HTTPStatus.NOT_FOUND)
            return
        try:
            length = min(int(self.headers.get("Content-Length", "0")), 100_000)
            payload = json.loads(self.rfile.read(length))
            message = str(payload.get("message", "")).strip()
            if not message:
                raise ValueError("Message is required")
            with self.agent_lock:
                reply = self.agent.ask(message)
            self._json({"reply": reply})
        except (ValueError, json.JSONDecodeError) as exc:
            self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
        except Exception as exc:
            self._json({"error": f"Agent error: {exc}"}, HTTPStatus.INTERNAL_SERVER_ERROR)


def run_web(agent: Agent, host: str = "127.0.0.1", port: int = 8765, open_browser: bool = True) -> None:
    """Run the local-only web interface until interrupted."""
    handler = type(
        "ConfiguredHandler",
        (LocalAgentHandler,),
        {"agent": agent, "agent_lock": threading.Lock()},
    )
    server = ThreadingHTTPServer((host, port), handler)
    server.daemon_threads = True
    url = f"http://{host}:{port}"
    print(f"Local Agent web app: {url}")
    print("Press Ctrl+C to stop.")
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
