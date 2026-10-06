"""Local developer workspace: tool discovery and explicitly submitted jobs."""
import json
import os
import shutil
import subprocess
import threading
import uuid
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / 'data' / 'dev'
TOOLS = {'code': 'VS Code', 'cursor': 'Cursor', 'windsurf': 'Windsurf',
         'codex': 'Codex CLI', 'claude': 'Claude Code', 'gemini': 'Gemini CLI',
         'aider': 'Aider', 'ollama': 'Ollama', 'git': 'Git',
         'python': 'Python', 'node': 'Node.js', 'npm': 'npm'}
EDITORS = {'code', 'cursor', 'windsurf'}
AGENTS = {'codex', 'claude', 'gemini', 'aider'}

def discover():
    result = []
    for key, label in TOOLS.items():
        path = shutil.which(key)
        if key == 'ollama' and not path and Path('E:/codex/ollama/ollama.exe').exists():
            path = 'E:/codex/ollama/ollama.exe'
        result.append(dict(id=key, name=label, path=path, installed=bool(path)))
    return result

def workspace(value):
    path = Path(value).resolve(strict=True)
    if not path.is_dir() or path.drive.upper() not in {'D:', 'E:'}:
        raise ValueError('Choose an existing project folder on D: or E:.')
    return path

def psquote(value):
    return "'" + str(value).replace("'", "''") + "'"

def job_environment(interactive):
    environment = os.environ.copy()
    if interactive:
        # A newly created Windows console must not inherit a noninteractive TERM.
        if environment.get('TERM', '').lower() in {'', 'dumb'}:
            environment['TERM'] = 'xterm-256color'
    return environment

def agent_arguments(key, executable):
    # The desktop app's extracted CLI lacks the standalone daemon package.
    # Its documented --no-daemon mode runs the interactive CLI directly.
    normalized = str(executable).replace('\\', '/').casefold()
    if key == 'codex' and '/openai/codex/bin/' in normalized:
        return ' --no-daemon'
    return ''

class Jobs:
    def __init__(self):
        self.lock = threading.RLock()
        self.items = {}
        self.processes = {}
        DATA.mkdir(parents=True, exist_ok=True)
        for path in DATA.glob('*.json'):
            try:
                item = json.loads(path.read_text(encoding='utf-8'))
                if item['status'] == 'running':
                    item['status'] = 'untracked after dashboard restart'
                self.items[item['id']] = item
            except (ValueError, KeyError, OSError):
                continue

    def save(self, item):
        target = DATA / (item['id'] + '.json')
        temporary = target.with_suffix('.tmp')
        temporary.write_text(json.dumps(item), encoding='utf-8')
        temporary.replace(target)

    def start(self, command, cwd, interactive=False):
        cwd = workspace(cwd)
        if not isinstance(command, str) or not command.strip() or len(command) > 8000:
            raise ValueError('Enter a command of at most 8000 characters.')
        with self.lock:
            if len(self.processes) >= 8:
                raise ValueError('Stop an active job before starting another (limit: 8).')
            key = uuid.uuid4().hex
            log = DATA / (key + '.log')
            script = DATA / (key + '.ps1')
            script.write_text(command, encoding='utf-8-sig')
            args = ['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass']
            if interactive:
                args.append('-NoExit')
            args += ['-File', str(script)]
            with log.open('ab') as output:
                process = subprocess.Popen(args, cwd=cwd, stdin=None if interactive else subprocess.DEVNULL,
                    env=job_environment(interactive),
                    stdout=None if interactive else output, stderr=None if interactive else subprocess.STDOUT,
                    creationflags=subprocess.CREATE_NEW_CONSOLE if interactive else subprocess.CREATE_NO_WINDOW)
            item = dict(id=key, command=command, cwd=str(cwd), status='running',
                        started=datetime.now().astimezone().isoformat(timespec='seconds'),
                        exit_code=None, interactive=interactive)
            self.items[key] = item
            self.processes[key] = process
            self.save(item)
        threading.Thread(target=self.wait, args=(key, process), daemon=True).start()
        return item.copy()

    def wait(self, key, process):
        code = process.wait()
        with self.lock:
            item = self.items[key]
            if item['status'] == 'running':
                item['status'] = 'finished' if code == 0 else 'failed'
            item['exit_code'] = code
            self.processes.pop(key, None)
            self.save(item)

    def stop(self, key):
        with self.lock:
            process = self.processes.get(key)
            if process is None or process.poll() is not None:
                raise ValueError('This job is no longer managed or has finished.')
            subprocess.run(['taskkill.exe', '/PID', str(process.pid), '/T', '/F'],
                           check=True, capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
            self.items[key]['status'] = 'stopped'
            self.save(self.items[key])

    def snapshot(self):
        with self.lock:
            result = []
            for item in sorted(self.items.values(), key=lambda i: i['started'], reverse=True)[:50]:
                row = item.copy()
                try:
                    with (DATA / (row['id'] + '.log')).open('rb') as stream:
                        stream.seek(0, 2)
                        stream.seek(max(0, stream.tell() - 16000))
                        row['output'] = stream.read().decode('utf-8', errors='replace')
                except OSError:
                    row['output'] = ''
                row['can_stop'] = row['id'] in self.processes
                result.append(row)
            return result

    def session(self, folder, editor, agent):
        folder = workspace(folder)
        installed = {t['id']: t['path'] for t in discover()}
        commands = []
        for key, allowed, interactive in [(editor, EDITORS, False), (agent, AGENTS, True)]:
            if not key:
                continue
            if key not in allowed or not installed.get(key):
                raise ValueError('Selected tool is not installed or supported: ' + key)
            command = '& ' + psquote(installed[key])
            command += agent_arguments(key, installed[key])
            if key in EDITORS:
                command += ' ' + psquote(folder)
            commands.append((command, interactive))
        if not commands:
            raise ValueError('Select an installed editor or agent.')
        return [self.start(command, str(folder), interactive) for command, interactive in commands]
