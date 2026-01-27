"""Tool registry for Thordata MCP Server.

This module provides a single entry point to register all MCP tools.

Design goals:
- English-only repository content
- Deterministic, discoverable tool naming
- 100% coverage of thordata-python-sdk v1.6.0 capabilities
- Stable, structured outputs (dict) for LLM consumption
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP


def register_all(mcp: FastMCP) -> None:
    """Register all tool groups."""

    # Data plane
    from thordata_mcp.tools.data import browser as browser_tools
    from thordata_mcp.tools.data import proxy as proxy_tools
    from thordata_mcp.tools.data import serp as serp_tools
    from thordata_mcp.tools.data import tasks as tasks_tools
    from thordata_mcp.tools.data import universal as universal_tools

    # Control plane
    from thordata_mcp.tools.control import account as account_tools
    from thordata_mcp.tools.control import proxy_users as proxy_users_tools
    from thordata_mcp.tools.control import unlimited as unlimited_tools
    from thordata_mcp.tools.control import whitelist as whitelist_tools
    from thordata_mcp.tools.control import locations as locations_tools

    serp_tools.register(mcp)
    universal_tools.register(mcp)
    browser_tools.register(mcp)
    proxy_tools.register(mcp)
    tasks_tools.register(mcp)

    account_tools.register(mcp)
    whitelist_tools.register(mcp)
    proxy_users_tools.register(mcp)
    locations_tools.register(mcp)
    unlimited_tools.register(mcp)
