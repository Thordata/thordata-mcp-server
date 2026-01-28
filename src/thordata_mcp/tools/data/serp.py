from __future__ import annotations

import asyncio
from typing import Any, Optional

from mcp.server.fastmcp import Context, FastMCP
from thordata import AsyncThordataClient
from thordata.types import Engine, SerpRequest

from ...config import settings
from ...utils import handle_mcp_errors, ok_response, safe_ctx_info


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
        """Run a SERP query and return results.
        
        Args:
            query: Search query string
            num: Number of results (default: 10)
            output_format: Output format - "json" (structured JSON) or "html" (raw HTML)
                           Note: SDK supports "json", "html", or "both" (returns both formats)
        """
        await safe_ctx_info(ctx, f"SERP search query={query!r} num={num} format={output_format}")

        async with AsyncThordataClient(scraper_token=settings.THORDATA_SCRAPER_TOKEN) as client:
            req = SerpRequest(query=query, engine=Engine.GOOGLE, num=num, output_format=output_format)
            data = await client.serp_search_advanced(req)
            return ok_response(
                tool="serp.search",
                input={"query": query, "num": num, "output_format": output_format},
                output=data,
            )

    @mcp.tool(name="serp.batch_search")
    @handle_mcp_errors
    async def serp_batch_search(
        requests: list[dict[str, Any]],
        *,
        concurrency: int = 5,
        output_format: str = "json",
        ctx: Optional[Context] = None,
    ) -> dict[str, Any]:
        """Run multiple SERP queries concurrently."""
        if concurrency < 1:
            concurrency = 1
        if concurrency > 20:
            concurrency = 20

        sem = asyncio.Semaphore(concurrency)

        async with AsyncThordataClient(scraper_token=settings.THORDATA_SCRAPER_TOKEN) as client:

            async def _one(i: int, r: dict[str, Any]) -> dict[str, Any]:
                query = str(r.get("query", ""))
                if not query:
                    return {
                        "index": i,
                        "ok": False,
                        "error": {"type": "validation_error", "message": "Missing query"},
                    }
                num = int(r.get("num", 10))
                engine = r.get("engine", Engine.GOOGLE)
                async with sem:
                    req = SerpRequest(
                        query=query,
                        engine=engine,
                        num=num,
                        output_format=output_format,
                    )
                    data = await client.serp_search_advanced(req)
                    return {"index": i, "ok": True, "query": query, "output": data}

            await safe_ctx_info(ctx, f"SERP batch_search count={len(requests)} concurrency={concurrency}")

            results = await asyncio.gather(*[_one(i, r) for i, r in enumerate(requests)])
            return ok_response(
                tool="serp.batch_search",
                input={"count": len(requests), "concurrency": concurrency, "output_format": output_format},
                output={"results": results},
            )
