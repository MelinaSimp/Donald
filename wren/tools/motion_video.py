"""Motion integration via MCP server (Tier 6+).

AI video creation for marketing, explainers, product demos, social media content.
Creates professional videos from text, URLs, or designs.
Requires Motion API key and MCP server connection.
Phase 3 integration — stub ready for production.
"""
from __future__ import annotations

from typing import Any

from .base import Registry, obj, string


def register(registry: Registry, ctx) -> None:
    def create_video(args: dict[str, Any]) -> str:
        """Create a video from a brief, URL, or text."""
        brief = (args.get("brief") or "").strip()
        if not brief:
            return "I need a video brief (goal, key points, audience, tone)."

        duration_seconds = int(args.get("duration_seconds", 30))
        aspect_ratio = args.get("aspect_ratio", "16:9")  # 16:9, 9:16, 1:1, etc.

        # Stub: In production, call Motion MCP server
        return f"TODO: Create {duration_seconds}s Motion video ({aspect_ratio}) from brief (requires Motion API)"

    def create_followup(args: dict[str, Any]) -> str:
        """Create a variation or follow-up on a previous video."""
        video_id = (args.get("video_id") or "").strip()
        if not video_id:
            return "I need the video ID of the original video."

        changes = (args.get("changes") or "").strip()
        if not changes:
            return "I need to know what to change (tone, style, voiceover, etc)."

        # Stub
        return f"TODO: Create follow-up video based on {video_id} with changes: {changes}"

    def get_session_status(args: dict[str, Any]) -> str:
        """Check the status of a video generation session."""
        session_id = (args.get("session_id") or "").strip()
        if not session_id:
            return "I need a session ID."

        # Stub
        return f"TODO: Get status of Motion session {session_id}"

    registry.add(
        "create_video",
        "Create a professional video using Motion AI. Provide a brief describing the goal, "
        "audience, tone, and key points. Optionally include a URL (article, product page) or design system.",
        obj(
            {
                "brief": string(
                    "Video brief (goal, key points, audience, tone). "
                    "E.g., 'Launch video for new SaaS tool; audience: startups; tone: upbeat'"
                ),
                "duration_seconds": {"type": "integer", "description": "Video length: 15-120 seconds (default 30)."},
                "aspect_ratio": string("16:9 (default), 9:16 (vertical), or 1:1 (square)."),
            },
            required=["brief"],
        ),
        create_video,
        consequential=True,
    )
    registry.add(
        "create_followup",
        "Create a variation of an existing video (change tone, style, voiceover, etc).",
        obj(
            {
                "video_id": string("The original video ID."),
                "changes": string("What to change (e.g., 'make it more casual', 'change voiceover to female')."),
            },
            required=["video_id", "changes"],
        ),
        create_followup,
        consequential=True,
    )
    registry.add(
        "get_session_status",
        "Check the status of a Motion video generation session.",
        obj({"session_id": string("Session ID from create_video.")}, required=["session_id"]),
        get_session_status,
    )
