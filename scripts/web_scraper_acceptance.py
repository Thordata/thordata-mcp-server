"""
Full, real acceptance runner for Thordata MCP "WEB SCRAPER" 100+ tools.

Design goals (competitor mindset):
- Clean UX: one command produces a reproducible report (JSON) + readable summary.
- Real calls: actually runs tasks and verifies download_url reachability.
- Practical: parameterizes as many tools as possible using a curated test-vector library.
- Honest: tools without known test vectors are SKIPPED with an explicit reason (so we can expand coverage).

Usage (PowerShell):
  $env:THORDATA_SCRAPER_TOKEN="..."
  $env:THORDATA_PUBLIC_TOKEN="..."
  $env:THORDATA_PUBLIC_KEY="..."
  python scripts\web_scraper_acceptance.py --mode sample
  python scripts\web_scraper_acceptance.py --mode full --concurrency 3 --max-wait 180

Outputs:
  - writes JSON report to ./acceptance_report.json (or --out)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import time
import dataclasses
from dataclasses import dataclass
from typing import Any, Literal

import aiohttp
from mcp.server.fastmcp import FastMCP

from thordata_mcp.context import ServerContext
from thordata_mcp.tools.product_compact import register as register_compact
from thordata_mcp.tools.utils import iter_tool_request_types, tool_group_from_key, tool_key


def _require_env(name: str) -> None:
    if not os.getenv(name):
        raise SystemExit(f"Missing env var: {name}")


def _now_ms() -> int:
    return int(time.time() * 1000)


def _json_dump(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=True, separators=(",", ":"))


async def _call(m: FastMCP, name: str, args: dict[str, Any]) -> dict[str, Any]:
    out = await m.call_tool(name, args)
    if isinstance(out, tuple) and len(out) == 2 and isinstance(out[1], dict):
        return out[1]
    if isinstance(out, dict):
        return out
    # Best-effort parse: some tools return content blocks (text)
    try:
        blocks = out[0] if isinstance(out, tuple) else out
        text_parts: list[str] = []
        for b in blocks or []:
            t = getattr(b, "text", None)
            if isinstance(t, str):
                text_parts.append(t)
        if text_parts:
            data = json.loads("\n".join(text_parts))
            return data if isinstance(data, dict) else {"ok": True, "output": data}
    except Exception:
        pass
    return {"ok": False, "error": {"type": "parse_error", "message": "Unable to parse tool output"}}


async def _fetch_download(url: str) -> dict[str, Any]:
    timeout = aiohttp.ClientTimeout(total=60)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(url) as resp:
            text = await resp.text()
            try:
                data = json.loads(text)
                preview = data[0] if isinstance(data, list) and data else data
                return {"ok": True, "status": resp.status, "type": "json", "preview": preview}
            except Exception:
                return {"ok": False, "status": resp.status, "type": "text", "preview": text[:600]}


@dataclass
class ToolCase:
    tool_key: str
    group: str
    spider_id: str | None
    spider_name: str | None
    required_fields: list[str]
    params: dict[str, Any] | None
    skip_reason: str | None


def _required_fields(schema: dict[str, Any]) -> list[str]:
    # NOTE: Kept for backward-compat debugging, but we no longer use schema-based required inference
    # because tool_schema collapses "default=None" and "dataclasses.MISSING" into the same value.
    fields = schema.get("fields")
    if not isinstance(fields, dict):
        return []
    return [k for k in fields.keys() if isinstance(k, str)]


def _required_fields_from_type(t: type[Any]) -> list[str]:
    """Precise required fields using dataclasses.MISSING (avoid false-positives for default=None)."""
    out: list[str] = []
    for name, f in getattr(t, "__dataclass_fields__", {}).items():  # type: ignore[attr-defined]
        if name.isupper():
            continue
        if f.default is dataclasses.MISSING and f.default_factory is dataclasses.MISSING:  # type: ignore[comparison-overlap]
            out.append(name)
    return out


def _test_vector_library() -> tuple[dict[str, Any], dict[str, str]]:
    """
    Returns:
      - field_values: best-effort mapping from common param names to safe public examples
      - group_default_url: fallback URL by group for tools requiring "url"
    """
    field_values: dict[str, Any] = {
        # common ids
        "video_id": "dQw4w9WgXcQ",
        "asin": "B0BZYCJK89",
        "sku": "14089348",
        "place_id": "ChIJN1t_tDeuEmsRUsoyG83frY4",  # Google Maps example
        "listing_id": "34689094",  # Airbnb listing id example (may not always work)
        "post_id": "3141054086080941683",  # Instagram numeric id (may not work)
        "username": "rickastley",
        "query": "pizza",
        "keyword": "pizza",
        "q": "pizza",
        "keywords": "pizza",
        "search_keyword": "pizza",
        "company_name": "Google",
        "industry": "Software",
        "brands": ["Nike"],
        # common URLs
        "product_url": "https://www.amazon.com/dp/B0BZYCJK89",
        "video_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "repo_url": "https://github.com/python/cpython",
        "github_search_url": "https://github.com/search?q=AI&type=repositories",
        "profile_url": "https://www.linkedin.com/in/williamhgates/",
        "place_url": "https://www.google.com/maps/place/Sydney+Opera+House/",
        "airbnb_listing_url": "https://www.airbnb.com/rooms/34689094",
        "glassdoor_job_url": "https://www.glassdoor.com/job-listing/staff-product-analyst-intuit-JV_IC4508422_KO0,21_KE22,28.htm?jl=1008980804695",
        "crunchbase_org": "apple",
        "ebay_item_url": "https://www.ebay.com/itm/187538926483",
        "ebay_category_url": "https://www.ebay.com/b/Smart-Watches/178893/bn_152365",
        "tiktok_post_url": "https://www.tiktok.com/@qatarliving/video/7294553558798650625",
        "tiktok_shop_category_url": "https://www.tiktok.com/shop/c/necklaces/605280",
        "tiktok_search_url": "https://www.tiktok.com/search?q=music",
        "tiktok_profile_url": "https://www.tiktok.com/@babyariel",
        "x_profile_url": "https://x.com/elonmusk",
        "facebook_post_url": "https://www.facebook.com/MayeMusk",
        "reddit_post_url": "https://www.reddit.com/r/datascience/comments/1cmnf0m/technical_interview_python_sql_problem_but_not/",
        # Some SDK tools use these exact names (legacy style)
        "posturl": "https://www.instagram.com/p/Cu8h5tZs3Yz/",
        "profileurl": "https://www.instagram.com/instagram/",
        # misc
        "country": "US",
        "location": "United States",
        "language": "en",
        "hl": "en",
        "gl": "us",
    }
    group_default_url = {
        "video": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "ecommerce": "https://www.amazon.com/dp/B0BZYCJK89",
        "search": "https://www.google.com/search?q=pizza",
        "social": "https://www.tiktok.com/",
        "travel": "https://www.airbnb.com/",
        "professional": "https://www.linkedin.com/",
        "code": "https://github.com/",
        "other": "https://example.com",
    }
    return field_values, group_default_url


def _best_url_for_tool(tool_key_str: str, spider_id: str | None, group: str, field_values: dict[str, Any], group_default_url: dict[str, str]) -> str:
    k = (tool_key_str or "").lower()
    sid = (spider_id or "").lower() if isinstance(spider_id, str) else ""
    if "youtube" in k or "youtube" in sid:
        return str(field_values.get("video_url") or group_default_url.get(group) or "https://example.com")
    if "amazon" in k or "amazon" in sid:
        return str(field_values.get("product_url") or group_default_url.get(group) or "https://example.com")
    if "googlemaps" in k or "google_map" in sid or "maps" in k and "google" in k:
        return str(field_values.get("place_url") or group_default_url.get(group) or "https://example.com")
    if "airbnb" in k or "airbnb" in sid:
        return str(field_values.get("airbnb_listing_url") or group_default_url.get(group) or "https://example.com")
    if "github" in k or "github" in sid:
        # Prefer search url for search-url tools
        if "search" in k or "search" in sid:
            return str(field_values.get("github_search_url") or "https://github.com/search?q=AI&type=repositories")
        return str(field_values.get("repo_url") or group_default_url.get(group) or "https://example.com")
    if "linkedin" in k or "linkedin" in sid:
        return str(field_values.get("profile_url") or group_default_url.get(group) or "https://example.com")
    if "ebay" in k or "ebay" in sid:
        if "category" in k or "category" in sid:
            return str(field_values.get("ebay_category_url") or "https://www.ebay.com/b/Smart-Watches/178893/bn_152365")
        return str(field_values.get("ebay_item_url") or "https://www.ebay.com/itm/187538926483")
    if "glassdoor" in k or "glassdoor" in sid:
        return str(field_values.get("glassdoor_job_url") or group_default_url.get(group) or "https://example.com")
    if "tiktok" in k or "tiktok" in sid:
        # Many TikTok tools accept url/search_url/category_url
        if "shop" in k and "category" in k:
            return str(field_values.get("tiktok_shop_category_url") or "https://www.tiktok.com/shop/c/necklaces/605280")
        if "search" in k:
            return str(field_values.get("tiktok_search_url") or "https://www.tiktok.com/search?q=music")
        if "profile" in k:
            return str(field_values.get("tiktok_profile_url") or "https://www.tiktok.com/@babyariel")
        return str(field_values.get("tiktok_post_url") or "https://www.tiktok.com/@qatarliving/video/7294553558798650625")
    if "twitter" in k or "x.com" in sid or "twitter" in sid:
        return str(field_values.get("x_profile_url") or "https://x.com/elonmusk")
    if "facebook" in k or "facebook" in sid:
        return str(field_values.get("facebook_post_url") or "https://www.facebook.com/MayeMusk")
    if "reddit" in k or "reddit" in sid:
        return str(field_values.get("reddit_post_url") or "https://www.reddit.com/")
    return group_default_url.get(group, "https://example.com")


def _build_case(t: type[Any]) -> ToolCase:
    key = tool_key(t)
    group = tool_group_from_key(key)
    spider_id = getattr(t, "SPIDER_ID", None)
    spider_name = getattr(t, "SPIDER_NAME", None)
    # Skip abstract/base tool requests that are not runnable (no SPIDER_ID / SPIDER_NAME)
    if not isinstance(spider_id, str) or not isinstance(spider_name, str):
        return ToolCase(
            tool_key=key,
            group=group,
            spider_id=spider_id if isinstance(spider_id, str) else None,
            spider_name=spider_name if isinstance(spider_name, str) else None,
            required_fields=[],
            params=None,
            skip_reason="Not runnable (missing SPIDER_ID/SPIDER_NAME; likely base/abstract request)",
        )
    required = _required_fields_from_type(t)
    field_values, group_default_url = _test_vector_library()

    params: dict[str, Any] = {}
    missing: list[str] = []
    for f in required:
        # For any URL-like field, prefer a realistic site-specific URL (not a homepage).
        if f in {"url", "search_url", "category_url", "company_url", "job_url", "job_listing_url"} or f.endswith("_url"):
            params[f] = _best_url_for_tool(key, spider_id if isinstance(spider_id, str) else None, group, field_values, group_default_url)
            continue
        if f in field_values:
            params[f] = field_values[f]
            continue
        # best-effort heuristics
        if f.endswith("_id") or f in {"id", "task_id"}:
            missing.append(f)
            continue
        missing.append(f)

    if missing:
        return ToolCase(
            tool_key=key,
            group=group,
            spider_id=spider_id if isinstance(spider_id, str) else None,
            spider_name=spider_name if isinstance(spider_name, str) else None,
            required_fields=required,
            params=None,
            skip_reason=f"Missing test vector(s) for required fields: {', '.join(missing)}",
        )

    return ToolCase(
        tool_key=key,
        group=group,
        spider_id=spider_id if isinstance(spider_id, str) else None,
        spider_name=spider_name if isinstance(spider_name, str) else None,
        required_fields=required,
        params=params,
        skip_reason=None,
    )


async def _catalog_all(m: FastMCP, *, limit: int = 200) -> list[dict[str, Any]]:
    tools: list[dict[str, Any]] = []
    offset = 0
    while True:
        r = await _call(m, "web_scraper", {"action": "catalog", "params": {"limit": limit, "offset": offset}})
        if r.get("ok") is not True:
            raise RuntimeError(f"catalog failed: {r.get('error')}")
        out = r.get("output")
        page = (out or {}).get("tools") if isinstance(out, dict) else None
        if not isinstance(page, list) or not page:
            break
        tools.extend([t for t in page if isinstance(t, dict)])
        offset += limit
        if len(page) < limit:
            break
    return tools


async def main() -> int:
    _require_env("THORDATA_SCRAPER_TOKEN")
    _require_env("THORDATA_PUBLIC_TOKEN")
    _require_env("THORDATA_PUBLIC_KEY")

    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["sample", "full"], default="sample")
    ap.add_argument("--concurrency", type=int, default=3)
    ap.add_argument("--max-wait", type=int, default=180)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--out", default="acceptance_report.json")
    ap.add_argument("--max-tools", type=int, default=30, help="Only used in sample mode.")
    args = ap.parse_args()

    random.seed(args.seed)
    sem = asyncio.Semaphore(max(1, min(args.concurrency, 10)))

    m = FastMCP("Thordata")
    register_compact(m)

    report: dict[str, Any] = {
        "mode": args.mode,
        "started_ms": _now_ms(),
        "concurrency": args.concurrency,
        "max_wait": args.max_wait,
        "seed": args.seed,
        "results": [],
        "summary": {},
    }

    try:
        types = iter_tool_request_types()
        cases = [_build_case(t) for t in types]

        runnable = [c for c in cases if c.skip_reason is None and c.params is not None]
        skipped = [c for c in cases if c.skip_reason is not None]

        if args.mode == "sample":
            random.shuffle(runnable)
            runnable = runnable[: max(1, args.max_tools)]

        print(f"Discovered tools: {len(cases)} | runnable: {len(runnable)} | skipped(no vectors): {len(skipped)}")
        if skipped:
            print("Top skip reasons (first 10):")
            for c in skipped[:10]:
                print("-", c.tool_key, "=>", c.skip_reason)

        async def _run_one(c: ToolCase) -> dict[str, Any]:
            async with sem:
                t0 = _now_ms()
                r = await _call(
                    m,
                    "web_scraper",
                    {
                        "action": "run",
                        "params": {
                            "tool": c.tool_key,
                            "params": c.params or {},
                            "wait": True,
                            "file_type": "json",
                            "max_wait_seconds": int(args.max_wait),
                        },
                    },
                )
                elapsed = _now_ms() - t0
                out = r.get("output") if isinstance(r.get("output"), dict) else {}
                download_url = out.get("download_url") if isinstance(out, dict) else None
                verified = None
                if r.get("ok") is True and isinstance(download_url, str) and download_url:
                    verified = await _fetch_download(download_url)
                return {
                    "tool_key": c.tool_key,
                    "group": c.group,
                    "spider_id": c.spider_id,
                    "spider_name": c.spider_name,
                    "params": c.params,
                    "ok": r.get("ok") is True,
                    "error": r.get("error"),
                    "output_brief": {k: out.get(k) for k in ("task_id", "status", "download_url") if isinstance(out, dict) and k in out},
                    "download_verify": verified,
                    "elapsed_ms": elapsed,
                }

        results = await asyncio.gather(*[_run_one(c) for c in runnable])
        report["results"] = results
        report["skipped"] = [
            {"tool_key": c.tool_key, "group": c.group, "required_fields": c.required_fields, "reason": c.skip_reason}
            for c in skipped
        ]

        # Define acceptance: task status should be successful and a download_url should be present (for json runs).
        success_statuses = {"Ready", "Succeeded", "Success", "Task Succeeded", "Task Succeeded "}
        ok_count = 0
        dl_ok = 0
        for r in results:
            if r.get("ok") is not True:
                continue
            brief = r.get("output_brief") if isinstance(r.get("output_brief"), dict) else {}
            status = brief.get("status")
            download_url = brief.get("download_url")
            if isinstance(status, str) and status.strip() in success_statuses and isinstance(download_url, str) and download_url:
                ok_count += 1
                if isinstance(r.get("download_verify"), dict) and r["download_verify"].get("ok") is True:
                    dl_ok += 1
        report["summary"] = {
            "catalog_total": len(cases),
            "runnable": len(runnable),
            "skipped_no_vectors": len(skipped),
            "task_succeeded": ok_count,
            "task_not_succeeded": len(runnable) - ok_count,
            "download_verified_ok": dl_ok,
        }
        report["ended_ms"] = _now_ms()

        with open(args.out, "w", encoding="utf-8") as f:
            f.write(json.dumps(report, ensure_ascii=False, indent=2))
        print("\nSummary:", _json_dump(report["summary"]))
        print(f"Report written: {args.out}")

        # Exit code for CI-ish usage
        return 0 if ok_count == len(runnable) else 2
    finally:
        await ServerContext.cleanup()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

