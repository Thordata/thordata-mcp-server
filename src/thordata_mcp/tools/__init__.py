"""Thordata MCP tools.

This package contains the MCP tool implementations exposed by the Thordata MCP server.

Current version focuses on scraping-related capabilities, main structure:
- product_compact.py: Streamlined product API for MCP clients (serp/unlocker/web_scraper/browser/smart_scrape)
- product.py: Full product implementation for internal use (reused by compact version, not directly exposed as tool namespace)
- data/: Data plane tools (serp.*, universal.*, browser.*, tasks.*), providing low-level encapsulation for product layer
"""

from __future__ import annotations

__all__ = ["data"]
