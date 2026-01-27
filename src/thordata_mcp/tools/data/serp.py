from __future__ import annotations

from typing import Any, Optional

from mcp.server.fastmcp import Context, FastMCP
from thordata import AsyncThordataClient
from thordata.types import Engine, SerpRequest

from ...config import settings
from ...utils import handle_mcp_errors, ok_response


def register(mcp: FastMCP) -> None:
    """Register SERP tools."""

    @mcp.tool(name="serp.search")
    @handle_mcp_errors
    async def serp_search(
        query: str,
        *,
        num: int = 10,
        output_format: str = "json",
        ctx: Optional[Context] = None,
    ) -> dict[str, Any]:
        """
        Run a Google SERP query and return the result in the specified format.

        Args:
            query: The search query.
            num: Number of results to return.
            output_format: "json" (default, rich), "json_light", or "html".
        """
        if ctx:
            await ctx.info(f"SERP search query={query!r} num={num} format={output_format}")

        async with AsyncThordataClient(scraper_token=settings.THORDATA_SCRAPER_TOKEN) as client:
            req = SerpRequest(query=query, engine=Engine.GOOGLE, num=num, output_format=output_format)
            data = await client.serp_search_advanced(req)
            return ok_response(
                tool="serp.search",
                input={"query": query, "num": num, "output_format": output_format},
                output=data,
            )
