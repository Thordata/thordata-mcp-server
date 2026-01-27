from __future__ import annotations

from typing import Any, Optional

from mcp.server.fastmcp import Context, FastMCP
from thordata import AsyncThordataClient

from ...config import settings
from ...utils import handle_mcp_errors, ok_response


def register(mcp: FastMCP) -> None:
    """Register Unlimited Residential proxy management tools."""

    @mcp.tool(name="unlimited.list_servers")
    @handle_mcp_errors
    async def unlimited_list_servers(ctx: Optional[Context] = None) -> dict[str, Any]:
        """List unlimited proxy servers."""
        if ctx:
            await ctx.info("Listing unlimited servers.")
        async with AsyncThordataClient(
            scraper_token=settings.THORDATA_SCRAPER_TOKEN,
            public_token=settings.THORDATA_PUBLIC_TOKEN,
            public_key=settings.THORDATA_PUBLIC_KEY,
        ) as client:
            data = await client.unlimited.list_servers()
            return ok_response(tool="unlimited.list_servers", input={}, output=data)

    @mcp.tool(name="unlimited.get_server_monitor")
    @handle_mcp_errors
    async def unlimited_get_server_monitor(
        ins_id: str,
        region: str,
        start_time: int,
        end_time: int,
        *,
        period: int = 300,
        ctx: Optional[Context] = None,
    ) -> dict[str, Any]:
        """Get server monitor metrics."""
        if ctx:
            await ctx.info(f"Getting server monitor ins_id={ins_id} region={region}")
        async with AsyncThordataClient(
            scraper_token=settings.THORDATA_SCRAPER_TOKEN,
            public_token=settings.THORDATA_PUBLIC_TOKEN,
            public_key=settings.THORDATA_PUBLIC_KEY,
        ) as client:
            data = await client.unlimited.get_server_monitor(
                ins_id=ins_id,
                region=region,
                start_time=start_time,
                end_time=end_time,
                period=period,
            )
            return ok_response(
                tool="unlimited.get_server_monitor",
                input={
                    "ins_id": ins_id,
                    "region": region,
                    "start_time": start_time,
                    "end_time": end_time,
                    "period": period,
                },
                output=data,
            )

    @mcp.tool(name="unlimited.bind_user")
    @handle_mcp_errors
    async def unlimited_bind_user(ip: str, username: str, ctx: Optional[Context] = None) -> dict[str, Any]:
        """Bind a user to an unlimited server."""
        if ctx:
            await ctx.info(f"Binding user {username} to unlimited ip={ip}")
        async with AsyncThordataClient(
            scraper_token=settings.THORDATA_SCRAPER_TOKEN,
            public_token=settings.THORDATA_PUBLIC_TOKEN,
            public_key=settings.THORDATA_PUBLIC_KEY,
        ) as client:
            data = await client.unlimited.bind_user(ip=ip, username=username)
            return ok_response(
                tool="unlimited.bind_user",
                input={"ip": ip, "username": username},
                output=data,
            )

    @mcp.tool(name="unlimited.unbind_user")
    @handle_mcp_errors
    async def unlimited_unbind_user(ip: str, username: str, ctx: Optional[Context] = None) -> dict[str, Any]:
        """Unbind a user from an unlimited server."""
        if ctx:
            await ctx.info(f"Unbinding user {username} from unlimited ip={ip}")
        async with AsyncThordataClient(
            scraper_token=settings.THORDATA_SCRAPER_TOKEN,
            public_token=settings.THORDATA_PUBLIC_TOKEN,
            public_key=settings.THORDATA_PUBLIC_KEY,
        ) as client:
            data = await client.unlimited.unbind_user(ip=ip, username=username)
            return ok_response(
                tool="unlimited.unbind_user",
                input={"ip": ip, "username": username},
                output=data,
            )

