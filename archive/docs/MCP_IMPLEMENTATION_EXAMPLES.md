# MCP Integration — Code Examples & Implementation Details

This document contains concrete code snippets and architectural details to support the MCP Integration Plan.

---

## Part 1: OAuth Foundation (Phase 1)

### `wren/mcp/__init__.py`

```python
"""MCP session manager with OAuth caching and token refresh."""
from __future__ import annotations

import os
from typing import Any

from ..config import Config


class MCPSessionManager:
    """Factory for authenticated MCP clients, with token caching."""

    def __init__(self, config: Config):
        self.config = config
        self._clients: dict[str, Any] = {}

    def get_client(self, service: str, client_class):
        """Get or create an authenticated client for a service."""
        if service not in self._clients:
            token = Config.secret(f"MCP_{service.upper()}_TOKEN")
            if not token:
                raise RuntimeError(
                    f"No token for {service}. Run: "
                    f"python -m wren auth {service}"
                )
            self._clients[service] = client_class(
                token=token,
                config=self.config,
            )
        return self._clients[service]


# Singleton instance (per app lifetime)
_session_manager = None


def get_session_manager(config: Config) -> MCPSessionManager:
    global _session_manager
    if not _session_manager:
        _session_manager = MCPSessionManager(config)
    return _session_manager
```

### `wren/mcp/google_auth.py`

```python
"""Google OAuth 2.0 flow and token refresh."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

from ..config import Config


class GoogleOAuthManager:
    """Manages Google OAuth tokens: obtain, refresh, persist."""

    SCOPES = {
        "gmail": ["https://www.googleapis.com/auth/gmail.modify"],
        "calendar": ["https://www.googleapis.com/auth/calendar"],
        "drive": ["https://www.googleapis.com/auth/drive.file"],
    }

    def __init__(self, config: Config, credentials_json_path: Path):
        self.config = config
        self.credentials_json = credentials_json_path
        self._credentials: Credentials | None = None

    def get_credentials(self, service: str = "gmail") -> Credentials:
        """Get valid OAuth credentials, refreshing if needed."""
        token_string = Config.secret("GOOGLE_OAUTH_TOKEN")
        
        if token_string:
            # Load from cached token
            token_dict = json.loads(token_string)
            self._credentials = Credentials.from_authorized_user_info(
                token_dict,
                scopes=self.SCOPES.get(service, []),
            )
            
            # Refresh if expired
            if self._credentials.expired:
                self._refresh_token()
        else:
            # First-time OAuth flow
            self._do_oauth_flow(service)

        return self._credentials

    def _do_oauth_flow(self, service: str) -> None:
        """Interactive OAuth consent screen."""
        flow = InstalledAppFlow.from_client_secrets_file(
            self.credentials_json,
            scopes=self.SCOPES.get(service, []),
        )
        # Local redirect URI (requires browser)
        self._credentials = flow.run_local_server(port=8080)
        self._save_token()

    def _refresh_token(self) -> None:
        """Refresh expired token."""
        request = Request()
        self._credentials.refresh(request)
        self._save_token()

    def _save_token(self) -> None:
        """Persist token to .env for next run."""
        token_json = self._credentials.to_json()
        # Write to .env (or config)
        # Note: This is a simplified example; real code should use secure storage
        os.environ["GOOGLE_OAUTH_TOKEN"] = token_json


# Usage in tools:
# oauth_manager = GoogleOAuthManager(config, Path("credentials.json"))
# credentials = oauth_manager.get_credentials("gmail")
# gmail_service = build("gmail", "v1", credentials=credentials)
```

---

## Part 2: Gmail Tool Module (Phase 1)

### `wren/tools/gmail.py`

```python
"""Gmail integration via Google API (read/search/send with rate limiting)."""
from __future__ import annotations

import base64
from typing import Any

from googleapiclient.discovery import build

from .base import Registry, obj, string


class GmailClient:
    """Wrapper around Google Gmail API."""

    def __init__(self, credentials, rate_limiter=None):
        self.service = build("gmail", "v1", credentials=credentials)
        self.rate_limiter = rate_limiter

    def list_emails(
        self,
        q: str = "",
        limit: int = 10,
        include_body: bool = False,
    ) -> list[dict[str, Any]]:
        """List emails matching query."""
        limit = min(limit, 50)  # API limit
        results = self.service.users().messages().list(
            userId="me",
            q=q,
            maxResults=limit,
        ).execute()

        messages = results.get("messages", [])
        output = []

        for msg in messages:
            msg_data = {
                "id": msg["id"],
                "snippet": msg.get("snippet", ""),
            }
            if include_body:
                full = self.service.users().messages().get(
                    userId="me",
                    id=msg["id"],
                    format="full",
                ).execute()
                headers = full["payload"]["headers"]
                msg_data["from"] = next(
                    (h["value"] for h in headers if h["name"] == "From"),
                    "",
                )
                msg_data["subject"] = next(
                    (h["value"] for h in headers if h["name"] == "Subject"),
                    "",
                )
                msg_data["date"] = next(
                    (h["value"] for h in headers if h["name"] == "Date"),
                    "",
                )
            output.append(msg_data)

        return output

    def send_email(self, to: str, subject: str, body: str) -> dict[str, Any]:
        """Send an email."""
        from email.mime.text import MIMEText

        message = MIMEText(body)
        message["to"] = to
        message["subject"] = subject
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()

        result = self.service.users().messages().send(
            userId="me",
            body={"raw": raw},
        ).execute()
        return result

    def get_label_id(self, label_name: str) -> str | None:
        """Get label ID by name."""
        results = self.service.users().labels().list(userId="me").execute()
        for label in results.get("labels", []):
            if label["name"] == label_name:
                return label["id"]
        return None

    def apply_label(self, message_ids: list[str], label_name: str) -> None:
        """Apply label to messages."""
        label_id = self.get_label_id(label_name)
        if not label_id:
            raise ValueError(f"Label '{label_name}' not found")

        for msg_id in message_ids:
            self.service.users().messages().modify(
                userId="me",
                id=msg_id,
                body={"addLabelIds": [label_id]},
            ).execute()


def register(registry: Registry, ctx) -> None:
    """Register Gmail tools."""
    # Build OAuth manager if not already done
    if not hasattr(ctx, "google_oauth"):
        from ..mcp.google_auth import GoogleOAuthManager
        from pathlib import Path

        ctx.google_oauth = GoogleOAuthManager(
            ctx.config,
            Path(ctx.config.resolve_path("mcp.google.credentials_json", "credentials.json")),
        )

    credentials = ctx.google_oauth.get_credentials("gmail")
    gmail = GmailClient(credentials)

    # --- list_emails ---
    def list_emails_handler(args: dict[str, Any]) -> str:
        q = args.get("q", "")
        limit = args.get("limit", 10)
        include_body = args.get("include_body", False)

        emails = gmail.list_emails(q, limit, include_body)
        if not emails:
            return "No emails found."

        lines = []
        for email in emails:
            snippet = email.get("snippet", "")[:50]
            if email.get("subject"):
                lines.append(f"- [{email['id']}] {email['subject']}: {snippet}")
            else:
                lines.append(f"- [{email['id']}] {snippet}")
        return "\n".join(lines)

    registry.add(
        "list_emails",
        "Search and list emails. Use Gmail query syntax: "
        "'is:unread', 'from:alice@example.com', 'subject:meeting'.",
        obj(
            {
                "q": string(
                    "Gmail search query (optional). "
                    "e.g., 'is:unread from:boss@company.com'."
                ),
                "limit": {
                    "type": "integer",
                    "description": "Max results (default 10, max 50).",
                    "default": 10,
                },
                "include_body": {
                    "type": "boolean",
                    "description": "Include full email body (slower).",
                    "default": False,
                },
            }
        ),
        list_emails_handler,
    )

    # --- send_email ---
    def send_email_handler(args: dict[str, Any]) -> str:
        to = args.get("to", "").strip()
        subject = args.get("subject", "").strip()
        body = args.get("body", "").strip()

        if not to or not body:
            return "Need both 'to' and 'body'."

        result = gmail.send_email(to, subject, body)
        return f"Email sent to {to} (ID: {result.get('id', 'unknown')})"

    registry.add(
        "send_email",
        "Send an email via Gmail. CONSEQUENTIAL: reaches someone.",
        obj(
            {
                "to": string("Recipient email address."),
                "subject": string("Email subject (optional)."),
                "body": string("Email body."),
            },
            required=["to", "body"],
        ),
        send_email_handler,
        consequential=True,
    )

    # --- draft_email (preview, non-consequential) ---
    def draft_email_handler(args: dict[str, Any]) -> str:
        to = (args.get("to") or "").strip()
        subject = (args.get("subject") or "").strip()
        body = (args.get("body") or "").strip()
        return f"""Draft email:
To: {to}
Subject: {subject}

{body}

(Not sent. Confirm with send_email to actually send it.)"""

    registry.add(
        "draft_email",
        "Preview an email draft (does NOT send).",
        obj(
            {
                "to": string("Recipient email address."),
                "subject": string("Email subject (optional)."),
                "body": string("Email body."),
            },
            required=["to", "body"],
        ),
        draft_email_handler,
    )

    # --- reply_to_email ---
    def reply_to_email_handler(args: dict[str, Any]) -> str:
        message_id = args.get("message_id", "").strip()
        body = args.get("body", "").strip()

        if not message_id or not body:
            return "Need both 'message_id' and 'body'."

        # Simplified: just forward with Re: prefix
        # Real implementation would parse the original email and quote it
        result = gmail.send_email(
            to="(reply impl)",  # Would extract from original
            subject="Re: (subject)",
            body=body,
        )
        return f"Reply sent (ID: {result.get('id', 'unknown')})"

    registry.add(
        "reply_to_email",
        "Reply to an email by message ID.",
        obj(
            {
                "message_id": string("The email's message ID."),
                "body": string("Your reply text."),
            },
            required=["message_id", "body"],
        ),
        reply_to_email_handler,
        consequential=True,
    )

    # --- mark_email_read ---
    def mark_email_read_handler(args: dict[str, Any]) -> str:
        message_ids = args.get("message_ids", [])
        if not message_ids:
            return "Need a list of message IDs."

        for msg_id in message_ids:
            gmail.service.users().messages().modify(
                userId="me",
                id=msg_id,
                body={"removeLabelIds": ["UNREAD"]},
            ).execute()
        return f"Marked {len(message_ids)} email(s) as read."

    registry.add(
        "mark_email_read",
        "Mark one or more emails as read.",
        obj(
            {
                "message_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of message IDs.",
                }
            },
            required=["message_ids"],
        ),
        mark_email_read_handler,
    )

    # Additional tools: delete_email, apply_label, create_label, etc.
    # (omitted for brevity; follow same pattern)
```

---

## Part 3: Browser Control (Phase 2)

### `wren/mcp/browser.py`

```python
"""Lightweight Playwright wrapper for screen automation."""
from __future__ import annotations

import base64
from io import BytesIO

from PIL import Image


class BrowserSession:
    """Reusable browser session (per app lifecycle)."""

    def __init__(self, headless: bool = True, width: int = 1280, height: int = 720):
        self.headless = headless
        self.width = width
        self.height = height
        self.browser = None
        self.page = None
        self._pw = None

    def init(self) -> None:
        """Start the browser (called once, on app startup)."""
        from playwright.sync_api import sync_playwright

        self._pw = sync_playwright().start()
        self.browser = self._pw.chromium.launch(headless=self.headless)
        self.page = self.browser.new_page(
            viewport={"width": self.width, "height": self.height}
        )

    def screenshot_b64(self) -> str:
        """Return base64-encoded PNG screenshot."""
        if not self.page:
            return ""
        png_bytes = self.page.screenshot()
        return base64.b64encode(png_bytes).decode("utf-8")

    def screenshot_with_annotations(self) -> str:
        """Screenshot with bounding boxes around clickable elements."""
        # Simplified: just return the raw screenshot
        # Real impl: overlay boxes around <button>, <a>, <input>, etc.
        return self.screenshot_b64()

    def navigate(self, url: str, wait_until: str = "load") -> str:
        """Navigate to URL; return page title."""
        self.page.goto(url, wait_until=wait_until)
        return f"Navigated to {url}. Title: {self.page.title()}"

    def click(self, selector: str) -> str:
        """Click an element."""
        self.page.click(selector)
        return f"Clicked {selector}"

    def type_text(self, selector: str, text: str, delay: int = 50) -> str:
        """Type text into input field."""
        self.page.fill(selector, "")  # Clear first
        self.page.type(selector, text, delay=delay)
        return f"Typed into {selector}: '{text}'"

    def get_text(self, selector: str) -> str:
        """Read text content of element."""
        text = self.page.text_content(selector) or ""
        return text.strip()

    def get_value(self, selector: str) -> str:
        """Read value of form input."""
        return self.page.input_value(selector) or ""

    def scroll(self, direction: str = "down", pixels: int = 500) -> str:
        """Scroll page."""
        if direction == "down":
            self.page.evaluate(f"window.scrollBy(0, {pixels})")
        elif direction == "up":
            self.page.evaluate(f"window.scrollBy(0, -{pixels})")
        elif direction == "top":
            self.page.evaluate("window.scrollTo(0, 0)")
        elif direction == "bottom":
            self.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        return f"Scrolled {direction} by {pixels}px"

    def wait_for_selector(self, selector: str, timeout_ms: int = 5000) -> bool:
        """Wait for element to appear."""
        try:
            self.page.wait_for_selector(selector, timeout=timeout_ms)
            return True
        except:
            return False

    def fill_form(self, fields: dict[str, str]) -> str:
        """Batch-fill multiple form inputs."""
        for selector, value in fields.items():
            self.page.fill(selector, value)
        return f"Filled {len(fields)} field(s)"

    def get_all_text(self) -> str:
        """Get all visible text on page (for context)."""
        return self.page.evaluate("document.body.innerText") or ""

    def close(self) -> None:
        """Shutdown browser."""
        if self.browser:
            self.browser.close()
        if self._pw:
            self._pw.stop()

    def __del__(self):
        """Cleanup on garbage collection."""
        self.close()
```

### `wren/tools/browser.py`

```python
"""Browser automation tools."""
from __future__ import annotations

from typing import Any

from .base import Registry, obj, string


def register(registry: Registry, ctx) -> None:
    """Register browser tools."""
    if not hasattr(ctx, "browser"):
        from ..mcp.browser import BrowserSession

        ctx.browser = BrowserSession(headless=True)
        ctx.browser.init()

    browser = ctx.browser

    # --- screenshot ---
    def screenshot_handler(args: dict[str, Any]) -> str:
        b64 = browser.screenshot_b64()
        # Return markdown that embeds the image
        return f"Screenshot taken. [View](data:image/png;base64,{b64})"

    registry.add(
        "screenshot",
        "Take a screenshot of the current browser window.",
        obj({}),
        screenshot_handler,
    )

    # --- navigate ---
    def navigate_handler(args: dict[str, Any]) -> str:
        url = args.get("url", "").strip()
        if not url:
            return "Need a URL."
        return browser.navigate(url)

    registry.add(
        "navigate",
        "Navigate to a URL.",
        obj({"url": string("The URL to navigate to (must include http:// or https://).")}),
        navigate_handler,
    )

    # --- click ---
    def click_handler(args: dict[str, Any]) -> str:
        selector = args.get("selector", "").strip()
        if not selector:
            return "Need a CSS selector or XPath."
        try:
            return browser.click(selector)
        except Exception as e:
            return f"Failed to click: {e}"

    registry.add(
        "click",
        "Click an element on the page by CSS selector or XPath.",
        obj(
            {
                "selector": string(
                    "CSS selector (e.g., '#submit-btn', '.btn', '[type=button]') "
                    "or XPath."
                )
            },
            required=["selector"],
        ),
        click_handler,
    )

    # --- type ---
    def type_handler(args: dict[str, Any]) -> str:
        selector = args.get("selector", "").strip()
        text = args.get("text", "").strip()
        if not selector or not text:
            return "Need both 'selector' and 'text'."
        try:
            return browser.type_text(selector, text)
        except Exception as e:
            return f"Failed to type: {e}"

    registry.add(
        "type",
        "Type text into a form input field.",
        obj(
            {
                "selector": string("CSS selector or XPath of input field."),
                "text": string("Text to type."),
            },
            required=["selector", "text"],
        ),
        type_handler,
    )

    # --- scroll ---
    def scroll_handler(args: dict[str, Any]) -> str:
        direction = args.get("direction", "down").lower()
        pixels = args.get("pixels", 500)
        return browser.scroll(direction, pixels)

    registry.add(
        "scroll",
        "Scroll the page up, down, to top, or to bottom.",
        obj(
            {
                "direction": {
                    "type": "string",
                    "enum": ["up", "down", "top", "bottom"],
                    "default": "down",
                },
                "pixels": {
                    "type": "integer",
                    "description": "Amount to scroll (for up/down).",
                    "default": 500,
                },
            }
        ),
        scroll_handler,
    )

    # --- fill_form ---
    def fill_form_handler(args: dict[str, Any]) -> str:
        fields = args.get("fields", {})
        if not fields:
            return "Need a dict of selector: value pairs."
        try:
            return browser.fill_form(fields)
        except Exception as e:
            return f"Failed to fill form: {e}"

    registry.add(
        "fill_form",
        "Fill multiple form inputs at once.",
        obj(
            {
                "fields": {
                    "type": "object",
                    "description": "Map of selector -> value (string).",
                    "additionalProperties": {"type": "string"},
                }
            },
            required=["fields"],
        ),
        fill_form_handler,
    )

    # --- wait_for ---
    def wait_for_handler(args: dict[str, Any]) -> str:
        selector = args.get("selector", "").strip()
        timeout = args.get("timeout_ms", 5000)
        if not selector:
            return "Need a selector."
        found = browser.wait_for_selector(selector, timeout)
        if found:
            return f"Element '{selector}' appeared."
        return f"Timeout waiting for '{selector}'."

    registry.add(
        "wait_for",
        "Wait for an element to appear on the page.",
        obj(
            {
                "selector": string("CSS selector or XPath."),
                "timeout_ms": {
                    "type": "integer",
                    "description": "Max wait time in milliseconds.",
                    "default": 5000,
                },
            },
            required=["selector"],
        ),
        wait_for_handler,
    )

    # --- get_text ---
    def get_text_handler(args: dict[str, Any]) -> str:
        selector = args.get("selector", "").strip()
        if not selector:
            return "Need a selector."
        text = browser.get_text(selector)
        return f"Text from {selector}: {text}"

    registry.add(
        "get_text",
        "Read text content from an element.",
        obj({"selector": string("CSS selector or XPath.")}),
        get_text_handler,
    )
```

---

## Part 4: Tool Registry Integration

### Updated `wren/tools/__init__.py`

```python
"""Tool registry assembly.

Each tool module exports register(registry, ctx). Build_registry iterates them.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from . import (
    apollo,
    browser,
    calendar,
    canva,
    consequential,
    drive,
    gmail,
    higgsfield,
    memory_tools,
    miro,
    motion,
    notes,
    reminders,
    stripe,
    twilio,
    web,
)
from .base import Registry
from .notes import Notes
from .reminders import Reminders


@dataclass
class ToolContext:
    """Shared services that tools need."""

    config: Any  # wren.config.Config
    reminders: Reminders
    notes: Notes
    memory: Any  # wren.memory.Memory
    mailer: Any = None  # wren.mailer.Mailer | None


def build_context(config, memory) -> ToolContext:
    from ..mailer import build_mailer

    return ToolContext(
        config=config,
        reminders=Reminders(config.resolve_path("reminders.path", "data/reminders.json")),
        notes=Notes(config.resolve_path("notes.path", "data/notes")),
        memory=memory,
        mailer=build_mailer(config),
    )


def build_registry(ctx: ToolContext) -> Registry:
    """Build the tool registry, respecting mcp.services.*.enabled in config."""
    registry = Registry()

    # Tier 2 — safe, non-consequential tools
    reminders.register(registry, ctx)
    notes.register(registry, ctx)
    web.register(registry, ctx)

    # Tier 4 — memory management
    memory_tools.register(registry, ctx)

    # Tier 6 — gated tools (send, delete, spend, configure)
    consequential.register(registry, ctx)

    # Phase 1: High-impact Google services
    if ctx.config.get("mcp.services.gmail.enabled", False):
        gmail.register(registry, ctx)
    if ctx.config.get("mcp.services.calendar.enabled", False):
        calendar.register(registry, ctx)
    if ctx.config.get("mcp.services.drive.enabled", False):
        drive.register(registry, ctx)

    # Phase 2: Browser automation
    if ctx.config.get("mcp.services.browser.enabled", False):
        browser.register(registry, ctx)

    # Phase 3: Specialized services
    if ctx.config.get("mcp.services.canva.enabled", False):
        canva.register(registry, ctx)
    if ctx.config.get("mcp.services.higgsfield.enabled", False):
        higgsfield.register(registry, ctx)
    if ctx.config.get("mcp.services.motion.enabled", False):
        motion.register(registry, ctx)
    if ctx.config.get("mcp.services.apollo.enabled", False):
        apollo.register(registry, ctx)
    if ctx.config.get("mcp.services.stripe.enabled", False):
        stripe.register(registry, ctx)
    if ctx.config.get("mcp.services.twilio.enabled", False):
        twilio.register(registry, ctx)
    if ctx.config.get("mcp.services.miro.enabled", False):
        miro.register(registry, ctx)

    return registry
```

---

## Part 5: Configuration Example

### Updated `config.yaml`

```yaml
# Wren — Agent Orchestration Layer
# This file configures the assistant, the tool registry, safety gates,
# and MCP service integrations.

assistant:
  name: Wren
  persona: |
    You are Wren, a helpful AI assistant. You have access to email, calendar,
    drive, and browser automation tools. You can help draft messages, schedule
    meetings, manage files, and automate web tasks.

brain:
  model: claude-opus-4-8  # or claude-sonnet, claude-haiku
  max_tool_rounds: 8

memory:
  path: data/memory.json
  max_facts: 12
  full_below: 20

heartbeat:
  enabled: false
  inbox_path: data/inbox.json

safety:
  audit_log: data/audit.log
  confirm_tools:
    # Tier 4 gates — these actions always ask first
    - send_message
    - send_email
    - reply_to_email
    - create_event
    - update_event
    - delete_event
    - upload_file
    - trash_file
    - share_file
    - spend_money
    - create_charge
    - refund_charge
    - send_sms
    - send_whatsapp
    - make_call
    - delete_data
    - change_settings
    - create_workflow
    - execute_workflow

# MCP Server Integration (Phase 1-4)
mcp:
  enabled: true
  
  services:
    # Phase 1: Google APIs
    gmail:
      enabled: false  # Set to true + set GOOGLE_OAUTH_TOKEN in .env
      scopes:
        - "https://www.googleapis.com/auth/gmail.modify"
    
    calendar:
      enabled: false
      scopes:
        - "https://www.googleapis.com/auth/calendar"
    
    drive:
      enabled: false
      scopes:
        - "https://www.googleapis.com/auth/drive.file"
    
    # Phase 2: Browser control
    browser:
      enabled: false  # Uses Playwright, no auth needed
      headless: true
      width: 1280
      height: 720
    
    # Phase 3: Specialized services
    canva:
      enabled: false
      # endpoint: "http://localhost:3001"  # Optional MCP server endpoint
    
    higgsfield:
      enabled: false
    
    motion:
      enabled: false
    
    apollo:
      enabled: false
    
    stripe:
      enabled: false
    
    twilio:
      enabled: false
    
    miro:
      enabled: false
  
  # Rate limits per service (to prevent accidental spam/cost overruns)
  rate_limits:
    gmail_send: 100  # emails/day
    gmail_read: 1000
    calendar_create: 50  # events/day
    browser_click: 100  # clicks/hour
    higgsfield_image: 10  # images/day (expensive)
    stripe_charge: 50  # charges/day
    twilio_sms: 100  # messages/day
```

### `.env.example`

```bash
# Core API
ANTHROPIC_API_KEY=sk-ant-...

# Phase 1: Google OAuth
# Get these from https://console.cloud.google.com/
GOOGLE_CLIENT_ID=your-client-id@apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your-client-secret
GOOGLE_OAUTH_TOKEN=  # Auto-populated after first auth flow

# Phase 3: Specialized Services
CANVA_API_KEY=
CANVA_WEBHOOK_SECRET=

STRIPE_SECRET_KEY=
STRIPE_PUBLISHABLE_KEY=

APOLLO_API_KEY=

TWILIO_ACCOUNT_SID=
TWILIO_AUTH_TOKEN=
TWILIO_PHONE_NUMBER=+1...

MIRO_API_TOKEN=

N8N_API_KEY=
N8N_WEBHOOK_URL=http://localhost:5678/webhook/

# SMTP (for fallback email, if not using Gmail)
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USERNAME=...
SMTP_PASSWORD=...
SMTP_FROM=wren@example.com
```

---

## Part 6: Error Handling Pattern

All tool handlers follow this pattern:

```python
def tool_handler(args: dict[str, Any]) -> str:
    """
    Every tool handler:
    1. Validates inputs
    2. Calls the underlying API
    3. Catches exceptions and converts to plain-language errors
    4. Returns a string (success or error message)
    
    The agent reads this string and decides what to do.
    """
    try:
        # Extract args
        param_a = args.get("param_a", "").strip()
        param_b = args.get("param_b")
        
        # Validate
        if not param_a:
            return "I need param_a."
        
        # Call API
        result = some_api_call(param_a, param_b)
        
        # Return success message
        return f"Done! Result: {result}"
    
    except AuthError as e:
        return f"Authorization failed: {e}. Run 'python -m wren auth service'."
    except RateLimitError as e:
        return f"Rate limit exceeded. Try again in {e.retry_after_seconds} seconds."
    except NotFoundError as e:
        return f"Not found: {e}"
    except Exception as e:
        return f"Unexpected error: {e}"
```

---

## Part 7: Testing Patterns

### Unit Test (No API Key)

```python
# tests/test_gmail.py
import pytest
from unittest.mock import MagicMock, patch

from wren.tools import gmail
from wren.tools.base import Registry


def test_send_email_schema():
    """Verify the tool schema is valid JSON schema."""
    registry = Registry()
    
    # Mock Google API
    with patch("wren.mcp.google_auth.GoogleOAuthManager") as mock_oauth:
        ctx = MagicMock()
        ctx.config.get.return_value = False
        ctx.config.resolve_path.return_value = "/fake/path"
        
        gmail.register(registry, ctx)
    
    # Verify tools were registered
    assert registry.get("send_email") is not None
    
    # Verify schema
    tool = registry.get("send_email")
    assert "to" in tool.input_schema["properties"]
    assert "to" in tool.input_schema["required"]


def test_send_email_handler_validation():
    """Test input validation (no API call)."""
    from wren.tools.gmail import send_email_handler_factory
    
    handler = send_email_handler_factory(MagicMock())
    
    # Missing 'to'
    result = handler({"body": "test"})
    assert "Need both" in result or "to" in result.lower()


@pytest.mark.integration
@pytest.mark.skipif(not os.environ.get("GOOGLE_TEST_CREDS"), reason="No test credentials")
def test_send_email_real():
    """Real integration test (requires GOOGLE_TEST_CREDS in .env)."""
    from wren.config import Config
    from wren.tools import gmail
    from wren.tools.base import Registry
    
    config = Config.load()
    ctx = MagicMock()
    ctx.config = config
    
    registry = Registry()
    gmail.register(registry, ctx)
    
    # Send a test email
    send_email = registry.get("send_email")
    result = send_email.run({
        "to": "test+wren@example.com",
        "subject": "Wren Test",
        "body": "This is a test email from Wren.",
    })
    
    assert "Sent" in result
    assert "test+wren@example.com" in result
```

---

## Part 8: Checklist for Implementation

### Pre-Phase-1 Setup
- [ ] Create `wren/mcp/` directory
- [ ] Create OAuth manager (`google_auth.py`)
- [ ] Test with real Google credentials (dev-only)
- [ ] Add Phase 1 dependencies to `requirements.txt`

### Phase 1 (Week 1-2)
- [ ] Implement `gmail.py` (9 tools)
- [ ] Implement `calendar.py` (7 tools)
- [ ] Implement `drive.py` (8 tools)
- [ ] Unit tests for each module (mocked API)
- [ ] Integration tests (real API, test credentials)
- [ ] Update `config.yaml` with MCP section
- [ ] Update `.env.example`
- [ ] Setup guide: "Add Gmail to Wren"

### Phase 2 (Week 3-4)
- [ ] Implement Playwright wrapper (`mcp/browser.py`)
- [ ] Implement `browser.py` (10 tools)
- [ ] Unit & integration tests
- [ ] Screenshot feedback loop
- [ ] Selector guide (CSS, XPath examples)

### Phase 3 (Week 5-8)
- [ ] Implement each service module (8 modules)
- [ ] Per-module tests
- [ ] Cost tracking for expensive services
- [ ] Authentication setup guides (per service)

### Phase 4 (Week 9-10)
- [ ] MCP dispatcher (`mcp_dispatcher.py`)
- [ ] Tool feedback system (`tool_feedback.py`)
- [ ] Workflow templates
- [ ] End-to-end tests across services

---

## Conclusion

This document provides:
1. **Concrete code** for OAuth, Gmail, Calendar, Drive, and browser automation
2. **Integration patterns** showing how to add tools to the registry
3. **Configuration examples** for enable/disable and rate limiting
4. **Testing strategies** at unit and integration levels
5. **Error handling patterns** for robust tool implementations

Use these as templates for Phase 3 and 4 services.
