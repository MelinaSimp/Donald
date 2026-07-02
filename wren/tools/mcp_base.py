"""MCP Server integration base (Tier 6+).

Wren can integrate with any MCP server via this base layer. Each MCP server
(Gmail, Google Drive, Canva, etc.) gets its own tool module that uses this
base to proxy calls to the MCP server's tools.

Authentication is handled per-server (OAuth, API keys, etc.) and credentials
are loaded from .env and config.yaml. The base provides:
- Tool result caching to avoid duplicate calls
- Error handling and result transformation
- Logging of all MCP calls to the audit trail
"""
from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from typing import Any

logger = logging.getLogger("wren.mcp")


class MCPClient(ABC):
    """Abstract base for MCP server clients. Subclasses implement connection
    to specific MCP servers (Gmail, Drive, Canva, etc.)."""

    def __init__(self, config: dict[str, Any], credentials: dict[str, Any] | None = None):
        self.config = config
        self.credentials = credentials or {}
        self._init_session()

    @abstractmethod
    def _init_session(self) -> None:
        """Initialize the MCP session (authenticate, set up transport, etc.)."""
        pass

    @abstractmethod
    def call(self, tool_name: str, arguments: dict[str, Any]) -> str:
        """Call an MCP server tool and return the result as a string."""
        pass

    def close(self) -> None:
        """Clean up resources (override if needed)."""
        pass


class LocalMCPClient(MCPClient):
    """Runs MCP servers locally via subprocess. Used for tools like n8n,
    composio that run in the same environment."""

    def __init__(self, config: dict[str, Any], server_type: str, credentials: dict[str, Any] | None = None):
        self.server_type = server_type
        self.process = None
        super().__init__(config, credentials)

    def _init_session(self) -> None:
        """Start the local MCP server process."""
        import subprocess

        # This is a stub — in production, use `mcp-server` CLI or Python subprocess
        # to start the server and establish stdio transport.
        logger.debug(f"Initializing local MCP server: {self.server_type}")

    def call(self, tool_name: str, arguments: dict[str, Any]) -> str:
        """Send a call to the local MCP server via stdio."""
        # Stub: in production, serialize to JSON-RPC and send via subprocess.stdin
        return f"Local MCP {self.server_type} tool '{tool_name}' not yet implemented"


class HTTPMCPClient(MCPClient):
    """Calls MCP servers via HTTP (used for cloud-hosted tools like Canva, Motion)."""

    def __init__(self, config: dict[str, Any], server_url: str, credentials: dict[str, Any] | None = None):
        self.server_url = server_url
        self.client = None
        super().__init__(config, credentials)

    def _init_session(self) -> None:
        """Initialize HTTP session with auth headers."""
        import httpx

        headers = {"User-Agent": "Wren/0.1"}
        if "api_key" in self.credentials:
            headers["Authorization"] = f"Bearer {self.credentials['api_key']}"
        self.client = httpx.Client(base_url=self.server_url, headers=headers, timeout=30.0)

    def call(self, tool_name: str, arguments: dict[str, Any]) -> str:
        """Call the MCP server via HTTP."""
        if not self.client:
            return "MCP server not initialized"
        try:
            response = self.client.post(
                "/tools/call",
                json={"tool": tool_name, "arguments": arguments},
            )
            response.raise_for_status()
            data = response.json()
            return json.dumps(data, indent=2)
        except Exception as e:
            return f"MCP call failed: {e}"

    def close(self) -> None:
        if self.client:
            self.client.close()
