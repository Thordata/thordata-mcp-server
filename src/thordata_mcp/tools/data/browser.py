from __future__ import annotations

import base64
from typing import Any, Optional

from mcp.server.fastmcp import Context, FastMCP, Image

from ...context import ServerContext
from ...utils import (
    handle_mcp_errors,
    ok_response,
    truncate_content,
)

PNG_TRUNCATE = 20000  # max chars for base64 png in output


def register_core_only(mcp: FastMCP) -> None:
    """Register only core browser automation tools (navigate and snapshot)."""
    
    @mcp.tool(name="browser.navigate", description="Navigate the browser to a URL")
    @handle_mcp_errors
    async def browser_navigate(url: str) -> dict[str, Any]:
        """Navigate to a specific URL in the current domain-scoped browser session.
        
        Requires THORDATA_BROWSER_USERNAME/THORDATA_BROWSER_PASSWORD (separate from residential proxy credentials).
        """
        # Check credentials before attempting to connect
        user = settings.THORDATA_BROWSER_USERNAME
        pwd = settings.THORDATA_BROWSER_PASSWORD
        if not user or not pwd:
            from ...utils import error_response
            return error_response(
                tool="browser.navigate",
                input={"url": url},
                error_type="config_error",
                code="E1001",
                message=(
                    "Missing browser credentials. Set THORDATA_BROWSER_USERNAME and THORDATA_BROWSER_PASSWORD. "
                    "Note: Browser credentials are separate from residential proxy credentials."
                ),
            )
        session = await ServerContext.get_browser_session()
        page = await session.get_page(url)
        if page.url != url:
            await page.goto(url, timeout=120_000)
        title = await page.title()
        return ok_response(
            tool="browser.navigate",
            input={"url": url},
            output={"url": page.url, "title": title},
        )

    @mcp.tool(
        name="browser.snapshot",
        description="Capture an ARIA-style snapshot with refs for interaction",
    )
    @handle_mcp_errors
    async def browser_snapshot(filtered: bool = True) -> dict[str, Any]:
        """
        Capture the current page state as a snapshot.

        Returns a text representation with [ref=X] IDs that can be used for
        clicking/typing via ref-based tools.
        
        Requires THORDATA_BROWSER_USERNAME/THORDATA_BROWSER_PASSWORD (separate from residential proxy credentials).
        """
        # Check credentials before attempting to connect
        user = settings.THORDATA_BROWSER_USERNAME
        pwd = settings.THORDATA_BROWSER_PASSWORD
        if not user or not pwd:
            from ...utils import error_response
            return error_response(
                tool="browser.snapshot",
                input={"filtered": filtered},
                error_type="config_error",
                code="E1001",
                message=(
                    "Missing browser credentials. Set THORDATA_BROWSER_USERNAME and THORDATA_BROWSER_PASSWORD. "
                    "Note: Browser credentials are separate from residential proxy credentials."
                ),
            )
        session = await ServerContext.get_browser_session()
        data = await session.capture_snapshot(filtered=filtered)
        
        aria_snapshot = truncate_content(str(data.get("aria_snapshot", "")))
        dom_snapshot = data.get("dom_snapshot")
        dom_snapshot = truncate_content(str(dom_snapshot)) if dom_snapshot else None

        output_lines = [
            f"Page: {data.get('url', '')}",
            f"Title: {data.get('title', '')}",
            "",
            "Interactive Elements:",
            aria_snapshot,
        ]
        if dom_snapshot:
            output_lines.extend(["", "DOM Interactive Elements:", dom_snapshot])

        return ok_response(
            tool="browser.snapshot",
            input={"filtered": filtered},
            output={
                "url": data.get("url"),
                "title": data.get("title"),
                "aria_snapshot": aria_snapshot,
                "dom_snapshot": dom_snapshot,
                "text": "\n".join(output_lines),
            },
        )


def register(mcp: FastMCP) -> None:
    """Register all browser-related tools (connection, automation, screenshots)."""

    @mcp.tool(name="browser.get_connection_url")
    @handle_mcp_errors
    async def browser_get_connection_url(ctx: Optional[Context] = None) -> dict[str, Any]:
        """Get a WebSocket URL for connecting to Thordata's Scraping Browser.
        
        Requires THORDATA_BROWSER_USERNAME/THORDATA_BROWSER_PASSWORD (separate from residential proxy credentials).
        """
        user = settings.THORDATA_BROWSER_USERNAME
        pwd = settings.THORDATA_BROWSER_PASSWORD

        if not user or not pwd:
            from ...utils import error_response
            return error_response(
                tool="browser.get_connection_url",
                input={},
                error_type="config_error",
                code="E1001",
                message=(
                    "Missing browser credentials. Set THORDATA_BROWSER_USERNAME and THORDATA_BROWSER_PASSWORD. "
                    "Note: Browser credentials are separate from residential proxy credentials."
                ),
            )

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

        client = await ServerContext.get_client()
        # Use new namespace API
        png_bytes = await client.universal.scrape_async(
                url=url,
                js_render=js_render,
                output_format="png",
            wait_time=int(wait_ms) if wait_ms is not None else None,
            device_scale=device_scale,
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

    # ---------------------------------------------------------------------
    # Browser Automation (Playwright-based, domain-scoped sessions)
    # ---------------------------------------------------------------------
    @mcp.tool(name="browser.navigate", description="Navigate the browser to a URL")
    @handle_mcp_errors
    async def browser_navigate(url: str) -> dict[str, Any]:
        """Navigate to a specific URL in the current domain-scoped browser session.
        
        Requires THORDATA_BROWSER_USERNAME/THORDATA_BROWSER_PASSWORD (separate from residential proxy credentials).
        """
        # Check credentials before attempting to connect
        user = settings.THORDATA_BROWSER_USERNAME
        pwd = settings.THORDATA_BROWSER_PASSWORD
        if not user or not pwd:
            from ...utils import error_response
            return error_response(
                tool="browser.navigate",
                input={"url": url},
                error_type="config_error",
                code="E1001",
                message=(
                    "Missing browser credentials. Set THORDATA_BROWSER_USERNAME and THORDATA_BROWSER_PASSWORD. "
                    "Note: Browser credentials are separate from residential proxy credentials."
                ),
            )
        session = await ServerContext.get_browser_session()
        page = await session.get_page(url)
        if page.url != url:
            await page.goto(url, timeout=120_000)
        title = await page.title()
        return ok_response(
            tool="browser.navigate",
            input={"url": url},
            output={"url": page.url, "title": title},
        )

    @mcp.tool(
        name="browser.snapshot",
        description="Capture an ARIA-style snapshot with refs for interaction",
    )
    @handle_mcp_errors
    async def browser_snapshot(filtered: bool = True) -> dict[str, Any]:
        """
        Capture the current page state as a snapshot.

        Returns a text representation with [ref=X] IDs that can be used for
        clicking/typing via ref-based tools.
        
        Requires THORDATA_BROWSER_USERNAME/THORDATA_BROWSER_PASSWORD (separate from residential proxy credentials).
        """
        # Check credentials before attempting to connect
        user = settings.THORDATA_BROWSER_USERNAME
        pwd = settings.THORDATA_BROWSER_PASSWORD
        if not user or not pwd:
            from ...utils import error_response
            return error_response(
                tool="browser.snapshot",
                input={"filtered": filtered},
                error_type="config_error",
                code="E1001",
                message=(
                    "Missing browser credentials. Set THORDATA_BROWSER_USERNAME and THORDATA_BROWSER_PASSWORD. "
                    "Note: Browser credentials are separate from residential proxy credentials."
                ),
            )
        session = await ServerContext.get_browser_session()
        data = await session.capture_snapshot(filtered=filtered)
        
        aria_snapshot = truncate_content(str(data.get("aria_snapshot", "")))
        dom_snapshot = data.get("dom_snapshot")
        dom_snapshot = truncate_content(str(dom_snapshot)) if dom_snapshot else None

        output_lines = [
            f"Page: {data.get('url', '')}",
            f"Title: {data.get('title', '')}",
            "",
            "Interactive Elements:",
            aria_snapshot,
        ]
        if dom_snapshot:
            output_lines.extend(["", "DOM Interactive Elements:", dom_snapshot])

        return ok_response(
            tool="browser.snapshot",
            input={"filtered": filtered},
            output={
                "url": data.get("url"),
                "title": data.get("title"),
                "aria_snapshot": aria_snapshot,
                "dom_snapshot": dom_snapshot,
                "text": "\n".join(output_lines),
            },
        )

    @mcp.tool(name="browser.click_ref", description="Click an element by its ref ID")
    @handle_mcp_errors
    async def browser_click_ref(
        ref: str,
        element: str = "element",
        wait_for_navigation_ms: Optional[int] = None,
    ) -> dict[str, Any]:
        """Click an element using the [ref=X] ID from the snapshot.
        
        Args:
            ref: The ref ID from snapshot (e.g., ref-w545663wqs)
            element: Description of the element for error messages
            wait_for_navigation_ms: Optional wait time in ms to detect navigation after click
        """
        session = await ServerContext.get_browser_session()
        page = await session.get_page()
        
        url_before = page.url
        try:
            locator = await session.ref_locator(ref, element)
            await locator.click(timeout=5_000)
            
            # Check for navigation if requested
            did_navigate = False
            url_after = url_before
            if wait_for_navigation_ms and wait_for_navigation_ms > 0:
                import asyncio
                await asyncio.sleep(wait_for_navigation_ms / 1000)
                url_after = page.url
                did_navigate = url_after != url_before
            
            return ok_response(
                tool="browser.click_ref",
                input={"ref": ref, "element": element, "wait_for_navigation_ms": wait_for_navigation_ms},
                output={
                    "message": f"Successfully clicked {element}",
                    "ref": ref,
                    "url_before": url_before,
                    "url_after": url_after,
                    "did_navigate": did_navigate,
                },
            )
        except Exception as e:
            # Enhanced error with diagnostics + self-heal for common browser lifecycle issues
            from ...utils import error_response

            err_s = str(e).lower()
            did_reset = False
            if any(k in err_s for k in [
                "target closed",
                "page closed",
                "browser has been closed",
                "execution context was destroyed",
                "has been disposed",
            ]):
                try:
                    session.reset_page()
                    did_reset = True
                except Exception:
                    did_reset = False

            # Try to get console and network diagnostics from session cache
            try:
                console_tail = session.get_console_tail(n=10)
            except Exception:
                console_tail = []
            try:
                network_tail = session.get_network_tail(n=20)
            except Exception:
                network_tail = []

            hint = "Try taking a new snapshot to get fresh refs, or check if the element is still visible"
            if did_reset:
                hint = "Browser page was closed/reset. Take a new snapshot to get fresh refs, then retry the click."

            return error_response(
                tool="browser.click_ref",
                input={"ref": ref, "element": element, "wait_for_navigation_ms": wait_for_navigation_ms},
                error_type="browser_interaction_error",
                code="E5001",
                message=f"Failed to click element: {str(e)}",
                details={
                    "ref": ref,
                    "element": element,
                    "url_before": url_before,
                    "url_after": page.url,
                    "did_reset": did_reset,
                    "hint": hint,
                    "console_tail": console_tail,
                    "network_tail": network_tail,
                },
            )

    @mcp.tool(
        name="browser.type_ref",
        description="Type text into an element by its ref ID",
    )
    @handle_mcp_errors
    async def browser_type_ref(
        ref: str,
        text: str,
        submit: bool = False,
        element: str = "element",
    ) -> dict[str, Any]:
        """Type text into an element using the [ref=X] ID."""
        session = await ServerContext.get_browser_session()
        page = await session.get_page()
        url_before = page.url
        
        try:
            locator = await session.ref_locator(ref, element)
            await locator.fill(text)
            if submit:
                await locator.press("Enter")
            
            return ok_response(
                tool="browser.type_ref",
                input={"ref": ref, "text": text, "submit": submit, "element": element},
                output={
                    "message": "Typed into element" + (" and submitted" if submit else ""),
                    "ref": ref,
                    "url_before": url_before,
                    "url_after": page.url,
                },
            )
        except Exception as e:
            from ...utils import error_response
            return error_response(
                tool="browser.type_ref",
                input={"ref": ref, "text": text, "submit": submit, "element": element},
                error_type="browser_interaction_error",
                code="E5002",
                message=f"Failed to type into element: {str(e)}",
                details={
                    "ref": ref,
                    "element": element,
                    "url_before": url_before,
                    "url_after": page.url,
                    "hint": "Try taking a new snapshot to get fresh refs, or check if the element is still visible and editable",
                },
            )

    @mcp.tool(name="browser.screenshot_page", description="Take a screenshot of the current browser page")
    @handle_mcp_errors
    async def browser_screenshot_page(ctx: Context, full_page: bool = False) -> Any:
        """Take a screenshot of the current browser page (Playwright-based)."""
        session = await ServerContext.get_browser_session()
        page = await session.get_page()
        image_bytes = await page.screenshot(full_page=full_page)
        
        # Prefer FastMCP Image content if available
        try:
            return Image(data=image_bytes, format="png")
        except Exception:
            size = len(image_bytes)
            return ok_response(
                tool="browser.screenshot_page",
                input={"full_page": full_page},
                output={"info": f"Screenshot taken (size: {size} bytes)."},
            )

    @mcp.tool(name="browser.get_html", description="Get the HTML content of the current browser page")
    @handle_mcp_errors
    async def browser_get_html(full_page: bool = False) -> dict[str, Any]:
        """Get the HTML content of the current browser page."""
        session = await ServerContext.get_browser_session()
        page = await session.get_page()
        if full_page:
            content = await page.content()
        else:
            try:
                content = await page.evaluate("document.body.innerHTML")
            except Exception:
                content = await page.content()
        html = truncate_content(str(content))
        return ok_response(
            tool="browser.get_html",
            input={"full_page": full_page},
            output={"html": html},
        )

    @mcp.tool(name="browser.scroll", description="Scroll to the bottom of the current page")
    @handle_mcp_errors
    async def browser_scroll() -> dict[str, Any]:
        """Scroll to the bottom of the page."""
        session = await ServerContext.get_browser_session()
        page = await session.get_page()
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        return ok_response(
            tool="browser.scroll",
            input={},
            output={"message": "Scrolled to bottom"},
        )

    @mcp.tool(name="browser.go_back", description="Navigate back in browser history")
    @handle_mcp_errors
    async def browser_go_back() -> dict[str, Any]:
        """Go back in browser history."""
        session = await ServerContext.get_browser_session()
        page = await session.get_page()
        await page.go_back()
        return ok_response(
            tool="browser.go_back",
            input={},
            output={"url": page.url},
            )
