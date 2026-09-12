"""Windows system-tray controller for Iris."""

from __future__ import annotations

import json
import subprocess
import threading
import time
from pathlib import Path

import pystray
from PIL import Image, ImageDraw


PROJECT_DIR = Path(__file__).parent
PYTHONW = PROJECT_DIR / ".venv" / "Scripts" / "pythonw.exe"
ASSISTANT = PROJECT_DIR / "assistant.py"
STATE_PATH = PROJECT_DIR / "iris-state.json"
MUTE_PATH = PROJECT_DIR / "iris-muted.flag"
CREATE_NO_WINDOW = 0x08000000

STATE_COLOURS = {
    "starting": "#3b82f6", "idle": "#64748b", "listening": "#22c55e",
    "awake": "#84cc16", "recording": "#ef4444", "transcribing": "#f59e0b",
    "thinking": "#a855f7", "speaking": "#06b6d4", "muted": "#dc2626",
    "stopped": "#475569",
}


def read_state() -> str:
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8")).get("state", "stopped")
    except (OSError, ValueError):
        return "stopped"


def write_state(state: str) -> None:
    STATE_PATH.write_text(json.dumps({"state": state}), encoding="utf-8")


def make_icon(colour: str) -> Image.Image:
    image = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.ellipse((4, 4, 60, 60), fill=colour, outline="white", width=3)
    draw.text((24, 17), "I", fill="white", stroke_width=1)
    return image


class IrisController:
    def __init__(self) -> None:
        self.process: subprocess.Popen[bytes] | None = None
        self.icon: pystray.Icon | None = None
        self.running = True

    def start_assistant(self) -> None:
        self.stop_assistant()
        MUTE_PATH.unlink(missing_ok=True)
        write_state("starting")
        self.process = subprocess.Popen(
            [str(PYTHONW), str(ASSISTANT), "--handsfree"],
            cwd=str(PROJECT_DIR), creationflags=CREATE_NO_WINDOW,
        )

    def stop_assistant(self) -> None:
        if self.process is not None and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
        self.process = None
        write_state("stopped")

    def toggle_mute(self, icon: pystray.Icon, item: pystray.MenuItem) -> None:
        if MUTE_PATH.exists():
            MUTE_PATH.unlink(missing_ok=True)
            write_state("listening")
        else:
            MUTE_PATH.touch()
            write_state("muted")
        icon.update_menu()

    def restart(self, icon: pystray.Icon, item: pystray.MenuItem) -> None:
        self.start_assistant()

    def quit(self, icon: pystray.Icon, item: pystray.MenuItem) -> None:
        self.running = False
        self.stop_assistant()
        icon.stop()

    def status_label(self, item: pystray.MenuItem) -> str:
        return f"Status: {read_state().replace('_', ' ').title()}"

    def poll_state(self) -> None:
        previous = ""
        while self.running:
            if self.process is not None and self.process.poll() is not None:
                write_state("stopped")
            state = read_state()
            if self.icon is not None and state != previous:
                self.icon.icon = make_icon(STATE_COLOURS.get(state, "#64748b"))
                self.icon.title = f"Iris — {state.replace('_', ' ').title()}"
                self.icon.update_menu()
                previous = state
            time.sleep(0.25)

    def run(self) -> None:
        menu = pystray.Menu(
            pystray.MenuItem(self.status_label, None, enabled=False),
            pystray.MenuItem("Mute / Resume", self.toggle_mute),
            pystray.MenuItem("Restart Iris", self.restart),
            pystray.MenuItem("Quit Iris", self.quit),
        )
        self.icon = pystray.Icon("iris", make_icon(STATE_COLOURS["starting"]), "Iris", menu)
        self.start_assistant()
        threading.Thread(target=self.poll_state, daemon=True).start()
        self.icon.run()


if __name__ == "__main__":
    IrisController().run()
