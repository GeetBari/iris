"""Small local-only control panel for Iris.

It intentionally binds to loopback only. No cloud service or extra package is
required, and all runtime data remains beside the Iris project on E:.
"""

from __future__ import annotations

import json
import os
import subprocess
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

PROJECT_DIR = Path(__file__).parent
STATE_PATH = PROJECT_DIR / "iris-state.json"
MUTE_PATH = PROJECT_DIR / "iris-muted.flag"
RESTART_PATH = PROJECT_DIR / "iris-restart.flag"
LOG_PATH = PROJECT_DIR / "iris.log"
PYTHON = PROJECT_DIR / ".venv" / "Scripts" / "python.exe"
ASSISTANT = PROJECT_DIR / "assistant.py"
HOST, PORT = "127.0.0.1", 8765
CREATE_NO_WINDOW = 0x08000000


def state() -> str:
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8")).get("state", "stopped")
    except (OSError, ValueError):
        return "stopped"


def logs() -> str:
    try:
        return LOG_PATH.read_text(encoding="utf-8", errors="replace")[-12000:]
    except OSError:
        return "No Iris log yet. Start the tray app first."


def run_command(command: str) -> None:
    subprocess.Popen(
        [str(PYTHON), str(ASSISTANT), command],
        cwd=str(PROJECT_DIR), creationflags=CREATE_NO_WINDOW,
    )


PAGE = """<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Iris Control Center</title>
<style>
:root{color-scheme:dark;--bg:#050505;--panel:#101010;--line:#2b2b2b;--text:#f5f5f5;--muted:#a1a1aa;--accent:#facc15}
*{box-sizing:border-box}body{margin:0;min-height:100vh;background:radial-gradient(circle at 10% 0%,#25210b 0,#050505 42%),var(--bg);color:var(--text);font:15px Inter,ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:1180px;margin:0 auto;padding:42px 24px}.top{display:flex;justify-content:space-between;align-items:center;gap:18px;margin-bottom:28px}
.brand{display:flex;align-items:center;gap:14px}.logo{display:grid;place-items:center;width:48px;height:48px;border-radius:15px;background:#facc15;color:#080808;font-weight:900;font-size:24px;box-shadow:0 0 28px #facc1544}
h1{margin:0;font-size:30px;letter-spacing:-.8px}.muted{color:var(--muted)}.grid{display:grid;grid-template-columns:minmax(300px,.85fr) minmax(0,1.6fr);gap:20px}
.card{background:linear-gradient(145deg,#171717ee,#0b0b0bee);border:1px solid var(--line);border-radius:20px;padding:22px;box-shadow:0 18px 50px #000000cc;backdrop-filter:blur(14px)}
.card h3{margin:28px 0 4px;font-size:15px;letter-spacing:.3px}.eyebrow{font-size:11px;font-weight:800;letter-spacing:1.4px;color:#facc15}
.state{display:flex;align-items:center;gap:11px;margin:15px 0 20px;font-size:25px;font-weight:750;text-transform:capitalize}.dot{width:14px;height:14px;border-radius:50%;background:#22c55e;box-shadow:0 0 18px currentColor}
button{border:1px solid #facc15;border-radius:10px;padding:10px 15px;margin:7px 5px 0 0;background:#facc15;color:#090909;font-weight:800;cursor:pointer;transition:transform .15s,filter .15s}button:hover{filter:brightness(1.12);transform:translateY(-1px)}button.alt{background:#1d1d1d;color:var(--text);border-color:#4a4a4a}
input{box-sizing:border-box;width:100%;padding:13px 14px;border-radius:10px;border:1px solid #3a3a3a;background:#090909;color:var(--text);margin-top:13px;outline:none}input:focus{border-color:var(--accent);box-shadow:0 0 0 3px #facc151c}input::placeholder{color:#666}
.terminal{height:440px;overflow:auto;background:#050505;border:1px solid #292929;border-radius:13px;padding:10px 0;color:#e4e4e7;font:13px "Cascadia Code",Consolas,monospace}.terminal-line{display:flex;gap:13px;padding:3px 14px;line-height:1.55}.terminal-line:hover{background:#171717}.line-no{width:32px;color:#555;text-align:right;user-select:none}.event{color:#facc15}.heard{color:#a1a1aa}.reply{color:#e5e7eb}.system{color:#737373}.terminal-empty{padding:18px;color:#737373}.session-bar{display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap;padding:10px 12px;margin-bottom:9px;border-bottom:1px solid #242424;color:#a1a1aa;font-size:12px}.session-bar strong{color:#facc15}.hint{font-size:13px;line-height:1.5}
@media(max-width:780px){main{padding:25px 15px}.top{align-items:flex-start}.grid{grid-template-columns:1fr}h1{font-size:25px}}
</style></head><body><main>
<div class="top"><div class="brand"><div class="logo">I</div><div><h1>Iris Control Center</h1><div class="muted">Your private local assistant · loopback only</div></div></div><button class="alt" onclick="refresh()">↻ Refresh</button></div>
<div class="grid"><section class="card"><div class="eyebrow">CURRENT STATE</div><p class="state"><span class="dot" id="dot"></span><span id="state">Loading...</span></p>
<button onclick="post('/api/restart')">Restart Iris</button><button class="alt" onclick="post('/api/mute')">Mute / Resume</button>
<h3>Command console</h3><div class="muted hint">Send a normal Iris command without using the microphone.</div>
<input id="command" placeholder="e.g. open calculator" onkeydown="if(event.key==='Enter')send()"><button onclick="send()">Send command</button><pre id="reply">Ready.</pre></section>
<section class="card"><div class="eyebrow">LIVE ACTIVITY</div><div class="muted hint" style="margin:8px 0 14px">Readable session history from Iris</div><div class="session-bar"><span>Session <strong id="session">Loading...</strong></span><span>Updated <strong id="updated">—</strong></span></div><div class="terminal" id="logs">Loading...</div></section></div></main>
<script>
function renderLogs(raw){let box=document.querySelector('#logs');box.innerHTML='';let lines=raw.split(/\\r?\\n/).filter(Boolean);if(!lines.length){box.innerHTML='<div class="terminal-empty">No session events yet.</div>';return}lines.forEach((line,i)=>{let row=document.createElement('div');row.className='terminal-line';let n=document.createElement('span');n.className='line-no';n.textContent=String(i+1).padStart(2,'0');let text=document.createElement('span');text.textContent=line;let low=line.toLowerCase();text.className=low.includes('iris:')?'reply':low.includes('you said')?'heard':low.includes('listening')||low.includes('understanding')?'event':'system';row.append(n,text);box.append(row)});box.scrollTop=box.scrollHeight}
async function refresh(){let s=await fetch('/api/status').then(r=>r.json());document.querySelector('#state').textContent=s.state.replaceAll('_',' ');document.querySelector('#dot').style.background=s.color;document.querySelector('#session').textContent=s.session;document.querySelector('#updated').textContent=s.updated;renderLogs(s.logs)}
async function post(url){let r=await fetch(url,{method:'POST'});document.querySelector('#reply').textContent=await r.text();setTimeout(refresh,400)}
async function send(){let c=document.querySelector('#command').value.trim();if(!c)return;let r=await fetch('/api/command',{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},body:'command='+encodeURIComponent(c)});document.querySelector('#reply').textContent=await r.text();document.querySelector('#command').value='';setTimeout(refresh,500)}
refresh();setInterval(refresh,2000)
</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    def send_text(self, body: str, status: int = 200, content_type: str = "text/plain") -> None:
        data = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", f"{content_type}; charset=utf-8")
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        if self.path == "/":
            self.send_text(PAGE, content_type="text/html")
        elif self.path == "/api/status":
            colours = {"listening":"#facc15","recording":"#f59e0b","thinking":"#fde047","speaking":"#facc15","muted":"#737373"}
            try:
                modified = LOG_PATH.stat().st_mtime
                session = __import__("datetime").datetime.fromtimestamp(modified).strftime("%d %b %Y, %H:%M")
                updated = __import__("datetime").datetime.now().strftime("%H:%M:%S")
            except OSError:
                session, updated = "Not started", "—"
            current = state()
            self.send_text(json.dumps({"state": current, "color": colours.get(current, "#737373"), "logs": logs(), "session": session, "updated": updated}), content_type="application/json")
        else:
            self.send_text("Not found", 404)

    def do_POST(self) -> None:
        if self.path == "/api/mute":
            if MUTE_PATH.exists(): MUTE_PATH.unlink(missing_ok=True); STATE_PATH.write_text('{"state":"listening"}', encoding="utf-8")
            else: MUTE_PATH.touch(); STATE_PATH.write_text('{"state":"muted"}', encoding="utf-8")
            self.send_text("Mute state changed.")
        elif self.path == "/api/restart":
            RESTART_PATH.touch()
            self.send_text("Restart requested through the tray controller.")
        elif self.path == "/api/command":
            length = int(self.headers.get("Content-Length", "0"))
            command = urllib.parse.parse_qs(self.rfile.read(length).decode()).get("command", [""])[0].strip()
            if not command or len(command) > 300: self.send_text("Enter a short command.", 400); return
            threading.Thread(target=run_command, args=(command,), daemon=True).start()
            self.send_text("Command sent to Iris.")
        else:
            self.send_text("Not found", 404)

    def log_message(self, *_: object) -> None: pass


if __name__ == "__main__":
    print(f"Iris dashboard: http://{HOST}:{PORT}")
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
