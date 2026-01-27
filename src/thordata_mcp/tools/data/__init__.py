"""
Data-plane tools for Thordata MCP Server.

Data-plane tools are responsible for retrieving data (SERP, Universal Scrape, Web Scraper Tasks, Browser).
All tools must be English-only and return structured dict outputs.
"""

from __future__ import annotations

__all__ = [
    "serp",
    "universal",
    "browser",  # get_connection_url, screenshot
    "tasks",
    "proxy",
]

