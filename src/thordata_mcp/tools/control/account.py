from __future__ import annotations

from typing import Any, Optional

from mcp.server.fastmcp import Context, FastMCP
from thordata import AsyncThordataClient

from ...config import settings
from ...utils import handle_mcp_errors, ok_response


def register(mcp: FastMCP) -> None:
    """Register account & usage tools."""

    @mcp.tool(name="account.get_usage_statistics")
    @handle_mcp_errors
    async def account_get_usage_statistics(
        from_date: str,
        to_date: str,
        *,
        ctx: Optional[Context] = None,
    ) -> dict[str, Any]:
        """
        Get account usage statistics for a date range.

        Args:
            from_date: "YYYY-MM-DD"
            to_date: "YYYY-MM-DD"
        """
        if ctx:
            await ctx.info(f"Fetching usage statistics {from_date} -> {to_date}")

        async with AsyncThordataClient(
            scraper_token=settings.THORDATA_SCRAPER_TOKEN,
            public_token=settings.THORDATA_PUBLIC_TOKEN,
            public_key=settings.THORDATA_PUBLIC_KEY,
        ) as client:
            data = await client.get_usage_statistics(from_date=from_date, to_date=to_date)
            return ok_response(
                tool="account.get_usage_statistics",
                input={"from_date": from_date, "to_date": to_date},
                output=data,
            )

    @mcp.tool(name="account.traffic_balance")
    @handle_mcp_errors
    async def account_traffic_balance(ctx: Optional[Context] = None) -> dict[str, Any]:
        """Get remaining traffic balance."""
        if ctx:
            await ctx.info("Fetching traffic balance.")
        async with AsyncThordataClient(
            scraper_token=settings.THORDATA_SCRAPER_TOKEN,
            public_token=settings.THORDATA_PUBLIC_TOKEN,
            public_key=settings.THORDATA_PUBLIC_KEY,
        ) as client:
            balance = await client.get_traffic_balance()
            return ok_response(
                tool="account.traffic_balance",
                input={},
                output={"traffic_balance": balance},
            )

    @mcp.tool(name="account.wallet_balance")
    @handle_mcp_errors
    async def account_wallet_balance(ctx: Optional[Context] = None) -> dict[str, Any]:
        """Get remaining wallet balance."""
        if ctx:
            await ctx.info("Fetching wallet balance.")
        async with AsyncThordataClient(
            scraper_token=settings.THORDATA_SCRAPER_TOKEN,
            public_token=settings.THORDATA_PUBLIC_TOKEN,
            public_key=settings.THORDATA_PUBLIC_KEY,
        ) as client:
            balance = await client.get_wallet_balance()
            return ok_response(
                tool="account.wallet_balance",
                input={},
                output={"wallet_balance": balance},
            )
