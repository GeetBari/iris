"""JSON client shared by voice and dashboard. No remote network endpoint."""
import json
import subprocess
import threading
import time
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
from iris_dev import ROOT

LOCK = threading.Lock()

def request(action, data=None):
    token = (ROOT / 'data' / 'task-service.token').read_text(encoding='utf-8')
    payload = json.dumps({'action': action, 'data': data or {}}).encode()
    req = Request('http://127.0.0.1:8766/', data=payload, headers={'X-Iris-Service': token, 'Content-Type':'application/json'})
    try:
        with urlopen(req, timeout=75 if action == 'voice' else 15) as response: result = json.load(response)
    except HTTPError as error:
        if error.code == 400:
            raise ValueError(json.loads(error.read())['error']) from error
        raise
    return result['result']

def ensure_service():
    with LOCK:
        try:
            request('profiles')
            return
        except (OSError, URLError): pass
        folder = ROOT / 'data'
        folder.mkdir(exist_ok=True)
        with (folder / 'task-service.log').open('ab') as log:
            subprocess.Popen([str(ROOT / '.venv/Scripts/python.exe'), '-u', str(ROOT / 'iris_task_service.py')], cwd=ROOT,
                             stdout=log, stderr=log, creationflags=subprocess.CREATE_NO_WINDOW)
        for _ in range(40):
            time.sleep(.1)
            try:
                request('profiles')
                return
            except (OSError, URLError): pass
        raise OSError('Task service could not start. See data/task-service.log.')

def call(action, data=None):
    ensure_service()
    # Do not retry a mutation: a lost response must not launch a duplicate job.
    return request(action, data)

class SharedJobs:
    def snapshot(self): return call('snapshot')
    def start(self, command, cwd, interactive=False): return call('start', dict(command=command,cwd=cwd,interactive=interactive))
    def session(self, cwd, editor, agent): return call('session', dict(cwd=cwd,editor=editor,agent=agent))
    def stop(self, key): return call('stop', {'id':key})
