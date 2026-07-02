# Hermes Command Center Dashboard

A live control panel for monitoring and controlling Donald's execution in real-time.

## Starting the Dashboard

The dashboard is automatically available when the gateway server is running:

```bash
python -m gateway.server
```

Then open your browser to:
- **Dashboard UI:** `http://localhost:8765/dashboard`
- **API endpoint:** `http://localhost:8765/api/dashboard`

## What You See

### Status Indicator
- **● LIVE** (purple) — Agent is running normally
- **● HALTED** (red) — Agent execution is paused

### Metrics
- **Turns** — Number of completed conversation turns
- **Hermes Actions** — Number of tasks delegated to Hermes
- **Status** — Current state (Ready or Halted)

### Live Activity Feed
Real-time log of every action:
- **✓** (green) — Action completed successfully
- **✕** (red) — Action failed with error
- **⏸** (amber) — Action pending (in progress)
- **⊘** (purple) — Action declined by user

Each entry shows:
- Timestamp
- Action status icon
- Action name (usually "hermes")
- Task description
- Preview of result (first 200 chars, truncated)
- Error message if applicable

### Last Messages
- **Last User Input** — What you said to Donald
- **Last Response** — What Donald replied with

## Controls

- **Stop** — Pause the agent (kill switch)
- **Resume** — Resume a paused agent

## API

### GET /api/dashboard
Returns a JSON snapshot of the current state:

```json
{
  "paused": false,
  "turn_count": 5,
  "hermes_actions": 3,
  "last_session_id": "default",
  "last_user_message": "What time is it?",
  "last_response": "It's 2:30 PM.",
  "actions": [
    {
      "timestamp": 1705334400.123,
      "action_type": "tool_call",
      "name": "hermes",
      "status": "ok",
      "task": "get current time",
      "reason": "user asked",
      "preview": "2025-01-15 14:30:00",
      "error": null
    }
  ]
}
```

### POST /api/dashboard/pause
Pause agent execution.

Response: `{"status": "paused"}`

### POST /api/dashboard/resume
Resume agent execution.

Response: `{"status": "resumed"}`

## How It Works

### State Tracking
The gateway server tracks all events from the orchestrator:
- `tool_call` — Hermes delegation initiated
- `tool_result` — Hermes result received (ok/error/declined)
- `final` — Turn completed with final response

Event data is stored in a **bounded deque** (max 100 actions by default) to prevent unbounded memory growth.

### Live Updates
The dashboard polls `/api/dashboard` every **2 seconds** and updates the UI with:
- New actions in the feed
- Updated metrics
- Latest messages

The 2-second refresh is fast enough for real-time monitoring while keeping network overhead minimal.

### Architecture
- **`gateway/dashboard_state.py`** — State tracking and storage
- **`gateway/server.py`** — API endpoints and HTML page
- **Frontend (HTML/JS in server.py)** — Interactive dashboard UI

## Implementation Details

### DashboardState Class
Manages mutable state:
- `actions` — Deque of DashboardAction objects (bounded)
- `session_turn_count` — Total turns completed
- `hermes_action_count` — Total Hermes delegations
- `_paused` — Execution pause flag
- `last_user_message` — Most recent user input
- `last_response` — Most recent Donald response

### Event Recording
When events flow through the gateway, they're captured:

1. **In `/api/chat` (non-streaming):**
   - User message is recorded
   - Turn completes
   - All events are recorded in batch

2. **In `/ws` (streaming):**
   - User message is recorded as it arrives
   - Events are recorded as they stream
   - UI receives both event stream AND sees dashboard updates

### Pause/Resume
The pause state is tracked but **not yet enforced** by the orchestrator. Current implementation:
- Dashboard shows pause state
- API can toggle the flag
- Future: Wire to orchestrator to halt tool execution mid-turn

## Testing

Run the test suite:

```bash
python -m pytest tests/test_dashboard.py -v
```

Tests cover:
- State creation and initialization
- Event recording (tool_call, tool_result, final)
- Declined actions
- Pause/resume
- Snapshot serialization
- Bounded action deque
- Global instance management

## Future Enhancements

- **Real-time streaming:** Switch from polling to Server-Sent Events (SSE) for instant updates
- **Enforce pause:** Actually halt tool execution when paused (requires orchestrator changes)
- **Persistence:** Save action log to disk for post-run analysis
- **Filtering:** Filter activity feed by action type or status
- **Metrics:** Charts showing action frequency over time
- **Session management:** View multiple sessions side-by-side
