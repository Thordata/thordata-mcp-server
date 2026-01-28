"""Browser session management for Thordata Scraping Browser.

This module provides a high-level wrapper around Playwright connected to
Thordata's Scraping Browser (via `AsyncThordataClient.get_browser_connection_url`),
inspired by Bright Data's browser session design but implemented in Python.

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
        
        ws_url = self._client.get_browser_connection_url(username=user, password=pwd)
        browser = await playwright.chromium.connect_over_cdp(ws_url)
        self._browsers[domain] = browser
        return browser

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
        
        async def on_request(request: Any) -> None:
            if domain in self._requests:
                self._requests[domain][request] = None
                
        async def on_response(response: Any) -> None:
            if domain in self._requests:
                try:
                    self._requests[domain][response.request] = response
                except Exception:
                    # Best-effort, non-fatal
                    pass

        page.on("request", on_request)
        page.on("response", on_response)
        
        self._pages[domain] = page
        return page

    async def capture_snapshot(self, filtered: bool = True) -> Dict[str, Any]:
        """Capture an ARIA-like snapshot and optional DOM snapshot."""
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
        
        filtered_snapshot = AriaSnapshotFilter.filter_snapshot(full_snapshot)
        dom_snapshot = await self._capture_dom_snapshot(page)
        self._dom_refs = {el["ref"] for el in dom_snapshot}
        
        return {
            "url": page.url,
            "title": await page.title(),
            "aria_snapshot": filtered_snapshot,
            "dom_snapshot": AriaSnapshotFilter.format_dom_elements(dom_snapshot),
        }
            
    async def _get_interactive_snapshot(self, page: Page) -> str:
        """Generate a text snapshot of interactive elements with refs."""
        script = """
        () => {
            function getSnapshot() {
                const lines = [];
                let refCounter = 0;

                function traverse(node) {
                    if (node.nodeType === Node.ELEMENT_NODE) {
                        const role = node.getAttribute('role') || node.tagName.toLowerCase();
                        const tag = node.tagName.toLowerCase();
                        const interactiveTag = ['a', 'button', 'input', 'select', 'textarea'].includes(tag);
                        const interactiveRole = ['button', 'link', 'textbox', 'checkbox'].includes(role);

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

