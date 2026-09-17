"""A safe, free starter assistant for Windows.

This intentionally uses an allowlist instead of executing arbitrary commands.
"""

from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import threading
import time
import urllib.parse
import webbrowser
import wave
from datetime import datetime
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
STATE_PATH = Path(__file__).parent / "iris-state.json"
MUTE_PATH = Path(__file__).parent / "iris-muted.flag"
DATA_DIR = Path(__file__).parent / "data"
NOTES_DIR = DATA_DIR / "notes"
SCREENSHOTS_DIR = DATA_DIR / "screenshots"
OLLAMA_URL = "http://127.0.0.1:11434/api/chat"
OLLAMA_MODEL = "qwen3:4b"
CREATE_NO_WINDOW = 0x08000000
START_APPS_CACHE: list[tuple[str, str]] | None = None
ACTIVE_TIMERS: list[threading.Timer] = []
VOICE_MODE = False


def set_state(state: str) -> None:
    """Publish Iris's local UI state for the tray controller."""
    try:
        STATE_PATH.write_text(json.dumps({"state": state}), encoding="utf-8")
    except OSError:
        pass


def get_state() -> str:
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8")).get("state", "stopped")
    except (OSError, ValueError):
        return "stopped"


def speak(text: str) -> None:
    """Speak a short reply using Windows' offline speech engine."""
    previous_state = get_state()
    set_state("speaking")
    try:
        import pyttsx3

        engine = pyttsx3.init()
        engine.setProperty("rate", 185)
        for voice in engine.getProperty("voices"):
            if "zira" in voice.name.casefold():
                engine.setProperty("voice", voice.id)
                break
        engine.say(text[:400])
        engine.runAndWait()
    except Exception as error:
        print(f"Iris voice is unavailable: {error}")
    finally:
        set_state(previous_state)


def wait_for_wake_word() -> bool:
    """Listen locally for 'Hey Iris' using a restricted lightweight grammar."""
    try:
        import sounddevice as sd
        from vosk import KaldiRecognizer, Model
    except ImportError:
        print("Wake-word support is unavailable because Vosk is not installed.")
        return False

    if not MODEL_PATH.is_dir():
        print(f"Wake-word model is missing: {MODEL_PATH}")
        return False

    microphone_queue: queue.Queue[bytes] = queue.Queue()

    def capture(indata: bytes, frames: int, timing: object, status: object) -> None:
        if status:
            print(f"Microphone status: {status}")
        microphone_queue.put(bytes(indata))

    recognizer = KaldiRecognizer(
        Model(str(MODEL_PATH)), 16_000,
        json.dumps(["hey iris", "iris", "[unk]"]),
    )
    print("Listening for 'Hey Iris' - press Ctrl+C to stop.")
    set_state("listening")
    with sd.RawInputStream(
        samplerate=16_000, blocksize=4_000, dtype="int16",
        channels=1, callback=capture,
    ):
        while True:
            audio = microphone_queue.get(timeout=1)
            if MUTE_PATH.exists():
                set_state("muted")
                recognizer.Reset()
                continue
            if get_state() == "muted":
                set_state("listening")
            if recognizer.AcceptWaveform(audio):
                text = json.loads(recognizer.Result()).get("text", "")
            else:
                text = json.loads(recognizer.PartialResult()).get("partial", "")
            if "iris" in text.casefold().split():
                set_state("awake")
                return True


def hands_free_mode() -> str:
    """Wait for the wake word, process one command, and resume listening."""
    global VOICE_MODE
    VOICE_MODE = True
    speak("Hands free mode is on. Say Hey Iris, then wait for the beep.")
    while wait_for_wake_word():
        try:
            import winsound

            winsound.MessageBeep()
        except ImportError:
            pass
        speak("Yes?")
        heard = listen_for_command()
        print(f"You said: {heard}")
        if heard.startswith(("I didn't", "I couldn't")):
            speak(heard)
            continue
        repaired = normalise_voice_command(heard)
        if repaired in {"stop listening", "mute", "hands free off"}:
            VOICE_MODE = False
            return "Hands free mode is off."
        reply = handle_command(repaired)
        print(f"Iris: {reply}")
        speak(reply)
    VOICE_MODE = False
    return "Hands free mode is unavailable."


def confirm_action(question: str) -> bool:
    """Ask for a clear yes/no before a local write or capture."""
    if VOICE_MODE:
        speak(question + " Say yes or no.")
        answer = listen_for_command(max_seconds=8).casefold()
        return any(word in answer.split() for word in ("yes", "yeah", "yep", "sure", "okay"))
    answer = input(f"Iris: {question} (yes/no) ").strip().casefold()
    return answer in {"y", "yes", "yeah", "yep", "sure", "okay"}


def listen_for_command(max_seconds: int = 15) -> str:
    """Record until the speaker pauses, then transcribe locally with Whisper."""
    try:
        import sounddevice as sd
        from faster_whisper import WhisperModel
    except ImportError:
        return "Whisper voice support is not installed. Run run_iris.bat from this folder."

    sample_rate = 16_000
    print("Iris is listening. Speak naturally, then pause when you are finished...")
    set_state("recording")
    try:
        import numpy as np

        chunks: queue.Queue[bytes] = queue.Queue()

        def capture(indata: bytes, frames: int, timing: object, status: object) -> None:
            if status:
                print(f"Microphone status: {status}")
            chunks.put(bytes(indata))

        audio_parts: list[bytes] = []
        heard_speech = False
        quiet_seconds = 0.0
        started_at = time.monotonic()
        block_seconds = 0.25
        with sd.RawInputStream(
            samplerate=sample_rate, blocksize=int(sample_rate * block_seconds),
            dtype="int16", channels=1, callback=capture,
        ):
            while time.monotonic() - started_at < max_seconds:
                chunk = chunks.get(timeout=1)
                audio_parts.append(chunk)
                volume = float(np.sqrt(np.mean(np.frombuffer(chunk, dtype=np.int16).astype(float) ** 2)))
                if volume > 350:
                    heard_speech = True
                    quiet_seconds = 0.0
                elif heard_speech:
                    quiet_seconds += block_seconds
                if heard_speech and quiet_seconds >= 1.2:
                    break
        if not heard_speech:
            return "I didn't hear any speech. Please try voice again."
    except Exception as error:
        return f"I couldn't use the microphone: {error}"

    try:
        with wave.open(str(RECORDING_PATH), "wb") as recording:
            recording.setnchannels(1)
            recording.setsampwidth(2)
            recording.setframerate(sample_rate)
            recording.writeframes(b"".join(audio_parts))
        print("Iris is understanding what you said...")
        set_state("transcribing")
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
Allowed actions are: open_app, open_path, search_google, search_youtube,
search_spotify, create_note, set_timer, volume_up, volume_down, volume_mute,
take_screenshot, chat, unknown.
For open_app, the JSON is {"action":"open_app","argument":"app name"}.
For every search, the JSON is {"action":"search_name","argument":"query"}.
For a file or folder, use open_path and put its name in argument.
For create_note, put only the note content in argument.
For set_timer, convert the duration to seconds and put only that integer in argument.
For volume actions and take_screenshot, use an empty argument string.
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
        "open_app", "open_path", "search_google", "search_youtube",
        "search_spotify", "create_note", "set_timer", "volume_up",
        "volume_down", "volume_mute", "take_screenshot", "chat", "unknown",
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
    set_state("thinking")
    action = ask_iris_brain(command)
    set_state("idle")
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
    if kind == "create_note" and argument:
        return create_note(argument)
    if kind == "set_timer" and argument:
        return set_timer(argument)
    if kind in {"volume_up", "volume_down", "volume_mute"}:
        return change_volume(kind)
    if kind == "take_screenshot":
        return take_screenshot()
    if kind == "open_path" and argument:
        return open_local_path(argument)
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
            subprocess.Popen([target], creationflags=CREATE_NO_WINDOW)
        except FileNotFoundError:
            return f"I couldn't find {target}. Check that it is installed or update APPS."
    return f"Opening {name}."


def installed_start_apps() -> list[tuple[str, str]]:
    """Read Windows' Start-menu app catalogue without maintaining our own list."""
    global START_APPS_CACHE
    if START_APPS_CACHE is not None:
        return START_APPS_CACHE

    separator = "\x1f"
    command = (
        "Get-StartApps | ForEach-Object { "
        "[Console]::WriteLine($_.Name + [char]31 + $_.AppID) }"
    )
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-Command", command],
        capture_output=True, text=True, check=False,
        creationflags=CREATE_NO_WINDOW,
    )
    apps = []
    for line in result.stdout.splitlines():
        if separator in line:
            app_name, app_id = line.split(separator, 1)
            if app_name and app_id:
                apps.append((app_name, app_id))
    START_APPS_CACHE = apps
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
        subprocess.Popen(
            ["explorer.exe", f"shell:AppsFolder\\{app_id}"],
            creationflags=CREATE_NO_WINDOW,
        )
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
        subprocess.Popen(
            ["explorer.exe", f"shell:AppsFolder\\{app_id}"],
            creationflags=CREATE_NO_WINDOW,
        )
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


def create_note(content: str) -> str:
    """Save a timestamped private note under Iris's E:-drive data directory."""
    if not confirm_action(f"Should I save this note: {content.strip()}?"):
        return "Okay, I did not save the note."
    NOTES_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    note_path = NOTES_DIR / f"note_{timestamp}.txt"
    note_path.write_text(content.strip() + "\n", encoding="utf-8")
    os.startfile(note_path)
    return f"I saved your note and opened it in Notepad: {content.strip()}"


def timer_finished(seconds: int) -> None:
    try:
        import winsound

        winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
    except ImportError:
        pass
    speak("Your timer is finished.")


def set_timer(seconds_text: str) -> str:
    """Start an in-process timer, limited to 24 hours."""
    try:
        seconds = int(float(seconds_text.strip()))
    except ValueError:
        return "I couldn't understand the timer duration."
    if not 1 <= seconds <= 86_400:
        return "Timers must be between one second and twenty four hours."
    timer = threading.Timer(seconds, timer_finished, args=(seconds,))
    timer.daemon = True
    ACTIVE_TIMERS.append(timer)
    timer.start()
    if seconds < 60:
        duration = f"{seconds} seconds"
    elif seconds % 60 == 0:
        duration = f"{seconds // 60} minutes"
    else:
        duration = f"{seconds // 60} minutes and {seconds % 60} seconds"
    return f"Timer set for {duration}."


def change_volume(action: str) -> str:
    """Use Windows media keys without installing a system-level utility."""
    import ctypes

    keys = {"volume_up": 0xAF, "volume_down": 0xAE, "volume_mute": 0xAD}
    repeats = 5 if action != "volume_mute" else 1
    for _ in range(repeats):
        key = keys[action]
        ctypes.windll.user32.keybd_event(key, 0, 0, 0)
        ctypes.windll.user32.keybd_event(key, 0, 2, 0)
    replies = {
        "volume_up": "I turned the volume up.",
        "volume_down": "I turned the volume down.",
        "volume_mute": "I toggled mute.",
    }
    return replies[action]


def take_screenshot() -> str:
    """Capture all screens to Iris's private local data directory."""
    from PIL import ImageGrab

    if not confirm_action("Should I take a screenshot now?"):
        return "Okay, I did not take a screenshot."

    SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    screenshot_path = SCREENSHOTS_DIR / f"screenshot_{timestamp}.png"
    ImageGrab.grab(all_screens=True).save(screenshot_path)
    subprocess.Popen(
        ["explorer.exe", "/select,", str(screenshot_path)],
        creationflags=CREATE_NO_WINDOW,
    )
    return "Screenshot saved. I opened its folder and selected the new image."


def searchable_roots() -> list[Path]:
    """Return useful local roots without scanning entire drives."""
    candidates = [
        Path("E:/codex"), Path("D:/projects"), Path.home() / "Desktop",
        Path.home() / "Documents", Path.home() / "Downloads",
    ]
    return [path for path in candidates if path.exists()]


def open_local_path(requested_name: str) -> str:
    """Find and open an unambiguous local file or folder by name."""
    requested = requested_name.casefold().strip()
    home = Path.home()
    onedrive = Path(os.environ.get("OneDrive", home / "OneDrive"))
    aliases = {
        "downloads": home / "Downloads",
        "download": home / "Downloads",
        "downloads folder": home / "Downloads",
        "download folder": home / "Downloads",
        "documents": onedrive / "Documents" if (onedrive / "Documents").exists() else home / "Documents",
        "documents folder": onedrive / "Documents" if (onedrive / "Documents").exists() else home / "Documents",
        "desktop": onedrive / "Desktop" if (onedrive / "Desktop").exists() else home / "Desktop",
        "desktop folder": onedrive / "Desktop" if (onedrive / "Desktop").exists() else home / "Desktop",
        "codex": Path("E:/codex"),
        "notes": NOTES_DIR,
        "notes folder": NOTES_DIR,
        "screenshots": SCREENSHOTS_DIR,
        "screenshots folder": SCREENSHOTS_DIR,
    }
    if requested in aliases and aliases[requested].exists():
        os.startfile(aliases[requested])
        return f"Opening {requested_name}."

    matches: list[Path] = []
    ignored = {".git", ".venv", "models", "pip-cache", "__pycache__"}
    inspected = 0
    for root in searchable_roots():
        for current, directories, files in os.walk(root):
            directories[:] = [name for name in directories if name not in ignored]
            for name in directories + files:
                inspected += 1
                if requested in name.casefold():
                    matches.append(Path(current) / name)
                    if len(matches) >= 6:
                        break
                if inspected >= 50_000:
                    break
            if len(matches) >= 6 or inspected >= 50_000:
                break
        if len(matches) >= 6 or inspected >= 50_000:
            break

    if len(matches) == 1:
        os.startfile(matches[0])
        return f"Opening {matches[0].name}."
    if matches:
        names = ", ".join(path.name for path in matches[:5])
        return f"I found several matches: {names}. Please be more specific."
    return f"I couldn't find a file or folder named {requested_name}."


def handle_command(command: str) -> str:
    command = command.strip().lower()
    if command in {"quit", "exit", "goodbye"}:
        raise SystemExit
    if command == "help":
        names = ", ".join(APPS)
        return (
            f"Try: open [ {names} ], search google for [words], "
            "search youtube for [words], voice, or handsfree."
        )
    if command in {"handsfree", "hands free"}:
        return hands_free_mode()
    if command == "voice":
        global VOICE_MODE
        VOICE_MODE = True
        heard = listen_for_command()
        print(f"You said: {heard}")
        if heard.startswith("i didn't") or heard.startswith("i couldn't"):
            return heard
        repaired = normalise_voice_command(heard)
        if repaired != heard:
            print(f"Iris interpreted that as: {repaired}")
        try:
            return handle_command(repaired)
        finally:
            VOICE_MODE = False
    if command.startswith("open "):
        requested = command.removeprefix("open ").strip()
        folder_names = {
            "download", "downloads", "download folder", "downloads folder",
            "document", "documents", "documents folder", "desktop",
            "desktop folder", "codex", "notes", "notes folder",
            "screenshots", "screenshots folder",
        }
        if requested in folder_names:
            return open_local_path(requested)
        return open_target(requested)
    for engine in ("google", "youtube"):
        prefix = f"search {engine} for "
        if command.startswith(prefix) and command[len(prefix) :].strip():
            return search(engine, command[len(prefix) :].strip())
    return handle_natural_command(command)


def main() -> None:
    if "--handsfree" in sys.argv:
        set_state("starting")
        try:
            hands_free_mode()
        except KeyboardInterrupt:
            pass
        finally:
            set_state("stopped")
        return

    set_state("idle")
    welcome = (
        "Iris is ready. Type voice and speak naturally, then pause when finished. For example, "
        "could you fire up Discord? Type help for examples or quit to stop."
    )
    print(welcome)
    speak("Iris is ready.")
    while True:
        try:
            reply = handle_command(input("You: "))
            print(f"Iris: {reply}")
            speak(reply)
        except (EOFError, KeyboardInterrupt, SystemExit):
            print("\nIris stopped.")
            set_state("stopped")
            return


if __name__ == "__main__":
    main()
