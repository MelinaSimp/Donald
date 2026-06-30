# MCP Integration — Architecture Reference & Decision Trees

This document contains architectural diagrams, decision trees, and reference material for the MCP integration plan.

---

## 1. System Architecture Diagrams

### 1.1 Wren Subsystems (Current)

```
┌─────────────────────────────────────────────────────────────────┐
│ Wren App (wren/app.py)                                          │
│                                                                 │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │ Agent (wren/agent.py)                                      │ │
│  │ ┌──────────────────────────────────────────────────────┐   │ │
│  │ │ Tool Loop                                            │   │ │
│  │ │  1. Message user's text to LLM                      │   │ │
│  │ │  2. LLM picks a tool                                │   │ │
│  │ │  3. Dispatch to tool.run(input)                     │   │ │
│  │ │  4. LLM reads tool result                           │   │ │
│  │ │  5. Repeat or finish                                │   │ │
│  │ └──────────────────────────────────────────────────────┘   │ │
│  │                        │                                   │ │
│  │                        ▼                                   │ │
│  │  ┌──────────────────────────────────────────────────────┐ │ │
│  │  │ ToolContext (wren/tools/__init__.py)               │ │ │
│  │  │ ├─ config: Config (from config.yaml)              │ │ │
│  │  │ ├─ memory: Memory (long-term facts)               │ │ │
│  │  │ ├─ reminders: Reminders (json-backed)             │ │ │
│  │  │ ├─ notes: Notes (file-backed)                     │ │ │
│  │  │ └─ mailer: Mailer (SMTP)                          │ │ │
│  │  └──────────────────────────────────────────────────────┘ │ │
│  │                                                             │ │
│  │  ┌──────────────────────────────────────────────────────┐ │ │
│  │  │ Registry (wren/tools/base.py)                      │ │ │
│  │  │ ├─ reminders (+ list, add, complete)             │ │ │
│  │  │ ├─ notes (+ list, create)                        │ │ │
│  │  │ ├─ web (+ fetch url)                             │ │ │
│  │  │ ├─ memory_tools (+ store, retrieve)              │ │ │
│  │  │ └─ consequential                                 │ │ │
│  │  │    ├─ send_message (GATED)                       │ │ │
│  │  │    ├─ delete_data (GATED)                        │ │ │
│  │  │    ├─ spend_money (GATED)                        │ │ │
│  │  │    └─ change_settings (GATED)                    │ │ │
│  │  └──────────────────────────────────────────────────────┘ │ │
│  └────────────────────────────────────────────────────────────┘ │
│                                                                 │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │ Safety Gate (wren/safety.py)                               │ │
│  │ ├─ Audit Log (for cost tracking)                          │ │
│  │ └─ Confirmation Gate (Tier 4)                             │ │
│  │    └─ For tools with consequential=True                   │ │
│  └────────────────────────────────────────────────────────────┘ │
│                                                                 │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │ LLM (wren/llm.py)                                          │ │
│  │ └─ Anthropic Messages API (claude-opus-4-8)               │ │
│  └────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

### 1.2 MCP Integration Layer (Post-Phase 1)

```
┌─────────────────────────────────────────────────────────────────────┐
│ Wren App + MCP                                                      │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │ Tool Registry (expanded)                                    │   │
│  │                                                             │   │
│  │ Core (always):                                             │   │
│  │  • reminders, notes, web, memory_tools, consequential      │   │
│  │                                                             │   │
│  │ Phase 1 (enabled via config):                              │   │
│  │  ├─ Gmail    [send, list, read, draft, reply, mark, ...]  │   │
│  │  ├─ Calendar [create, list, get, update, delete, ...]     │   │
│  │  └─ Drive    [upload, list, read, create_folder, ...]     │   │
│  │                                                             │   │
│  │ Phase 2 (enabled via config):                              │   │
│  │  └─ Browser  [navigate, click, type, screenshot, scroll]  │   │
│  │                                                             │   │
│  │ Phase 3 (enabled via config):                              │   │
│  │  ├─ Canva    [create_design, export, search_templates]    │   │
│  │  ├─ Higgsfield [generate_image, generate_video, ...]      │   │
│  │  ├─ Motion   [create_video, create_followup]              │   │
│  │  ├─ Apollo   [search_contacts, enrich, create, ...]       │   │
│  │  ├─ Stripe   [charge, refund, get_balance]                │   │
│  │  ├─ Twilio   [send_sms, send_whatsapp, make_call]         │   │
│  │  ├─ Miro     [create_board, add_shape, comment]           │   │
│  │  └─ n8n      [create_workflow, execute, get_status]       │   │
│  │                                                             │   │
│  │ Phase 4 (enabled via config):                              │   │
│  │  ├─ MCP Dispatcher [list_tools, call_tool]                │   │
│  │  └─ Tool Feedback  [log, suggest]                         │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │ MCP Session Manager (wren/mcp/__init__.py)                 │   │
│  │                                                             │   │
│  │ Lazy-load & cache clients:                                 │   │
│  │  ├─ GoogleOAuthClient [gmail, calendar, drive]           │   │
│  │  ├─ CanvaClient                                           │   │
│  │  ├─ HiggsFieldClient                                      │   │
│  │  ├─ MotionClient                                          │   │
│  │  ├─ ApolloClient                                          │   │
│  │  ├─ StripeClient                                          │   │
│  │  ├─ TwilioClient                                          │   │
│  │  ├─ MiroClient                                            │   │
│  │  └─ BrowserSession [Playwright]                           │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │ Config (expanded)                                           │   │
│  │                                                             │   │
│  │ mcp:                                                       │   │
│  │   services:                                               │   │
│  │     gmail:       {enabled: false, scopes: [...]}         │   │
│  │     calendar:    {enabled: false, scopes: [...]}         │   │
│  │     drive:       {enabled: false, scopes: [...]}         │   │
│  │     browser:     {enabled: false, headless: true}        │   │
│  │     canva:       {enabled: false}                        │   │
│  │     ... (etc)                                            │   │
│  │   rate_limits:                                           │   │
│  │     gmail_send: 100                                      │   │
│  │     browser_click: 100                                   │   │
│  │     ... (etc)                                            │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │ ToolContext (extended)                                     │   │
│  │                                                             │   │
│  │ Original:                                                  │   │
│  │  • config, memory, reminders, notes, mailer               │   │
│  │                                                             │   │
│  │ New (added by tool modules):                               │   │
│  │  • google_oauth: GoogleOAuthClient                        │   │
│  │  • browser: BrowserSession                                │   │
│  │  • mcp_clients: {canva, apollo, ...}                      │   │
│  └──────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
        │                      │                      │
        ▼                      ▼                      ▼
    ┌─────────┐            ┌──────────┐          ┌────────────┐
    │ Google  │            │Playwright│          │Third-party│
    │ APIs    │            │ Browser  │          │   APIs    │
    └─────────┘            └──────────┘          └────────────┘
```

---

## 2. Tool Lifecycle Diagram

```
User Input
   │
   ▼
┌─────────────────────────────────────────┐
│ Agent.respond(text)                     │
│  1. System prompt + tool specs to LLM  │
│  2. LLM picks a tool + input params    │
└─────────────────────────────────────────┘
   │
   ▼
┌─────────────────────────────────────────┐
│ Lookup Tool (registry.get(tool_name))  │
│ Returns: Tool instance                 │
└─────────────────────────────────────────┘
   │
   ▼
┌─────────────────────────────────────────┐
│ Check: tool.consequential?             │
└─────────────────────────────────────────┘
   │
   ├─ NO  ─────────────────────────────┐
   │                                    │
   │                                    ▼
   │                              ┌───────────────┐
   │                              │ Run tool      │
   │                              │ (handler call)│
   │                              └───────────────┘
   │                                    │
   │                                    ▼
   │                              ┌───────────────────┐
   │                              │ Catch exceptions? │
   │                              │ Return str result │
   │                              └───────────────────┘
   │                                    │
   │                                    ▼
   │                              ┌──────────────────┐
   │                              │ Feed to LLM      │
   │                              │ (tool_result)    │
   │                              └──────────────────┘
   │                                    │
   │                                    ▼
   │                              LLM decides next
   │
   │
   ├─ YES ─────────────────────────────┐
   │                                    │
   │                                    ▼
   │                              ┌──────────────────┐
   │                              │ Surface request  │
   │                              │ (tool + params)  │
   │                              └──────────────────┘
   │                                    │
   │                                    ▼
   │                              ┌──────────────────┐
   │                              │ Wait for human   │
   │                              │ approval         │
   │                              └──────────────────┘
   │                                    │
   │                                    ├─ APPROVE
   │                                    │   │
   │                                    │   ▼
   │                                    │ Run tool
   │                                    │ → Feed to LLM
   │                                    │
   │                                    ├─ DENY
   │                                    │   │
   │                                    │   ▼
   │                                    │ "User declined"
   │                                    │ → Feed to LLM
```

---

## 3. Tool Registration Decision Tree

```
┌─ Is this a new capability you want to add to Wren?
│
├─ YES, I want to...
│
│  ├─ Read data (list emails, get contacts, fetch URL)
│  │  │
│  │  └─ Write a tool module in wren/tools/
│  │     ├─ Define input_schema
│  │     ├─ Implement handler(args) -> str
│  │     ├─ registry.add("tool_name", ..., handler, consequential=False)
│  │     └─ Done! No gate needed.
│  │
│  ├─ Write data (send email, create calendar event, upload file)
│  │  │
│  │  └─ Write a tool module in wren/tools/
│  │     ├─ Define input_schema
│  │     ├─ Implement handler(args) -> str
│  │     ├─ registry.add("tool_name", ..., handler, consequential=True)
│  │     └─ GATED! User must approve before it runs.
│  │
│  ├─ Delete data (remove email, trash file, cancel meeting)
│  │  │
│  │  └─ Write a tool module in wren/tools/
│  │     ├─ Define input_schema
│  │     ├─ Implement handler(args) -> str
│  │     ├─ registry.add("tool_name", ..., handler, consequential=True)
│  │     └─ GATED! (same as write)
│  │
│  ├─ Spend money (make charge, purchase credits)
│  │  │
│  │  └─ Write a tool module in wren/tools/
│  │     ├─ Define input_schema
│  │     ├─ Implement handler(args) -> str
│  │     ├─ registry.add("tool_name", ..., handler, consequential=True)
│  │     ├─ Add to config.yaml: safety.confirm_tools: [...]
│  │     └─ TRIPLE-GATED! (user approval + audit log + config)
│  │
│  ├─ Interact with a webpage (click, type, navigate)
│  │  │
│  │  └─ Use the browser tools (wren/tools/browser.py)
│  │     ├─ navigate(url)
│  │     ├─ click(selector)
│  │     ├─ type(selector, text)
│  │     ├─ screenshot()
│  │     └─ These are composable for page automation.
│  │
│  ├─ Use a third-party API (Canva, Stripe, etc.)
│  │  │
│  │  └─ Check if MCP server exists
│  │     ├─ If yes:
│  │     │  ├─ Create wren/tools/[service].py
│  │     │  ├─ Implement register(registry, ctx) function
│  │     │  ├─ Create wren/mcp/[service]_client.py (if needed)
│  │     │  ├─ Add to build_registry() in wren/tools/__init__.py
│  │     │  ├─ Add to config.yaml: mcp.services.[service].enabled
│  │     │  ├─ Add secrets to .env.example
│  │     │  └─ Document setup + examples
│  │     │
│  │     └─ If no:
│  │        ├─ Check if REST API + simple
│  │        ├─ If yes: write wren/tools/[service].py (use requests)
│  │        └─ If complex: consider starting an MCP server for it
│  │
│  └─ (end of capability tree)
│
└─ NO, I just want to use existing tools
   └─ Set enabled: true in config.yaml + add secrets to .env
```

---

## 4. OAuth Flow Decision Tree

```
┌─ Does the service need OAuth (Google, Canva, Apollo)?
│
├─ YES
│  │
│  ├─ Is it Google (Gmail/Calendar/Drive)?
│  │  │
│  │  └─ Use GoogleOAuthManager (wren/mcp/google_auth.py)
│  │     ├─ On first run:
│  │     │  └─ Launch local browser → user consents
│  │     │  └─ Token cached in GOOGLE_OAUTH_TOKEN
│  │     │
│  │     └─ On subsequent runs:
│  │        ├─ Read token from .env
│  │        ├─ Check if expired
│  │        ├─ If expired: call refresh() → save new token
│  │        └─ If valid: use as-is
│  │
│  ├─ Is it another service (Canva, Apollo, etc.)?
│  │  │
│  │  └─ Create a [Service]OAuthManager
│  │     ├─ Follow same pattern as GoogleOAuthManager
│  │     ├─ Store token in MCP_[SERVICE]_TOKEN (env var)
│  │     ├─ Implement get_client() method
│  │     └─ Integrate into MCPSessionManager
│  │
│  └─ End: Token is cached, ready to use
│
├─ NO (API key, not OAuth)
│  │
│  └─ Store in .env as MCP_[SERVICE]_API_KEY
│     └─ Read in tool handler: Config.secret("MCP_[SERVICE]_API_KEY")
│
└─ NO (no auth, public API)
   └─ Just call the API directly
```

---

## 5. Tool Schema Design Decision Tree

```
┌─ What type of input does your tool need?
│
├─ Simple string(s)
│  │
│  └─ Use string() helper
│     Example: string("Email address or URL")
│     ▶ properties: {"field": {"type": "string", "description": "..."}}
│
├─ A number
│  │
│  └─ Use number or integer
│     Example: {"type": "integer", "description": "Quantity"}
│     ▶ Integer: must be whole number
│     ▶ Number: can be decimal
│
├─ Pick from a list (enum)
│  │
│  └─ Use enum
│     Example: {"type": "string", "enum": ["red", "green", "blue"]}
│     ▶ LLM sees the choices
│
├─ A boolean flag
│  │
│  └─ Use boolean
│     Example: {"type": "boolean", "description": "Include...?"}
│     ▶ Default: false
│
├─ A complex object (dict)
│  │
│  └─ Use obj() helper (from wren/tools/base.py)
│     Example:
│       obj({
│         "name": string("User's name"),
│         "age": {"type": "integer"},
│       }, required=["name"])
│     ▶ properties: {...}
│     ▶ required: ["name"]
│
├─ An array (list)
│  │
│  └─ Use array type
│     Example:
│       {
│         "type": "array",
│         "items": {"type": "string"},
│         "description": "List of email addresses"
│       }
│     ▶ LLM will construct arrays naturally
│
└─ Not sure? Ask: "Can this be represented in JSON?"
   ▶ Yes → design a schema
   ▶ No → break it into smaller inputs (one tool per concept)
```

---

## 6. Error Handling Decision Tree

```
┌─ Your tool raised an exception. What now?
│
├─ Is it a validation error (user gave bad input)?
│  │
│  └─ Return plain-language error to LLM
│     Example: "I need an email address to send to."
│     ▶ LLM reads this and asks the user to clarify
│
├─ Is it an auth error (token expired, key invalid)?
│  │
│  └─ Return instruction for user to re-auth
│     Example: "Gmail token expired. Run: python -m wren auth gmail"
│     ▶ Tell the user what to do
│
├─ Is it a rate limit error?
│  │
│  └─ Return error with retry advice
│     Example: "Rate limit hit. Try again in 60 seconds."
│     ▶ LLM can offer to retry later
│
├─ Is it a "not found" error (email doesn't exist)?
│  │
│  └─ Return "not found" message
│     Example: "No email found with subject 'meeting'."
│     ▶ LLM can suggest a different search
│
├─ Is it a network error (API down)?
│  │
│  └─ Return "service unavailable" message
│     Example: "Gmail is temporarily unavailable. Try again in a moment."
│     ▶ LLM can acknowledge and retry
│
├─ Is it an unexpected error (you don't know what happened)?
│  │
│  └─ Catch it, log it, return generic message
│     Example: "Unexpected error calling Gmail: [error details]"
│     ▶ Log to audit trail for debugging
│     ▶ Tell user something went wrong (no false confidence)
│
└─ Rule: Never raise an exception. Always return a string error message.
   ▶ Tool.run() catches exceptions anyway, so be defensive.
```

---

## 7. Phase Rollout Decision Tree

```
┌─ Should I enable this service in my Wren instance?
│
├─ It's in Phase 1 (Gmail, Calendar, Drive)
│  │
│  └─ Strongly recommended for most users
│     ├─ Email is universal
│     ├─ Calendar integration is high-impact
│     ├─ Drive is safe (no local filesystem access)
│     └─ Action: Set enabled: true + run auth flow
│
├─ It's in Phase 2 (Browser control)
│  │
│  └─ Only if you have web automation tasks
│     ├─ Playwright is installed (requires apt-get playwright)
│     ├─ No auth needed (runs locally)
│     ├─ Risk: can click wrong button (but asks for confirmation on forms)
│     └─ Action: Set enabled: true + test with a safe URL first
│
├─ It's in Phase 3 (Canva, Higgsfield, Stripe, etc.)
│  │
│  └─ Depends on your use case
│     ├─ If you do design: enable Canva
│     ├─ If you generate content: enable Higgsfield or Motion
│     ├─ If you process payments: enable Stripe
│     ├─ If you use Apollo for sales: enable Apollo
│     ├─ If you send SMS: enable Twilio
│     └─ Action: Set enabled: true only for what you need
│
├─ It's in Phase 4 (Orchestration & learning)
│  │
│  └─ Advanced users only
│     ├─ Adds composability (combine tools in new ways)
│     ├─ Feedback system learns which chains work
│     └─ Action: Enable if you want tool auto-discovery
│
└─ Cost concerns?
   ├─ Phase 1: Free (Google APIs have generous limits)
   ├─ Phase 2: Free (Playwright is local)
   ├─ Phase 3: Varies
   │  ├─ Canva: free plan; design features may need upgrade
   │  ├─ Higgsfield: pay-per-image (check your credits)
   │  ├─ Stripe: per-transaction fees (set rate_limit if worried)
   │  ├─ Twilio: per-SMS charges
   │  └─ → Set rate_limits in config.yaml to avoid surprises
   └─ Phase 4: Free (adds no new services)
```

---

## 8. Common Patterns

### Pattern 1: Simple Read Tool

```python
def register(registry: Registry, ctx) -> None:
    def read_something(args: dict[str, Any]) -> str:
        query = args.get("query", "").strip()
        if not query:
            return "Need a query."
        
        # Call API or service
        results = some_api.search(query)
        
        # Format results for LLM
        if not results:
            return "No results found."
        return "\n".join([f"- {r}" for r in results])
    
    registry.add(
        "read_something",
        "Search for things.",
        obj({"query": string("What to search for")}),
        read_something,
    )
```

### Pattern 2: Consequential Action Tool

```python
def register(registry: Registry, ctx) -> None:
    def create_something(args: dict[str, Any]) -> str:
        name = args.get("name", "").strip()
        description = args.get("description", "").strip()
        
        if not name:
            return "Need a name."
        
        try:
            result = some_api.create(name, description)
            return f"Created: {result.id}"
        except AlreadyExistsError:
            return f"Something with name '{name}' already exists."
        except Exception as e:
            return f"Failed to create: {e}"
    
    registry.add(
        "create_something",
        "Create a new thing.",
        obj({
            "name": string("Name of the thing"),
            "description": string("Optional description"),
        }, required=["name"]),
        create_something,
        consequential=True,  # ← User must approve
    )
```

### Pattern 3: Batch Operation Tool

```python
def register(registry: Registry, ctx) -> None:
    def bulk_update(args: dict[str, Any]) -> str:
        ids = args.get("ids", [])
        action = args.get("action", "").strip()
        
        if not ids or len(ids) == 0:
            return "Need at least one ID."
        if not action:
            return "Need an action."
        
        results = []
        for item_id in ids:
            try:
                some_api.apply_action(item_id, action)
                results.append(f"✓ {item_id}")
            except Exception as e:
                results.append(f"✗ {item_id}: {e}")
        
        return "\n".join(results)
    
    registry.add(
        "bulk_update",
        "Apply an action to multiple items.",
        obj({
            "ids": {
                "type": "array",
                "items": {"type": "string"},
            },
            "action": string("What to do (e.g., 'archive', 'delete')"),
        }, required=["ids", "action"]),
        bulk_update,
        consequential=True,
    )
```

### Pattern 4: Interactive Tool (with follow-ups)

```python
def register(registry: Registry, ctx) -> None:
    def interactive_search(args: dict[str, Any]) -> str:
        query = args.get("query", "").strip()
        if not query:
            return "Need a query."
        
        results = some_api.search(query)
        
        if len(results) == 0:
            return "No results. Try a different query?"
        elif len(results) == 1:
            return f"Found exactly one: {results[0].name}"
        else:
            # Return list; let LLM ask user which one
            lines = [f"{i+1}. {r.name}" for i, r in enumerate(results[:5])]
            extra = f"\n... and {len(results) - 5} more" if len(results) > 5 else ""
            return "Found " + str(len(results)) + " results:\n" + "\n".join(lines) + extra
    
    registry.add(
        "interactive_search",
        "Search and let the user pick from results.",
        obj({"query": string("What to search for")}),
        interactive_search,
    )
```

---

## 9. Security Checklist

- [ ] All API keys are in `.env` (not in code)
- [ ] `.env` is in `.gitignore`
- [ ] `.env.example` has placeholders (not real values)
- [ ] Secrets are accessed via `Config.secret(name)`, not `os.environ` directly
- [ ] Tokens are cached, not re-requested on each call
- [ ] OAuth refresh logic is tested
- [ ] Consequential tools have `consequential=True` flag
- [ ] consequential tools are in `safety.confirm_tools` in config
- [ ] Tool handlers catch all exceptions (never raise)
- [ ] Error messages don't leak sensitive data (no tokens in errors)
- [ ] Audit log records all tool calls (for compliance)
- [ ] Rate limits are set in config (prevent accidental spam)

---

## 10. Performance Checklist

- [ ] Tool handlers return quickly (no blocking I/O if possible)
- [ ] Heavy operations (file upload) have progress feedback
- [ ] API calls are batched when possible (list 50 emails, not 1×50)
- [ ] Results are cached (don't re-fetch unchanged data)
- [ ] Screenshots are compressed (only send necessary pixels)
- [ ] Large responses are truncated for LLM (send summary, not full dump)
- [ ] Rate limits prevent API exhaustion
- [ ] Token refresh is async (don't block on auth)

---

## 11. Testing Checklist

- [ ] Unit tests run without API keys (mocked external APIs)
- [ ] Unit tests verify schema validity
- [ ] Unit tests verify input validation
- [ ] Integration tests use sandbox/test credentials (not production)
- [ ] Integration tests verify end-to-end flow
- [ ] Error paths are tested (auth failure, rate limit, not found)
- [ ] Edge cases are tested (empty results, very large responses)
- [ ] Tool can be disabled via config without crashing
- [ ] Missing secrets fail gracefully (not with a traceback)

---

## 12. Configuration Checklist

- [ ] Service is added to `mcp.services` in `config.yaml`
- [ ] Service has `enabled: false` by default (opt-in)
- [ ] Service has documented scopes (if OAuth)
- [ ] Rate limits are sensible (not too strict, not too permissive)
- [ ] Secrets are documented in `.env.example`
- [ ] Tools are documented in README
- [ ] Setup guide exists (how to enable + get credentials)

---

## Glossary

| Term | Definition |
|------|-----------|
| **Tool** | A capability the agent can call (send email, click button, etc.) |
| **MCP** | Model Control Protocol; standard for connecting LLMs to external systems |
| **Consequential** | A tool that sends/deletes/spends; requires user approval before running |
| **Registry** | The collection of all available tools; built at app startup |
| **ToolContext** | Shared services (config, memory, mailer, etc.) passed to all tools |
| **OAuth** | Auth standard for delegated access (e.g., "let this app use your Gmail") |
| **Token** | Proof of authorization; cached and refreshed as needed |
| **Rate Limit** | Max calls per time period to prevent API abuse |
| **Schema** | JSON schema describing tool's inputs (what the LLM must provide) |
| **Handler** | The function that runs when a tool is called |
| **Phase** | Rollout stage; Phase 1 (Gmail/Calendar/Drive), Phase 2 (Browser), etc. |

---

## Quick Reference: File Locations

```
wren/
  ├─ app.py                          → App assembly (build_context, build_registry)
  ├─ config.py                       → Config loading + secrets
  ├─ agent.py                        → Tool loop (calls tool handlers)
  ├─ safety.py                       → Audit + confirmation gate
  ├─ llm.py                          → LLM wrapper (Claude API)
  │
  ├─ tools/
  │  ├─ __init__.py                  → build_context, build_registry
  │  ├─ base.py                      → Tool, Registry, obj(), string() helpers
  │  ├─ (Phase 1) gmail.py, calendar.py, drive.py
  │  ├─ (Phase 2) browser.py
  │  ├─ (Phase 3) canva.py, higgsfield.py, motion.py, apollo.py, stripe.py, twilio.py, miro.py
  │  └─ (Phase 4) mcp_dispatcher.py, tool_feedback.py
  │
  ├─ mcp/
  │  ├─ __init__.py                  → MCPSessionManager
  │  ├─ google_auth.py               → GoogleOAuthManager
  │  ├─ browser.py                   → BrowserSession (Playwright)
  │  └─ (Phase 3) canva_client.py, apollo_client.py, etc.
  │
  ├─ config.yaml                     → Configuration (mcp.services, rate_limits)
  └─ .env (git-ignored)              → Secrets (API keys, tokens)
```

---

## Conclusion

Use these diagrams and decision trees to:
1. **Understand the system** — how tools flow through the agent loop
2. **Design new tools** — follow the decision trees for your use case
3. **Troubleshoot** — find the right layer when things break
4. **Optimize** — use the checklists to ensure quality

Refer back to this doc when building Phase 3 and Phase 4 services.
