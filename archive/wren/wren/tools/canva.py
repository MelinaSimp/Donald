"""Canva integration via MCP server (Tier 6+).

Create, edit, and manage Canva designs. Requires Canva API key.
This is a Phase 3 integration — stub implementation ready for production.
"""
from __future__ import annotations

from typing import Any

from .base import Registry, obj, string


def register(registry: Registry, ctx) -> None:
    def create_design(args: dict[str, Any]) -> str:
        """Create a new Canva design from a template."""
        title = (args.get("title") or "").strip()
        if not title:
            return "I need a design title."

        design_type = args.get("design_type", "instagram_post")  # post, presentation, doc, etc.
        # Stub: In production, call Canva MCP server via HTTP or subprocess
        return f"TODO: Create Canva {design_type} '{title}' (requires Canva API key + MCP server)"

    def list_designs(args: dict[str, Any]) -> str:
        """List the user's Canva designs."""
        # Stub: In production, call Canva API
        return "TODO: List Canva designs (requires Canva API key)"

    def export_design(args: dict[str, Any]) -> str:
        """Export a design as PNG, PDF, or video."""
        design_id = (args.get("design_id") or "").strip()
        if not design_id:
            return "I need a design ID."

        export_format = args.get("format", "png").lower()
        # Stub
        return f"TODO: Export design {design_id} as {export_format} (requires Canva API)"

    registry.add(
        "create_design",
        "Create a new Canva design. Specify the type (instagram_post, presentation, document, etc).",
        obj(
            {
                "title": string("Design title."),
                "design_type": string("Type: instagram_post, presentation, document, flyer, etc."),
            },
            required=["title"],
        ),
        create_design,
        consequential=True,
    )
    registry.add(
        "list_designs",
        "List all your Canva designs.",
        obj({}),
        list_designs,
    )
    registry.add(
        "export_design",
        "Export a Canva design as PNG, PDF, or MP4.",
        obj(
            {
                "design_id": string("The design ID."),
                "format": string("Export format: png, pdf, or mp4."),
            },
            required=["design_id"],
        ),
        export_design,
        consequential=True,
    )
