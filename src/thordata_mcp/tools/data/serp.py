from __future__ import annotations

import asyncio
from typing import Any, Optional

from mcp.server.fastmcp import Context, FastMCP
from thordata import Engine, SerpRequest
from thordata.enums import OutputFormat

from ...context import ServerContext
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
        engine: str = "google",
        ai_overview: bool = False,
        start: int = 0,
        country: str | None = None,
        language: str | None = None,
        device: str | None = None,
        render_js: bool | None = None,
        no_cache: bool | None = None,
        search_type: str | None = None,
        google_domain: str | None = None,
        location: str | None = None,
        ctx: Optional[Context] = None,
    ) -> dict[str, Any]:
        """Run a SERP query and return results.
        
        Args:
            query: Search query string
            num: Number of results (default: 10)
            output_format: Output format - "json" (structured JSON), "html" (raw HTML), 
                           "light_json" (minimal JSON), or "both" (returns both formats)
            engine: Search engine (default: "google"). Supports google, bing, yandex, etc.
            ai_overview: Enable AI Overview for Google search (default: False, only for google engine)
            start: Starting position for results (default: 0)
            country: Country code for geolocation (e.g., "us", "jp")
            language: Language code (e.g., "en", "ja")
            device: Device type ("desktop", "mobile", "tablet")
            render_js: Enable JavaScript rendering
            no_cache: Disable cache
            search_type: Search type filter ("images", "news", "videos", "shopping")
            google_domain: Google domain (e.g., "google.com", "google.co.jp")
            location: Location string for local search
        """
        await safe_ctx_info(ctx, f"SERP search query={query!r} num={num} format={output_format} engine={engine}")

        client = await ServerContext.get_client()
        
        # Normalize engine enum
        engine_enum = Engine.GOOGLE
        if engine.lower() == "bing":
            engine_enum = Engine.BING
        elif engine.lower() == "yandex":
            engine_enum = Engine.YANDEX
        elif engine.lower() != "google":
            # Try to match by name (case-insensitive)
            try:
                engine_enum = Engine[engine.upper()]
            except (KeyError, AttributeError):
                engine_enum = Engine.GOOGLE
        
        # Validate ai_overview (only for Google)
        if ai_overview and engine_enum != Engine.GOOGLE:
            return {
                "ok": False,
                "error": {
                    "type": "validation_error",
                    "message": "ai_overview is only supported for Google engine",
                },
            }
        
        req = SerpRequest(
            query=query, 
            engine=engine_enum, 
            num=num,
            start=start,
            output_format=output_format,
            country=country,
            language=language,
            device=device,
            render_js=render_js,
            no_cache=no_cache,
            search_type=search_type,
            google_domain=google_domain,
            location=location,
            ai_overview=ai_overview if engine_enum == Engine.GOOGLE else None,
        )
        
        # Use client's serp_search_advanced method
            data = await client.serp_search_advanced(req)
        
            return ok_response(
                tool="serp.search",
            input={
                "query": query,
                "num": num,
                "start": start,
                "output_format": output_format,
                "engine": engine,
                "ai_overview": ai_overview,
                "country": country,
                "language": language,
                "device": device,
                "render_js": render_js,
                "no_cache": no_cache,
                "search_type": search_type,
                "google_domain": google_domain,
                "location": location,
            },
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
        client = await ServerContext.get_client()

            async def _one(i: int, r: dict[str, Any]) -> dict[str, Any]:
                query = str(r.get("query", ""))
                if not query:
                    return {
                        "index": i,
                        "ok": False,
                        "error": {"type": "validation_error", "message": "Missing query"},
                    }
                num = int(r.get("num", 10))
            engine_str = str(r.get("engine", "google")).lower()
            ai_overview = bool(r.get("ai_overview", False))
            
            # Normalize engine enum
            engine_enum = Engine.GOOGLE
            if engine_str == "bing":
                engine_enum = Engine.BING
            elif engine_str == "yandex":
                engine_enum = Engine.YANDEX
            elif engine_str != "google":
                try:
                    engine_enum = Engine[engine_str.upper()]
                except (KeyError, AttributeError):
                    engine_enum = Engine.GOOGLE
            
            # Validate ai_overview
            if ai_overview and engine_enum != Engine.GOOGLE:
                return {
                    "index": i,
                    "ok": False,
                    "error": {"type": "validation_error", "message": "ai_overview only supported for Google"},
                }
            
                async with sem:
                    req = SerpRequest(
                        query=query,
                    engine=engine_enum,
                        num=num,
                        output_format=output_format,
                    ai_overview=ai_overview if engine_enum == Engine.GOOGLE else None,
                    )
                # Use client's serp_search_advanced method
                    data = await client.serp_search_advanced(req)
                    return {"index": i, "ok": True, "query": query, "output": data}

            await safe_ctx_info(ctx, f"SERP batch_search count={len(requests)} concurrency={concurrency}")

            results = await asyncio.gather(*[_one(i, r) for i, r in enumerate(requests)])
            return ok_response(
                tool="serp.batch_search",
                input={"count": len(requests), "concurrency": concurrency, "output_format": output_format},
                output={"results": results},
            )
