"""Agent adapters: quoted launch plans and readable streamed events."""
import json
from iris_dev import psquote, agent_arguments

def codex_command(executable, prompt_path, result_path, mode):
    if mode not in {'read-only', 'workspace-write'}:
        raise ValueError('Choose read-only or workspace-write.')
    # Prompt content goes through stdin, never through PowerShell evaluation.
    return ("$OutputEncoding = [System.Text.UTF8Encoding]::new(); "
        "Get-Content -LiteralPath " + psquote(prompt_path) + " -Raw -Encoding UTF8 | & " + psquote(executable)
        + agent_arguments('codex', executable)
        + " exec --json --ephemeral --color never --sandbox " + mode
        + " --output-last-message " + psquote(result_path) + " -")

def readable_events(raw):
    lines = []
    for line in raw.splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            lines.append(line)
            continue
        if not isinstance(event, dict):
            continue
        kind = event.get('type', 'event')
        item = event.get('item', {})
        if kind in {'item.started', 'item.updated', 'item.completed'} and isinstance(item, dict):
            label = item.get('type', 'activity')
            content = item.get('text') or item.get('command') or item.get('aggregated_output')
            if not content and item.get('changes'):
                content = json.dumps(item['changes'], ensure_ascii=False)
            if content: lines.append(label + ': ' + str(content))
        elif kind in {'error', 'turn.failed'}:
            lines.append('Error: ' + str(event.get('message') or event.get('error', 'Agent failed')))
        elif kind in {'thread.started','turn.started','turn.completed'}:
            lines.append(kind.replace('.', ' '))
    return '\n'.join(lines)
