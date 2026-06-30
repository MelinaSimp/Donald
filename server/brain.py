import json
import logging
from anthropic import Anthropic
from server.config import settings

logger = logging.getLogger(__name__)

# Lazy initialization of Anthropic client to avoid proxy issues at import time
_client = None


def get_client():
    global _client
    if _client is None:
        _client = Anthropic(api_key=settings.anthropic_api_key)
    return _client

# Tool definitions
TOOLS = [
    {
        "name": "get_weather",
        "description": "Get current weather conditions and forecast for a location.",
        "input_schema": {
            "type": "object",
            "properties": {
                "location": {
                    "type": "string",
                    "description": "City name or coordinates (e.g., 'San Francisco' or '37.7749,-122.4194')",
                },
                "units": {
                    "type": "string",
                    "enum": ["celsius", "fahrenheit"],
                    "description": "Temperature units",
                },
            },
            "required": ["location"],
        },
    },
    {
        "name": "list_calendar_events",
        "description": "List upcoming calendar events.",
        "input_schema": {
            "type": "object",
            "properties": {
                "days_ahead": {
                    "type": "integer",
                    "description": "Number of days to look ahead (default: 7)",
                },
            },
        },
    },
    {
        "name": "create_calendar_event",
        "description": "Create a new calendar event. Must call await_confirmation first.",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "start_time": {
                    "type": "string",
                    "description": "ISO 8601 format: 2024-12-25T10:00:00",
                },
                "end_time": {
                    "type": "string",
                    "description": "ISO 8601 format: 2024-12-25T11:00:00",
                },
                "description": {"type": "string"},
            },
            "required": ["title", "start_time", "end_time"],
        },
    },
    {
        "name": "update_calendar_event",
        "description": "Modify an existing calendar event. Must call await_confirmation first.",
        "input_schema": {
            "type": "object",
            "properties": {
                "event_id": {"type": "string"},
                "title": {"type": "string"},
                "start_time": {"type": "string"},
                "end_time": {"type": "string"},
            },
            "required": ["event_id"],
        },
    },
    {
        "name": "list_emails",
        "description": "Search and list emails from your inbox.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query (e.g., 'from:alice subject:meeting')",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max emails to return (default: 10)",
                },
            },
        },
    },
    {
        "name": "send_email",
        "description": "Send an email. Must call await_confirmation first.",
        "input_schema": {
            "type": "object",
            "properties": {
                "to": {"type": "string", "description": "Recipient email address"},
                "subject": {"type": "string"},
                "body": {"type": "string"},
            },
            "required": ["to", "subject", "body"],
        },
    },
    {
        "name": "await_confirmation",
        "description": (
            "Signal that you're about to take a destructive or risky action. "
            "Call this BEFORE the actual tool (send_email, create_calendar_event, etc.). "
            "After calling this, voice the proposed action in the same turn and "
            "wait for the user's verbal yes/no in the next turn. "
            "Do NOT call the destructive tool again until the user confirms."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "summary": {
                    "type": "string",
                    "description": "Brief summary of what you're about to do (e.g., 'send email to alice@example.com')",
                },
                "target_tool": {
                    "type": "string",
                    "description": "Name of the tool that requires confirmation (e.g., 'send_email')",
                },
            },
            "required": ["summary", "target_tool"],
        },
    },
]

SYSTEM_PROMPT = """You are Donald, a voice-first mobile AI agent. You help users get things done through conversation.

You have access to tools for weather, calendar, and email. Some tools are destructive and require voice confirmation:
- Before calling send_email, create_calendar_event, or update_calendar_event, you MUST call await_confirmation first in the same turn.
- Voice the proposal to the user ("Sending Sarah an email about the meeting. Confirm?") and wait for their verbal yes/no response in the next turn.
- Only call the destructive tool after the user says yes.

Anti-hallucination rule for numbers:
Numbers about real-world data (weather, calendar times, email counts, anything quantitative) MUST come from a tool you called THIS turn.
Quote the tool's exact number. Don't round, soften ("about", "roughly"), or estimate from training data.
If a tool returns no data or fails, say so plainly: "I don't have current weather data right now. The service may be down."
Never fabricate or hallucinate numbers.

Keep responses concise and conversational. You're speaking to someone who can't look at their screen — be clear and brief."""


class Brain:
    def __init__(self):
        self.conversation_history = []

    def start_session(self):
        """Reset conversation for a new session."""
        self.conversation_history = []

    def add_turn(self, role: str, content: str):
        """Add a turn to the conversation history."""
        self.conversation_history.append({"role": role, "content": content})

    def get_history_for_api(self) -> list[dict]:
        """Format history for Anthropic API."""
        return self.conversation_history

    def stream_response(self, user_message: str) -> tuple[str, list[dict]]:
        """
        Stream a response from Claude.
        Yields (text_chunk, [tool_uses]) as they arrive.

        Returns (full_response_text, tool_uses).
        """
        self.add_turn("user", user_message)

        response_text = ""
        tool_uses = []

        client = get_client()

        with client.messages.stream(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=self.get_history_for_api(),
        ) as stream:
            for event in stream.text_stream:
                response_text += event
                yield event, []

            # After stream finishes, check for tool uses
            final_message = stream.get_final_message()
            if final_message.stop_reason == "tool_use":
                for block in final_message.content:
                    if hasattr(block, "name"):  # tool use block
                        tool_uses.append(
                            {
                                "name": block.name,
                                "id": block.id,
                                "input": block.input,
                            }
                        )

        # Save assistant response to history
        self.add_turn("assistant", response_text)

        return response_text, tool_uses

    def execute_tool(self, tool_name: str, tool_input: dict) -> dict:
        """Execute a tool and return result."""
        logger.info(f"Executing tool: {tool_name} with input: {tool_input}")

        if tool_name == "get_weather":
            return execute_get_weather(tool_input)
        elif tool_name == "list_calendar_events":
            return execute_list_calendar_events(tool_input)
        elif tool_name == "create_calendar_event":
            return execute_create_calendar_event(tool_input)
        elif tool_name == "update_calendar_event":
            return execute_update_calendar_event(tool_input)
        elif tool_name == "list_emails":
            return execute_list_emails(tool_input)
        elif tool_name == "send_email":
            return execute_send_email(tool_input)
        elif tool_name == "await_confirmation":
            # Signal tool: no-op on execute. Server emits confirm_request to PWA.
            return {"status": "awaiting_user_confirmation"}
        else:
            return {"error": f"Unknown tool: {tool_name}"}


# Tool implementations (stubbed for now; will integrate with real APIs at deploy)


def execute_get_weather(input_data: dict) -> dict:
    """Stub: return fake weather data."""
    location = input_data.get("location", "Unknown")
    return {
        "location": location,
        "temperature": 72,
        "condition": "Partly Cloudy",
        "humidity": 55,
        "wind_speed": 8,
    }


def execute_list_calendar_events(input_data: dict) -> dict:
    """Stub: return empty calendar."""
    return {"events": []}


def execute_create_calendar_event(input_data: dict) -> dict:
    """Stub: pretend to create event."""
    return {"status": "created", "event_id": "fake-event-123"}


def execute_update_calendar_event(input_data: dict) -> dict:
    """Stub: pretend to update event."""
    return {"status": "updated", "event_id": input_data.get("event_id")}


def execute_list_emails(input_data: dict) -> dict:
    """Stub: return empty inbox."""
    return {"emails": []}


def execute_send_email(input_data: dict) -> dict:
    """Stub: pretend to send email."""
    return {"status": "sent", "to": input_data.get("to")}
