"""Donald, the voice desktop assistant — local app server.

Run it on your own machine::

    export ANTHROPIC_API_KEY=sk-...
    python -m donald.app

It starts a tiny local server (127.0.0.1 only) and opens the Donald UI in your
browser. Say **"Donald"** to wake him; then just talk. The browser does the
listening and the speaking (wake word, speech-to-text, and Donald's voice all
run in the browser via the Web Speech API — no native audio deps, works on
macOS/Windows/Linux). This server runs the brain and lets **Hermes** act on
*this* computer.

Why a local web app: the browser already ships best-in-class, cross-platform
voice; the Python side already has the personality, the brain, and the security
gates. The server binds to loopback only — it is your machine talking to
itself, not a service on the network.

Endpoints
---------
``GET  /``          → the UI
``POST /api/turn``  → ``{"transcript": "..."}`` → ``{"reply", "actions", ...}``
``GET  /api/health``→ readiness + whether the API key is present
"""

from __future__ import annotations

import json
import os
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .brain import DonaldBrain
from .hermes import Hermes, detect_platform

WEB_DIR = Path(__file__).parent / "web"
HOST = "127.0.0.1"
DEFAULT_PORT = 8765

_CONTENT_TYPES = {".html": "text/html", ".js": "text/javascript", ".css": "text/css"}


class _DonaldServer(ThreadingHTTPServer):
    """Holds the shared brain, kill switch, and proactive message queue."""

    daemon_threads = True

    def __init__(self, addr, handler, brain: DonaldBrain, kill_switch, proactive):
        super().__init__(addr, handler)
        self.brain = brain
        self.brain_lock = threading.Lock()
        self.kill_switch = kill_switch
        self.proactive = proactive
        self._events: list = []          # spoken lines Donald pushes on his own
        self._events_lock = threading.Lock()

    def push_event(self, line: str) -> None:
        """Queue a proactive spoken line for the UI to pick up and say."""
        with self._events_lock:
            self._events.append(line)

    def drain_events(self) -> list:
        with self._events_lock:
            out, self._events = self._events, []
        return out


class _Handler(BaseHTTPRequestHandler):
    server: _DonaldServer  # type: ignore[assignment]

    def log_message(self, *args):  # quiet the default access log
        pass

    # -- helpers -----------------------------------------------------------
    def _send(self, code: int, body: bytes, content_type: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, code: int, obj: dict) -> None:
        self._send(code, json.dumps(obj).encode("utf-8"), "application/json")

    # -- routes ------------------------------------------------------------
    def do_GET(self) -> None:
        if self.path in ("/", "/index.html"):
            return self._serve_file("index.html")
        if self.path == "/api/health":
            return self._send_json(
                200,
                {
                    "ok": True,
                    "platform": detect_platform(),
                    "has_api_key": bool(os.environ.get("ANTHROPIC_API_KEY")),
                    "paused": self.server.kill_switch.active,
                },
            )
        if self.path == "/api/events":
            # The UI polls this; returns any proactive lines Donald wants to say.
            return self._send_json(200, {"say": self.server.drain_events()})
        safe = self.path.lstrip("/")
        if safe in {"app.js", "styles.css"}:
            return self._serve_file(safe)
        self._send_json(404, {"error": "not found"})

    def do_POST(self) -> None:
        if self.path == "/api/killswitch":
            return self._handle_killswitch()
        if self.path != "/api/turn":
            return self._send_json(404, {"error": "not found"})
        try:
            length = int(self.headers.get("Content-Length", 0))
            payload = json.loads(self.rfile.read(length) or b"{}")
            transcript = (payload.get("transcript") or "").strip()
        except (ValueError, json.JSONDecodeError):
            return self._send_json(400, {"error": "bad request"})

        if not transcript:
            return self._send_json(200, {"reply": "", "actions": [], "awaiting_confirmation": False})

        with self.server.brain_lock:  # one turn at a time; shared conversation
            try:
                result = self.server.brain.take_turn(transcript)
            except Exception as exc:  # surface errors in Donald's voice, don't 500
                return self._send_json(
                    200,
                    {
                        "reply": f"Something glitched on my end — even my mistakes are interesting. ({exc})",
                        "actions": [],
                        "awaiting_confirmation": False,
                    },
                )
        self._send_json(
            200,
            {
                "reply": result.reply,
                "actions": result.actions,
                "awaiting_confirmation": result.awaiting_confirmation,
            },
        )

    def _handle_killswitch(self) -> None:
        try:
            length = int(self.headers.get("Content-Length", 0))
            action = json.loads(self.rfile.read(length) or b"{}").get("action", "")
        except (ValueError, json.JSONDecodeError):
            return self._send_json(400, {"error": "bad request"})
        if action == "engage":
            self.server.kill_switch.engage()
        elif action == "release":
            self.server.kill_switch.release()
        return self._send_json(200, {"paused": self.server.kill_switch.active})

    def _serve_file(self, name: str) -> None:
        path = WEB_DIR / name
        if not path.is_file():
            return self._send_json(404, {"error": "not found"})
        ctype = _CONTENT_TYPES.get(path.suffix, "application/octet-stream")
        self._send(200, path.read_bytes(), ctype)


def build_assembly(dry_run: bool = False, computer_use: bool = False):
    """Wire the brain, kill switch, and proactive engine together.

    Returns ``(brain, kill_switch, proactive)``. ``proactive``'s sink is set by
    :func:`serve` once the server (which owns the outbound queue) exists.
    """
    from anthropic import Anthropic

    from .killswitch import KillSwitch
    from .proactive import ProactiveEngine

    kill_switch = KillSwitch()
    # Sink is rebound to the server's queue in serve(); no-op until then.
    proactive = ProactiveEngine(sink=lambda line: None, kill_switch=kill_switch)

    hermes = Hermes(
        dry_run=dry_run,
        enable_computer_use=computer_use,
        kill_switch=kill_switch,
        reminder_sink=proactive.add_reminder,
    )
    brain = DonaldBrain(client=Anthropic(), hermes=hermes, kill_switch=kill_switch)
    return brain, kill_switch, proactive


def serve(
    port: int = DEFAULT_PORT,
    open_browser: bool = True,
    dry_run: bool = False,
    computer_use: bool = False,
) -> None:
    """Start the local server and (optionally) open the UI."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise SystemExit(
            "Set ANTHROPIC_API_KEY so Donald can think. (export ANTHROPIC_API_KEY=sk-...)"
        )
    brain, kill_switch, proactive = build_assembly(dry_run=dry_run, computer_use=computer_use)
    httpd = _DonaldServer((HOST, port), _Handler, brain, kill_switch, proactive)
    # Now that the server (and its queue) exist, point proactive output at it.
    proactive.set_sink(httpd.push_event)
    proactive.start()
    url = f"http://{HOST}:{port}/"
    print(f"Donald is live at {url}  (Ctrl-C to shut it down)")
    print('Open it, allow the microphone, and say "Donald".')
    if open_browser:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nDonald> Leaving already? Tremendous instincts. I'll be here.")
    finally:
        httpd.server_close()


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Donald — voice desktop assistant")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--no-browser", action="store_true", help="don't auto-open the UI")
    parser.add_argument(
        "--dry-run", action="store_true", help="Hermes describes actions instead of running them"
    )
    parser.add_argument(
        "--computer-use",
        action="store_true",
        help="let Hermes see the screen and click/type any app (needs pyautogui + OS permissions)",
    )
    args = parser.parse_args()
    serve(
        port=args.port,
        open_browser=not args.no_browser,
        dry_run=args.dry_run,
        computer_use=args.computer_use,
    )


if __name__ == "__main__":
    main()
