# MCP Integration — Complete Documentation Index

This is the master index for the MCP integration project. Start here to understand what exists and where to find what you need.

---

## The Four Documents

### 1. **MCP_INTEGRATION_PLAN.md** ← START HERE
**Purpose:** Strategic overview of the entire 4-phase project

**Contains:**
- Executive summary of the approach
- Current Wren architecture recap
- Detailed breakdown of all 4 phases:
  - Phase 1: Gmail, Calendar, Drive (Weeks 1-2)
  - Phase 2: Browser control (Weeks 3-4)
  - Phase 3: Specialized services (Weeks 5-8)
  - Phase 4: Orchestration & learning (Weeks 9-10)
- For each phase: files to create/modify, dependencies, testing, docs
- Risk mitigation strategies
- Rollback plan
- Success criteria

**Read when:** Planning the project, deciding which phase to start with, understanding the big picture

**Skip if:** You just want to implement one tool (go to Quick Start instead)

---

### 2. **MCP_IMPLEMENTATION_EXAMPLES.md** ← COPY FROM HERE
**Purpose:** Concrete, ready-to-use code snippets

**Contains:**
- Full working examples of:
  - OAuth foundation (GoogleOAuthManager)
  - Gmail tool module (with 9 tools)
  - Calendar tool module (skeleton)
  - Browser control (BrowserSession wrapper)
  - Browser tools (10 implementations)
  - Updated `build_registry()` function
  - Example `config.yaml` structure
  - Example `.env.example`
  - Error handling patterns
  - Testing patterns (unit + integration)
  - Implementation checklist

**Read when:** Building Phase 1 or Phase 2 tools; need working code to adapt

**Skip if:** You just want architectural overview (use Architecture Reference instead)

---

### 3. **MCP_ARCHITECTURE_REFERENCE.md** ← REFER WHILE CODING
**Purpose:** Diagrams, decision trees, and architectural patterns

**Contains:**
- System architecture diagrams (current + post-Phase 1)
- Tool lifecycle diagram (how a tool call flows through the system)
- Decision trees for:
  - Tool registration (when to create a new tool)
  - OAuth flow (how to handle authentication)
  - Schema design (what input types exist)
  - Error handling (how to gracefully fail)
  - Phase rollout (which services to enable)
- 4 common tool patterns (read, write, batch, interactive)
- 12 checklists (security, performance, testing, config, etc.)
- Glossary of terms
- File location reference

**Read when:** Designing a new tool, debugging a problem, understanding tool patterns

**Use:** Keep open while coding; refer to relevant section as needed

---

### 4. **MCP_QUICK_START.md** ← QUICK REFERENCE
**Purpose:** One-page cheat sheet and quick walkthrough

**Contains:**
- What you're building (5-line summary)
- 4-phase overview (1 table)
- Quickest path to first win (send email in 25 min)
- File checklist template (copy for each new service)
- Decision tree (which phase am I in?)
- Testing checklist (before merge)
- Common errors & fixes
- One complete walkthrough (Apollo tool)
- Deployment checklist
- Performance tuning tips
- Security & compliance reminders
- Next steps

**Read when:** Starting a new tool, stuck on implementation, need quick reference

**Use:** Bookmark this; refer constantly while coding

---

## How to Use These Docs

### Scenario 1: "I'm starting Phase 1. What do I do?"

1. Read **MCP_INTEGRATION_PLAN.md** (Phase 1 section only) — understand the high-level plan
2. Read **MCP_QUICK_START.md** — quickest path to first win
3. Copy code from **MCP_IMPLEMENTATION_EXAMPLES.md** (Part 1 & 2: OAuth + Gmail)
4. Refer to **MCP_ARCHITECTURE_REFERENCE.md** (decision trees + error handling) while coding
5. Follow the **MCP_QUICK_START.md** checklist before committing

### Scenario 2: "I want to add Apollo (Phase 3 tool)"

1. Read **MCP_QUICK_START.md** (One-Tool Walkthrough) — see the pattern
2. Copy the pattern from **MCP_IMPLEMENTATION_EXAMPLES.md** (Part 4: simple read tool)
3. Adapt it for Apollo (search contacts, enrich, create, add to sequence)
4. Refer to **MCP_ARCHITECTURE_REFERENCE.md** for schema design help (Part 5)
5. Test using patterns from **MCP_IMPLEMENTATION_EXAMPLES.md** (Part 8)
6. Follow **MCP_QUICK_START.md** checklist

### Scenario 3: "I'm stuck on X. How do I fix it?"

| Problem | Go to |
|---------|-------|
| "Tool schema is invalid" | MCP_ARCHITECTURE_REFERENCE.md Part 5 (schema design decision tree) |
| "Tool isn't showing up" | MCP_QUICK_START.md (Common Errors section) |
| "How do I handle OAuth?" | MCP_ARCHITECTURE_REFERENCE.md Part 4 (OAuth decision tree) |
| "What error message should I return?" | MCP_ARCHITECTURE_REFERENCE.md Part 6 (error handling tree) |
| "Tool is too slow" | MCP_QUICK_START.md (Performance Tuning section) |
| "Need working code example" | MCP_IMPLEMENTATION_EXAMPLES.md |
| "Need to understand the big picture" | MCP_INTEGRATION_PLAN.md |

### Scenario 4: "I'm reviewing someone's Phase 2 PR"

1. Check against **MCP_QUICK_START.md** testing checklist
2. Verify error handling using **MCP_ARCHITECTURE_REFERENCE.md** Part 6
3. Verify schema using **MCP_ARCHITECTURE_REFERENCE.md** Part 5
4. Check config/env changes against **MCP_IMPLEMENTATION_EXAMPLES.md**
5. Ensure security using **MCP_QUICK_START.md** security section

---

## Document Map

```
MCP_INTEGRATION_INDEX.md (you are here)
│
├─ MCP_INTEGRATION_PLAN.md (Strategy, 4 phases, 30-min read)
│  └─ Use: Understand the whole project
│
├─ MCP_IMPLEMENTATION_EXAMPLES.md (Code snippets, 20-min skim)
│  └─ Use: Copy-paste starting points
│
├─ MCP_ARCHITECTURE_REFERENCE.md (Diagrams & trees, 15-min ref)
│  └─ Use: Solve design problems while coding
│
└─ MCP_QUICK_START.md (Checklists & walkthroughs, 10-min ref)
   └─ Use: Day-to-day while building
```

---

## Phase-by-Phase Reading List

### Before starting Phase 1:
1. Read MCP_INTEGRATION_PLAN.md (Phase 1 section only)
2. Skim MCP_QUICK_START.md (high-level summary)
3. Read MCP_IMPLEMENTATION_EXAMPLES.md (Parts 1-2)

### Before starting Phase 2:
1. Read MCP_INTEGRATION_PLAN.md (Phase 2 section only)
2. Read MCP_IMPLEMENTATION_EXAMPLES.md (Part 3)
3. Reference MCP_ARCHITECTURE_REFERENCE.md while coding

### Before starting Phase 3:
1. Read MCP_INTEGRATION_PLAN.md (Phase 3 section only)
2. Read MCP_QUICK_START.md (One-Tool Walkthrough)
3. Adapt examples from MCP_IMPLEMENTATION_EXAMPLES.md for each service

### Before starting Phase 4:
1. Read MCP_INTEGRATION_PLAN.md (Phase 4 section only)
2. Check how composio + n8n work (external research)
3. Follow MCP_QUICK_START.md pattern for dispatcher + feedback tools

---

## Key Concepts (Glossary)

**Tool:** A capability the agent can call. Schema + handler + metadata.

**Handler:** The function that runs when a tool is called. Takes `dict[str, Any]`, returns `str`.

**Registry:** Collection of all tools. Built at app startup from `register()` functions.

**ToolContext:** Shared services (config, memory, reminders, etc.) passed to all tool modules.

**Consequential:** A tool that sends/deletes/spends. Requires user approval before running (Tier 4 gate).

**MCP:** Model Control Protocol. Standard for connecting LLMs to external systems.

**OAuth:** Auth standard for delegated access (e.g., "let this app use your Gmail").

**Phase:** Rollout stage. 4 phases, each adding ~10 tools.

**Schema:** JSON Schema describing a tool's inputs (what the LLM must provide).

**Rate Limit:** Max calls per time period to prevent API abuse.

---

## Critical Files to Modify

These files change in every phase:

1. **wren/tools/__init__.py**
   - Import new tool modules
   - Add conditional registration in `build_registry()`

2. **config.yaml**
   - Add `mcp.services.[name].enabled: false`
   - Add `mcp.rate_limits` entries
   - Add to `safety.confirm_tools` if consequential

3. **.env.example**
   - Add placeholder for every new secret

4. **wren/tools/[new_service].py**
   - Create one per service (copy the template)

5. **wren/mcp/[new_service].py**
   - Create only if you need a custom client wrapper
   - Many services can use direct HTTP requests (no special wrapper)

---

## Typical Implementation Timeline

| Phase | Services | Effort | Dependencies | Timeline |
|-------|----------|--------|--------------|----------|
| 1 | Gmail, Calendar, Drive | 1-2 days | google-auth-oauthlib, google-api-python-client | Week 1-2 |
| 2 | Browser | 0.5 days | playwright | Week 3-4 |
| 3 | 8 services | 0.5 days each | service-specific | Week 5-8 |
| 4 | Dispatcher + Feedback | 1 day | — | Week 9-10 |

**Total: ~4 weeks, assuming 1-2 hours/day**

---

## Quality Checklist (For Every Tool)

Before submitting a PR:

- [ ] **Code:**
  - [ ] Handler catches all exceptions (no crashes)
  - [ ] Inputs validated (returns error if bad input)
  - [ ] No secrets in source code
  - [ ] Error messages are user-friendly

- [ ] **Schema:**
  - [ ] Valid JSON Schema
  - [ ] All fields have descriptions
  - [ ] Required fields listed
  - [ ] Input types are correct (string, integer, etc.)

- [ ] **Config:**
  - [ ] Service added to config.yaml (enabled: false)
  - [ ] Rate limits set (if applicable)
  - [ ] Added to safety.confirm_tools (if consequential)

- [ ] **Secrets:**
  - [ ] All API keys / tokens in .env.example
  - [ ] Correct env var names (use MCP_[SERVICE]_* pattern)

- [ ] **Testing:**
  - [ ] Unit test (schema validation, input check)
  - [ ] Integration test (real API, if possible)
  - [ ] Error path (what happens if API fails?)
  - [ ] Tests run without API key (mocked)

- [ ] **Documentation:**
  - [ ] Setup guide (how to enable + get credentials)
  - [ ] Example usage (what the agent can do)
  - [ ] Rate limits & costs (if applicable)

---

## When to Reach Out for Help

Use each doc for different types of questions:

| Question | Answer |
|----------|--------|
| "Should I implement this as Phase 1 or Phase 3?" | MCP_INTEGRATION_PLAN.md |
| "How do I implement OAuth?" | MCP_IMPLEMENTATION_EXAMPLES.md (Part 1) + MCP_ARCHITECTURE_REFERENCE.md (Part 4) |
| "What should my schema look like?" | MCP_ARCHITECTURE_REFERENCE.md (Part 5) |
| "Why isn't my tool showing up?" | MCP_QUICK_START.md (Common Errors) |
| "How do I test this?" | MCP_IMPLEMENTATION_EXAMPLES.md (Part 8) |
| "What patterns exist?" | MCP_ARCHITECTURE_REFERENCE.md (Part 8) |

---

## Troubleshooting Guide

### Build Error
→ Check: MCP_QUICK_START.md "Common Errors" section

### Tool Not Appearing
→ Check:
1. config.yaml: `mcp.services.[name].enabled: true`
2. wren/tools/__init__.py: import and register in `build_registry()`
3. No exceptions during import (check logs)
4. Restart Wren (config changes require restart)

### Auth Failing
→ Check:
1. Secret exists in .env (correct name)
2. Secret value is correct (not expired)
3. OAuth flow completed (if first time)
4. Token refresh logic (if cached token expired)

### Schema Invalid
→ Check:
1. Refer to MCP_ARCHITECTURE_REFERENCE.md Part 5
2. Valid JSON (use JSONLint)
3. Uses correct types: string, integer, number, boolean, array, object
4. All required fields listed

### Tool Too Slow
→ Check:
1. MCP_QUICK_START.md "Performance Tuning"
2. Cache repeated queries
3. Truncate large responses
4. Batch API calls instead of looping

---

## Contributing a New Phase 3 Tool

Template:

1. Create `wren/tools/[service].py` (use MCP_QUICK_START.md One-Tool Walkthrough)
2. Create `.wren/mcp/[service]_client.py` if needed (usually not needed; just use requests)
3. Update `wren/tools/__init__.py` (import + conditional register)
4. Update `config.yaml` (add service to mcp.services)
5. Update `.env.example` (add secrets)
6. Create `docs/SETUP_[SERVICE].md` (setup guide)
7. Add tests (`tests/test_[service].py`)
8. Update README with link to setup guide
9. Submit PR with all above ✓

Estimated time: **1 hour per tool**

---

## FAQ

**Q: Do I need to modify wren/agent.py or wren/orchestrator/**?
A: No. All integration happens in wren/tools/ and wren/mcp/. The core agent loop doesn't change.

**Q: Can I add a tool without changing config.yaml?
A: No. Every service must be explicitly enabled (enabled: false by default).

**Q: What if a tool handler fails?
A: It's caught by Tool.run(), returned as an error string. The agent reads it and decides what to do.

**Q: Can I disable a tool at runtime?
A: Yes, by setting enabled: false in config.yaml and restarting Wren. Or remove from registry.add() dynamically (advanced).

**Q: How do I handle expensive APIs (Higgsfield, Stripe)?
A: Set rate_limits in config.yaml. Check balance before calling. Log cost to audit trail.

**Q: Can tools call other tools?
A: Not directly. The agent loop picks one tool per turn. Chain via multi-turn conversation.

**Q: How do I test without real API keys?
A: Use unittest.mock to patch external calls. See MCP_IMPLEMENTATION_EXAMPLES.md Part 8.

---

## Next Steps

1. **Choose a phase:** Start with Phase 1 if you want high impact.
2. **Read the plan:** MCP_INTEGRATION_PLAN.md (Phase N section)
3. **Follow the quick start:** MCP_QUICK_START.md
4. **Copy code:** MCP_IMPLEMENTATION_EXAMPLES.md
5. **Debug issues:** MCP_ARCHITECTURE_REFERENCE.md
6. **Submit PR:** Verify against MCP_QUICK_START.md checklist

---

## Document Maintenance

These docs should be updated when:
- A new MCP service is discovered or released
- Phase N is completed (update status in each doc)
- A new pattern emerges (add to MCP_ARCHITECTURE_REFERENCE.md)
- A common error appears (add to MCP_QUICK_START.md)

---

Good luck! 🚀

Questions? Refer to the document map above.
