from mcp.server.fastmcp import FastMCP

# High-level entrypoints (simplified API for LLMs)
from thordata_mcp.tools.entrypoints import register as register_entrypoints

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
    - High-level entrypoints: search, scrape, task_run (for LLM convenience)
    - Data-plane tools: serp.*, universal.*, browser.*, tasks.*, proxy.* (structured namespace)
    - Control-plane tools: account.*, whitelist.*, proxy_users.*, unlimited.*, locations.*
    
    Args:
        expose_all: If False (default), only expose 6 core tools:
                    search, scrape, task_run, browser.navigate, browser.snapshot, tasks.list
                    If True, expose all 43 tools.
    """
    import anyio
    
    async def _reg() -> None:
        # High-level entrypoints (simplified API for LLMs) - always register
        register_entrypoints(mcp)
        
        if expose_all:
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
            # Core mode: only register essential tools
            # Register browser.navigate and browser.snapshot for automation
            data_browser.register_core_only(mcp)
            # Register tasks.list to help users discover available tools
            data_tasks.register_list_only(mcp)

    try:
        anyio.run(_reg)
    except Exception as e:  # pragma: no cover - defensive
        print(f"Error registering tools: {e}")
        raise e