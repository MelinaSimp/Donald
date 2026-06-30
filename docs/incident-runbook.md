# Incident Response Runbook (3.6)

> The point of this file is that during the first 30 minutes of a real
> incident you are **reading actions, not searching docs**. Keep it current.
> Replace every `<PLACEHOLDER>` with your real console URLs and CLI commands.

## Universal first moves

```bash
# 1. Stop the agent from making any more tool calls.
<your secrets CLI> secrets set AGENT_KILL_SWITCH=true   # e.g. doppler secrets set ...

# 2. Capture forensic state.
TS=$(date +%s)
git log --oneline -20            >  /tmp/agent-incident-$TS.log
journalctl -u agent --since "2 hours ago" >> /tmp/agent-incident-$TS.log 2>/dev/null || true
```

The kill switch (security/killswitch.py) short-circuits every tool dispatch on
the next call. The audit shield will show `kill-switch: ACTIVE (critical)`.

---

## "The agent is misbehaving / doing something I didn't ask for"

1. **Kill switch first** (above). Stop the bleeding before diagnosing.
2. Disable any user-defined scheduled tasks / cron triggers.
3. Grep the last 24h of conversation/messages for the trigger:
   ```bash
   grep -rniE 'ignore (all|previous)|new instructions|send (all|every)' <message-store>
   ```
   A hit inside ingested content (email body, fetched page, DB row) points at
   prompt injection — confirm the gate (security/injection_gate.py) flagged it.
4. Once contained, review which tools fired via the anomaly-gate counters and
   the approval-gate decisions in the logs.

---

## Per-credential playbooks

Duplicate one block per credential the agent holds. Fill in the real URLs.

### `ANTHROPIC_API_KEY` (or your LLM provider key) leaked

**Blast radius:** attacker can run your model on your dime; no data access by
itself, but cost + any tool calls the key enables via your agent.

1. `<provider console URL>` → revoke / regenerate the key.
2. `<secrets CLI> secrets set ANTHROPIC_API_KEY=<new_value>` in dev + prod.
3. Restart the agent.
4. Verify: send one chat turn, confirm the model responds.
5. Audit recent usage at `<provider usage URL>`. Unexpected spend = abuse window.

### `AGENT_BEARER_TOKEN` leaked

**Blast radius:** attacker can call your agent's HTTP/WebSocket surface as you.

1. Rotate using the overlap procedure (security/bearer_auth.py):
   copy CURRENT → PREV, set a new CURRENT, redeploy.
2. Re-pair every client to the new token.
3. After the overlap window, unset PREV.
4. Review the auth-rate-limiter lockout logs for the source IP.

### `GITHUB_TOKEN` / PAT leaked

**Blast radius:** depends on scope — read code, open PRs, or (if over-scoped)
push to / delete repos.

1. `https://github.com/settings/tokens` → revoke.
2. Regenerate as a **fine-grained, repo-scoped, read-only** token (see
   docs/secrets-inventory.md for the minimal scope set).
3. `<secrets CLI> secrets set GITHUB_TOKEN=<new_value>`; restart; verify a
   read flow (e.g. "check repo status").
4. Audit `https://github.com/settings/security-log` for unexpected actions.

### `STRIPE_*` / payment-processor key leaked

**Blast radius:** with a full secret key — read customer + payment data, issue
refunds, create charges.

1. `https://dashboard.stripe.com/apikeys` → roll the key.
2. Re-issue as a **restricted key** with only the read scopes the agent uses.
3. Rotate in secrets manager; restart; verify.
4. Review `https://dashboard.stripe.com/logs` for unexpected API calls.

### Database credential leaked

**Blast radius:** read (and if not read-only, write/delete) every row.

1. Rotate the DB password in your provider console.
2. Update `DATABASE_URL` (+ `DATABASE_URL_READONLY`) in secrets manager.
3. Restart; verify a query path.
4. If you have the read-only role (2.5), confirm the leaked credential was the
   read-only one — smaller blast radius.

---

## After any incident

- Confirm the leaked credential is **revoked**, not just rotated. Revocation is
  the load-bearing step.
- Run `POST /api/security/audit`; confirm the shield is back to green.
- File a short note: what leaked, how, what the abuse window was, what changed.
- Set `AGENT_KILL_SWITCH=false` only once you are confident the hole is closed.
