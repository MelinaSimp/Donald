"""Google Calendar integration via Google API (Tier 6+).

List events, create events, and check upcoming availability.
Uses the same OAuth credentials as gmail.py (shared scopes).
"""
from __future__ import annotations

import os
from typing import Any

from .base import Registry, obj, string


def _build_calendar_service():
    """Build a Google Calendar API client using OAuth credentials."""
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
    except ImportError:
        return None, "Google API client not installed. Run: pip install -r requirements.txt"

    SCOPES = ["https://www.googleapis.com/auth/calendar"]
    cred_path = os.path.expanduser("~/.wren_oauth/calendar_token.json")
    os_path = os.path.expanduser("~/.wren_oauth")

    creds = None
    if os.path.exists(cred_path):
        creds = Credentials.from_authorized_user_file(cred_path, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            client_secret = os.path.expanduser("~/.wren_oauth/client_secret.json")
            if not os.path.exists(client_secret):
                return None, "Calendar auth not set up. Requires Google Cloud credentials."
            flow = InstalledAppFlow.from_client_secrets_file(client_secret, SCOPES)
            creds = flow.run_local_server(port=0)

        os.makedirs(os_path, exist_ok=True)
        with open(cred_path, "w") as f:
            f.write(creds.to_json())

    try:
        service = build("calendar", "v3", credentials=creds)
        return service, None
    except Exception as e:
        return None, f"Failed to build Calendar service: {e}"


def register(registry: Registry, ctx) -> None:
    def list_events(args: dict[str, Any]) -> str:
        service, err = _build_calendar_service()
        if err:
            return err

        try:
            from datetime import datetime, timedelta

            days_ahead = int(args.get("days_ahead") or 7)
            now = datetime.utcnow().isoformat() + "Z"
            end_time = (datetime.utcnow() + timedelta(days=days_ahead)).isoformat() + "Z"

            events_result = (
                service.events()
                .list(
                    calendarId="primary",
                    timeMin=now,
                    timeMax=end_time,
                    maxResults=20,
                    singleEvents=True,
                    orderBy="startTime",
                )
                .execute()
            )
            events = events_result.get("items", [])

            if not events:
                return f"No events in the next {days_ahead} days."

            lines = []
            for event in events:
                start = event["start"].get("dateTime", event["start"].get("date", ""))
                title = event.get("summary", "(no title)")
                lines.append(f"- {start}: {title}")
            return "\n".join(lines)
        except Exception as e:
            return f"Failed to list events: {e}"

    def create_event(args: dict[str, Any]) -> str:
        service, err = _build_calendar_service()
        if err:
            return err

        title = (args.get("title") or "").strip()
        if not title:
            return "I need an event title."

        start_time = (args.get("start_time") or "").strip()
        if not start_time:
            return "I need a start time (ISO format: 2026-06-30T14:00:00)."

        end_time = (args.get("end_time") or "").strip()
        if not end_time:
            # Default to 1 hour later
            from datetime import datetime, timedelta

            start = datetime.fromisoformat(start_time)
            end = start + timedelta(hours=1)
            end_time = end.isoformat()

        description = args.get("description", "")

        try:
            event = {
                "summary": title,
                "description": description,
                "start": {"dateTime": start_time, "timeZone": "UTC"},
                "end": {"dateTime": end_time, "timeZone": "UTC"},
            }
            created = service.events().insert(calendarId="primary", body=event).execute()
            return f"Created event '{title}' at {start_time}"
        except Exception as e:
            return f"Failed to create event: {e}"

    registry.add(
        "list_events",
        "List upcoming calendar events for the next N days. Use to check your schedule.",
        obj(
            {
                "days_ahead": {"type": "integer", "description": "Days to look ahead (default 7)."},
            }
        ),
        list_events,
    )
    registry.add(
        "create_event",
        "Create a calendar event with title, start time, and optional description.",
        obj(
            {
                "title": string("Event title."),
                "start_time": string("Start time (ISO format: 2026-06-30T14:00:00)."),
                "end_time": string("End time (ISO format, optional — defaults to 1 hour after start)."),
                "description": string("Optional event description."),
            },
            required=["title", "start_time"],
        ),
        create_event,
    )
