"""Thordata MCP tools.

This package contains the MCP tool implementations exposed by the Thordata MCP server.

Architecture:
- entrypoints.py: High-level simplified API (search, scrape, task_run) for LLMs
- data/: Data-plane tools with structured namespace (serp.*, universal.*, browser.*, tasks.*, proxy.*)
- control/: Control-plane tools for account management (account.*, whitelist.*, proxy_users.*, unlimited.*, locations.*)
"""

from __future__ import annotations

__all__ = [
    "entrypoints",
    "data",
    "control",
]
