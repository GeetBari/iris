"""A safe, free starter assistant for Windows.

This intentionally uses an allowlist instead of executing arbitrary commands.
"""

from __future__ import annotations

import json
import subprocess
import sys
import urllib.parse
import webbrowser
import wave
from difflib import get_close_matches
from pathlib import Path
import re
from urllib.error import URLError
from urllib.request import Request, urlopen


# Add only applications or sites you trust. Values can be a URL, an executable,
# or a Windows command such as "notepad.exe".
APPS: dict[str, str] = {
    "browser": "https://www.google.com",
    "brave": r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
    "chrome": "chrome.exe",
    "notepad": "notepad.exe",
    "calculator": "calc.exe",
    "youtube": "https://www.youtube.com",
}

MODEL_PATH = Path(__file__).parent / "models" / "vosk-model-small-en-us-0.15"
WHISPER_CACHE_DIR = Path(__file__).parent / "models" / "whisper"
RECORDING_PATH = Path(__file__).parent / "iris-command.wav"
OLLAMA_URL = "http://127.0.0.1:11434/api/chat"
OLLAMA_MODEL = "qwen3:4b"


def listen_for_command(seconds: int = 6) -> str:
    """Record a short command and transcribe it locally with Whisper."""
    try:
        import sounddevice as sd
        from faster_whisper import WhisperModel
    except ImportError:
        return "Whisper voice support is not installed. Run run_iris.bat from this folder."

    sample_rate = 16_000
    print(f"Iris is listening for {seconds} seconds. Speak now...")
    try:
        audio = sd.rec(
            int(seconds * sample_rate), samplerate=sample_rate,
            channels=1, dtype="int16"
        )
        sd.wait()
    except Exception as error:
        return f"I couldn't use the microphone: {error}"

    try:
        with wave.open(str(RECORDING_PATH), "wb") as recording:
            recording.setnchannels(1)
            recording.setsampwidth(2)
            recording.setframerate(sample_rate)
            recording.writeframes(audio.tobytes())
        print("Iris is understanding what you said...")
        model = WhisperModel(
            "small.en", device="cpu", compute_type="int8",
            download_root=str(WHISPER_CACHE_DIR),
        )
        segments, _ = model.transcribe(
            str(RECORDING_PATH), language="en", beam_size=5,
            vad_filter=True, condition_on_previous_text=False,
        )
        heard = " ".join(segment.text.strip() for segment in segments).strip()
        return heard or "I didn't catch that. Please try voice again."
    except Exception as error:
        return f"I couldn't understand the recording: {error}"
    finally:
        RECORDING_PATH.unlink(missing_ok=True)


def ask_iris_brain(command: str) -> dict[str, str] | None:
    """Translate natural language into one safe, structured action locally."""
    system = """You are Iris, a Windows assistant. Return exactly one JSON object.
Allowed actions are: open_app, search_google, search_youtube, search_spotify,
chat, unknown.
For open_app, the JSON is {"action":"open_app","argument":"app name"}.
For every search, the JSON is {"action":"search_name","argument":"query"}.
Use search_spotify whenever the user asks to play, find, or search for music,
an artist, an album, or a playlist on Spotify.
For chat, argument is a brief helpful reply. Never suggest shell commands, file
operations, purchases, messages, settings changes, or any action not listed."""
    payload = json.dumps({
        "model": OLLAMA_MODEL,
        "stream": False,
        "think": False,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": command},
        ],
    }).encode("utf-8")
    request = Request(OLLAMA_URL, data=payload, headers={"Content-Type": "application/json"})
    try:
        with urlopen(request, timeout=90) as response:
            content = json.loads(response.read())['message']['content'].strip()
        # Some local Qwen variants prefix their answer with a thinking trace.
        # The final JSON object remains the only part Iris is allowed to act on.
        objects = re.findall(r"\{[^{}]*\}", content, flags=re.DOTALL)
        action = json.loads(objects[-1])
    except (URLError, TimeoutError, KeyError, ValueError, json.JSONDecodeError):
        return None
    if action.get("action") not in {
        "open_app", "search_google", "search_youtube", "search_spotify",
        "chat", "unknown",
    }:
        return None
    # Accept `query` from a model that follows conventional search naming,
    # while converting it to Iris's single internal argument format.
    if "argument" not in action and isinstance(action.get("query"), str):
        action["argument"] = action["query"]
    if not isinstance(action.get("argument"), str):
        return None
    return action


def handle_natural_command(command: str) -> str:
    """Use the local model for flexible phrasing, then execute only safe tools."""
    action = ask_iris_brain(command)
    if action is None:
        return "My local brain is still starting. Please try again in a moment."
    kind, argument = action["action"], action["argument"].strip()
    if kind == "open_app" and argument:
        return open_target(argument.casefold())
    if kind == "search_google" and argument:
        return search("google", argument)
    if kind == "search_youtube" and argument:
        return search("youtube", argument)
    if kind == "search_spotify" and argument:
        return search_spotify(argument)
    if kind == "chat":
        return argument
    return "I can open apps, search Google or YouTube, and answer simple questions."


def normalise_voice_command(command: str) -> str:
    """Repair a few common offline speech-recognition mistakes safely.

    This never creates a shell command; it can only select an already approved
    item from APPS.
    """
    command = command.strip().lower()
    for misheard_prefix in ("oh been ", "oh pen ", "opener ", "open the "):
        if command.startswith(misheard_prefix):
            command = "open " + command[len(misheard_prefix) :]
            break

    if command.startswith("oh "):
        command = "open " + command.removeprefix("oh ")

    # If recognizer hears extra filler words but an approved app name clearly
    # appears, prefer the safe, exact open command.
    for app_name in APPS:
        if app_name in command and ("open" in command or "oh " in command):
            return f"open {app_name}"

    if command.startswith("open "):
        requested = command.removeprefix("open ").strip()
        match = get_close_matches(requested, APPS.keys(), n=1, cutoff=0.78)
        if match:
            return f"open {match[0]}"
    return command


def open_target(name: str) -> str:
    """Open an approved app/site, or find an installed Start-menu application."""
    target = APPS.get(name)
    if target is None:
        return open_installed_app(name)

    if target.startswith(("https://", "http://")):
        webbrowser.open(target)
    else:
        try:
            subprocess.Popen([target])
        except FileNotFoundError:
            return f"I couldn't find {target}. Check that it is installed or update APPS."
    return f"Opening {name}."


def installed_start_apps() -> list[tuple[str, str]]:
    """Read Windows' Start-menu app catalogue without maintaining our own list."""
    separator = "\x1f"
    command = (
        "Get-StartApps | ForEach-Object { "
        "[Console]::WriteLine($_.Name + [char]31 + $_.AppID) }"
    )
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-Command", command],
        capture_output=True, text=True, check=False,
    )
    apps = []
    for line in result.stdout.splitlines():
        if separator in line:
            app_name, app_id = line.split(separator, 1)
            if app_name and app_id:
                apps.append((app_name, app_id))
    return apps


def open_installed_app(requested_name: str) -> str:
    """Launch an unambiguous application listed in the Windows Start menu."""
    requested = requested_name.casefold().strip()
    apps = installed_start_apps()
    exact = [(app_name, app_id) for app_name, app_id in apps if app_name.casefold() == requested]
    contains = [
        (app_name, app_id) for app_name, app_id in apps
        if requested in app_name.casefold() or app_name.casefold() in requested
    ]
    matches = exact or contains
    if len(matches) == 1:
        app_name, app_id = matches[0]
        subprocess.Popen(["explorer.exe", f"shell:AppsFolder\\{app_id}"])
        return f"Opening {app_name}."
    if len(matches) > 1:
        names = ", ".join(app_name for app_name, _ in matches[:5])
        return f"I found several matches: {names}. Please use a more specific app name."

    names = [app_name.casefold() for app_name, _ in apps]
    suggestion = get_close_matches(requested, names, n=1, cutoff=0.80)
    if suggestion:
        app_name, app_id = next(
            (app_name, app_id)
            for app_name, app_id in apps
            if app_name.casefold() == suggestion[0]
        )
        subprocess.Popen(["explorer.exe", f"shell:AppsFolder\\{app_id}"])
        return f"I heard '{requested_name}' and opened {app_name}."
    return f"I couldn't find an installed app named '{requested_name}'."


def search(engine: str, query: str) -> str:
    encoded = urllib.parse.quote_plus(query)
    urls = {
        "google": f"https://www.google.com/search?q={encoded}",
        "youtube": f"https://www.youtube.com/results?search_query={encoded}",
    }
    webbrowser.open(urls[engine])
    return f"Searching {engine} for: {query}"


def search_spotify(query: str) -> str:
    """Open the installed Spotify app directly to a search result."""
    spotify_uri = f"spotify:search:{urllib.parse.quote(query)}"
    webbrowser.open(spotify_uri)
    return f"Opening Spotify and searching for: {query}"


def handle_command(command: str) -> str:
    command = command.strip().lower()
    if command in {"quit", "exit", "goodbye"}:
        raise SystemExit
    if command == "help":
        names = ", ".join(APPS)
        return (
            f"Try: open [ {names} ], search google for [words], "
            "or search youtube for [words]."
        )
    if command == "voice":
        heard = listen_for_command()
        print(f"You said: {heard}")
        if heard.startswith("i didn't") or heard.startswith("i couldn't"):
            return heard
        repaired = normalise_voice_command(heard)
        if repaired != heard:
            print(f"Iris interpreted that as: {repaired}")
        return handle_command(repaired)
    if command.startswith("open "):
        return open_target(command.removeprefix("open ").strip())
    for engine in ("google", "youtube"):
        prefix = f"search {engine} for "
        if command.startswith(prefix) and command[len(prefix) :].strip():
            return search(engine, command[len(prefix) :].strip())
    return handle_natural_command(command)


def main() -> None:
    print(
        "Iris is ready. Type 'voice' and speak naturally, for example "
        "'could you fire up Discord?'. Type 'help' for examples or 'quit' to stop."
    )
    while True:
        try:
            reply = handle_command(input("You: "))
            print(f"Iris: {reply}")
        except (EOFError, KeyboardInterrupt, SystemExit):
            print("\nIris stopped.")
            return


if __name__ == "__main__":
    main()
