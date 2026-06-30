# MCP Server Integration Setup Guide

This guide walks through setting up Wren's MCP server integrations: Gmail, Google Calendar, Google Drive, and computer control.

## Overview

Wren now supports:
- **Gmail** — search, read, and manage emails
- **Google Calendar** — list events, create meetings, check availability
- **Google Drive** — search, list, and read files
- **Computer Control** — take screenshots, click, type, navigate (Playwright + PyAutoGUI)

All these tools are marked as `consequential=True` and require user confirmation before execution.

## Prerequisites

Install the MCP dependencies:

```bash
pip install -r requirements.txt
```

This includes:
- `google-auth-oauthlib` — OAuth2 for Google APIs
- `google-api-python-client` — Gmail, Calendar, Drive APIs
- `playwright` — Browser automation for computer control
- `pyautogui` — Screen control (click/type)

## Phase 1: Google APIs (Gmail, Calendar, Drive)

### Step 1: Create a Google Cloud Project

1. Go to [Google Cloud Console](https://console.cloud.google.com)
2. Create a new project (name it "Wren")
3. Enable the following APIs:
   - Gmail API
   - Google Calendar API
   - Google Drive API

### Step 2: Create OAuth Credentials

1. Go to **Credentials** → **Create Credentials** → **OAuth Client ID**
2. Application type: **Desktop application**
3. Download the JSON credentials file
4. Save it as `~/.wren_oauth/client_secret.json`

### Step 3: First-Time OAuth Flow

The first time you use a Google tool (e.g., `list_events`), Wren will:
1. Open a browser window
2. Ask you to authorize Wren to access your Google account
3. Save the authorized credentials to `~/.wren_oauth/<service>_token.json`

After that, credentials are refreshed automatically.

### Step 4: Enable in Config

Edit `config.yaml`:

```yaml
mcp_servers:
  gmail:
    enabled: true          # Change from false to true
  calendar:
    enabled: true
  drive:
    enabled: true
```

### Step 5: Test It

```bash
python -m wren.cli
```

Then try:
```
you ▷ What's on my calendar for the next 7 days?
Wren ▷ <calls list_events>
```

## Phase 2: Computer Control

### Screenshot

Requires `PIL` (Pillow). Already included in `requirements.txt`.

Test:
```bash
python -c "from wren.tools.computer_control import _take_screenshot; print(_take_screenshot()[:50])"
```

### Click & Type (PyAutoGUI)

PyAutoGUI works on Windows, macOS, and Linux (with X11).

**Test clicking:**
```bash
python -c "from wren.tools.computer_control import _click; _click(100, 100)"
```

**Test typing:**
```bash
python -c "from wren.tools.computer_control import _type_text; _type_text('hello')"
```

### Browser Remote Debugging (Playwright)

To use `find_element` and `navigate_url`, you need a browser with remote debugging enabled:

**Chrome/Chromium:**
```bash
google-chrome --remote-debugging-port=9222 &
```

**Firefox:**
Firefox doesn't support CDP natively. Use Chromium-based browsers.

Then Wren can:
- Find elements by CSS selector
- Navigate to URLs
- Fill forms, click buttons, extract content

Test:
```bash
google-chrome --remote-debugging-port=9222 &
python -m wren.cli
```

Then try:
```
you ▷ Take a screenshot
Wren ▷ <calls take_screenshot>

you ▷ Click on the Google Search button
Wren ▷ <calls click to focus the button>
```

## Configuration

### Gating & Confirmation

All MCP and computer control tools are marked `consequential=True`. Edit `config.yaml` to change this:

```yaml
safety:
  confirm_tools:
  - take_screenshot       # Remove to allow without asking
  - click
  - type_text
  - navigate_url
```

### Rate Limiting & Timeouts

Edit tool modules (e.g., `wren/tools/gmail.py`) to adjust:
- Max API results returned
- Timeout values
- Search scope

### OAuth Scopes

Google API scopes are defined in each tool module:
- Gmail: `https://www.googleapis.com/auth/gmail.modify`
- Calendar: `https://www.googleapis.com/auth/calendar`
- Drive: `https://www.googleapis.com/auth/drive.readonly`

To change scopes, edit the `SCOPES` list in each tool file and delete cached tokens in `~/.wren_oauth/`.

## Troubleshooting

### "Gmail auth not set up"

- Verify `~/.wren_oauth/client_secret.json` exists
- Delete `~/.wren_oauth/gmail_token.json` and retry (forces re-auth)
- Check that Gmail API is enabled in Google Cloud Console

### "No active browser page found"

- Run Chrome with `--remote-debugging-port=9222`
- Make sure a browser tab is active before calling `find_element` or `navigate_url`

### PyAutoGUI errors on Linux

- Install: `sudo apt-get install python3-tk python3-dev`
- Some systems need X11; Wayland isn't fully supported

### Playwright errors

- Run: `playwright install chromium`
- For CDP (remote debugging), use Chromium-based browsers only

## Next Steps

### Phase 3: Specialized MCP Servers

Ready to add:
- **Canva** — design and create graphics
- **Higgsfield** — AI image/video/audio generation
- **Motion** — AI video creation
- **n8n** — workflow automation
- **Stripe** — payment processing
- **Twilio** — SMS/calls

Each follows the same pattern as Gmail/Calendar/Drive:
1. Create a tool module in `wren/tools/`
2. Implement API calls
3. Register in `wren/tools/__init__.py`
4. Add config section in `config.yaml`
5. Test via CLI

### Audit & Cost Tracking

All tool calls are logged to `data/audit.log` (JSON format). Check cost:

```bash
python -m wren.cli cost
```

This reads the audit log and sums API costs (when available).

## Security Notes

- OAuth tokens are stored locally in `~/.wren_oauth/` (readable by you only)
- Never commit `client_secret.json` or `.env` to version control
- Computer control tools (`click`, `type_text`) can interact with any window — use with care
- All consequential actions require user confirmation (Tier 6 gate)

## Support

For issues:
1. Check `data/audit.log` for the exact API error
2. Run `python -c "from wren.tools import gmail; gmail._build_gmail_service()"` to test auth
3. Look at the error traceback in the agent output
