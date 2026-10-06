"""Project profiles and validated voice actions, owned by the task service."""
import json
import re
import threading
from datetime import datetime
from iris_intents import developer_language, interpret, canonical
from pathlib import Path
from iris_dev import ROOT, Jobs, workspace

class Tasks:
    def __init__(self, jobs=None, profile_file=None):
        self.jobs = jobs or Jobs()
        self.path = profile_file or ROOT / 'data' / 'projects.json'
        self.lock = threading.RLock()
        if self.path.exists():
            self.profiles = json.loads(self.path.read_text(encoding='utf-8'))
        else:
            self.profiles = {'iris': {'name': 'iris', 'cwd': str(ROOT), 'editor': 'code',
                'agent': 'codex', 'commands': {'tests': "& '.\\.venv\\Scripts\\python.exe' -B -m unittest discover -v"}}}
        self.active = 'iris'
        self.last_ids = []
        self.pending = None
        self.context_path = self.path.with_name('task-context.json')
        self.events_path = self.path.with_name('task-events.jsonl')
        try:
            context = json.loads(self.context_path.read_text(encoding='utf-8'))
            if context.get('active') in self.profiles:
                self.active = context['active']
            self.last_ids = context.get('last_ids', [])
        except (OSError, ValueError, TypeError):
            pass

    def remember(self, text, reply):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.context_path.with_suffix('.tmp')
        temporary.write_text(json.dumps({'active':self.active,'last_ids':self.last_ids}), encoding='utf-8')
        temporary.replace(self.context_path)
        with self.events_path.open('a', encoding='utf-8') as stream:
            stream.write(json.dumps({'time':datetime.now().astimezone().isoformat(timespec='seconds'), 'request':text, 'reply':reply}) + '\n')

    def events(self):
        try:
            with self.events_path.open('rb') as stream:
                stream.seek(0, 2)
                size = stream.tell()
                stream.seek(max(0, size - 32000))
                lines = stream.read().decode('utf-8', errors='replace').splitlines()
                if size > 32000: lines = lines[1:]
            return [json.loads(line) for line in lines[-40:]]
        except (OSError, ValueError): return []

    def save_profile(self, profile):
        name = str(profile['name']).strip().lower()
        if not re.fullmatch(r'[a-z0-9][a-z0-9 -]{0,59}', name):
            raise ValueError('Use a short project name with letters, numbers, spaces or hyphens.')
        cwd = str(workspace(profile['cwd']))
        if profile.get('editor', '') not in {'', 'code', 'cursor', 'windsurf'} or profile.get('agent', '') not in {'', 'codex', 'claude', 'gemini', 'aider'}:
            raise ValueError('Select a supported editor and agent.')
        commands = profile.get('commands', {})
        if not isinstance(commands, dict) or any(k not in {'tests', 'server', 'build'} or not isinstance(v, str) or len(v) > 8000 for k, v in commands.items()):
            raise ValueError('Only tests, server and build commands are supported.')
        item = dict(name=name, cwd=cwd, editor=profile.get('editor', ''), agent=profile.get('agent', ''), commands=commands)
        with self.lock:
            updated = {**self.profiles, name: item}
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_suffix('.tmp')
            temporary.write_text(json.dumps(updated, indent=2), encoding='utf-8')
            temporary.replace(self.path)
            self.profiles = updated
        return item

    def voice(self, text):
        if not isinstance(text, str) or not 0 < len(text) <= 1000:
            raise ValueError('Give me a short voice request.')
        with self.lock:
            reply = self._voice(text)
            projects, active = dict(self.profiles), self.active
        if reply is None and developer_language(text):
            intent = interpret(text, projects, active)
            translated = canonical(intent)
            if translated:
                with self.lock:
                    reply = self._voice(translated)
            else:
                reply = 'I could not match that to one supported developer action. Please rephrase it.'
        if reply is not None:
            with self.lock: self.remember(text, reply)
        return reply

    def _voice(self, text):
        text = re.sub(r'[.!?]+$', '', text.strip().lower())
        text = re.sub(r'^(?:hey iris[, ]+|please )', '', text)
        text = text.replace('vs code', 'vscode').replace('visual studio code', 'vscode')
        if re.search(r'\b(note|screenshot|spotify|volume|timer|google|youtube)\b', text):
            return None
        if re.match(r'(?:how (?:do|can|would)|explain|tell me how|what would happen|if I)\b', text, re.I):
            return 'That sounds like a question rather than an execution request. Say start coding, run tests, or check a port when you want me to act.'
        if text in {'cancel', 'cancel that', 'never mind', 'nevermind'}:
            self.pending = None
            return 'Cancelled the pending request. Running jobs were left running.'
        if re.search(r"\b(don't|do not|never|stop trying to)\b", text):
            return 'Okay. I have not started an action.'
        if self.pending and text in self.profiles:
            previous = self.pending
            self.pending = None
            self.active = text
            return self._voice(previous + ' for ' + text)
        if text in {'what projects do you know', 'list projects'}:
            return 'Saved projects: ' + ', '.join(self.profiles)
        if re.search(r'\b(what|list|show)\b.*\b(tasks|jobs)\b', text):
            running = [j for j in self.jobs.snapshot() if j['can_stop']]
            return ('Running: ' + '; '.join(j.get('label', j['command'][:70]) for j in running)) if running else 'No managed tasks are running.'
        if text in {'did they pass', 'did the tests pass', 'is it done', 'task status', 'did it finish'}:
            items = [j for j in self.jobs.snapshot() if j['id'] in self.last_ids]
            if not items:
                return 'There is no recent task to report.'
            return '; '.join(j.get('label', 'Task') + ': ' + j['status'] + (f", exit code {j['exit_code']}" if j['exit_code'] is not None else '') for j in items)
        if re.match(r'stop\b', text) and re.search(r'\b(task|job|server|tests)\b', text):
            items = [j for j in self.jobs.snapshot() if j['can_stop']]
            if 'server' in text:
                items = [j for j in items if j.get('label') == self.active + ' server']
            else:
                items = [j for j in items if j['id'] in self.last_ids]
            if len(items) != 1:
                return 'Please choose the exact job using its Stop button in the dashboard.'
            self.jobs.stop(items[0]['id'])
            return 'Stopped ' + items[0].get('label', 'the job') + '.'
        port = re.search(r'\bport\s+(\d{1,5})\b', text)
        if port and re.search(r'\b(what|show|check|using)\b', text):
            number = int(port[1])
            if not 1 <= number <= 65535:
                return 'Port numbers must be between 1 and 65535.'
            command = f"Get-NetTCPConnection -LocalPort {number} -ErrorAction SilentlyContinue | Select-Object LocalAddress,LocalPort,State,OwningProcess | Format-Table -AutoSize"
            return self.start_job(command, str(ROOT), f'Port {number} diagnostic')
        kind = None
        if re.search(r'\b(start|open|launch|begin)\b.*\b(coding|session|workspace)\b', text):
            kind = 'session'
        elif re.search(r'\b(run|start)\b.*\btests?\b', text):
            kind = 'tests'
        elif re.search(r'\b(start|run)\b.*\bserver\b', text):
            kind = 'server'
        elif re.search(r'\b(build|compile)\b.*\b(project|it|iris)\b', text):
            kind = 'build'
        if not kind:
            return None
        if re.search(r'\b(?:and then|then|also)\b', text):
            return 'Please give me one developer action at a time for now.'
        # Explicit unknown project names never fall back to the active project.
        project_match = re.search(r'\b(?:on|for)\s+(.+?)(?:\s+(?:with|using)\b|$)', text)
        name = self.active
        if project_match:
            requested = re.sub(r'^(my |the )', '', project_match[1]).strip()
            if requested not in {'this project', 'the project', 'it'}:
                name = requested
        if name not in self.profiles:
            self.pending = re.split(r'\b(?:on|for)\b', text)[0].strip()
            return 'I do not know that project. Say one of: ' + ', '.join(self.profiles)
        profile = self.profiles[name]
        self.active = name
        if kind == 'session':
            selection = re.search(r'\b(?:with|using)\s+(.+)$', text)
            if selection:
                # Repair speech aliases only within the explicit tool selection;
                # never rewrite project names or saved shell commands.
                tools = re.sub(r'\b(?:codecs|code x|codex cli)\b', 'codex', selection[1])
                tools = re.sub(r'\b(?:please|the|editor|agent)\b', '', tools)
                text = text[:selection.start(1)] + tools
                selection = re.search(r'\b(?:with|using)\s+(.+)$', text)
                if selection is None:
                    return 'Please name the editor or agent you want to use.'
                words = set(re.findall(r'[a-z]+', selection[1]))
                if words - {'vscode','code','cursor','windsurf','codex','claude','gemini','aider','and'}:
                    return 'I did not recognize those coding tools. Choose them in the developer workspace.'
            editor, agent = profile['editor'], profile['agent']
            for spoken, key in {'vscode':'code', 'cursor':'cursor', 'windsurf':'windsurf'}.items():
                if re.search(r'\b' + spoken + r'\b', text): editor = key
            for spoken, key in {'codex':'codex', 'claude':'claude', 'gemini':'gemini', 'aider':'aider'}.items():
                if re.search(r'\b' + spoken + r'\b', text): agent = key
            items = self.jobs.session(profile['cwd'], editor, agent)
            self.last_ids = [j['id'] for j in items]
            return 'Requested the coding tools for ' + name + '. The agent opens in its own terminal. Check job history for launch results.'
        command = profile['commands'].get(kind, '').strip()
        if not command:
            return f'No {kind} command is saved for {name}. Add it in Project profiles first.'
        if kind == 'server' and any(j.get('label') == name + ' server' and j['can_stop'] for j in self.jobs.snapshot()):
            return 'That project already has a server job running.'
        return self.start_job(command, profile['cwd'], name + ' ' + kind)

    def start_job(self, command, cwd, label):
        item = self.jobs.start(command, cwd)
        with self.jobs.lock:
            self.jobs.items[item['id']]['label'] = label
            self.jobs.save(self.jobs.items[item['id']])
        self.last_ids = [item['id']]
        return 'Started ' + label + '. Results will appear in job history. Ask task status to check completion.'

    def dispatch(self, action, data):
        # Model interpretation can be slow; keep stop/status requests available.
        if action == 'voice': return self.voice(data['text'])
        with self.lock:
            if action == 'snapshot': return self.jobs.snapshot()
            if action == 'profiles': return list(self.profiles.values())
            if action == 'save_profile': return self.save_profile(data)
            if action == 'events': return self.events()
            if action == 'start': return self.jobs.start(data['command'], data['cwd'], data.get('interactive', False))
            if action == 'session': return self.jobs.session(data['cwd'], data['editor'], data['agent'])
            if action == 'stop': return self.jobs.stop(data['id'])
            raise ValueError('Unknown task action.')
