"""
Lightweight sanity checks for the productized MCP tool surface.

This script does NOT run the MCP server. It only validates that the tools can
be registered and lists their names.
"""

import asyncio

from mcp.server.fastmcp import FastMCP

from thordata_mcp.context import ServerContext
from thordata_mcp.tools.product_compact import register as register_product_tools


async def main() -> None:
    try:
        m = FastMCP("Thordata")
        register_product_tools(m)
        tools = await m.list_tools()
        names = [getattr(t, "name", None) if not isinstance(t, dict) else t.get("name") for t in tools]
        print("Registered core tools:")
        for n in names:
            print("-", n)
    finally:
        await ServerContext.cleanup()


if __name__ == "__main__":
    asyncio.run(main())

