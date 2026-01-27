from __future__ import annotations

import base64
from typing import Any, Optional

from mcp.server.fastmcp import Context, FastMCP
from thordata import AsyncThordataClient

from ...config import settings
from ...utils import (
    handle_mcp_errors,
    html_to_markdown_clean,
    ok_response,
    truncate_content,
)

PNG_TRUNCATE = 20000  # max chars for base64 png in output


def register(mcp: FastMCP) -> None:
    """Register Scraping Browser connection tools."""

    @mcp.tool(name="browser.get_connection_url")
    @handle_mcp_errors
    async def browser_get_connection_url(ctx: Optional[Context] = None) -> dict[str, Any]:
        """Get a WebSocket URL for connecting to Thordata's Scraping Browser."""
        user = settings.THORDATA_BROWSER_USERNAME or settings.THORDATA_RESIDENTIAL_USERNAME
        pwd = settings.THORDATA_BROWSER_PASSWORD or settings.THORDATA_RESIDENTIAL_PASSWORD

        if not user or not pwd:
            return {
                "ok": False,
                "tool": "browser.get_connection_url",
                "input": {},
                "error": {
                    "type": "config_error",
                    "message": (
                        "Missing browser/proxy credentials. Set THORDATA_BROWSER_USERNAME/THORDATA_BROWSER_PASSWORD "
                        "(or THORDATA_RESIDENTIAL_USERNAME/THORDATA_RESIDENTIAL_PASSWORD)."
                    ),
                },
            }

        async with AsyncThordataClient(scraper_token=settings.THORDATA_SCRAPER_TOKEN) as client:
            url = client.get_browser_connection_url(username=user, password=pwd)
            if ctx:
                await ctx.info("Generated scraping browser connection URL.")
            return ok_response(
                tool="browser.get_connection_url",
                input={},
                output={
                    "ws_url": url,
                    "playwright_python": f"browser = await playwright.chromium.connect_over_cdp('{url}')",
                },
            )

    # ---------------------------------------------------------------------
    # New helper: lightweight screenshot via Universal API (png output)
    # ---------------------------------------------------------------------
    @mcp.tool(name="browser.screenshot")
    @handle_mcp_errors
    async def browser_screenshot(
        url: str,
        *,
        js_render: bool = True,
        wait_ms: int = 2000,
        device_scale: int = 1,
        ctx: Optional[Context] = None,
    ) -> dict[str, Any]:
        """Capture a full-page screenshot of a URL via Universal API.

        Args:
            url: Target page URL.
            js_render: Whether to enable JavaScript rendering.
            wait_ms: Wait time before capture (ms).
            device_scale: DPR / device pixel ratio (1-3 typically).
        """
        if ctx:
            await ctx.info(f"Screenshot url={url!r} js_render={js_render} wait_ms={wait_ms}")

        async with AsyncThordataClient(scraper_token=settings.THORDATA_SCRAPER_TOKEN) as client:
            png_bytes = await client.universal_scrape(
                url=url,
                js_render=js_render,
                output_format="png",
                wait=int(wait_ms / 1000) if wait_ms is not None else None,
                extra_params={"device_scale": device_scale},
            )
            # Ensure bytes, then base64
            if isinstance(png_bytes, str):
                png_bytes = png_bytes.encode()
            b64 = base64.b64encode(png_bytes).decode()
            b64_trunc = truncate_content(b64, PNG_TRUNCATE)
            return ok_response(
                tool="browser.screenshot",
                input={
                    "url": url,
                    "js_render": js_render,
                    "wait_ms": wait_ms,
                    "device_scale": device_scale,
                },
                output={
                    "png_base64": b64_trunc,
                    "truncated": len(b64) > len(b64_trunc),
                },
            )
