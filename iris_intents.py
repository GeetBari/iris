"""Local-model interpretation into a small validated developer action vocabulary."""
import json
import re
from urllib.request import Request, urlopen

ACTIONS = {'session', 'tests', 'server', 'build', 'port', 'list', 'status', 'stop', 'unknown'}
EDITORS = {'', 'code', 'cursor', 'windsurf'}
AGENTS = {'', 'codex', 'claude', 'gemini', 'aider'}

def developer_language(text):
    if re.search(r'\b(note|screenshot|spotify|volume|timer|google|youtube)\b', text, re.I):
        return False
    return bool(re.search(r'\b(coding|code|codex|claude|gemini|aider|cursor|windsurf|project|workspace|dev|development|server|tests?|build|compile|port|jobs?|tasks?|setup)\b', text, re.I))

def validate(intent, projects, active):
    if not isinstance(intent, dict) or intent.get('action') not in ACTIONS:
        raise ValueError('I could not identify a supported developer action.')
    if set(intent) - {'action','project','editor','agent','port'}:
        raise ValueError('I could not validate that developer request. Please rephrase it.')
    result = {**intent}
    result['project'] = result.get('project') or active
    if isinstance(result['project'], str): result['project'] = result['project'].strip().lower()
    if result['project'] not in projects:
        raise ValueError('Unknown project. Saved projects: ' + ', '.join(projects))
    if result.get('editor', '') not in EDITORS or result.get('agent', '') not in AGENTS:
        raise ValueError('I did not recognize the requested editor or agent.')
    if result['action'] == 'port' and (type(result.get('port')) is not int or not 1 <= result['port'] <= 65535):
        raise ValueError('I need a port number between 1 and 65535.')
    return result

def interpret(text, projects, active):
    system = ('Interpret one developer request. Return a JSON object only. '
        'Allowed action: session, tests, server, build, port, list, status, stop, unknown. '
        'Use unknown for negation, hypothetical questions, instructions explaining how to do something, '
        'multiple actions, ordinary app requests, or unsupported operations. '
        'Fields: action, project, editor, agent, port. Never produce shell commands. '
        'Project is the explicitly requested name, or the active name when omitted. Never substitute a different project. '
        'Editor values: code, cursor, windsurf, or empty string for saved default. '
        'Agent values: codex, claude, gemini, aider, or empty string for saved default. '
        'port must be an integer only for port diagnostics. stop means stop the most recent managed job. '
        'A session opens the project editor and coding agent. Tests/server/build use saved commands. '
        'Saved projects: ' + json.dumps(list(projects)) + '. Active: ' + active)
    request = Request('http://127.0.0.1:11434/api/chat', data=json.dumps({
        'model':'qwen3:4b','stream':False,'think':False,'format':'json',
        'options':{'temperature':0},'messages':[{'role':'system','content':system},{'role':'user','content':text}]
    }).encode(), headers={'Content-Type':'application/json'})
    try:
        with urlopen(request, timeout=60) as response:
            content = json.load(response)['message']['content']
        return validate(json.loads(content), projects, active)
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise ValueError('I could not interpret that request locally. Try start coding on Iris, run tests for Iris, or task status.') from error

def canonical(intent):
    action, project = intent['action'], intent['project']
    if action == 'session':
        tools = [({'code':'vscode'}.get(intent.get('editor'), intent.get('editor'))), intent.get('agent')]
        suffix = ' with ' + ' and '.join(t for t in tools if t) if any(tools) else ''
        return 'start coding on ' + project + suffix
    if action in {'tests','server'}: return 'run ' + action + ' for ' + project
    if action == 'build': return 'build project for ' + project
    if action == 'port': return 'check port ' + str(intent['port'])
    return {'list':'list tasks','status':'task status','stop':'stop the last task'}.get(action)
