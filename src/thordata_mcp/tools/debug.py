from __future__ import annotations

import asyncio
from typing import Any, Optional

from mcp.server.fastmcp import FastMCP

from thordata_mcp.config import settings
from thordata_mcp.context import ServerContext
from thordata_mcp.utils import ok_response
from thordata_mcp.tools.params_utils import normalize_params


def register(mcp: FastMCP) -> None:
    @mcp.tool(name="debug.status", description="Return server status and effective configuration (no secrets).")
    async def debug_status() -> dict[str, Any]:
        def _mask(v: str | None) -> dict[str, Any]:
            if not v:
                return {"set": False}
            return {
                "set": True,
                "length": len(v),
                "tail4": v[-4:] if len(v) >= 4 else v,
            }

        return ok_response(
            tool="debug.status",
            input={},
            output={
                "python": __import__("sys").version,
                "settings": {
                    "THORDATA_SCRAPER_TOKEN": _mask(settings.THORDATA_SCRAPER_TOKEN),
                    "THORDATA_PUBLIC_TOKEN": _mask(settings.THORDATA_PUBLIC_TOKEN),
                    "THORDATA_PUBLIC_KEY": _mask(settings.THORDATA_PUBLIC_KEY),
                    "THORDATA_BROWSER_USERNAME": _mask(settings.THORDATA_BROWSER_USERNAME),
                    "THORDATA_BROWSER_PASSWORD": _mask(settings.THORDATA_BROWSER_PASSWORD),
                    "THORDATA_TASKS_LIST_MODE": settings.THORDATA_TASKS_LIST_MODE,
                    "THORDATA_TASKS_LIST_DEFAULT_LIMIT": settings.THORDATA_TASKS_LIST_DEFAULT_LIMIT,
                },
            },
        )

    @mcp.tool(name="browser.diagnostics", description="Return recent browser console/network diagnostics for the current session.")
    async def browser_diagnostics(
        console_limit: int = 10,
        network_limit: int = 20,
    ) -> dict[str, Any]:
        session = await ServerContext.get_browser_session()
        page = await session.get_page()
        
        return ok_response(
            tool="browser.diagnostics",
            input={"console_limit": console_limit, "network_limit": network_limit},
            output={
                "url": page.url,
                "title": await page.title(),
                "console_tail": session.get_console_tail(n=console_limit),
                "network_tail": session.get_network_tail(n=network_limit),
            },
        )

    @mcp.tool(
        name="debug.self_test",
        description=(
            "Run a small, non-destructive smoke test suite for core scraping capabilities and return a compact report. "
            "Useful after restarting the MCP server. Params: {\"timeout_s\": 30}."
        ),
    )
    async def debug_self_test(*, params: Any = None) -> dict[str, Any]:
        try:
            p = normalize_params(params, "debug.self_test", "run")
        except Exception:
            p = {}

        timeout_s = int(p.get("timeout_s", 30))
        timeout_s = max(5, min(timeout_s, 120))

        async def _run(name: str, fn) -> dict[str, Any]:
            try:
                out = await asyncio.wait_for(fn(), timeout=timeout_s)
                return {"check": name, "ok": True, "detail": out}
            except Exception as e:
                return {"check": name, "ok": False, "error": str(e)}

        client = await ServerContext.get_client()

        async def _check_serp() -> dict[str, Any]:
            from thordata import Engine, SerpRequest

            req = SerpRequest(query="thordata", engine=Engine.GOOGLE, num=3, output_format="light_json")
            # Use client's serp_search_advanced method
            data = await client.serp_search_advanced(req)
            organic = data.get("organic") if isinstance(data, dict) else None
            return {"has_organic": isinstance(organic, list) and len(organic) > 0, "organic_count": len(organic) if isinstance(organic, list) else None}

        async def _check_unlocker() -> dict[str, Any]:
            # Use new namespace API
            html = await client.universal.scrape_async(url="https://example.com", js_render=True, output_format="html")
            s = html if isinstance(html, str) else str(html)
            return {"html_len": len(s), "contains_example_domain": "Example Domain" in s}

        async def _check_browser_snapshot() -> dict[str, Any]:
            session = await ServerContext.get_browser_session()
            snap = await session.capture_snapshot(url="https://example.com", filtered=True, max_items=20)
            aria = snap.get("aria_snapshot") if isinstance(snap, dict) else None
            return {"aria_non_empty": bool(aria), "aria_len": len(aria) if isinstance(aria, str) else None, "url": snap.get("url") if isinstance(snap, dict) else None}

        results = await asyncio.gather(
            _run("serp.search", _check_serp),
            _run("unlocker.fetch(html,js_render=true)", _check_unlocker),
            _run("browser.snapshot(filtered,max_items=20)", _check_browser_snapshot),
        )

        summary = []
        ok_all = True
        for r in results:
            if r.get("ok"):
                summary.append({"check": r.get("check"), "ok": True})
            else:
                ok_all = False
                summary.append({"check": r.get("check"), "ok": False, "error": r.get("error")})

        return ok_response(
            tool="debug.self_test",
            input={"params": {"timeout_s": timeout_s}},
            output={"ok_all": ok_all, "summary": summary, "_meta": {"timeout_s": timeout_s}},
        )
