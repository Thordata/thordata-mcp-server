"""Browser session management for Thordata Scraping Browser.

This module provides a high-level wrapper around Playwright connected to
Thordata's Scraping Browser (via `AsyncThordataClient.get_browser_connection_url`).

Design goals:
- Domain-scoped browser sessions (one browser/page per domain).
- Simple ARIA-like snapshot text for interactive elements (with refs).
- DOM snapshot used to build stable `data-fastmcp-ref` refs for ref-based tools.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Set
from urllib.parse import urlparse

from playwright.async_api import Browser, Page, Playwright, async_playwright

import time

from thordata.async_client import AsyncThordataClient

from .aria_snapshot import AriaSnapshotFilter
from .config import get_settings

logger = logging.getLogger(__name__)


class BrowserSession:
    """Domain-aware browser session wrapper."""

    def __init__(self, client: AsyncThordataClient) -> None:
        self._client = client
        self._playwright: Optional[Playwright] = None
        self._browsers: Dict[str, Browser] = {}
        self._pages: Dict[str, Page] = {}
        self._requests: Dict[str, Dict[Any, Any]] = {}
        self._dom_refs: Set[str] = set()
        self._current_domain: str = "default"
        # Console and network diagnostics cache
        self._console_messages: Dict[str, List[Dict[str, Any]]] = {}
        self._network_requests: Dict[str, List[Dict[str, Any]]] = {}
        self._max_console_messages = 10
        self._max_network_requests = 20

    @staticmethod
    def _get_domain(url: str) -> str:
        try:
            parsed = urlparse(url)
            return parsed.hostname or "default"
        except Exception:
            return "default"

    async def _ensure_playwright(self) -> Playwright:
        if self._playwright is None:
            self._playwright = await async_playwright().start()
        return self._playwright

    async def get_browser(self, domain: str = "default") -> Browser:
        """Get or create a browser instance for a given domain."""
        existing = self._browsers.get(domain)
        if existing and existing.is_connected():
            return existing

        # Clean up stale browser/page
        if existing is not None:
            logger.info("Browser for domain %s disconnected, recreating", domain)
            self._browsers.pop(domain, None)
            self._pages.pop(domain, None)

        playwright = await self._ensure_playwright()

        logger.info("Connecting to Thordata Scraping Browser for domain %s", domain)
        # Get browser credentials from settings (separate from residential proxy credentials)
        settings = get_settings()
        user = settings.THORDATA_BROWSER_USERNAME
        pwd = settings.THORDATA_BROWSER_PASSWORD

        if not user or not pwd:
            raise ValueError(
                "Missing browser credentials. Set THORDATA_BROWSER_USERNAME and THORDATA_BROWSER_PASSWORD. "
                "Note: Browser credentials are separate from residential proxy credentials."
            )

        # Retry logic with exponential backoff
        max_retries = 3
        last_error = None

        for attempt in range(max_retries):
            try:
                ws_url = self._client.get_browser_connection_url(username=user, password=pwd)
                logger.debug(f"Attempt {attempt + 1}/{max_retries}: Connecting to {ws_url[:50]}...")
                browser = await playwright.chromium.connect_over_cdp(ws_url)
                logger.info(f"Successfully connected to browser for domain {domain}")
                self._browsers[domain] = browser
                return browser
            except Exception as e:
                last_error = e
                logger.warning(
                    f"Browser connection attempt {attempt + 1}/{max_retries} failed: {e}"
                )

                if attempt < max_retries - 1:
                    import asyncio
                    wait_time = 2 ** attempt  # Exponential backoff: 1s, 2s, 4s
                    logger.info(f"Retrying in {wait_time} seconds...")
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(
                        f"Failed to connect to browser after {max_retries} attempts. "
                        f"Last error: {e}"
                    )
                    logger.error(f"Credentials: username={user[:5]}*** (length={len(user)})")
                    logger.error(f"WebSocket URL: {ws_url[:50]}...")

        # If all retries failed, raise the last error
        raise RuntimeError(
            f"Failed to connect to Thordata Scraping Browser after {max_retries} attempts. "
            f"Last error: {last_error}"
        ) from last_error

    async def get_page(self, url: Optional[str] = None) -> Page:
        """Get or create a page for the current (or provided) domain."""
        if url:
            self._current_domain = self._get_domain(url)
        domain = self._current_domain
        
        existing = self._pages.get(domain)
        if existing and not existing.is_closed():
            return existing

        browser = await self.get_browser(domain)
        contexts = browser.contexts
        if not contexts:
            context = await browser.new_context()
        else:
            context = contexts[0]
            
        pages = context.pages
        if pages:
            page = pages[0]
        else:
            page = await context.new_page()
            
        # Reset network tracking for this domain
        self._requests[domain] = {}
        self._console_messages[domain] = []
        self._network_requests[domain] = []
        
        async def on_request(request: Any) -> None:
            if domain in self._requests:
                self._requests[domain][request] = None
            try:
                self._network_requests.setdefault(domain, [])
                self._network_requests[domain].append(
                    {
                        "url": request.url,
                        "method": request.method,
                        "resourceType": getattr(request, "resource_type", None),
                        "timestamp": int(time.time() * 1000),
                    }
                )
                self._network_requests[domain] = self._network_requests[domain][-self._max_network_requests :]
            except Exception:
                pass

        async def on_response(response: Any) -> None:
            if domain in self._requests:
                try:
                    self._requests[domain][response.request] = response
                except Exception:
                    # Best-effort, non-fatal
                    pass
            try:
                # Update last matching request with status
                req = response.request
                url = getattr(req, "url", None)
                if url and domain in self._network_requests:
                    for item in reversed(self._network_requests[domain]):
                        if item.get("url") == url and item.get("statusCode") is None:
                            item["statusCode"] = response.status
                            break
            except Exception:
                pass

        page.on("request", on_request)
        page.on("response", on_response)

        # Console message tracking
        async def on_console(msg: Any) -> None:
            try:
                self._console_messages.setdefault(domain, [])
                self._console_messages[domain].append(
                    {
                        "type": msg.type,
                        "message": msg.text,
                        "timestamp": int(time.time() * 1000),
                    }
                )
                self._console_messages[domain] = self._console_messages[domain][-self._max_console_messages :]
            except Exception:
                pass

        page.on("console", on_console)

        self._pages[domain] = page
        return page

    def get_console_tail(self, n: int = 10, domain: Optional[str] = None) -> List[Dict[str, Any]]:
        """Return recent console messages for the given domain."""
        d = domain or self._current_domain
        items = self._console_messages.get(d, [])
        return items[-max(0, int(n)) :]

    def get_network_tail(self, n: int = 20, domain: Optional[str] = None) -> List[Dict[str, Any]]:
        """Return recent network request summaries for the given domain."""
        d = domain or self._current_domain
        items = self._network_requests.get(d, [])
        return items[-max(0, int(n)) :]

    def reset_page(self, domain: Optional[str] = None) -> None:
        """Drop cached page for a domain so the next call recreates it."""
        d = domain or self._current_domain
        self._pages.pop(d, None)
        self._requests.pop(d, None)
        self._console_messages.pop(d, None)
        self._network_requests.pop(d, None)


    async def capture_snapshot(
        self,
        *,
        filtered: bool = True,
        mode: str = "compact",
        max_items: int = 80,
        include_dom: bool = False,
    ) -> Dict[str, Any]:
        """Capture an ARIA-like snapshot and optional DOM snapshot.

        Args:
            filtered: Whether to apply AriaSnapshotFilter (legacy, kept for compatibility).
            mode: "compact" | "full". Compact returns minimal interactive elements.
            max_items: Maximum number of interactive elements to include (compact mode only).
            include_dom: Whether to include dom_snapshot (compact mode defaults to False).
        """
        page = await self.get_page()
        
        try:
            full_snapshot = await self._get_interactive_snapshot(page)
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Snapshot failed: %s", exc)
            full_snapshot = "Error capturing snapshot"

        if not filtered:
            return {
                "url": page.url,
                "title": await page.title(),
                "aria_snapshot": full_snapshot,
            }
        
        if mode == "compact":
            # Compact: return only filtered interactive elements, optionally without dom_snapshot
            filtered_snapshot = AriaSnapshotFilter.filter_snapshot(full_snapshot)
            filtered_snapshot = self._limit_aria_snapshot_items(filtered_snapshot, max_items=max_items)
            dom_snapshot = None
            if include_dom:
                dom_snapshot_raw = await self._capture_dom_snapshot(page)
                self._dom_refs = {el["ref"] for el in dom_snapshot_raw}
                dom_snapshot = AriaSnapshotFilter.format_dom_elements(dom_snapshot_raw)
            return {
                "url": page.url,
                "title": await page.title(),
                "aria_snapshot": filtered_snapshot,
                "dom_snapshot": dom_snapshot,
                "_meta": {"mode": mode, "max_items": max_items, "include_dom": include_dom},
            }

        # Full mode: include both filtered aria and dom_snapshot (legacy behavior)
        filtered_snapshot = AriaSnapshotFilter.filter_snapshot(full_snapshot)
        dom_snapshot_raw = await self._capture_dom_snapshot(page)
        self._dom_refs = {el["ref"] for el in dom_snapshot_raw}
        return {
            "url": page.url,
            "title": await page.title(),
            "aria_snapshot": filtered_snapshot,
            "dom_snapshot": AriaSnapshotFilter.format_dom_elements(dom_snapshot_raw),
            "_meta": {"mode": mode},
        }

    @staticmethod
    def _limit_aria_snapshot_items(text: str, *, max_items: int) -> str:
        """Limit snapshot to the first N interactive element blocks.

        The snapshot format is a list where each element starts with a line beginning
        with '- ' (Playwright raw) or '[' (AriaSnapshotFilter compact), and may include
        one or more indented continuation lines.
        """
        try:
            n = int(max_items)
        except Exception:
            n = 80
        if n <= 0:
            return ""
        if not text:
            return text

        lines = text.splitlines()
        out: list[str] = []
        items = 0
        for line in lines:
            if line.startswith("- ") or line.startswith("["):
                if items >= n:
                    break
                items += 1
            # Include continuation lines only if we've started collecting items.
            if items > 0:
                out.append(line)
        return "\n".join(out).strip()
            
    async def _get_interactive_snapshot(self, page: Page) -> str:
        """Generate a text snapshot of interactive elements with refs."""
        script = """
        () => {
            function getSnapshot() {
                const lines = [];
                let refCounter = 0;

                function normalizeRole(tag, explicitRole) {
                    const role = (explicitRole || '').toLowerCase();
                    const t = (tag || '').toLowerCase();
                    if (role) return role;
                    // Map common interactive tags to standard ARIA roles
                    if (t === 'a') return 'link';
                    if (t === 'button') return 'button';
                    if (t === 'input') return 'textbox';
                    if (t === 'select') return 'combobox';
                    if (t === 'textarea') return 'textbox';
                    return t;
                }

                function traverse(node) {
                    if (node.nodeType === Node.ELEMENT_NODE) {
                        const tag = node.tagName.toLowerCase();
                        const interactiveTag = ['a', 'button', 'input', 'select', 'textarea'].includes(tag);
                        const role = normalizeRole(tag, node.getAttribute('role'));
                        const interactiveRole = ['button', 'link', 'textbox', 'searchbox', 'combobox', 'checkbox', 'radio', 'switch', 'tab', 'menuitem', 'option'].includes(role);

                        if (interactiveTag || interactiveRole) {
                            if (!node.dataset.fastmcpRef) {
                                node.dataset.fastmcpRef = (++refCounter).toString();
                            }
                            let name = node.innerText || node.getAttribute('aria-label') || '';
                            name = (name || '').replace(/\\s+/g, ' ').trim().substring(0, 80);

                            lines.push(`- ${role} "${name}" [ref=${node.dataset.fastmcpRef}]`);
                            if (node.href) {
                                lines.push(`  /url: "${node.href}"`);
                            }
                        }
                    }

                    node.childNodes.forEach(child => traverse(child));
                }

                traverse(document.body);
                return lines.join('\\n');
            }
            return getSnapshot();
        }
        """
        return await page.evaluate(script)

    async def _capture_dom_snapshot(self, page: Page) -> List[Dict[str, Any]]:
        """Capture a lightweight DOM snapshot of interactive elements."""
        script = """
        () => {
            const selectors = [
                'a[href]', 'button', 'input', 'select', 'textarea',
                '[role="button"]', '[role="link"]', '[role="checkbox"]',
                '[tabindex]:not([tabindex="-1"])'
            ];
            const elements = Array.from(document.querySelectorAll(selectors.join(',')));
            const results = [];
            let counter = 0;

            for (const el of elements) {
                const style = window.getComputedStyle(el);
                if (style.display === 'none' || style.visibility === 'hidden') {
                    continue;
                }

                if (!el.dataset.fastmcpRef) {
                    el.dataset.fastmcpRef = `dom-${++counter}`;
                }

                let name = el.innerText || el.getAttribute('aria-label') || el.getAttribute('title') || '';
                name = (name || '').replace(/\\s+/g, ' ').trim();

                results.push({
                    ref: el.dataset.fastmcpRef,
                    role: el.getAttribute('role') || el.tagName.toLowerCase(),
                    name,
                    url: el.href || ''
                });
            }
            return results;
        }
        """
        return await page.evaluate(script)

    async def ref_locator(self, ref: str, element_desc: str) -> Any:
        """Return a Playwright locator for a given ref."""
        del element_desc  # not used currently, reserved for logging
        page = await self.get_page()
        # We always rely on data-fastmcp-ref set by snapshots
        return page.locator(f'[data-fastmcp-ref="{ref}"]').first

    async def close(self) -> None:
        """Cleanly close all pages, browsers, and Playwright."""
        for page in list(self._pages.values()):
            try:
                await page.close()
            except Exception:
                pass
            self._pages.clear()
            
        for browser in list(self._browsers.values()):
            try:
                await browser.close()
            except Exception:
                pass
            self._browsers.clear()
            
        if self._playwright is not None:
            try:
                await self._playwright.stop()
            finally:
                self._playwright = None

