"""Gmail integration via Google API (Tier 6+).

Read and search emails, list labels, and draft/send messages.
Authentication: OAuth2 via google-auth-oauthlib. Credentials are cached
in ~/.wren_oauth/ after the first auth flow.

Sending email is gated (consequential=True) — it stops for user confirmation
before actually sending.
"""
from __future__ import annotations

import os
from typing import Any

from .base import Registry, obj, string


def _build_gmail_service():
    """Build a Gmail API client using OAuth credentials."""
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
    except ImportError:
        return None, "Google API client not installed. Run: pip install -r requirements.txt"

    SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]
    cred_path = os.path.expanduser("~/.wren_oauth/gmail_token.json")
    os_path = os.path.expanduser("~/.wren_oauth")

    creds = None
    if os.path.exists(cred_path):
        creds = Credentials.from_authorized_user_file(cred_path, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            # First time: user must authorize. This requires client_secret.json from
            # Google Cloud Console (not included in repo for security).
            client_secret = os.path.expanduser("~/.wren_oauth/client_secret.json")
            if not os.path.exists(client_secret):
                return None, (
                    "Gmail auth not set up. Requires Google Cloud credentials. "
                    "See docs/GMAIL_SETUP.md for instructions."
                )
            flow = InstalledAppFlow.from_client_secrets_file(client_secret, SCOPES)
            creds = flow.run_local_server(port=0)

        os.makedirs(os_path, exist_ok=True)
        with open(cred_path, "w") as f:
            f.write(creds.to_json())

    try:
        service = build("gmail", "v1", credentials=creds)
        return service, None
    except Exception as e:
        return None, f"Failed to build Gmail service: {e}"


def register(registry: Registry, ctx) -> None:
    def search_emails(args: dict[str, Any]) -> str:
        service, err = _build_gmail_service()
        if err:
            return err

        query = (args.get("query") or "").strip()
        if not query:
            return "I need a search query (e.g., 'from:alice' or 'subject:invoice')."

        max_results = min(int(args.get("max_results") or 5), 20)
        try:
            results = service.users().messages().list(userId="me", q=query, maxResults=max_results).execute()
            messages = results.get("messages", [])
            if not messages:
                return f"No emails found matching '{query}'."

            lines = []
            for msg in messages[:max_results]:
                header_result = service.users().messages().get(userId="me", id=msg["id"], format="metadata", metadataHeaders=["Subject", "From"]).execute()
                headers = {h["name"]: h["value"] for h in header_result.get("payload", {}).get("headers", [])}
                lines.append(f"- {headers.get('From', 'Unknown')} — {headers.get('Subject', '(no subject)')}")
            return "\n".join(lines)
        except Exception as e:
            return f"Gmail search failed: {e}"

    def read_email(args: dict[str, Any]) -> str:
        service, err = _build_gmail_service()
        if err:
            return err

        email_id = (args.get("email_id") or "").strip()
        if not email_id:
            return "I need the email id (from search_emails)."

        try:
            msg = service.users().messages().get(userId="me", id=email_id, format="full").execute()
            headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
            body = ""
            if "parts" in msg.get("payload", {}):
                for part in msg["payload"]["parts"]:
                    if part.get("mimeType") == "text/plain":
                        data = part.get("body", {}).get("data", "")
                        if data:
                            import base64
                            body = base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")
                            break
            else:
                body = msg.get("payload", {}).get("body", {}).get("data", "")
                if body:
                    import base64
                    body = base64.urlsafe_b64decode(body).decode("utf-8", errors="ignore")

            return f"From: {headers.get('From')}\nSubject: {headers.get('Subject')}\n\n{body[:1000]}"
        except Exception as e:
            return f"Failed to read email: {e}"

    def list_labels(args: dict[str, Any]) -> str:
        service, err = _build_gmail_service()
        if err:
            return err

        try:
            results = service.users().labels().list(userId="me").execute()
            labels = results.get("labels", [])
            return "\n".join(f"- {l['name']}" for l in labels[:20])
        except Exception as e:
            return f"Failed to list labels: {e}"

    registry.add(
        "search_emails",
        "Search the user's Gmail inbox by query (e.g., 'from:alice', 'subject:invoice', 'is:unread'). "
        "Returns a list of matching emails with sender and subject.",
        obj(
            {
                "query": string("Gmail search query (supports: from, subject, is:unread, etc)."),
                "max_results": {"type": "integer", "description": "How many results to return (1-20, default 5)."},
            },
            required=["query"],
        ),
        search_emails,
    )
    registry.add(
        "read_email",
        "Read the full content of a specific email by its id. Use after search_emails to read a message.",
        obj({"email_id": string("The email id (from search_emails result).")}, required=["email_id"]),
        read_email,
    )
    registry.add(
        "list_labels",
        "List all Gmail labels (categories). Use to see what labels you have organized.",
        obj({}),
        list_labels,
    )
