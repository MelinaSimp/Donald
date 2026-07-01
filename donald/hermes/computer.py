"""Computer-use for Hermes — Donald sees the screen and clicks/types.

The shell/app/URL tools in :mod:`donald.hermes.engine` are fast and precise but
blind: they can't operate an app that has no CLI. Computer-use fills that gap.
Donald is given Anthropic's native ``computer`` tool; the model looks at a
screenshot and emits actions (move, click, type, key, scroll, screenshot),
which :class:`ComputerController` carries out on the real display and answers
with a fresh screenshot.

This is the most powerful thing Hermes can do — and the least contained, since
a click can press any button on screen. So it is **opt-in** (off by default),
supports **dry-run**, and the brain is told to confirm before consequential GUI
actions (buying, deleting, sending). Screen input is done through ``pyautogui``
(cross-platform), imported lazily so the package still works without it.

The GUI-free parts — the tool spec, action validation, key-name mapping,
dry-run behavior — are pure and unit-tested; only actual pixels need a display.
"""

from __future__ import annotations

import base64
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

# Anthropic computer-use: the tool type + the beta flag the API call needs.
COMPUTER_TOOL_TYPE = "computer_20250124"
COMPUTER_BETA_FLAG = "computer-use-2025-01-24"

# Actions we execute. (Anthropic's tool may emit a few more esoteric ones; those
# come back as a clear "unsupported" rather than a crash.)
SUPPORTED_ACTIONS = frozenset(
    {
        "screenshot",
        "cursor_position",
        "mouse_move",
        "left_click",
        "right_click",
        "middle_click",
        "double_click",
        "triple_click",
        "left_click_drag",
        "type",
        "key",
        "scroll",
        "wait",
    }
)

# Default logical screen size when we can't measure one (dry-run / headless).
# Kept modest: Anthropic recommends <= ~1280px wide for coordinate accuracy.
DEFAULT_SIZE = (1280, 800)

# Map a few common Anthropic/xdotool key names to what pyautogui expects.
_KEY_ALIASES = {
    "return": "enter",
    "escape": "esc",
    "cmd": "command",
    "super": "command" if sys.platform == "darwin" else "win",
    "control": "ctrl",
    "prior": "pageup",
    "next": "pagedown",
}


def computer_tool_spec(width: int, height: int, display_number: int = 1) -> dict:
    """The native ``computer`` tool definition for the API ``tools`` list."""
    return {
        "type": COMPUTER_TOOL_TYPE,
        "name": "computer",
        "display_width_px": int(width),
        "display_height_px": int(height),
        "display_number": display_number,
    }


def normalize_key(combo: str) -> List[str]:
    """Turn a key combo like ``"cmd+s"`` / ``"Return"`` into pyautogui keys."""
    parts = [p.strip().lower() for p in str(combo).replace(" ", "").split("+") if p.strip()]
    return [_KEY_ALIASES.get(p, p) for p in parts]


@dataclass
class ComputerResult:
    """Outcome of one computer action: text for the log, optional screenshot."""

    ok: bool
    output: str = ""
    image_b64: Optional[str] = None

    def summary(self) -> str:
        return self.output or ("screenshot" if self.image_b64 else "done")


@dataclass
class ComputerController:
    """Executes computer-use actions on the real display.

    Parameters
    ----------
    dry_run:
        Describe actions instead of performing them (no pyautogui, no pixels).
    size:
        Logical (width, height) reported to the model. Defaults to the measured
        screen size, or :data:`DEFAULT_SIZE` when there's no display.
    """

    dry_run: bool = False
    size: Tuple[int, int] = field(default_factory=lambda: DEFAULT_SIZE)
    _gui: object = field(default=None, repr=False)

    # -- dispatch (pure control flow; testable) ---------------------------
    def execute(self, action: str, **params) -> ComputerResult:
        if action not in SUPPORTED_ACTIONS:
            return ComputerResult(False, f"Unsupported computer action: {action!r}.")

        if action == "wait":
            return ComputerResult(True, "waited")

        if self.dry_run:
            detail = ", ".join(f"{k}={v}" for k, v in params.items() if v is not None)
            return ComputerResult(True, f"[dry-run] {action}({detail})", image_b64=None)

        if action == "screenshot":
            return self._screenshot()
        if action == "cursor_position":
            return self._cursor_position()
        return self._input_action(action, **params)

    # -- screenshots ------------------------------------------------------
    def _screenshot(self) -> ComputerResult:
        """Grab the screen as base64 PNG using the OS's native tool."""
        try:
            with tempfile.NamedTemporaryFile(suffix=".png", delete=True) as tmp:
                if sys.platform == "darwin":
                    cmd = ["screencapture", "-x", tmp.name]
                elif sys.platform.startswith("linux"):
                    # Prefer scrot; many desktops have it. (gnome-screenshot is a fallback.)
                    cmd = ["scrot", "-o", tmp.name]
                else:  # windows: use pyautogui/pillow
                    return self._screenshot_pyautogui()
                subprocess.run(cmd, check=True, timeout=15)
                data = open(tmp.name, "rb").read()
            return ComputerResult(True, "screenshot", base64.b64encode(data).decode())
        except FileNotFoundError:
            return self._screenshot_pyautogui()
        except Exception as exc:  # pragma: no cover - display-dependent
            return ComputerResult(False, f"Screenshot failed: {exc}")

    def _screenshot_pyautogui(self) -> ComputerResult:
        gui = self._load_gui()
        if gui is None:
            return ComputerResult(False, _MISSING_GUI)
        try:  # pragma: no cover - display-dependent
            import io

            buf = io.BytesIO()
            gui.screenshot().save(buf, format="PNG")
            return ComputerResult(True, "screenshot", base64.b64encode(buf.getvalue()).decode())
        except Exception as exc:  # pragma: no cover
            return ComputerResult(False, f"Screenshot failed: {exc}")

    def _cursor_position(self) -> ComputerResult:
        gui = self._load_gui()
        if gui is None:
            return ComputerResult(False, _MISSING_GUI)
        x, y = gui.position()  # pragma: no cover - display-dependent
        return ComputerResult(True, f"cursor at ({x}, {y})")

    # -- mouse/keyboard ---------------------------------------------------
    def _input_action(self, action: str, **params) -> ComputerResult:  # pragma: no cover - display-dependent
        gui = self._load_gui()
        if gui is None:
            return ComputerResult(False, _MISSING_GUI)
        coord = params.get("coordinate")
        try:
            if action == "mouse_move":
                gui.moveTo(*coord)
            elif action == "left_click":
                gui.click(*coord) if coord else gui.click()
            elif action == "right_click":
                gui.rightClick(*coord) if coord else gui.rightClick()
            elif action == "middle_click":
                gui.middleClick(*coord) if coord else gui.middleClick()
            elif action == "double_click":
                gui.doubleClick(*coord) if coord else gui.doubleClick()
            elif action == "triple_click":
                gui.click(*(coord or ()), clicks=3, interval=0.05) if coord else gui.click(clicks=3, interval=0.05)
            elif action == "left_click_drag":
                gui.dragTo(*coord, duration=0.3)
            elif action == "type":
                gui.write(params.get("text", ""), interval=0.02)
            elif action == "key":
                keys = normalize_key(params.get("text", ""))
                gui.hotkey(*keys) if len(keys) > 1 else gui.press(keys[0] if keys else "")
            elif action == "scroll":
                amt = int(params.get("scroll_amount", 3))
                direction = params.get("scroll_direction", "down")
                gui.scroll(-amt if direction == "down" else amt)
            else:
                return ComputerResult(False, f"Unsupported computer action: {action!r}.")
        except Exception as exc:
            return ComputerResult(False, f"{action} failed: {exc}")
        # Follow every input with a screenshot so the model sees the result.
        shot = self._screenshot()
        return ComputerResult(True, f"{action} done", image_b64=shot.image_b64)

    # -- lazy pyautogui ---------------------------------------------------
    def _load_gui(self):
        if self._gui is not None:
            return self._gui
        try:  # pragma: no cover - environment-dependent
            import pyautogui

            pyautogui.FAILSAFE = True
            self._gui = pyautogui
            self.size = pyautogui.size()
        except Exception:
            self._gui = None
        return self._gui


_MISSING_GUI = (
    "Computer-use needs pyautogui: pip install pyautogui pillow. "
    "On macOS also grant Terminal 'Screen Recording' and 'Accessibility' in "
    "System Settings > Privacy & Security."
)
