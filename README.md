# Iris — Local Voice Assistant

A free, local-first Windows assistant. Iris uses Whisper for offline speech recognition and Qwen for local natural-language understanding, while retaining a strict safe-action boundary.

## What it can do now

* `open chrome`
* `open brave`
* `open notepad`
* `open calculator`
* `open youtube`
* `search youtube for lo-fi music`
* `search google for weather in delhi`
* `play relaxing music on Spotify` — opens Spotify directly to a music search.
* `voice` — then speak naturally within six seconds, e.g. `could you fire up Discord?`
* `help`
* `quit`

Iris can open any unambiguous application listed in your Windows Start menu; the built-in list is only for trusted websites and reliable shortcuts. For example, try `open Discord` or `open Steam` without adding them first.

## Run it

Double-click `run_iris.bat`, or open PowerShell in this folder and run:

```powershell
.\.venv\Scripts\python.exe assistant.py
```

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

1. **Current:** safe typed-command, voice, natural-language, and Start-menu app launcher.
2. Offline spoken replies using Piper.
3. Optional wake word, with a visible microphone indicator.

Do not give the assistant arbitrary shell-command or file-delete access. Keep destructive actions behind confirmation prompts.
