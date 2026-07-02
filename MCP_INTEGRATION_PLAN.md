# MCP Server & Computer Control Integration Plan for Wren

## Executive Summary

This plan outlines a phased, modular integration of MCP (Model Control Protocol) servers and computer control into Wren's tool ecosystem. The implementation leverages Wren's existing modular architecture (`wren/tools/` registration pattern) to minimize core changes and maintain the principle of least privilege.

**Key principles:**
- Each MCP server becomes one or more Wren tools
- Tools follow Wren's `Tool(name, description, input_schema, handler)` pattern
- Consequential actions (OAuth, spending, deletions) are gated through the confirmation system
- Computer control is exposed as discrete, auditable tools (not raw "run code" access)

---

## Current Architecture (Recap)

### Tool System
- **Registration point:** `wren/tools/__init__.py` → `build_registry(ctx)` collects all tools
- **Tool pattern:** Each module exports `register(registry: Registry, ctx: ToolContext)` function
- **Safety layers:**
  - `Tool.consequential=True` → gated through confirmation (Tier 4/6)
  - `ToolContext` provides shared services: config, memory, reminders, notes, mailer
  - Error handling via `try/except` in `Tool.run()` → errors surface as plain-language strings

### Existing Tool Examples
1. **reminders.py** — demonstrates stateful tools with file-backed storage
2. **consequential.py** — demonstrates gating (send_message, spend_money, delete_data, change_settings)
3. **web.py** — demonstrates external API calls

### Config & Secrets
- `Config.get(dotted_key, default)` for application settings
- `Config.secret(env_var_name)` for OAuth tokens, API keys
- `.env` file (git-ignored) holds secrets; environment variables override defaults

---

## Phases Overview

| Phase | Focus | Services | Timeline | Impact |
|-------|-------|----------|----------|--------|
| **Phase 1** | High-impact Gmail/Calendar/Drive | Google APIs + OAuth wrapper | Weeks 1-2 | Core productivity |
| **Phase 2** | Computer control | Playwright-based screen/type tools | Weeks 3-4 | Automation multiplier |
| **Phase 3** | Specialized services | Canva, Higgsfield, Motion, etc. | Weeks 5-8 | Long-tail features |
| **Phase 4** | Multi-MCP orchestration | composio, n8n integration | Weeks 9-10 | Composability |

---

## Phase 1: High-Impact MCP Servers (Gmail, Calendar, Drive)

### Why First?
- **Email** is the universal inbox; most workflows involve it
- **Calendar** enables scheduling, availability checks, meeting creation
- **Drive** is a safe data layer for file operations (no local filesystem access)
- These three cover 70% of "I need to integrate with my digital life"

### Design Principles
- **One MCP tool per capability** (not one massive wrapper)
  - Example: `send_email`, `list_emails`, `search_emails` are separate tools
- **OAuth as a one-time setup cost** (cached in .env)
- **Batched operations** where the API allows (list 50 emails, not 1 email × 50 calls)
- **Confirmation gate** for sends/deletes (consequential=True)

### 1.1 Google OAuth Wrapper (New Foundation)

**File:** `wren/mcp/__init__.py` (new directory)

Create a reusable OAuth session manager that MCP tools will use:

```python
"""
MCP server wrappers with OAuth caching.

The pattern:
1. Check if token exists in config.secret('GOOGLE_OAUTH_TOKEN')
2. If expired or missing, trigger OAuth flow (or tell user to authenticate)
3. Cache token back to .env with explicit rotation
4. Pass authenticated client to downstream tools
"""

class GoogleOAuthClient:
    def __init__(self, config: Config, scopes: list[str]):
        self.config = config
        self.scopes = scopes
        self._client = None
    
    def get_client(self):
        """Lazy-load or refresh OAuth client."""
        # Use google-auth-oauthlib to manage tokens
        # Token storage: config.secret() backed by .env
        pass
    
    def is_authenticated(self) -> bool:
        """Check if we have a valid token."""
        pass
```

**Files to create:**
- `wren/mcp/__init__.py` — OAuth + MCP session management
- `wren/mcp/google_auth.py` — Google-specific OAuth flow
- `.env.example` — updated with GOOGLE_OAUTH_TOKEN, GMAIL_SCOPES, etc.

**Dependencies to add:**
```
google-auth-oauthlib>=1.0.0
google-auth-httplib2>=0.2.0
google-api-python-client>=2.100.0
```

**Config changes (config.yaml):**
```yaml
mcp:
  google:
    scopes:
      gmail: ["https://www.googleapis.com/auth/gmail.modify"]
      calendar: ["https://www.googleapis.com/auth/calendar"]
      drive: ["https://www.googleapis.com/auth/drive.file"]
    redirect_uri: "http://localhost:8080/callback"  # for local OAuth flow
```

---

### 1.2 Gmail Tool Module

**File:** `wren/tools/gmail.py`

```python
"""Gmail integration via MCP (read/search/send, with rate limiting)."""

def register(registry: Registry, ctx: ToolContext) -> None:
    oauth = ctx.google_oauth  # from ctx (built in build_context)
    
    # list_emails(limit=10, q="is:unread") → structured list
    # search_emails(q="from:boss") → metadata only, not full body (save tokens)
    # read_email(message_id) → full body (on demand)
    # send_email(to, subject, body) → CONSEQUENTIAL
    # draft_email(to, subject, body) → non-consequential preview
    # mark_read(message_ids)
    # delete_email(message_ids) → CONSEQUENTIAL
    # create_label(name)
    # apply_label(message_ids, label_name)
```

**Tools to register:**

| Tool | Consequential | Notes |
|------|---------------|-------|
| `list_emails` | No | Search, up to 50; sender/date/subject only |
| `read_email` | No | Full body on demand; cache common ones |
| `search_emails` | No | Gmail query syntax (from, to, is:unread, etc.) |
| `send_email` | **Yes** | Requires confirmation |
| `draft_email` | No | Preview only; safe to offer |
| `mark_email_read` | No | Convenience, but non-destructive |
| `delete_email` | **Yes** | Requires confirmation |
| `create_label` | No | Safe side-effect |
| `apply_label` | No | Safe side-effect |
| `reply_to_email` | **Yes** | Consequential (sends) |

**Schema example (for list_emails):**
```python
{
    "type": "object",
    "properties": {
        "q": {
            "type": "string",
            "description": "Gmail search query (e.g., 'is:unread from:alice')"
        },
        "limit": {
            "type": "integer",
            "description": "Max results (default 10, max 50)",
            "default": 10
        },
        "include_body": {
            "type": "boolean",
            "description": "Include full email body (slower, use sparingly)",
            "default": False
        }
    },
    "required": []
}
```

---

### 1.3 Google Calendar Tool Module

**File:** `wren/tools/calendar.py`

```python
"""Google Calendar integration (read availability, create events, set reminders)."""

def register(registry: Registry, ctx: ToolContext) -> None:
    oauth = ctx.google_oauth
    
    # list_events(calendar_id="primary", time_min=now, time_max=week_end, limit=50)
    # get_event(event_id)
    # create_event(summary, start, end, description, attendees) → CONSEQUENTIAL
    # update_event(event_id, summary, start, end) → CONSEQUENTIAL
    # delete_event(event_id) → CONSEQUENTIAL
    # get_availability(calendar_id, time_slots) → check if free
    # find_free_slot(duration_minutes, date_range) → AI-friendly search
```

**Tools to register:**

| Tool | Consequential | Notes |
|------|---------------|-------|
| `list_events` | No | Date range, summary + times only |
| `get_event` | No | Full event details on demand |
| `create_event` | **Yes** | Sends invite to attendees |
| `update_event` | **Yes** | May notify attendees |
| `delete_event` | **Yes** | Requires confirmation |
| `get_availability` | No | Read-only; check if free 9-5 tomorrow |
| `find_free_slot` | No | Search for open 30min blocks next week |

---

### 1.4 Google Drive Tool Module

**File:** `wren/tools/drive.py`

```python
"""Google Drive integration (upload, list, read text files, download links)."""

def register(registry: Registry, ctx: ToolContext) -> None:
    oauth = ctx.google_oauth
    
    # list_files(query, parent_folder_id, limit=50)
    # get_file_metadata(file_id)
    # read_file_text(file_id) → if text-like (txt, csv, md, json)
    # upload_file(file_path, parent_folder_id, name) → CONSEQUENTIAL (no undo)
    # create_folder(name, parent_folder_id)
    # share_file(file_id, email, role) → CONSEQUENTIAL
    # trash_file(file_id) → CONSEQUENTIAL
    # get_download_link(file_id) → shareable link
```

**Tools to register:**

| Tool | Consequential | Notes |
|------|---------------|-------|
| `list_files` | No | Name, size, type, created_by |
| `get_file_metadata` | No | Full file info |
| `read_file_text` | No | For docs, sheets (CSV export) |
| `create_folder` | No | Safe operation |
| `upload_file` | **Yes** | Persistent storage |
| `share_file` | **Yes** | Access control change |
| `trash_file` | **Yes** | Deletion (recoverable) |
| `get_download_link` | No | Read-only; returns URL |

---

### 1.5 Integration Checklist (Phase 1)

**Files to create:**
- [ ] `wren/mcp/__init__.py` — OAuth session manager
- [ ] `wren/mcp/google_auth.py` — Google OAuth flow
- [ ] `wren/tools/gmail.py` — All 9 tools
- [ ] `wren/tools/calendar.py` — All 7 tools
- [ ] `wren/tools/drive.py` — All 8 tools

**Files to modify:**
- [ ] `wren/tools/__init__.py` — import gmail, calendar, drive + register them
- [ ] `wren/tools/__init__.py` → `build_context()` — add `google_oauth: GoogleOAuthClient`
- [ ] `config.yaml` — add `mcp.google` section
- [ ] `.env.example` — add GOOGLE_OAUTH_TOKEN

**Testing:**
- [ ] Unit tests for each tool (mocked OAuth client)
- [ ] Integration tests with real Google API (requires test credentials)
- [ ] Manual: "send email to myself", "create calendar event", "upload a file"

**Documentation:**
- [ ] Setup guide: "How to authorize Wren with Gmail/Calendar/Drive"
- [ ] Schema reference (auto-generated from code)

---

## Phase 2: Computer Control Tools

### Why Second?
- Unlocks "click the button on the screen" automation
- Enables interaction with web apps that lack APIs (legacy systems, SaaS without SDK)
- Multiplies impact of Phase 1 (e.g., "fill out the form, then click submit")

### Design Principles
- **Discrete actions** (click, type, scroll) — not "run arbitrary code"
- **Limited scope** — target a specific element by selector/xpath
- **Screenshot + reasoning** — the agent sees what it changed
- **Rate limits** — avoid rapid-fire actions that crash browsers
- **Confirmation for destructive actions** — though "click" isn't inherently destructive, form submissions should ask

### 2.1 Browser/Screen Control Base

**File:** `wren/mcp/browser.py`

Use **Playwright** (no extra dependency; already in many Python envs):

```python
"""Lightweight Playwright wrapper for screen automation."""

class BrowserSession:
    def __init__(self, headless=True):
        self.browser = None
        self.page = None
    
    def init(self):
        """Start a browser (once, reused for session)."""
        from playwright.sync_api import sync_playwright
        self._pw = sync_playwright().start()
        self.browser = self._pw.chromium.launch(headless=True)
        self.page = self.browser.new_page()
    
    def screenshot(self) -> bytes:
        """Return current screen as PNG."""
        return self.page.screenshot()
    
    def navigate(self, url: str) -> str:
        """Go to URL, return page title."""
        self.page.goto(url, wait_until="load")
        return self.page.title()
    
    def click(self, selector: str) -> str:
        """Click element, return outcome (e.g., 'clicked #submit-btn')."""
        self.page.click(selector)
        return f"Clicked {selector}"
    
    def type(self, selector: str, text: str) -> str:
        """Type in input field."""
        self.page.fill(selector, text)
        return f"Typed '{text}' into {selector}"
    
    def get_text(self, selector: str) -> str:
        """Read text from element."""
        return self.page.text_content(selector) or ""
    
    def get_value(self, selector: str) -> str:
        """Read form input value."""
        return self.page.input_value(selector) or ""
    
    def scroll(self, direction: str = "down", amount: int = 3) -> str:
        """Scroll page."""
        if direction == "down":
            self.page.evaluate("window.scrollBy(0, 500)")
        elif direction == "up":
            self.page.evaluate("window.scrollBy(0, -500)")
        return f"Scrolled {direction}"
    
    def wait_for(self, selector: str, timeout_ms: int = 5000) -> bool:
        """Wait for element to appear."""
        try:
            self.page.wait_for_selector(selector, timeout=timeout_ms)
            return True
        except TimeoutError:
            return False
    
    def close(self):
        """Clean up browser."""
        if self.browser:
            self.browser.close()
        if self._pw:
            self._pw.stop()
```

**File:** `wren/tools/browser.py`

```python
"""Browser automation tools (Playwright-backed)."""

def register(registry: Registry, ctx: ToolContext) -> None:
    # Singleton browser session
    if not hasattr(ctx, "browser"):
        from ..mcp.browser import BrowserSession
        ctx.browser = BrowserSession()
        ctx.browser.init()
    
    browser = ctx.browser
    
    # navigate(url) → go to webpage
    # screenshot() → visual feedback
    # click(selector) → click element
    # type(selector, text) → type in input
    # get_text(selector) → read text
    # get_value(selector) → read input value
    # scroll(direction, amount)
    # wait_for(selector) → wait for element
    # fill_form({field_selector: value}) → batch fill
    # submit_form(selector) → click submit button
```

**Tools to register:**

| Tool | Consequential | Notes |
|------|---------------|-------|
| `screenshot` | No | Visual context for agent |
| `navigate` | No | Go to URL |
| `click` | No | Click element by selector |
| `type` | No | Type text in input |
| `get_text` | No | Read text from element |
| `get_value` | No | Read form input |
| `scroll` | No | Scroll page |
| `wait_for` | No | Wait for element (w/ timeout) |
| `fill_form` | No | Batch-fill multiple inputs |
| `submit_form` | **Yes** | Form submission = action |

**Screenshot + feedback loop:**
- Agent calls `screenshot` → gets base64 PNG
- Agent reasons over visual state
- Agent calls `click(selector)` or `type()`
- System returns structured feedback ("Clicked X", "Typed Y")
- Optionally: second screenshot to confirm change

---

### 2.2 Integration Checklist (Phase 2)

**Files to create:**
- [ ] `wren/mcp/browser.py` — BrowserSession wrapper
- [ ] `wren/tools/browser.py` — 10+ browser control tools

**Files to modify:**
- [ ] `wren/tools/__init__.py` — import browser + register
- [ ] `build_context()` — initialize BrowserSession singleton
- [ ] `requirements.txt` — add playwright

**Testing:**
- [ ] Unit tests (mock Playwright)
- [ ] Integration tests ("open google.com, search for X, click first result")
- [ ] Screenshot assertion tests

**Documentation:**
- [ ] Selector guide (CSS, XPath examples)
- [ ] Rate-limiting best practices
- [ ] Common patterns (fill form, navigate, verify)

---

## Phase 3: Specialized Services

### Why Third?
- Phase 1 covers "my digital hub" (email/calendar/drive)
- Phase 2 covers "automate any webpage"
- Phase 3 is long-tail: content creation, design, lead gen, payments

### 3.1 Canva (Design Tool)

**File:** `wren/tools/canva.py`

MCP server already available; wrapper bridges to Wren schema:

```python
"""Canva design tool integration."""

def register(registry: Registry, ctx: ToolContext) -> None:
    # create_design(template, content) → design_id
    # get_design(design_id) → metadata + preview
    # export_design(design_id, format) → download URL
    # list_designs(limit=20) → user's design library
    # search_templates(query) → find design templates
```

**Dependencies:**
```
canva>=0.1.0  # MCP client library
```

---

### 3.2 Higgsfield (AI Generation)

**File:** `wren/tools/higgsfield.py`

Image/video/audio/3D generation:

```python
def register(registry: Registry, ctx: ToolContext) -> None:
    # generate_image(prompt, model="default") → image_url
    # generate_video(prompt, duration_sec=10) → video_url + job_id
    # generate_audio(prompt, voice="default") → audio_url
    # generate_3d(image_url) → 3d_model_url
    # upscale_image(image_url, scale=2) → upscaled_url
    # remove_background(image_url) → transparent_png_url
```

**Considerations:**
- Higgsfield jobs are async → return job_id + polling endpoint
- Credit/quota system → check balance before big requests
- Cost tracking (log to audit)

---

### 3.3 Motion (Video Creation)

**File:** `wren/tools/motion.py`

```python
def register(registry: Registry, ctx: ToolContext) -> None:
    # create_video(brief, source_url=None, aspect_ratio="16:9") → video_url
    # create_followup(video_id, feedback) → updated_video_url
    # get_session_status(session_id) → progress
```

---

### 3.4 Apollo.io (Lead Generation)

**File:** `wren/tools/apollo.py`

```python
def register(registry: Registry, ctx: ToolContext) -> None:
    # search_contacts(query, limit=50) → contact list
    # search_companies(query, limit=20) → company list
    # enrich_contact(email) → full profile
    # enrich_company(domain) → company data
    # create_contact(name, email, company, title) → contact_id
    # add_to_sequence(contact_ids, sequence_id) → outcome
```

---

### 3.5 Stripe (Payments)

**File:** `wren/tools/stripe.py`

```python
def register(registry: Registry, ctx: ToolContext) -> None:
    # get_account_balance() → amount + currency
    # create_payment_link(amount, description) → link (for user to pay)
    # create_charge(amount, description, customer_email) → charge_id (CONSEQUENTIAL)
    # refund_charge(charge_id, amount) → refund_id (CONSEQUENTIAL)
    # list_charges(limit=50) → transaction history
```

---

### 3.6 Twilio (SMS/Calls)

**File:** `wren/tools/twilio.py`

```python
def register(registry: Registry, ctx: ToolContext) -> None:
    # send_sms(to, body) → message_id (CONSEQUENTIAL)
    # send_whatsapp(to, body) → message_id (CONSEQUENTIAL)
    # make_call(to, message_script) → call_id (CONSEQUENTIAL)
    # get_message_log(limit=50) → sms history
```

---

### 3.7 Miro (Whiteboarding)

**File:** `wren/tools/miro.py`

```python
def register(registry: Registry, ctx: ToolContext) -> None:
    # create_board(name, team_id) → board_id
    # get_board(board_id) → metadata
    # add_shape(board_id, shape_type, x, y, text) → shape_id
    # add_comment(board_id, x, y, text) → comment_id
    # list_boards(team_id, limit=50) → user's boards
```

---

### 3.8 n8n (Workflow Automation)

**File:** `wren/tools/n8n.py`

```python
def register(registry: Registry, ctx: ToolContext) -> None:
    # search_workflows(query) → workflow list
    # get_workflow(workflow_id) → full definition
    # create_workflow(name, nodes, connections) → workflow_id (CONSEQUENTIAL)
    # execute_workflow(workflow_id, input_data) → execution_id
    # get_execution_status(execution_id) → status + logs
    # list_credentials() → available integrations
```

---

### 3.9 composio (Tool Aggregation)

**File:** `wren/tools/composio_bridge.py`

composio aggregates 100+ third-party tools; bridge it as a meta-tool:

```python
def register(registry: Registry, ctx: ToolContext) -> None:
    # list_tools(category) → available integrations
    # execute_composio_tool(tool_name, action, params) → result
    # search_tools(query) → find tool by name/category
```

This lets the agent "reach" into composio's ecosystem without writing N separate wrappers.

---

### 3.10 Integration Checklist (Phase 3)

**Files to create:**
```
wren/tools/
  ├── canva.py
  ├── higgsfield.py
  ├── motion.py
  ├── apollo.py
  ├── stripe.py
  ├── twilio.py
  ├── miro.py
  ├── n8n.py
  └── composio_bridge.py
```

**Files to modify:**
- [ ] `wren/tools/__init__.py` — register all Phase 3 modules
- [ ] `config.yaml` — API keys & endpoints
- [ ] `.env.example` — secrets for each service

**Testing:**
- [ ] Per-tool integration tests (with test API keys)
- [ ] Error handling (API down, quota exceeded, auth failed)

**Documentation:**
- [ ] Authentication setup guide (one per service)
- [ ] Cost tracking & alerts
- [ ] Rate limits & batching strategies

---

## Phase 4: Multi-MCP Orchestration & Composition

### 4.1 Automatic Tool Discovery

Add a tool to list and call tools from multiple MCP servers without hardcoding wrappers:

```python
"""wren/tools/mcp_dispatcher.py"""

def register(registry: Registry, ctx: ToolContext) -> None:
    # list_mcp_servers() → ["gmail", "slack", "github", ...]
    # call_mcp_tool(server, tool_name, params) → result
    # get_tool_schema(server, tool_name) → full schema
```

This makes Wren extensible: add a new MCP server to config, and its tools become available without code changes.

---

### 4.2 Workflow Templates

Pre-built sequences of tools (as n8n workflows or as Wren composite tools):

**Examples:**
- "Send email + mark calendar + upload to drive" (one tool that chains 3)
- "Scrape webpage + generate image + post to social" (browser + Higgsfield + API)
- "Search contacts + create Apollo sequence + send first email" (Apollo + Gmail)

---

### 4.3 Feedback Loop Optimization

Store which tool combinations work well, learn from agent failures:

```python
"""wren/tools/tool_feedback.py"""

class ToolFeedback:
    """Track success rates, errors, and user corrections."""
    
    def log(self, tool_name, success, duration_ms, error=None):
        """Record: did this tool work? How fast?"""
        pass
    
    def get_suggestions(self, partial_task):
        """Based on history, suggest which tools to try."""
        pass
```

---

## Architecture: MCP Integration Points

### How MCP Servers Connect

```
┌─────────────────────────────────────────────────────────────┐
│ Wren Agent (orchestrator/agent.py)                          │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐  │
│  │ Tool Loop                                            │  │
│  │  1. Call LLM with tool_specs                        │  │
│  │  2. LLM picks tool + params                         │  │
│  │  3. Dispatch to tool handler                        │  │
│  │  4. Return result to LLM                            │  │
│  └──────────────────────────────────────────────────────┘  │
│                         │                                   │
│                         ▼                                   │
│  ┌──────────────────────────────────────────────────────┐  │
│  │ Tool Registry (orchestrator/registry.py)            │  │
│  │  ├─ Gmail tools                                    │  │
│  │  ├─ Calendar tools                                 │  │
│  │  ├─ Drive tools                                    │  │
│  │  ├─ Browser tools                                  │  │
│  │  ├─ Canva tools                                    │  │
│  │  ├─ Higgsfield tools                               │  │
│  │  ├─ n8n tools                                      │  │
│  │  └─ composio tools (meta)                          │  │
│  └──────────────────────────────────────────────────────┘  │
│                         │                                   │
└─────────────────────────┼───────────────────────────────────┘
                          │
           ┌──────────────┼──────────────┐
           ▼              ▼              ▼
       ┌────────┐    ┌────────┐    ┌─────────────┐
       │ Google │    │Playwright │  │ Apollo/Canva│
       │ APIs   │    │(Browser) │  │   APIs      │
       └────────┘    └────────┘    └─────────────┘
```

### Implementation: The MCP Tool Wrapper

Each tool module wraps MCP server(s):

```python
# wren/tools/gmail.py
def register(registry: Registry, ctx: ToolContext) -> None:
    # Get or create MCP client
    mcp_client = ctx.get_mcp_client("gmail")
    
    def send_email(args):
        # Translate Wren schema → MCP schema
        result = mcp_client.call("send_email", {
            "to": args["to"],
            "subject": args["subject"],
            "body": args["body"],
        })
        # Translate MCP result → plain-language string
        return f"Sent email to {args['to']} ({result['message_id']})"
    
    registry.add(
        "send_email",
        "Send an email via Gmail.",
        schema,
        send_email,
        consequential=True,  # Wren's gate, not MCP's
    )
```

### Authentication Strategy

```
Config Layer (config.yaml)
├─ mcp.services[name].enabled = true/false
├─ mcp.services[name].endpoint = "http://localhost:3000"
└─ mcp.services[name].scopes = [...]

Secrets Layer (.env, git-ignored)
├─ MCP_GMAIL_TOKEN = "..." (OAuth token)
├─ MCP_CANVA_API_KEY = "..."
├─ STRIPE_SECRET_KEY = "..."
└─ ...

Runtime (ToolContext)
├─ mcp_clients = {
│   "gmail": GoogleMCPClient(...),
│   "canva": CanvaMCPClient(...),
│   ...
│ }
└─ (lazy-loaded on first tool call)
```

---

## File Structure Summary

```
wren/
├─ tools/
│  ├─ __init__.py          (builds registry; imports all tool modules)
│  ├─ base.py              (Registry, Tool, ToolContext — unchanged)
│  ├─ reminders.py         (existing)
│  ├─ notes.py             (existing)
│  ├─ web.py               (existing)
│  ├─ memory_tools.py      (existing)
│  ├─ consequential.py      (existing)
│  │
│  ├─ gmail.py             (PHASE 1: 9 tools)
│  ├─ calendar.py          (PHASE 1: 7 tools)
│  ├─ drive.py             (PHASE 1: 8 tools)
│  │
│  ├─ browser.py           (PHASE 2: 10 tools)
│  │
│  ├─ canva.py             (PHASE 3: 5 tools)
│  ├─ higgsfield.py        (PHASE 3: 8 tools)
│  ├─ motion.py            (PHASE 3: 3 tools)
│  ├─ apollo.py            (PHASE 3: 6 tools)
│  ├─ stripe.py            (PHASE 3: 5 tools)
│  ├─ twilio.py            (PHASE 3: 4 tools)
│  ├─ miro.py              (PHASE 3: 5 tools)
│  ├─ n8n.py               (PHASE 3: 6 tools)
│  ├─ composio_bridge.py   (PHASE 3: 3 tools)
│  │
│  ├─ mcp_dispatcher.py    (PHASE 4: 3 tools)
│  └─ tool_feedback.py     (PHASE 4: learning layer)
│
├─ mcp/
│  ├─ __init__.py          (MCP session manager, OAuth wrapper)
│  ├─ google_auth.py       (Google OAuth flow)
│  ├─ browser.py           (Playwright wrapper)
│  └─ clients.py           (base MCP client + connection pool)
│
├─ app.py                  (update: pass ctx with MCP clients)
├─ config.py               (unchanged — uses existing Config)
└─ ...
```

---

## Dependency Management

### New Requirements (by phase)

**Phase 1:**
```
google-auth-oauthlib>=1.0.0
google-auth-httplib2>=0.2.0
google-api-python-client>=2.100.0
```

**Phase 2:**
```
playwright>=1.40.0
```

**Phase 3:**
```
stripe>=5.0.0
twilio>=8.0.0
apollo-python>=1.0.0  # (or direct HTTP wrapper)
canva>=0.1.0
```

**Phase 4:**
```
composio>=0.1.0
n8n>=0.1.0
```

### Optional Dependencies

Some services might not be enabled. Consider:
- Moving Phase 3+ to `extras_require` in setup.py
- Lazy imports (import only when tool is called)

---

## Configuration Deep Dive

### config.yaml Structure

```yaml
# Core Wren (existing)
assistant:
  name: Wren
  persona: "You are Wren, a helpful AI assistant."

# Tier 4 Confirmation (existing)
safety:
  confirm_tools:
    - send_message
    - spend_money
    - delete_data
    - send_email
    - create_event
    - spend_money
    - make_call
    - create_charge

# New: MCP Services
mcp:
  enabled: true
  services:
    gmail:
      enabled: true
      scopes:
        - "https://www.googleapis.com/auth/gmail.modify"
    calendar:
      enabled: true
      scopes:
        - "https://www.googleapis.com/auth/calendar"
    drive:
      enabled: true
      scopes:
        - "https://www.googleapis.com/auth/drive.file"
    canva:
      enabled: false
      endpoint: "http://localhost:3001"
    higgsfield:
      enabled: false
    stripe:
      enabled: false
    apollo:
      enabled: false
    twilio:
      enabled: false

# Rate limits & quotas
mcp:
  rate_limits:
    gmail_send: 100  # per day
    gmail_read: 1000
    calendar_create: 50
    browser_screenshot: 30  # per 60s (prevent spam)
```

### .env.example

```bash
# Google OAuth (Phase 1)
GOOGLE_OAUTH_TOKEN=
GOOGLE_OAUTH_REFRESH_TOKEN=
GOOGLE_CLIENT_ID=your-client-id@apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=

# Canva (Phase 3)
CANVA_API_KEY=

# Stripe (Phase 3)
STRIPE_SECRET_KEY=

# Apollo (Phase 3)
APOLLO_API_KEY=

# Twilio (Phase 3)
TWILIO_ACCOUNT_SID=
TWILIO_AUTH_TOKEN=
TWILIO_PHONE_NUMBER=

# n8n (Phase 3)
N8N_WEBHOOK_URL=
N8N_API_KEY=
```

---

## Confirmation Gate Integration

Wren's existing Tier 4 confirmation system already works. Phase 1-4 tools mark actions as `consequential=True`:

```python
registry.add(
    "send_email",
    "Send an email via Gmail.",
    schema,
    handler,
    consequential=True,  # ← This line triggers Tier 4 gate
)
```

The agent loop (in `wren/agent.py` or orchestrator) checks `tool.consequential` and surfaces a confirmation request before executing.

**No changes needed to the gate itself** — just set the flag on each tool.

---

## Error Handling & Observability

### Per-Tool Error Handling

Each tool catches exceptions and returns them as plain-language errors:

```python
def send_email(args):
    try:
        result = gmail_client.send(to=args["to"], subject=..., body=...)
        return f"Sent to {args['to']} (ID: {result.id})"
    except google.auth.exceptions.RefreshError:
        return "Gmail token expired. Re-authenticate with 'python -m wren auth gmail'."
    except Exception as e:
        return f"Failed to send email: {e}"
```

### Audit Trail

The existing audit system (in `wren/safety.py`) logs all tool calls. MCP tools are no different — they go through the same gate and audit.

### Cost Tracking

Some services (Higgsfield, Stripe) have real costs. Extend the audit:

```python
# wren/audit.py (existing)
class Audit:
    def log(self, ...):
        # Existing: LLM cost
        # New: service-specific cost
        self.f.write(f"CALL: send_email to={to} cost=$0.01\n")
```

---

## Migration & Rollout Strategy

### Week 1: Phase 1 (Gmail/Calendar/Drive)

- [ ] Design MCP wrapper architecture
- [ ] Implement GoogleOAuthClient
- [ ] Write gmail.py, calendar.py, drive.py (50 lines each)
- [ ] Wire into `build_registry()`
- [ ] Write integration tests (mocked Google API)
- [ ] Test with real Google account (dev-only)
- [ ] Publish setup guide

### Week 2: Phase 1 Polish

- [ ] Handle OAuth token refresh
- [ ] Rate limiting
- [ ] Error messages (user-friendly)
- [ ] Performance: cache common queries (recent emails)
- [ ] Documentation: examples + troubleshooting

### Week 3-4: Phase 2 (Browser Control)

- [ ] Implement BrowserSession (Playwright wrapper)
- [ ] Write browser.py (10 tools)
- [ ] Screenshot feedback loop
- [ ] Testing: navigate + click + verify
- [ ] Docs: selector guide, best practices

### Week 5-8: Phase 3 (Specialized Services)

- [ ] Canva, Higgsfield, Motion, Apollo, Stripe, Twilio, Miro, n8n
- [ ] 1 per day; each is ~50-100 lines
- [ ] Test with sandbox/test API keys
- [ ] Cost tracking integration

### Week 9-10: Phase 4 (Composition)

- [ ] MCP dispatcher (meta-tool)
- [ ] Tool feedback learning
- [ ] Workflow templates (pre-built chains)
- [ ] End-to-end tests (email + calendar + drive + browser)

---

## Risk Mitigation

| Risk | Mitigation |
|------|-----------|
| OAuth token expiry | Auto-refresh + graceful error message ("re-authenticate") |
| API rate limits | Batch operations, cache responses, per-tool rate limit enforcement |
| Broken MCP server | Tool handler catches exceptions; surfaced as plain error |
| Runaway browser | Playwright has built-in timeouts; optional headless screenshot limit |
| Expensive API calls (Higgsfield) | Check balance before calling; quota alerts in config |
| Conflicting tool names | Namespace: `gmail_send_email` vs `send_email` in composio |

---

## Testing Strategy

### Unit Tests (No API Key)

```python
# tests/test_gmail.py
def test_list_emails_schema():
    """Verify input schema is valid JSON schema."""
    assert "q" in tool.input_schema["properties"]

def test_send_email_mocked(mocker):
    """Mock Google API; test handler logic."""
    mock_client = mocker.MagicMock()
    # Set up mock
    result = send_email_handler({"to": "alice@example.com", ...})
    assert "Sent to alice" in result
```

### Integration Tests (Real API, Test Credentials)

```python
# tests/integration/test_gmail_real.py
@pytest.mark.integration
def test_send_email_real():
    """Real send to test account (requires GOOGLE_TEST_CREDS)."""
    ctx = build_test_context()
    result = tools["send_email"]({"to": "test+wren@example.com", ...})
    assert "Sent to" in result
```

### End-to-End Tests (Via Agent)

```python
# tests/e2e/test_email_workflow.py
def test_email_plus_calendar():
    """Agent: 'Send meeting invite to alice'."""
    agent = build_test_agent()
    response = agent.respond(
        "Send a calendar invite to alice@example.com for Friday 2pm",
        source="text"
    )
    # Verify: 1 email sent, 1 calendar event created
    assert "Sent" in response and "created" in response
```

---

## Documentation Outline

### 1. Getting Started

- [ ] "Add Gmail to Wren" (5 min setup)
- [ ] "Add Calendar to Wren" (5 min setup)
- [ ] "Add Drive to Wren" (5 min setup)

### 2. Reference

- [ ] Tool schemas (auto-generated from code)
- [ ] API error reference (common mistakes)
- [ ] Rate limits & quotas

### 3. Recipes

- [ ] "Send email + create reminder"
- [ ] "Scrape webpage + upload to Drive"
- [ ] "Search contacts + add to sequence + send email"

### 4. Troubleshooting

- [ ] "Gmail auth fails"
- [ ] "Tool not appearing in agent's toolkit"
- [ ] "Rate limit exceeded"

---

## Success Criteria

### Phase 1
- [ ] Agent can send email, read inbox, create calendar event, upload file
- [ ] Consequential actions ask for confirmation
- [ ] OAuth tokens refresh automatically

### Phase 2
- [ ] Agent can navigate webpage, click button, type in form
- [ ] Screenshots confirm changes
- [ ] No false positives (e.g., clicking wrong button)

### Phase 3
- [ ] All 9 services callable (even if some are disabled)
- [ ] Cost tracking works (Higgsfield, Stripe)
- [ ] Rate limits enforced

### Phase 4
- [ ] Multi-service workflows work end-to-end
- [ ] composio dispatcher bridges 100+ tools
- [ ] Tool feedback system identifies which chains are most reliable

---

## Rollback Plan

If a phase doesn't work:
1. Remove the tool module from `build_registry()` in `wren/tools/__init__.py`
2. Update config.yaml to disable that service
3. No restart needed (if Wren supports hot-reload; otherwise restart)

Example:
```python
# wren/tools/__init__.py
def build_registry(ctx: ToolContext) -> Registry:
    registry = Registry()
    # ... existing tools ...
    
    # Phase 1
    if ctx.config.get("mcp.services.gmail.enabled", False):
        gmail.register(registry, ctx)
    
    # Disable by removing this block (or set enabled: false in config)
```

---

## Conclusion

This plan provides a **modular, phased approach** to integrating 10+ MCP servers and computer control into Wren. Each phase is independently shippable, and the architecture leverages Wren's existing tool registry and confirmation system — **no major refactoring needed**.

**Key advantages:**
1. **Incremental value** — high-impact tools first (email/calendar/drive)
2. **Fail-safe** — exceptions surface as errors, not crashes
3. **Auditable** — all actions logged; consequential ones gated
4. **Extensible** — add a new service = add one tool module + 50 lines
5. **Testable** — unit tests work without API keys; integration tests use sandbox credentials

**Next step:** Start Phase 1 Week 1 (Google OAuth + Gmail/Calendar/Drive).
