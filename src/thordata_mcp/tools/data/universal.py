from __future__ import annotations

import asyncio
from typing import Any, Optional

from mcp.server.fastmcp import Context, FastMCP
from thordata import AsyncThordataClient

from ...config import settings
from ...utils import handle_mcp_errors, html_to_markdown_clean, ok_response, safe_ctx_info, truncate_content


def register(mcp: FastMCP) -> None:
    """Register Universal Scrape (Web Unlocker) tools."""

    @mcp.tool(name="universal.fetch")
    @handle_mcp_errors
    async def universal_fetch(
        url: str,
        *,
        output_format: str = "html",
        js_render: bool = False,
        country: str | None = None,
        block_resources: str | None = None,
        wait_ms: int | None = None,
        wait_for: str | None = None,
        extra_params: dict[str, Any] | None = None,
        ctx: Optional[Context] = None,
    ) -> dict[str, Any]:
        """Fetch a URL using Universal Scrape (Web Unlocker).
        
        Args:
            url: Target URL to scrape
            output_format: "html" (HTML content) or "png" (screenshot as PNG bytes)
            js_render: Whether to enable JavaScript rendering (default: False)
            country: Country code for geolocation (optional)
            block_resources: Comma-separated resource types to block (optional)
            wait_ms: Wait time in milliseconds before capture (optional)
            wait_for: CSS selector or text to wait for (optional)
        """
        await safe_ctx_info(
            ctx, f"Universal fetch url={url!r} output_format={output_format} js_render={js_render}"
        )

        kwargs = extra_params or {}
        wait_seconds = int(wait_ms / 1000) if wait_ms is not None else None

        async with AsyncThordataClient(scraper_token=settings.THORDATA_SCRAPER_TOKEN) as client:
            data = await client.universal_scrape(
                url=url,
                js_render=js_render,
                output_format=output_format,
                country=country,
                block_resources=block_resources,
                wait=wait_seconds,
                wait_for=wait_for,
                **kwargs,
            )

            if output_format.lower() == "png":
                # Convert PNG bytes to base64 string for JSON serialization
                import base64
                if isinstance(data, (bytes, bytearray)):
                    png_base64 = base64.b64encode(data).decode("utf-8")
                    size = len(data)
                else:
                    png_base64 = str(data)
                    size = None
                return ok_response(
                    tool="universal.fetch",
                    input={
                        "url": url,
                        "output_format": output_format,
                        "js_render": js_render,
                        "country": country,
                        "block_resources": block_resources,
                        "wait_ms": wait_ms,
                        "wait_for": wait_for,
                        "extra_params": extra_params,
                    },
                    output={"png_base64": png_base64, "size": size, "format": "png"},
                )

            html = str(data) if not isinstance(data, str) else data
            return ok_response(
                tool="universal.fetch",
                input={
                    "url": url,
                    "output_format": output_format,
                    "js_render": js_render,
                    "country": country,
                    "block_resources": block_resources,
                    "wait_ms": wait_ms,
                    "wait_for": wait_for,
                    "extra_params": extra_params,
                },
                output={"html": html},
            )

    @mcp.tool(name="universal.fetch_markdown")
    @handle_mcp_errors
    async def universal_fetch_markdown(
        url: str,
        *,
        js_render: bool = True,
        wait_ms: int = 2000,
        max_chars: int = 20000,
        country: str | None = None,
        block_resources: str | None = None,
        wait_for: str | None = None,
        extra_params: dict[str, Any] | None = None,
        ctx: Optional[Context] = None,
    ) -> dict[str, Any]:
        """Fetch a URL via Universal Scrape and return cleaned Markdown text."""
        await safe_ctx_info(
            ctx, f"Universal markdown url={url!r} js_render={js_render} wait_ms={wait_ms}"
        )

        kwargs = extra_params or {}
        wait_seconds = int(wait_ms / 1000) if wait_ms is not None else None

        async with AsyncThordataClient(scraper_token=settings.THORDATA_SCRAPER_TOKEN) as client:
            html = await client.universal_scrape(
                url=url,
                js_render=js_render,
                output_format="html",
                country=country,
                block_resources=block_resources,
                wait=wait_seconds,
                wait_for=wait_for,
                **kwargs,
            )
            html_str = str(html) if not isinstance(html, str) else html
            markdown = html_to_markdown_clean(html_str)
            markdown = truncate_content(markdown, max_length=max_chars)
            return ok_response(
                tool="universal.fetch_markdown",
                input={
                    "url": url,
                    "js_render": js_render,
                    "wait_ms": wait_ms,
                    "max_chars": max_chars,
                    "country": country,
                    "block_resources": block_resources,
                    "wait_for": wait_for,
                    "extra_params": extra_params,
                },
                output={"markdown": markdown},
            )

    @mcp.tool(name="universal.batch_fetch")
    @handle_mcp_errors
    async def universal_batch_fetch(
        requests: list[dict[str, Any]],
        *,
        concurrency: int = 5,
        ctx: Optional[Context] = None,
    ) -> dict[str, Any]:
        """Fetch multiple URLs concurrently via Universal Scrape.

        Each request item supports the same keys as `universal.fetch`.
        """
        if concurrency < 1:
            concurrency = 1
        if concurrency > 20:
            concurrency = 20

        sem = asyncio.Semaphore(concurrency)

        async with AsyncThordataClient(scraper_token=settings.THORDATA_SCRAPER_TOKEN) as client:

            async def _one(i: int, r: dict[str, Any]) -> dict[str, Any]:
                url = str(r.get("url", ""))
                if not url:
                    return {"index": i, "ok": False, "error": {"type": "validation_error", "message": "Missing url"}}

                output_format = str(r.get("output_format", "html"))
                js_render = bool(r.get("js_render", False))
                country = r.get("country")
                block_resources = r.get("block_resources")
                wait_ms = r.get("wait_ms")
                wait_for = r.get("wait_for")
                extra_params = r.get("extra_params") or {}
                if not isinstance(extra_params, dict):
                    extra_params = {}

                wait_seconds = int(wait_ms / 1000) if isinstance(wait_ms, (int, float)) else None

                async with sem:
                    data = await client.universal_scrape(
                        url=url,
                        js_render=js_render,
                        output_format=output_format,
                        country=country,
                        block_resources=block_resources,
                        wait=wait_seconds,
                        wait_for=wait_for,
                        **extra_params,
                    )

                if output_format.lower() == "png":
                    # Convert PNG bytes to base64 string for JSON serialization
                    import base64
                    if isinstance(data, (bytes, bytearray)):
                        png_base64 = base64.b64encode(data).decode("utf-8")
                        size = len(data)
                    else:
                        png_base64 = str(data)
                        size = None
                    return {"index": i, "ok": True, "url": url, "output": {"png_base64": png_base64, "size": size, "format": "png"}}

                html = str(data) if not isinstance(data, str) else data
                return {"index": i, "ok": True, "url": url, "output": {"html": html}}

            await safe_ctx_info(ctx, f"Universal batch_fetch count={len(requests)} concurrency={concurrency}")

            results = await asyncio.gather(*[_one(i, r) for i, r in enumerate(requests)])
            return ok_response(
                tool="universal.batch_fetch",
                input={"count": len(requests), "concurrency": concurrency},
                output={"results": results},
            )
