"""Google Drive integration via Google API (Tier 6+).

Search, list, and read files from Google Drive. Supports both Docs and raw files.
Uses OAuth for authentication.
"""
from __future__ import annotations

import os
from typing import Any

from .base import Registry, obj, string


def _build_drive_service():
    """Build a Google Drive API client using OAuth credentials."""
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
    except ImportError:
        return None, "Google API client not installed. Run: pip install -r requirements.txt"

    SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]
    cred_path = os.path.expanduser("~/.wren_oauth/drive_token.json")
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
                return None, "Drive auth not set up. Requires Google Cloud credentials."
            flow = InstalledAppFlow.from_client_secrets_file(client_secret, SCOPES)
            creds = flow.run_local_server(port=0)

        os.makedirs(os_path, exist_ok=True)
        with open(cred_path, "w") as f:
            f.write(creds.to_json())

    try:
        service = build("drive", "v3", credentials=creds)
        return service, None
    except Exception as e:
        return None, f"Failed to build Drive service: {e}"


def register(registry: Registry, ctx) -> None:
    def search_files(args: dict[str, Any]) -> str:
        service, err = _build_drive_service()
        if err:
            return err

        query_str = (args.get("query") or "").strip()
        if not query_str:
            return "I need a filename or search term."

        max_results = min(int(args.get("max_results") or 10), 50)
        try:
            # Search in Drive for files matching the name
            q = f"name contains '{query_str}' and trashed=false"
            results = (
                service.files()
                .list(q=q, spaces="drive", pageSize=max_results, fields="files(id, name, mimeType)")
                .execute()
            )
            files = results.get("files", [])

            if not files:
                return f"No files found matching '{query_str}'."

            lines = []
            for file in files:
                mime = file.get("mimeType", "unknown")
                icon = "📄" if "document" in mime else "📊" if "spreadsheet" in mime else "📁"
                lines.append(f"{icon} {file['name']} (id: {file['id']})")
            return "\n".join(lines[:max_results])
        except Exception as e:
            return f"Search failed: {e}"

    def read_file(args: dict[str, Any]) -> str:
        service, err = _build_drive_service()
        if err:
            return err

        file_id = (args.get("file_id") or "").strip()
        if not file_id:
            return "I need the file id (from search_files)."

        try:
            # Get file metadata
            file = service.files().get(fileId=file_id, fields="name, mimeType, webViewLink").execute()

            # If it's a Google Doc, export as plain text
            if "document" in file.get("mimeType", ""):
                export_result = (
                    service.files()
                    .export(fileId=file_id, mimeType="text/plain")
                    .execute()
                )
                content = export_result.decode("utf-8", errors="ignore")
            else:
                # For other types, try to get the raw content (if readable)
                import base64

                export_result = service.files().get_media(fileId=file_id).execute()
                content = export_result.decode("utf-8", errors="ignore")

            # Return first 2000 chars plus link
            return f"**{file['name']}**\n\n{content[:2000]}\n\n[View on Drive]({file['webViewLink']})"
        except Exception as e:
            return f"Failed to read file: {e}"

    def list_recent_files(args: dict[str, Any]) -> str:
        service, err = _build_drive_service()
        if err:
            return err

        max_results = min(int(args.get("max_results") or 10), 50)
        try:
            results = (
                service.files()
                .list(
                    spaces="drive",
                    pageSize=max_results,
                    fields="files(id, name, modifiedTime, mimeType)",
                    orderBy="modifiedTime desc",
                )
                .execute()
            )
            files = results.get("files", [])

            if not files:
                return "No recent files."

            lines = []
            for file in files:
                mime = file.get("mimeType", "")
                icon = "📄" if "document" in mime else "📊" if "spreadsheet" in mime else "📁"
                modified = file.get("modifiedTime", "").split("T")[0]
                lines.append(f"{icon} {file['name']} (modified {modified})")
            return "\n".join(lines[:max_results])
        except Exception as e:
            return f"Failed to list files: {e}"

    registry.add(
        "search_files",
        "Search Google Drive for files by name. Returns file ids you can use with read_file.",
        obj(
            {
                "query": string("Filename or search term."),
                "max_results": {"type": "integer", "description": "How many results to return (1-50, default 10)."},
            },
            required=["query"],
        ),
        search_files,
    )
    registry.add(
        "read_file",
        "Read the content of a Google Drive file (Docs, Sheets, text files, etc).",
        obj({"file_id": string("The file id (from search_files).")}, required=["file_id"]),
        read_file,
    )
    registry.add(
        "list_recent_files",
        "List your most recently modified files on Google Drive.",
        obj(
            {
                "max_results": {"type": "integer", "description": "How many files to list (1-50, default 10)."},
            }
        ),
        list_recent_files,
    )
