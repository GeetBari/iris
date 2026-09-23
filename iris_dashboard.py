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
body{margin:0;background:#0f172a;color:#e2e8f0;font:15px system-ui,Segoe UI,sans-serif}
main{max-width:1100px;margin:0 auto;padding:28px}.top{display:flex;justify-content:space-between;align-items:center;gap:16px}
h1{margin:0;font-size:30px}.muted{color:#94a3b8}.grid{display:grid;grid-template-columns:1fr 2fr;gap:18px;margin-top:22px}
.card{background:#1e293b;border:1px solid #334155;border-radius:14px;padding:18px;box-shadow:0 8px 24px #02061755}
.state{display:inline-flex;align-items:center;gap:9px;font-size:22px;font-weight:700}.dot{width:14px;height:14px;border-radius:50%;background:#22c55e}
button{background:#38bdf8;border:0;border-radius:8px;padding:10px 14px;margin:5px 4px 0 0;font-weight:700;cursor:pointer}button.alt{background:#475569;color:#fff}
input{box-sizing:border-box;width:100%;padding:13px;border-radius:8px;border:1px solid #475569;background:#0f172a;color:#fff;margin-top:12px}
pre{height:420px;overflow:auto;background:#020617;border-radius:8px;padding:14px;white-space:pre-wrap;color:#cbd5e1}
@media(max-width:750px){.grid{grid-template-columns:1fr}}
</style></head><body><main>
<div class="top"><div><h1>Iris Control Center</h1><div class="muted">Local dashboard — loopback only</div></div><button onclick="refresh()">Refresh</button></div>
<div class="grid"><section class="card"><div class="muted">CURRENT STATE</div><p class="state"><span class="dot" id="dot"></span><span id="state">Loading...</span></p>
<button onclick="post('/api/restart')">Restart Iris</button><button class="alt" onclick="post('/api/mute')">Mute / Resume</button>
<h3>Command console</h3><div class="muted">Send a normal Iris command without using the microphone.</div>
<input id="command" placeholder="e.g. open calculator" onkeydown="if(event.key==='Enter')send()"><button onclick="send()">Send command</button><pre id="reply">Ready.</pre></section>
<section class="card"><div class="muted">LIVE LOG</div><pre id="logs">Loading...</pre></section></div></main>
<script>
async function refresh(){let s=await fetch('/api/status').then(r=>r.json());document.querySelector('#state').textContent=s.state.replaceAll('_',' ');document.querySelector('#dot').style.background=s.color;document.querySelector('#logs').textContent=s.logs}
async function post(url){let r=await fetch(url,{method:'POST'});document.querySelector('#reply').textContent=await r.text();setTimeout(refresh,400)}
async function send(){let c=document.querySelector('#command').value.trim();if(!c)return;let r=await fetch('/api/command',{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},body:'command='+encodeURIComponent(c)});document.querySelector('#reply').textContent=await r.text();document.querySelector('#command').value='';setTimeout(refresh,500)}
refresh();setInterval(refresh,2000)
</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    def send_text(self, body: str, status: int = 200, content_type: str = "text/plain") -> None:
        data = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", f"{content_type}; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        if self.path == "/":
            self.send_text(PAGE, content_type="text/html")
        elif self.path == "/api/status":
            colours = {"listening":"#22c55e","recording":"#ef4444","thinking":"#a855f7","speaking":"#06b6d4","muted":"#dc2626"}
            self.send_text(json.dumps({"state": state(), "color": colours.get(state(), "#64748b"), "logs": logs()}), content_type="application/json")
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
