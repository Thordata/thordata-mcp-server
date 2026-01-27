from __future__ import annotations

from typing import Any, Optional

from mcp.server.fastmcp import Context, FastMCP
from thordata import AsyncThordataClient

from ...config import settings
from ...utils import handle_mcp_errors, html_to_markdown_clean, ok_response, truncate_content


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
        """Fetch a URL using Universal Scrape.

        Args:
            url: Target URL.
            output_format: "html" (default) or "png".
            js_render: Enable JS rendering.
            country: Optional country code.
            block_resources: Optional resource blocking mode.
            wait_ms: Optional wait time in milliseconds.
            wait_for: Optional CSS selector to wait for.
            extra_params: Additional API parameters.
        """
        if ctx:
            await ctx.info(
                f"Universal fetch url={url!r} output_format={output_format} js_render={js_render}"
            )

        kwargs = extra_params or {}
        wait_seconds = None
        if wait_ms is not None:
            wait_seconds = int(wait_ms / 1000)

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
                size = len(data) if isinstance(data, (bytes, bytearray)) else None
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
                    output={"png_bytes": data, "size": size},
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
        if ctx:
            await ctx.info(
                f"Universal markdown url={url!r} js_render={js_render} wait_ms={wait_ms}"
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
