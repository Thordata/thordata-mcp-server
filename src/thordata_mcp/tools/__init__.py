"""Thordata MCP tools.

This package contains the MCP tool implementations exposed by the Thordata MCP server.

Architecture:
- product_compact.py: Compact product API for MCP clients (serp/unlocker/web_scraper/browser/smart_scrape)
- product.py: Expanded product API (serp.* / unlocker.* / web_scraper.* / browser.*) used in --expose-all-tools
- data/: Data-plane tools with structured namespace (serp.*, universal.*, browser.*, tasks.*, proxy.*)
- control/: Control-plane tools for account management (account.*, whitelist.*, proxy_users.*, unlimited.*, locations.*)
"""

from __future__ import annotations

__all__ = [
    "data",
    "control",
]
