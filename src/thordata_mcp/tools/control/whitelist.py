from __future__ import annotations

from typing import Any, Optional

from mcp.server.fastmcp import Context, FastMCP
from thordata import AsyncThordataClient

from ...config import settings
from ...utils import handle_mcp_errors, ok_response


def register(mcp: FastMCP) -> None:
    """Register whitelist IP management tools."""

    @mcp.tool(name="whitelist.list_ips")
    @handle_mcp_errors
    async def whitelist_list_ips(ctx: Optional[Context] = None) -> dict[str, Any]:
        """List whitelisted IPs."""
        if ctx:
            await ctx.info("Listing whitelisted IPs.")
        async with AsyncThordataClient(
            scraper_token=settings.THORDATA_SCRAPER_TOKEN,
            public_token=settings.THORDATA_PUBLIC_TOKEN,
            public_key=settings.THORDATA_PUBLIC_KEY,
        ) as client:
            data = await client.list_whitelist_ips()
            return ok_response(tool="whitelist.list_ips", input={}, output=data)

    @mcp.tool(name="whitelist.add_ip")
    @handle_mcp_errors
    async def whitelist_add_ip(ip: str, ctx: Optional[Context] = None) -> dict[str, Any]:
        """Add an IP to whitelist."""
        if ctx:
            await ctx.info(f"Adding whitelist IP: {ip}")
        async with AsyncThordataClient(
            scraper_token=settings.THORDATA_SCRAPER_TOKEN,
            public_token=settings.THORDATA_PUBLIC_TOKEN,
            public_key=settings.THORDATA_PUBLIC_KEY,
        ) as client:
            data = await client.add_whitelist_ip(ip=ip)
            return ok_response(tool="whitelist.add_ip", input={"ip": ip}, output=data)

    @mcp.tool(name="whitelist.delete_ip")
    @handle_mcp_errors
    async def whitelist_delete_ip(ip: str, ctx: Optional[Context] = None) -> dict[str, Any]:
        """Delete an IP from whitelist."""
        if ctx:
            await ctx.info(f"Deleting whitelist IP: {ip}")
        async with AsyncThordataClient(
            scraper_token=settings.THORDATA_SCRAPER_TOKEN,
            public_token=settings.THORDATA_PUBLIC_TOKEN,
            public_key=settings.THORDATA_PUBLIC_KEY,
        ) as client:
            data = await client.delete_whitelist_ip(ip=ip)
            return ok_response(tool="whitelist.delete_ip", input={"ip": ip}, output=data)

