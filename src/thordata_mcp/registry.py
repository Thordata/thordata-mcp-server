from mcp.server.fastmcp import FastMCP

# High-level product APIs (compact by default)
from thordata_mcp.tools.product import register as register_product_tools
from thordata_mcp.tools.product_compact import register as register_compact_tools

# Data-plane tools (structured namespace: serp.*, universal.*, browser.*, tasks.*, proxy.*)
from thordata_mcp.tools.data import serp as data_serp
from thordata_mcp.tools.data import universal as data_universal
from thordata_mcp.tools.data import browser as data_browser
from thordata_mcp.tools.data import tasks as data_tasks
from thordata_mcp.tools.data import proxy as data_proxy

# Control-plane tools (account management: account.*, whitelist.*, proxy_users.*, unlimited.*, locations.*)
from thordata_mcp.tools.control import account as control_account
from thordata_mcp.tools.control import whitelist as control_whitelist
from thordata_mcp.tools.control import proxy_users as control_proxy_users
from thordata_mcp.tools.control import unlimited as control_unlimited
from thordata_mcp.tools.control import locations as control_locations


def register_all(mcp: FastMCP, expose_all: bool = False) -> None:
    """Synchronously register all tool groups with the MCP server instance.
    
    Architecture:
    - Product-line tools: serp.*, unlocker.*, web_scraper.*, smart_scrape (LLM-friendly)
    - Data-plane tools: serp.*, universal.*, browser.*, tasks.*, proxy.* (advanced/structured namespace)
    - Control-plane tools: account.*, whitelist.*, proxy_users.*, unlimited.*, locations.* (admin/ops)
    
    Args:
        expose_all: If False (default), expose only product-line tools and minimal browser automation.
                    If True, additionally expose advanced data-plane + control-plane tools for debugging/admin.
    """
    import anyio
    
    async def _reg() -> None:
        if expose_all:
            # Full tool surface (debug/admin). Not recommended for Cursor default UX.
            register_product_tools(mcp)
            # Data-plane tools (structured namespace)
            data_serp.register(mcp)
            data_universal.register(mcp)
            data_browser.register(mcp)
            data_tasks.register(mcp)
            data_proxy.register(mcp)
            
            # Control-plane tools (account management)
            control_account.register(mcp)
            control_whitelist.register(mcp)
            control_proxy_users.register(mcp)
            control_unlimited.register(mcp)
            control_locations.register(mcp)
        else:
            # Core mode: competitor-style compact product surface (only 5 tools)
            register_compact_tools(mcp)
            # Note: full namespaces and admin tools are intentionally not exposed in core mode.

    try:
        anyio.run(_reg)
    except Exception as e:  # pragma: no cover - defensive
        print(f"Error registering tools: {e}")
        raise e