"""
End-to-end-ish smoke test for the productized MCP tool surface.

Runs tools in-process via FastMCP.call_tool() (no Cursor needed).

Requirements:
- Set env vars: THORDATA_SCRAPER_TOKEN, THORDATA_PUBLIC_TOKEN, THORDATA_PUBLIC_KEY
- Optional for browser tools: THORDATA_BROWSER_USERNAME, THORDATA_BROWSER_PASSWORD
"""

from __future__ import annotations

import asyncio
import os
from typing import Any

from mcp.server.fastmcp import FastMCP

from thordata_mcp.context import ServerContext
from thordata_mcp.tools.product_compact import register as register_product_tools


def _require_env(name: str) -> None:
    if not os.getenv(name):
        raise SystemExit(f"Missing env var: {name}")


async def _call(m: FastMCP, name: str, args: dict[str, Any]) -> Any:
    print(f"\n==> call {name} {args}")
    out = await m.call_tool(name, args)
    # FastMCP may return MCP content blocks or raw dicts depending on tool.
    print("<== result type:", type(out).__name__)
    if isinstance(out, dict):
        print("<== ok:", out.get("ok"))
        # Print a small preview
        print("<== keys:", list(out.keys())[:10])
        if out.get("ok") is False:
            print("<== error:", out.get("error"))
    else:
        # content blocks
        print("<== blocks:", len(out))
    return out


async def main() -> None:
    _require_env("THORDATA_SCRAPER_TOKEN")
    _require_env("THORDATA_PUBLIC_TOKEN")
    _require_env("THORDATA_PUBLIC_KEY")

    try:
        m = FastMCP("Thordata")
        register_product_tools(m)

        tools = await m.list_tools()
        tool_names = [getattr(t, "name", None) if not isinstance(t, dict) else t.get("name") for t in tools]
        print("Registered tools:", tool_names)

        # SERP
        await _call(m, "serp", {"action": "search", "params": {"engine": "google", "q": "pizza", "num": 5, "start": 0, "format": "light_json"}})

        # Unlocker
        await _call(m, "unlocker", {"action": "fetch", "params": {"url": "https://example.com", "output_format": "markdown", "js_render": False, "max_chars": 3000}})

        # Web Scraper catalog/groups
        await _call(m, "web_scraper", {"action": "groups", "params": {}})
        await _call(m, "web_scraper", {"action": "catalog", "params": {"keyword": "youtube", "limit": 5, "offset": 0}})

        # Smart scrape (should choose a structured tool or fallback unlocker)
        await _call(m, "smart_scrape", {"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ", "prefer_structured": True, "preview": True})
    finally:
        await ServerContext.cleanup()


if __name__ == "__main__":
    asyncio.run(main())

