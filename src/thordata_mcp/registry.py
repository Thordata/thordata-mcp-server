from mcp.server.fastmcp import FastMCP

# Compact product API for MCP clients (serp / unlocker / web_scraper / browser / smart_scrape)
from thordata_mcp.tools.product_compact import register as register_compact_tools


def register_all(mcp: FastMCP, expose_all: bool = False) -> None:
    """Register tools with the MCP server instance.

    Current version focuses on **four core scraping capabilities + smart routing**:
    - SERP SCRAPER (`serp`)
    - WEB UNLOCKER (`unlocker`)
    - WEB SCRAPER API (`web_scraper`)
    - BROWSER SCRAPER (`browser`)
    - SMART SCRAPE (`smart_scrape`)

    Earlier versions supported `proxy.*` / `account.*` control plane tools, but this streamlined version
    no longer exposes these management interfaces to keep the MCP tool surface clean and focused on scraping.

    Args:
        expose_all: Kept for backward compatibility with old CLI, but current implementation ignores this flag
                   and always registers the streamlined scraping tool set.
    """
    import anyio

    async def _reg() -> None:
        # Use compact surface uniformly to avoid exposing proxy/account management tools
        register_compact_tools(mcp)

    try:
        anyio.run(_reg)
    except Exception as e:  # pragma: no cover - defensive
        print(f"Error registering tools: {e}")
        raise e