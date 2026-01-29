"""
Deeper productized MCP tests, including verifying download_url is reachable.

Runs tools in-process via FastMCP.call_tool().

Requires env vars (same as your Cursor MCP config):
- THORDATA_SCRAPER_TOKEN, THORDATA_PUBLIC_TOKEN, THORDATA_PUBLIC_KEY
- Optional for browser tools: THORDATA_BROWSER_USERNAME, THORDATA_BROWSER_PASSWORD
"""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any

import aiohttp
from mcp.server.fastmcp import FastMCP

from thordata_mcp.context import ServerContext
from thordata_mcp.tools.product_compact import register as register_product_tools


def _require_env(name: str) -> None:
    if not os.getenv(name):
        raise SystemExit(f"Missing env var: {name}")


def _compact(obj: Any, max_len: int = 4000) -> str:
    try:
        # Use ensure_ascii=True to avoid Windows console encoding issues (GBK).
        s = json.dumps(obj, ensure_ascii=True)[:max_len]
        return s + ("..." if len(s) >= max_len else "")
    except Exception:
        s = str(obj)
        return s[:max_len] + ("..." if len(s) >= max_len else "")


async def _call(m: FastMCP, name: str, args: dict[str, Any]) -> Any:
    print(f"\n==> call {name} {args}")
    out = await m.call_tool(name, args)
    if isinstance(out, dict):
        print("<== ok:", out.get("ok"))
        if out.get("ok") is False:
            print("<== error:", _compact(out.get("error")))
        else:
            print("<== output keys:", list((out.get("output") or {}).keys()) if isinstance(out.get("output"), dict) else type(out.get("output")).__name__)
    else:
        # FastMCP.call_tool may return (content_blocks, raw_dict) tuple in-process
        if isinstance(out, tuple) and len(out) == 2:
            print("<== call_tool returned tuple:", type(out[0]).__name__, "+", type(out[1]).__name__)
        else:
            print("<== content blocks:", len(out))
    return out


def _blocks_to_text(out: Any) -> str | None:
    """Extract concatenated text from MCP content blocks."""
    # In-process FastMCP may return (blocks, raw_dict)
    if isinstance(out, tuple) and len(out) == 2:
        out = out[0]
    if isinstance(out, dict):
        return _compact(out, max_len=20000)
    if not out:
        return None
    parts: list[str] = []
    for b in out:
        t = getattr(b, "text", None)
        if isinstance(t, str):
            parts.append(t)
    if not parts:
        return None
    return "\n".join(parts)


def _maybe_parse_json_from_blocks(out: Any) -> dict[str, Any] | None:
    # Prefer raw dict if available
    if isinstance(out, tuple) and len(out) == 2 and isinstance(out[1], dict):
        return out[1]
    text = _blocks_to_text(out)
    if not text:
        return None
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else {"_data": data}
    except Exception:
        # Some tools return non-JSON text content blocks
        return None


async def _fetch_download(url: str) -> dict[str, Any]:
    timeout = aiohttp.ClientTimeout(total=60)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(url) as resp:
            text = await resp.text()
            try:
                data = json.loads(text)
                return {"status": resp.status, "ok": True, "type": "json", "preview": data[0] if isinstance(data, list) and data else data}
            except Exception:
                return {"status": resp.status, "ok": False, "type": "text", "preview": text[:500]}


async def main() -> None:
    _require_env("THORDATA_SCRAPER_TOKEN")
    _require_env("THORDATA_PUBLIC_TOKEN")
    _require_env("THORDATA_PUBLIC_KEY")

    m = FastMCP("Thordata")
    register_product_tools(m)

    tools = await m.list_tools()
    names = [getattr(t, "name", None) if not isinstance(t, dict) else t.get("name") for t in tools]
    print("Registered core tools:", names)

    try:
        # 1) SERP (light_json)
        await _call(m, "serp", {"action": "search", "params": {"engine": "google", "q": "pizza", "num": 5, "start": 0, "format": "light_json"}})

        # 2) Unlocker (markdown)
        await _call(m, "unlocker", {"action": "fetch", "params": {"url": "https://example.com", "output_format": "markdown", "js_render": False, "max_chars": 1500}})

        # 3) Web Scraper catalog (youtube)
        await _call(m, "web_scraper", {"action": "catalog", "params": {"keyword": "youtube", "limit": 8, "offset": 0}})

        # 4) Web Scraper run: YouTube VideoInfo (should return download_url on success)
        yt_out = await _call(
            m,
            "web_scraper",
            {"action": "run", "params": {"tool": "thordata.tools.video.YouTube.VideoInfo", "params": {"video_id": "dQw4w9WgXcQ"}, "wait": True, "file_type": "json", "max_wait_seconds": 300}},
        )
        yt = _maybe_parse_json_from_blocks(yt_out) if not isinstance(yt_out, dict) else yt_out
        if isinstance(yt, dict) and yt.get("ok") is True:
            out = yt.get("output") if isinstance(yt.get("output"), dict) else {}
            download_url = out.get("download_url") if isinstance(out, dict) else None
            print("<== extracted download_url:", download_url)
            if isinstance(download_url, str) and download_url:
                print("\n==> verifying download_url reachable (GET)")
                fetched = await _fetch_download(download_url)
                print("<== download_url status:", fetched.get("status"), "ok:", fetched.get("ok"), "type:", fetched.get("type"))
                print("<== download_url preview:", _compact(fetched.get("preview"), max_len=2000))
            else:
                print("\n!! No download_url returned for YouTube VideoInfo")
        else:
            print("\n!! Unable to parse web_scraper.run response as JSON. Raw text preview:")
            print(_compact(_blocks_to_text(yt_out), max_len=1200))

        # 4b) web_scraper.status + web_scraper.result parity tools
        if isinstance(yt, dict) and isinstance(yt.get("output"), dict) and yt["output"].get("task_id"):
            tid = yt["output"]["task_id"]
            await _call(m, "web_scraper", {"action": "status", "params": {"task_id": tid}})
            await _call(m, "web_scraper", {"action": "status_batch", "params": {"task_ids": [tid]}})
            await _call(m, "web_scraper", {"action": "result", "params": {"task_id": tid, "file_type": "json", "preview": True}})
            await _call(m, "web_scraper", {"action": "result_batch", "params": {"task_ids": [tid], "file_type": "json", "preview": False}})
            await _call(m, "web_scraper", {"action": "cancel", "params": {"task_id": tid}})

        # 5) smart_scrape (structured + preview)
        await _call(m, "smart_scrape", {"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ", "prefer_structured": True, "preview": True})

        # 6) Browser tools (optional; will fail with config_error if creds missing)
        await _call(m, "browser", {"action": "navigate", "params": {"url": "https://example.com"}})
        await _call(m, "browser", {"action": "snapshot", "params": {"filtered": True}})
    finally:
        # Avoid aiohttp session warnings at interpreter shutdown
        await ServerContext.cleanup()


if __name__ == "__main__":
    asyncio.run(main())

