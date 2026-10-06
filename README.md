     # Iris — Local Voice Assistant

A free, local-first Windows assistant. Iris uses Whisper for offline speech recognition and Qwen for local natural-language understanding, while retaining a strict safe-action boundary.

## Development update

Iris is actively developed on Windows with its models, notes, screenshots, and
runtime kept on a non-system drive. The public repository tracks source and
setup files only; private runtime data and downloaded models remain excluded.

## What it can do now

* `open chrome`
* `open brave`
* `open notepad`
* `open calculator`
* `open youtube`
* `search youtube for lo-fi music`
* `search google for weather in delhi`
* `play relaxing music on Spotify` — opens Spotify directly to a music search.
* `voice` — speak naturally, then pause to submit the command, e.g. `could you fire up Discord?`
* Spoken replies — Iris uses the built-in Windows offline voice by default.
* `handsfree` — enables the local “Hey Iris” wake word; press `Ctrl+C` for an immediate stop.
* `take a note saying buy milk` — saves a private text note under `data/notes`.
* `set a timer for five minutes`
* `turn the volume up`, `turn the volume down`, or `mute the volume`
* `take a screenshot` — saves it under `data/screenshots`.
* `open my Downloads folder` or `open the Iris README file`
* `help`
* `quit`

Iris can open any unambiguous application listed in your Windows Start menu; the built-in list is only for trusted websites and reliable shortcuts. For example, try `open Discord` or `open Steam` without adding them first.

## Run it

For the hands-free tray app, double-click `run_iris_tray.bat`. The tray icon
shows Iris's current state; right-click it to mute, resume, restart, or quit.
Use only one Iris launcher at a time.

For the original terminal interface, double-click `run_iris.bat`, or open
PowerShell in this folder and run:

```powershell
.\.venv\Scripts\python.exe assistant.py
```

For the local control center, double-click `run_iris_dashboard.bat`. It opens
`http://127.0.0.1:8765` with Iris's state, recent logs, mute/restart controls,
and a command console. The dashboard binds only to this PC.

## Setup on another Windows PC

Iris requires Python 3.11+ and an Ollama-compatible local model server. Keep
models on a non-system drive by setting `OLLAMA_MODELS` before downloading a
model. Create an environment and install the Python requirements:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Install Ollama, start its local server, and download the model used by Iris:

```powershell
ollama pull qwen3:4b
```

The first use of voice mode downloads Whisper's English model into `models`.
It is intentionally excluded from Git because it is a large, reproducible
download.

No API keys, subscriptions, or internet accounts are needed. Voice recognition and language understanding run on this PC. Searches and web sites naturally require an internet connection once opened.

## Roadmap

### Developer workspace

Voice task controls now use a separate local task service. Say “Hey Iris”, wait
for the response, then “start coding on Iris with VS Code and Codex”, “run tests
for Iris”, “task status”, “what tasks are running”, “show what is using port
3000”, or “stop the task I just started”. Follow-up test requests use the active
project. Unknown project names prompt for a saved name; repeat the wake word
before answering. Common patterns work directly; developer paraphrases use the
local Qwen model when Ollama is running. Model output is restricted to supported
actions and saved projects. Active project and recent task context persist on E:.

Use Project profiles in `/dev` to save a name, folder, tools and test/server/build
commands. Saving approves those exact commands for later voice execution.
The default Iris profile includes its test command; server/build commands are
unset until you configure them. Job results appear in the same history whether
started by voice or dashboard. Jobs survive dashboard restarts while the task
service remains running. Restart the Iris tray worker after updating voice code.

Open `/dev` from the running local dashboard (or use its Developer Workspace
link). Select an existing project folder on E: or D:, then choose installed
editors and agents. VS Code, Cursor, Windsurf, Codex CLI, Claude Code, Gemini CLI,
and Aider launchers are supported when available on PATH. Ollama is detected
as a local model runtime; use the reviewed command box for its commands.

Interactive agents open their own terminal. Background PowerShell jobs show
output, completion status, and Stop controls in the workspace. Job history is
stored privately under `data/dev`. Restarting the task service itself loses control
of active jobs; they are labeled untracked and may still be running. Review the displayed
command before execution. Execution uses the dashboard's existing Windows
permissions; launch Iris as a normal user. External tools may require accounts
or paid subscriptions; detection does not install or sign into them.

Say “open developer workspace” to open this page when the dashboard is running.
Use Save selections to remember your project/editor/agent in this browser.

1. **Current:** safe typed-command, voice, natural-language, and Start-menu app launcher.
2. Offline spoken replies using Piper.
3. Optional wake word, with a visible microphone indicator.

Do not give the assistant arbitrary shell-command or file-delete access. Keep destructive actions behind confirmation prompts.
