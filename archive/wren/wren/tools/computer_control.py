"""Computer control tools — click, type, screenshot (Tier 6+).

Enables Wren to interact with the user's screen: take screenshots, click buttons,
type text, and navigate websites. Powered by Playwright (for browsers) and
PyAutoGUI (for screen control).

These are high-consequence tools and must be gated with user confirmation.
All uses are logged to the audit trail.
"""
from __future__ import annotations

from typing import Any

from .base import Registry, obj, string


def _take_screenshot() -> str:
    """Take a screenshot of the current screen and return base64-encoded image."""
    try:
        import base64
        from io import BytesIO

        from PIL import ImageGrab

        img = ImageGrab.grab()
        buf = BytesIO()
        img.save(buf, format="PNG")
        data = base64.b64encode(buf.getvalue()).decode("utf-8")
        return f"data:image/png;base64,{data}"
    except ImportError:
        return "Screenshot tool not available. Run: pip install pillow"
    except Exception as e:
        return f"Failed to take screenshot: {e}"


def _click(x: int, y: int, button: str = "left") -> str:
    """Click at screen coordinates (x, y)."""
    try:
        import pyautogui

        pyautogui.click(x, y, button=button)
        return f"Clicked at ({x}, {y})"
    except Exception as e:
        return f"Click failed: {e}"


def _type_text(text: str, interval: float = 0.05) -> str:
    """Type text character by character."""
    try:
        import pyautogui

        pyautogui.typewrite(text, interval=interval)
        return f"Typed: {text}"
    except Exception as e:
        return f"Type failed: {e}"


def _press_key(key: str) -> str:
    """Press a single key (e.g., 'enter', 'escape', 'tab')."""
    try:
        import pyautogui

        pyautogui.press(key)
        return f"Pressed: {key}"
    except Exception as e:
        return f"Key press failed: {e}"


def _find_element(selector: str) -> str:
    """Find an element on screen by CSS selector (requires Playwright browser context)."""
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp("ws://localhost:3222")
            page = browser.pages[0] if browser.pages else None
            if not page:
                return "No active browser page found."

            element = page.query_selector(selector)
            if not element:
                return f"Element not found: {selector}"

            box = element.bounding_box()
            if not box:
                return f"Element has no bounding box: {selector}"
            return f"Found at ({box['x']}, {box['y']}, {box['width']}, {box['height']})"
    except Exception as e:
        return f"Element search failed: {e}"


def _navigate_url(url: str) -> str:
    """Navigate to a URL in the active browser (requires CDP connection)."""
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp("ws://localhost:3222")
            page = browser.pages[0] if browser.pages else None
            if not page:
                return "No active browser page found."

            page.goto(url, wait_until="load")
            return f"Navigated to {url}"
    except Exception as e:
        return f"Navigation failed: {e}"


def register(registry: Registry, ctx) -> None:
    def take_screenshot(args: dict[str, Any]) -> str:
        return _take_screenshot()

    def click(args: dict[str, Any]) -> str:
        x = args.get("x")
        y = args.get("y")
        if x is None or y is None:
            return "I need x and y coordinates."
        button = args.get("button", "left")
        return _click(int(x), int(y), button)

    def type_text(args: dict[str, Any]) -> str:
        text = (args.get("text") or "").strip()
        if not text:
            return "I need text to type."
        interval = float(args.get("interval", 0.05))
        return _type_text(text, interval)

    def press_key(args: dict[str, Any]) -> str:
        key = (args.get("key") or "").strip()
        if not key:
            return "I need a key name (e.g., 'enter', 'escape')."
        return _press_key(key)

    def find_element(args: dict[str, Any]) -> str:
        selector = (args.get("selector") or "").strip()
        if not selector:
            return "I need a CSS selector."
        return _find_element(selector)

    def navigate_url(args: dict[str, Any]) -> str:
        url = (args.get("url") or "").strip()
        if not url:
            return "I need a URL."
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        return _navigate_url(url)

    registry.add(
        "take_screenshot",
        "Take a screenshot of the current screen and return it as a base64-encoded image. "
        "Use to see what's on screen and locate elements to interact with.",
        obj({}),
        take_screenshot,
        consequential=True,
    )
    registry.add(
        "click",
        "Click at screen coordinates (x, y). First use take_screenshot to find what to click.",
        obj(
            {
                "x": {"type": "integer", "description": "X coordinate."},
                "y": {"type": "integer", "description": "Y coordinate."},
                "button": {"type": "string", "description": "Mouse button: 'left', 'right', or 'middle'."},
            },
            required=["x", "y"],
        ),
        click,
        consequential=True,
    )
    registry.add(
        "type_text",
        "Type text into the focused field. Use after clicking an input field.",
        obj(
            {
                "text": string("Text to type."),
                "interval": {"type": "number", "description": "Delay between characters (seconds, default 0.05)."},
            },
            required=["text"],
        ),
        type_text,
        consequential=True,
    )
    registry.add(
        "press_key",
        "Press a single key (e.g., 'enter', 'escape', 'tab', 'backspace').",
        obj({"key": string("Key name.")}, required=["key"]),
        press_key,
        consequential=True,
    )
    registry.add(
        "find_element",
        "Find an element by CSS selector in the active browser page. Returns bounding box coordinates.",
        obj({"selector": string("CSS selector (e.g., 'button.submit', '#email-input').")}, required=["selector"]),
        find_element,
    )
    registry.add(
        "navigate_url",
        "Navigate to a URL in the active browser (requires browser remote debugging enabled).",
        obj({"url": string("Full URL (e.g., 'https://example.com').")}, required=["url"]),
        navigate_url,
        consequential=True,
    )
