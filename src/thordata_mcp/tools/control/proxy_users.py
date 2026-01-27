from __future__ import annotations

from typing import Any, Optional

from mcp.server.fastmcp import Context, FastMCP
from thordata import AsyncThordataClient

from ...config import settings
from ...utils import handle_mcp_errors, ok_response


def register(mcp: FastMCP) -> None:
    """Register proxy user management tools."""

    @mcp.tool(name="proxy_users.list")
    @handle_mcp_errors
    async def proxy_users_list(ctx: Optional[Context] = None) -> dict[str, Any]:
        """List proxy sub-users."""
        if ctx:
            await ctx.info("Listing proxy users.")
        async with AsyncThordataClient(
            scraper_token=settings.THORDATA_SCRAPER_TOKEN,
            public_token=settings.THORDATA_PUBLIC_TOKEN,
            public_key=settings.THORDATA_PUBLIC_KEY,
        ) as client:
            data = await client.list_proxy_users()
            return ok_response(tool="proxy_users.list", input={}, output=data)

    @mcp.tool(name="proxy_users.create")
    @handle_mcp_errors
    async def proxy_users_create(
        username: str,
        password: str,
        *,
        proxy_type: int = 2,
        traffic_limit: int = 0,
        status: bool = True,
        ctx: Optional[Context] = None,
    ) -> dict[str, Any]:
        """Create a proxy sub-user."""
        if ctx:
            await ctx.info(f"Creating proxy user: {username}")
        async with AsyncThordataClient(
            scraper_token=settings.THORDATA_SCRAPER_TOKEN,
            public_token=settings.THORDATA_PUBLIC_TOKEN,
            public_key=settings.THORDATA_PUBLIC_KEY,
        ) as client:
            data = await client.create_proxy_user(
                username=username,
                password=password,
                proxy_type=proxy_type,
                traffic_limit=traffic_limit,
                status=status,
            )
            return ok_response(
                tool="proxy_users.create",
                input={
                    "username": username,
                    "proxy_type": proxy_type,
                    "traffic_limit": traffic_limit,
                    "status": status,
                },
                output=data,
            )

    @mcp.tool(name="proxy_users.update")
    @handle_mcp_errors
    async def proxy_users_update(
        username: str,
        password: str,
        *,
        proxy_type: int = 2,
        traffic_limit: int | None = None,
        status: bool | None = None,
        new_username: str | None = None,
        ctx: Optional[Context] = None,
    ) -> dict[str, Any]:
        """Update a proxy sub-user."""
        if ctx:
            await ctx.info(f"Updating proxy user: {username}")
        async with AsyncThordataClient(
            scraper_token=settings.THORDATA_SCRAPER_TOKEN,
            public_token=settings.THORDATA_PUBLIC_TOKEN,
            public_key=settings.THORDATA_PUBLIC_KEY,
        ) as client:
            data = await client.update_proxy_user(
                username=username,
                password=password,
                traffic_limit=traffic_limit,
                status=status,
                proxy_type=proxy_type,
                new_username=new_username,
            )
            return ok_response(
                tool="proxy_users.update",
                input={
                    "username": username,
                    "proxy_type": proxy_type,
                    "traffic_limit": traffic_limit,
                    "status": status,
                    "new_username": new_username,
                },
                output=data,
            )

    @mcp.tool(name="proxy_users.delete")
    @handle_mcp_errors
    async def proxy_users_delete(username: str, ctx: Optional[Context] = None) -> dict[str, Any]:
        """Delete a proxy sub-user."""
        if ctx:
            await ctx.info(f"Deleting proxy user: {username}")
        async with AsyncThordataClient(
            scraper_token=settings.THORDATA_SCRAPER_TOKEN,
            public_token=settings.THORDATA_PUBLIC_TOKEN,
            public_key=settings.THORDATA_PUBLIC_KEY,
        ) as client:
            data = await client.delete_proxy_user(username=username)
            return ok_response(tool="proxy_users.delete", input={"username": username}, output=data)

