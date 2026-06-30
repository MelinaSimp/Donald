# MCP Integration — Quick Start Guide

A one-page reference for implementing each phase.

---

## What You're Building

A **modular tool integration layer** that adds 50+ AI-powered capabilities to Wren without touching the core agent loop.

**Key principle:** One tool module (50-100 lines) per service, registered in `wren/tools/`, follows Wren's existing patterns.

---

## Quick Summary: All 4 Phases

| Phase | Services | Files | Impact | Effort |
|-------|----------|-------|--------|--------|
| **1** | Gmail, Calendar, Drive | 3 files (gmail.py, calendar.py, drive.py) + oauth setup | Email/calendar/file access | **High impact, medium effort** |
| **2** | Browser automation | 1 file (browser.py) + Playwright | "Click that button" automation | **Medium impact, low effort** |
| **3** | 8 specialized services | 8 files (canva, higgsfield, motion, etc.) | Design, AI generation, payments, etc. | **Variable impact, low effort** |
| **4** | Meta-tools + learning | 2 files (mcp_dispatcher, tool_feedback) | Composability & auto-discovery | **Efficiency gain, low effort** |

---

## Quickest Path to First Win

**Goal:** Agent can send email (25 min)

1. **Create OAuth wrapper** (5 min)
   ```bash
   touch wren/mcp/__init__.py wren/mcp/google_auth.py
   ```
   Copy the `GoogleOAuthManager` from `MCP_IMPLEMENTATION_EXAMPLES.md`

2. **Create Gmail tool** (10 min)
   ```bash
   touch wren/tools/gmail.py
   ```
   Copy the `GmailClient` + `send_email` handler from examples

3. **Wire it in** (5 min)
   Edit `wren/tools/__init__.py`:
   ```python
   from . import gmail
   
   def build_registry(ctx: ToolContext) -> Registry:
       # ... existing tools ...
       if ctx.config.get("mcp.services.gmail.enabled", False):
           gmail.register(registry, ctx)
   ```

4. **Enable in config** (2 min)
   Edit `config.yaml`:
   ```yaml
   mcp:
     services:
       gmail:
         enabled: true
   ```

5. **Add secret** (3 min)
   Run: `python -m wren auth gmail` (opens browser for OAuth consent)
   Token saved to `.env`

6. **Test** (1 min)
   ```python
   agent.respond("Send an email to alice@example.com saying hello")
   ```

---

## File Checklist Template

Use this for each new service:

### Creating `wren/tools/[service].py`

```python
"""[Service] integration."""
from __future__ import annotations
from typing import Any
from .base import Registry, obj, string

def register(registry: Registry, ctx) -> None:
    # 1. Get or create client
    if not hasattr(ctx, "[service]_client"):
        from ..[service]_module import Client  # or use ctx.config.secret()
        ctx.[service]_client = Client(ctx.config)
    
    client = ctx.[service]_client
    
    # 2. For each capability, define a handler
    def tool_name(args: dict[str, Any]) -> str:
        param1 = args.get("param1", "").strip()
        if not param1:
            return "Need param1."
        try:
            result = client.do_something(param1)
            return f"Done: {result}"
        except Exception as e:
            return f"Error: {e}"
    
    # 3. Register the tool
    registry.add(
        "tool_name",
        "One-line description of what this does.",
        obj({
            "param1": string("Description of param1"),
            # ... more params
        }, required=["param1"]),
        tool_name,
        consequential=False,  # or True if it sends/deletes/spends
    )
    
    # 4. Repeat for each capability
```

### Modifying `wren/tools/__init__.py`

```python
# Add import at top
from . import [service_name]

# Add to build_registry()
if ctx.config.get("mcp.services.[service_name].enabled", False):
    [service_name].register(registry, ctx)
```

### Modifying `config.yaml`

```yaml
mcp:
  services:
    [service_name]:
      enabled: false
      # ... service-specific config
```

### Modifying `.env.example`

```bash
# [Service Name]
[SERVICE_NAME]_API_KEY=
[SERVICE_NAME]_WEBHOOK_URL=
# ... other secrets
```

---

## Decision Tree: Which Phase Am I Implementing?

```
Q: What service am I adding?
├─ Gmail/Calendar/Drive → PHASE 1 (Google APIs)
├─ Browser clicking/typing → PHASE 2 (Playwright)
├─ Canva/Higgsfield/Motion/Apollo/Stripe/Twilio/Miro/n8n → PHASE 3
├─ Meta-tool discovery / learning system → PHASE 4
└─ Something else → Check MCP server availability first
```

---

## Testing Checklist (Before Merge)

- [ ] Tool schema is valid JSON schema
- [ ] All inputs have descriptions
- [ ] Required params are listed
- [ ] Handler validates inputs (returns error if missing)
- [ ] Handler catches exceptions (no crashes)
- [ ] Error messages are user-friendly (no tracebacks)
- [ ] Consequential flag is correct (True if sends/deletes/spends)
- [ ] Tool is added to `config.yaml` + `.env.example`
- [ ] Tool is imported and registered in `build_registry()`
- [ ] Setup guide exists (how to enable + get credentials)
- [ ] At least one integration test (even if mocked)

---

## Common Errors & Fixes

### "Tool not appearing in agent's toolkit"
- [ ] Check: `mcp.services.[name].enabled: true` in config.yaml
- [ ] Check: Tool is registered in `build_registry()`
- [ ] Check: No exceptions during `register()` call
- [ ] Restart Wren (config changes require restart)

### "Authorization failed"
- [ ] Check: Secret exists in .env
- [ ] Check: Secret is correct (not expired, not typo)
- [ ] Check: Config.secret("NAME") is called with correct env var name
- [ ] Re-run auth flow: `python -m wren auth [service]`

### "Tool handler is crashing"
- [ ] Add try/except to handler
- [ ] Return error string, not exception
- [ ] Check: Tool.run() will catch it, but better to be explicit
- [ ] Log to audit trail for debugging: `ctx.audit.log(...)`

### "Rate limit exceeded"
- [ ] Check: config.yaml `mcp.rate_limits.[tool_name]` is reasonable
- [ ] Batch operations (send 10 emails, not 1×10 calls)
- [ ] Add exponential backoff in handler
- [ ] Document rate limits in tool description

### "Consequential tool not asking for confirmation"
- [ ] Check: `consequential=True` in registry.add()
- [ ] Check: Tool name is in config.yaml `safety.confirm_tools`
- [ ] Restart Wren (config changes require restart)

---

## One-Tool Walkthrough: Adding Apollo (Lead Generation)

**File 1: `wren/tools/apollo.py`**

```python
"""Apollo.io integration for lead generation and enrichment."""
from typing import Any
from .base import Registry, obj, string

def register(registry: Registry, ctx) -> None:
    # Get API key from .env
    api_key = ctx.config.secret("APOLLO_API_KEY", required=True)
    
    # Search for contacts
    def search_contacts(args: dict[str, Any]) -> str:
        query = args.get("query", "").strip()
        limit = args.get("limit", 10)
        
        if not query:
            return "Need a search query (e.g., 'CEO at Acme Corp')."
        
        try:
            import requests
            resp = requests.get(
                "https://api.apollo.io/v1/contacts/search",
                params={"q": query, "limit": min(limit, 100)},
                headers={"X-Api-Key": api_key},
            )
            resp.raise_for_status()
            data = resp.json()
            
            if not data.get("contacts"):
                return "No contacts found."
            
            lines = []
            for contact in data["contacts"][:limit]:
                lines.append(
                    f"- {contact['name']} ({contact['title']}) at {contact['company']}"
                )
            return "\n".join(lines)
        
        except requests.exceptions.RequestException as e:
            return f"Apollo API error: {e}"
    
    registry.add(
        "search_contacts",
        "Search for contacts in Apollo (e.g., 'VP Sales at Acme').",
        obj({
            "query": string("Search query (name, title, company)"),
            "limit": {"type": "integer", "description": "Max results", "default": 10},
        }, required=["query"]),
        search_contacts,
    )
    
    # (Add more tools: enrich_contact, create_contact, add_to_sequence, etc.)
```

**File 2: Update `wren/tools/__init__.py`**

```python
from . import apollo  # Add this line

def build_registry(ctx: ToolContext) -> Registry:
    # ... existing tools ...
    if ctx.config.get("mcp.services.apollo.enabled", False):
        apollo.register(registry, ctx)
```

**File 3: Update `config.yaml`**

```yaml
mcp:
  services:
    apollo:
      enabled: false
      # No special config needed
```

**File 4: Update `.env.example`**

```bash
# Apollo.io (lead generation / sales engagement)
APOLLO_API_KEY=
```

**File 5: Create `docs/SETUP_APOLLO.md`**

```markdown
# Adding Apollo to Wren

1. Get an API key from apollo.io
2. Add to .env: APOLLO_API_KEY=your-key-here
3. Enable in config.yaml: mcp.services.apollo.enabled: true
4. Restart Wren

Now you can: "Search for VPs at tech companies in SF"
```

**Done!** 50 lines of code + config changes. No core agent changes.

---

## Deployment Checklist

Before shipping a phase:

- [ ] All Phase N tools implemented + tested
- [ ] config.yaml has all services (disabled by default)
- [ ] .env.example has all secrets
- [ ] README has links to setup guides
- [ ] Code review: no secrets in source
- [ ] Tests pass (unit + integration)
- [ ] Manual smoke test (enable one tool, use it)
- [ ] Documentation is complete
- [ ] Rollback plan exists (just disable in config)

---

## Performance Tuning

If tools are slow:

1. **Cache results** (same query within 5 min? return cached)
   ```python
   if not hasattr(ctx, "search_cache"):
       ctx.search_cache = {}
   cache_key = f"{service}:{query}"
   if cache_key in ctx.search_cache:
       return ctx.search_cache[cache_key]
   ```

2. **Truncate large responses** (don't send 1000 lines to LLM)
   ```python
   if len(results) > 50:
       results = results[:50]
       results.append(f"... and {len(total) - 50} more")
   ```

3. **Batch API calls** (list 50, not 1×50)
   ```python
   all_results = api.bulk_operation(ids)  # vs loop + call 50 times
   ```

4. **Async where possible** (don't block on slow API)
   ```python
   # Complex; only if needed. Tools should return quick feedback.
   ```

---

## Security & Compliance

- [ ] Never commit `.env` (use `.gitignore`)
- [ ] Never commit real API keys (use placeholders in `.env.example`)
- [ ] All exceptions caught (no stack traces to user)
- [ ] Errors don't leak tokens (sanitize error messages)
- [ ] Audit log records all tool calls (config.yaml: safety.audit_log)
- [ ] Consequential tools require approval (config.yaml: safety.confirm_tools)
- [ ] Rate limits prevent abuse (config.yaml: mcp.rate_limits)
- [ ] No local file access (except via explicit Drive/S3 uploader)

---

## Next Steps

1. **Pick a Phase:** Start with Phase 1 if you want email. Phase 2 if you want web automation.

2. **Pick a Service:** Gmail is easiest; has OAuth setup code already.

3. **Copy the template:** Use the "One-Tool Walkthrough" pattern.

4. **Test locally:** Enable in config, add secret to .env, run Wren.

5. **Commit & ship:** Once tests pass, merge to main.

6. **Repeat:** Add the next service.

---

## Reference Docs

- **MCP_INTEGRATION_PLAN.md** — Full strategy (read first)
- **MCP_IMPLEMENTATION_EXAMPLES.md** — Code snippets (copy from here)
- **MCP_ARCHITECTURE_REFERENCE.md** — Diagrams & decision trees (ref while coding)
- **MCP_QUICK_START.md** — This file (checklist + walkthroughs)

---

## TL;DR

1. Create `wren/tools/[service].py` with `register(registry, ctx)` function
2. Define handlers that take `args: dict[str, Any]` and return `str`
3. Call `registry.add(name, desc, schema, handler, consequential=...)`
4. Add service to `config.yaml` (disabled by default)
5. Add secrets to `.env.example` and actual `.env`
6. Update `wren/tools/__init__.py` to import and conditionally register
7. Test + ship

Estimated time per tool: **30-60 minutes** (including tests + docs)

---

Good luck! 🚀
