from __future__ import annotations

import asyncio
import json
from typing import Any, Optional
from urllib.parse import quote, urlparse, urlunparse

from thordata_mcp.tools.params_utils import create_params_error, normalize_params
from thordata_mcp.tools.debug import register as register_debug
from thordata_mcp.config import get_settings

from mcp.server.fastmcp import Context, FastMCP
from thordata import ThordataAPIError, ThordataNetworkError

from thordata_mcp.config import settings
from thordata_mcp.context import ServerContext
from thordata_mcp.monitoring import PerformanceTimer
from thordata_mcp.utils import (
    error_response,
    handle_mcp_errors,
    html_to_markdown_clean,
    ok_response,
    safe_ctx_info,
    truncate_content,
)

# Tool schema helper (for catalog)
from .utils import tool_schema  # noqa: E402

# Reuse battle-tested helpers from the full product module
from .product import (  # noqa: E402
    _catalog,
    _candidate_tools_for_url,
    _classify_error,
    _extract_structured_from_html,
    _fetch_json_preview,
    _guess_tool_for_url,
    _hostname,
    _normalize_extracted,
    _normalize_record,
    _run_web_scraper_tool,
    _to_light_json,
)

def _build_params_template(schema: dict[str, Any]) -> dict[str, Any]:
    """Build a minimal runnable params template from a tool_schema() dict.

    We do NOT include URL examples; we only provide placeholders and defaults.
    """
    fields = schema.get("fields") if isinstance(schema, dict) else None
    if not isinstance(fields, dict):
        return {}

    template: dict[str, Any] = {}
    for k, meta in fields.items():
        if k in {"SPIDER_ID", "SPIDER_NAME"}:
            continue
        if not isinstance(meta, dict):
            continue
        required = bool(meta.get("required"))
        default = meta.get("default")
        typ = str(meta.get("type") or "")

        # Always special-case common_settings for video tools, regardless of required/optional.
        if k == "common_settings":
            try:
                from thordata.types.common import CommonSettings

                cs_fields = getattr(CommonSettings, "__dataclass_fields__", {})  # type: ignore[attr-defined]
                cs_template: dict[str, Any] = {}
                for ck, cf in cs_fields.items():
                    # Keep all optional keys visible; user fills what they need.
                    if ck.startswith("_"):
                        continue
                    # default is always None in SDK, keep placeholder to make schema explicit
                    cs_template[ck] = f"<{ck}>"
                template[k] = cs_template
            except Exception:
                # Fall back to a generic dict placeholder if SDK shape changes.
                template[k] = {}
            continue

        # For required fields without defaults, provide a clear placeholder.
        if required and default is None:
            template[k] = f"<{k}>"
            continue

        # For optional fields, include default only if it's not None.
        if default is not None:
            template[k] = default
            continue

        # For some known shapes, provide a sensible empty structure.
        if "dict" in typ:
            template[k] = {}
        elif "list" in typ:
            template[k] = []
        # else: omit

    return template


def register(mcp: FastMCP) -> None:
    """Register the compact product surface (competitor-style).

    Core tools are exposed:
    - serp
    - search_engine / search_engine_batch (minimal web search)
    - unlocker
    - web_scraper
    - browser
    - smart_scrape

    Plus optional debug helper:
    - debug.status

    Tool exposure can be controlled via environment variables:
    - THORDATA_TOOLS: comma-separated tool names to explicitly enable (optional)
    - THORDATA_MODE / THORDATA_GROUPS: legacy knobs (kept for backward-compat)
    """

    cfg = get_settings()
    mode = str(getattr(cfg, "THORDATA_MODE", "rapid")).strip().lower()
    groups = [g.strip().lower() for g in (getattr(cfg, "THORDATA_GROUPS", "") or "").split(",") if g.strip()]
    tools = [t.strip().lower() for t in (getattr(cfg, "THORDATA_TOOLS", "") or "").split(",") if t.strip()]

    # Register debug helper tools (read-only) only when enabled
    if getattr(cfg, "THORDATA_DEBUG_TOOLS", False):
        register_debug(mcp)

    # Decide which tools to register.
    # Competitor-style defaults: keep tool surface small for LLMs.
    # We always expose a small base set; advanced tools require explicit allowlisting via THORDATA_TOOLS.
    all_tools = {
        "search_engine",
        "search_engine_batch",
        "serp",
        "unlocker",
        "unlocker_batch",
        "web_scraper",
        "web_scraper.help",
        "browser",
        "smart_scrape",
    }
    # Default tools: include batch operations for better productivity
    base_tools = {
        "search_engine",
        "search_engine_batch",  # Batch search enabled by default
        "serp",  # Low-level SERP enabled by default for advanced users
        "unlocker",
        "unlocker_batch",  # Batch unlocker enabled by default
        "browser",
        "smart_scrape",
    }

    # Legacy note:
    # We keep THORDATA_MODE/THORDATA_GROUPS for backward-compat, but avoid relying on multi-tier modes.
    # If someone explicitly sets THORDATA_MODE=pro, we still honor it for now.
    if mode == "pro":
        allowed_tools = set(all_tools)
    else:
        allowed_tools = set(base_tools)
        allowed_tools |= {t for t in tools if t in all_tools}

    def _allow(name: str) -> bool:
        return name.lower() in allowed_tools

    # -------------------------
    # SERP (compact)
    # -------------------------
    # Web search aliases
    # - search_engine: single query web search
    # - search_engine_batch: batch web search
    if _allow("search_engine"):
        @mcp.tool(
            name="search_engine",
            description=(
                "Web search with AI-optimized results. Returns a minimal, LLM-friendly subset: title/link/description. "
                "Supports Google, Bing, Yandex and other search engines. "
                "For batch searches (multiple queries), use search_engine_batch tool. "
                "For batch searches (multiple queries), use search_engine_batch tool. "
                "\n\n"
                "Parameters:\n"
                "- q (required): Search query string\n"
                "- num (default: 10): Number of results (1-50)\n"
                "- engine (default: 'google'): Search engine ('google', 'bing', 'yandex')\n"
                "- format (default: 'light_json'): Output format ('light_json', 'json', 'html')\n"
                "- start (default: 0): Starting position for pagination\n"
                "- country: Country code for geolocation (e.g., 'US', 'JP')\n"
                "- language: Language code (e.g., 'en', 'ja')\n"
                "- ai_overview (default: False): Enable AI Overview for Google (Google only)\n"
                "- device: Device type ('desktop', 'mobile', 'tablet')\n"
                "- render_js: Enable JavaScript rendering\n"
                "- no_cache: Disable cache\n"
                "- search_type: Search type filter ('images', 'news', 'videos', 'shopping')\n"
                "- google_domain: Google domain (e.g., 'google.com', 'google.co.jp')\n"
                "- location: Location string for local search\n"
                "\n"
                "Examples:\n"
                "- search_engine(q='Python programming', num=5)\n"
                "- search_engine(q='latest news', search_type='news', country='US')\n"
                "- search_engine(q='AI tools', ai_overview=True, device='mobile')"
            ),
        )
        @handle_mcp_errors
        async def search_engine(
            q: str,
            *,
            num: int = 10,
            engine: str = "google",
            format: str = "light_json",
            start: int = 0,
            country: str | None = None,
            language: str | None = None,
            ai_overview: bool = False,
            device: str | None = None,
            render_js: bool | None = None,
            no_cache: bool | None = None,
            search_type: str | None = None,
            google_domain: str | None = None,
            location: str | None = None,
            ctx: Optional[Context] = None,
        ) -> dict[str, Any]:
            # Normalize query
            q = str(q).strip()
            if not q:
                return error_response(
                    tool="search_engine",
                    input={"q": q, "num": num, "engine": engine, "format": format},
                    error_type="validation_error",
                    code="E4001",
                    message="Query parameter 'q' is required and cannot be empty",
                )

            # Normalize basic options with defaults
            engine = str(engine or "google").strip()
            num = int(num or 10)
            start = int(start or 0)
            fmt = str(format or "light_json").strip().lower()
            if num <= 0 or num > 50:
                return error_response(
                    tool="search_engine",
                    input={"q": q, "num": num, "engine": engine, "format": format},
                    error_type="validation_error",
                    code="E4001",
                    message="num must be between 1 and 50",
                    details={"num": num},
                )

            # Delegate to serp.search - build params efficiently
            await safe_ctx_info(ctx, f"search_engine q={q!r} engine={engine!r} num={num} start={start}")
            
            # Note: Query string should be passed as-is to the API, which will handle encoding
            # The API expects the raw query string, not URL-encoded
            serp_params: dict[str, Any] = {
                "q": q,
                "engine": engine,
                "num": num,
                "start": start,
                "format": fmt,
            }
            # Only add non-None optional parameters to reduce payload size
            optional_params = {
                "country": country,
                "language": language,
                "device": device,
                "google_domain": google_domain,
                "location": location,
            }
            for key, value in optional_params.items():
                if value:
                    serp_params[key] = value
            
            # Boolean and special parameters
            if ai_overview:
                serp_params["ai_overview"] = True
            if render_js is not None:
                serp_params["render_js"] = render_js
            if no_cache is not None:
                serp_params["no_cache"] = no_cache
            if search_type:
                # Map search_type to tbm for serp function
                # Note: Special characters in query string should be handled by the API
                serp_params["tbm"] = search_type
            out = await serp(
                action="search",
                params=serp_params,
                ctx=ctx,
            )
            if out.get("ok") is not True:
                return out

            data = out.get("output")
            organic = data.get("organic") if isinstance(data, dict) else None
            results = []
            if isinstance(organic, list):
                # Limit results to requested num to avoid unnecessary processing
                # Use list comprehension for better performance
                results = [
                    {
                        "title": r.get("title"),
                        "link": r.get("link"),
                        "description": r.get("description"),
                    }
                    for r in organic[:num]
                    if isinstance(r, dict) and (r.get("title") or r.get("link"))
                ]

            # Build input dict efficiently - only include non-None values
            input_dict: dict[str, Any] = {
                "q": q,
                "num": num,
                "engine": engine,
                "format": format,
                "start": start,
            }
            # Only add non-None optional parameters
            optional_inputs = {
                "country": country,
                "language": language,
                "device": device,
                "search_type": search_type,
                "google_domain": google_domain,
                "location": location,
            }
            for key, value in optional_inputs.items():
                if value is not None:
                    input_dict[key] = value
            
            # Boolean parameters
            if ai_overview:
                input_dict["ai_overview"] = True
            if render_js is not None:
                input_dict["render_js"] = render_js
            if no_cache is not None:
                input_dict["no_cache"] = no_cache
            
            # Check for empty results and provide helpful message
            has_results = len(results) > 0
            empty_result_note = None
            if not has_results:
                # Provide helpful message for empty results
                if language and ("zh" in language.lower() or "cn" in language.lower()):
                    empty_result_note = "No results found. This may be due to API limitations with Chinese queries. Try using English queries or different search parameters."
                elif engine.lower() == "bing":
                    empty_result_note = "No results found. Bing API may have limitations or rate limits. Try using Google engine or different query."
                else:
                    empty_result_note = "No results found. This may be due to API limitations, rate limits, or the query not matching any results."
            
            meta = data.get("_meta") if isinstance(data, dict) else {}
            if isinstance(meta, dict):
                meta["has_organic"] = has_results
                meta["organic_count"] = len(results)
                if empty_result_note:
                    meta["note"] = empty_result_note
            
            return ok_response(
                tool="search_engine",
                input=input_dict,
                output={
                    "query": q,
                    "engine": engine,
                    "results": results,
                    "meta": meta,
                },
            )

    if _allow("search_engine_batch"):
        @mcp.tool(
            name="search_engine_batch",
            description=(
                "Batch web search: Execute multiple search queries concurrently. "
                "Returns results for each query with index, status, and results. "
                "\n\n"
                "Parameters:\n"
                "- requests (required): Array of search request objects, each with 'q' (query string) and optional 'engine', 'num'\n"
                "- concurrency (default: 5): Number of concurrent requests (1-20)\n"
                "- engine (default: 'google'): Default search engine for all requests (can be overridden per request)\n"
                "- num (default: 10): Default number of results per request (1-50, can be overridden per request)\n"
                "\n"
                "Examples:\n"
                "- search_engine_batch(requests=[{'q': 'Python programming'}, {'q': 'Java programming'}], concurrency=3)\n"
                "- search_engine_batch(requests=[{'q': 'Python'}, {'q': 'Java'}], engine='bing', num=5)\n"
                "\n"
                "Note: This tool is enabled by default. Use it for efficient batch processing of multiple search queries."
            ),
        )
        @handle_mcp_errors
        async def search_engine_batch(
            requests: list[dict[str, Any]],
            *,
            concurrency: int = 5,
            engine: str = "google",
            num: int = 10,
            ctx: Optional[Context] = None,
        ) -> dict[str, Any]:
            # Validate requests
            if not isinstance(requests, list) or not requests:
                return error_response(
                    tool="search_engine_batch",
                    input={"requests": requests, "concurrency": concurrency, "engine": engine, "num": num},
                    error_type="validation_error",
                    code="E4001",
                    message="requests must be a non-empty array of search request objects",
                )
            
            # Validate concurrency
            concurrency = max(1, min(int(concurrency), 20))
            
            # Validate engine
            engine = str(engine or "google").strip()
            
            # Validate num
            num = int(num or 10)
            if num <= 0 or num > 50:
                return error_response(
                    tool="search_engine_batch",
                    input={"requests": requests, "concurrency": concurrency, "engine": engine, "num": num},
                    error_type="validation_error",
                    code="E4001",
                    message="num must be between 1 and 50",
                    details={"num": num},
                )
            
            # Build params dict for serp call
            p = {
                "requests": requests,
                "concurrency": concurrency,
                "engine": engine,
                "num": num,
            }
            
            # Normalize requests: ensure each has q, engine, num
            default_engine = engine
            default_num = num
            normalized_requests = []
            for r in requests:
                if not isinstance(r, dict):
                    continue
                # Extract query
                q = str((r.get("q") or r.get("query") or "")).strip()
                if not q:
                    continue
                # Use request-specific engine/num or fallback to defaults
                req_engine = str((r.get("engine") or default_engine)).strip()
                req_num = int((r.get("num") or default_num))
                if req_num <= 0 or req_num > 50:
                    req_num = default_num
                normalized_requests.append({
                    "q": q,
                    "engine": req_engine,
                    "num": req_num,
                    **{k: v for k, v in r.items() if k not in ("q", "query", "engine", "num")},
                })
            
            if not normalized_requests:
                return error_response(
                    tool="search_engine_batch",
                    input={"requests": requests, "concurrency": concurrency, "engine": engine, "num": num},
                    error_type="validation_error",
                    code="E4001",
                    message="No valid requests found. Each request must have 'q' (query string)",
                )

            # Delegate to serp.batch_search
            await safe_ctx_info(ctx, f"search_engine_batch count={len(normalized_requests)}")
            out = await serp(
                action="batch_search",
                params={
                    "requests": normalized_requests,
                    "concurrency": concurrency,
                },
                ctx=ctx,
            )
            if out.get("ok") is not True:
                return out

            data = out.get("output")
            results = []
            if isinstance(data, dict):
                for item in data.get("results", []) if isinstance(data.get("results"), list) else []:
                    if not isinstance(item, dict):
                        continue
                    o = item.get("output")
                    organic = o.get("organic") if isinstance(o, dict) else None
                    mapped = []
                    if isinstance(organic, list):
                        for r in organic:
                            if not isinstance(r, dict):
                                continue
                            mapped.append({"title": r.get("title"), "link": r.get("link"), "description": r.get("description")})
                    
                    # Check for empty results and add note
                    query_text = item.get("q") or ""
                    has_results = len(mapped) > 0
                    note = None
                    if not has_results:
                        # Check if it's a Chinese query or Bing engine
                        if any(ord(c) > 127 for c in query_text):  # Contains non-ASCII (likely Chinese)
                            note = "No results found. This may be due to API limitations with Chinese queries. Try using English queries or different search parameters."
                        elif item.get("engine", "").lower() == "bing":
                            note = "No results found. Bing API may have limitations or rate limits. Try using Google engine or different query."
                        else:
                            note = "No results found. This may be due to API limitations, rate limits, or the query not matching any results."
                    
                    results.append(
                        {
                            "index": item.get("index"),
                            "ok": bool(item.get("ok")),
                            "input": {"q": item.get("q"), "engine": item.get("engine"), "num": item.get("num")},
                            "results": mapped if item.get("ok") else None,
                            "error": item.get("error") if not item.get("ok") else None,
                            "note": note,
                        }
                    )

            return ok_response(
                tool="search_engine_batch",
                input={"requests": requests, "concurrency": concurrency, "engine": engine, "num": num},
                output={"results": results},
            )

    # -------------------------
    # Low-level SERP (advanced users; not exposed by default)
    @handle_mcp_errors
    async def serp(
        action: str,
        *,
        params: dict[str, Any] | None = None,
        ctx: Optional[Context] = None,
    ) -> dict[str, Any]:
        """SERP SCRAPER: action in {search, batch_search}.
        
        Args:
            action: Action to perform - "search" or "batch_search"
            params: Parameters dictionary. For "search": {"q": "query", "num": 10, "engine": "google", ...}
                   For "batch_search": {"requests": [{"q": "query1"}, ...], "concurrency": 5}
        
        Examples:
            serp(action="search", params={"q": "Python programming", "num": 10})
            serp(action="batch_search", params={"requests": [{"q": "query1"}, {"q": "query2"}], "concurrency": 5})
        """
        # Normalize params with enhanced error messages
        try:
            p = normalize_params(params, "serp", action)
        except ValueError as e:
            if "JSON" in str(e):
                return create_params_error("serp", action, params, str(e))
            else:
                return create_params_error("serp", action, params, str(e))
        
        a = (action or "").strip().lower()
        if not a:
            return error_response(
                tool="serp",
                input={"action": action, "params": p},
                error_type="validation_error",
                code="E4001",
                message="action is required",
            )
        
        client = await ServerContext.get_client()

        if a == "search":
            # Mirror serp.search product contract
            q = str(p.get("q", ""))
            if not q:
                return error_response(tool="serp", input={"action": action, "params": p}, error_type="validation_error", code="E4001", message="Missing q")
            
            # Check for special characters that might cause API errors
            # Note: The API should handle special characters, but some may cause issues
            special_chars = set("@#$%^&*()[]{}|\\:;\"'<>?/~`")
            detected_special = [c for c in special_chars if c in q]
            has_special = len(detected_special) > 0
            if has_special:
                # Log warning but proceed - let API handle it
                await safe_ctx_info(ctx, f"serp: Query contains special characters: {detected_special}, API may return error")
            engine_in = str(p.get("engine", "google")).strip() or "google"
            num = int(p.get("num", 10))
            start = int(p.get("start", 0))
            fmt = str(p.get("format", "json")).strip().lower()
            # Backend contract nuance:
            # - Some engines support "mode" via engine name (google_images/news/videos/shopping/ai_mode)
            # - For engine=google, passing tbm often breaks on some backends. We route to a specific engine when possible.
            tbm_raw = p.get("tbm")
            tbm_lower = tbm_raw.strip().lower() if isinstance(tbm_raw, str) else None
            engine = engine_in
            if engine_in.lower() == "google" and tbm_lower in {"images", "news", "videos", "shops", "shopping"}:
                # Map tbm-style mode to dedicated engine.
                engine_map = {
                    "images": "google_images",
                    "news": "google_news",
                    "videos": "google_videos",
                    "shops": "google_shopping",
                    "shopping": "google_shopping",
                }
                engine = engine_map[tbm_lower]

            # For engines that explicitly support tbm modes, keep tbm as-is but normalize common aliases
            # (do NOT convert to isch/nws/vid/shop here; those are Google UI tbm values and may differ from backend contract).
            if isinstance(tbm_raw, str):
                tbm_alias = {"image": "images", "video": "videos", "shop": "shops"}
                tbm_norm = tbm_alias.get(tbm_lower)
                if tbm_norm:
                    p = dict(p)
                    p["tbm"] = tbm_norm
            # Leverage SerpRequest mapping via SDK by calling full tool through request object
            from thordata.types import SerpRequest

            sdk_fmt = "json" if fmt in {"json", "light_json", "light"} else ("both" if fmt in {"both", "json+html", "2"} else "html")
            extra_params = p.get("extra_params") if isinstance(p.get("extra_params"), dict) else {}
            if p.get("ai_overview") is not None:
                extra_params = dict(extra_params)
                extra_params["ai_overview"] = p.get("ai_overview")
            # Dashboard-style passthrough parameters (kept in extra_params)
            for k in ("safe", "nfpr", "filter", "tbs", "ibp", "lsig", "si", "uds"):
                if p.get(k) is not None:
                    extra_params = dict(extra_params)
                    extra_params[k] = p.get(k)
            req = SerpRequest(
                query=q,
                engine=engine,
                num=num,
                start=start,
                device=p.get("device"),
                output_format=sdk_fmt,
                render_js=p.get("render_js"),
                no_cache=p.get("no_cache"),
                google_domain=p.get("google_domain"),
                country=p.get("gl"),
                language=p.get("hl"),
                countries_filter=p.get("cr"),
                languages_filter=p.get("lr"),
                location=p.get("location"),
                uule=p.get("uule"),
                search_type=p.get("tbm"),
                ludocid=p.get("ludocid"),
                kgmid=p.get("kgmid"),
                extra_params=extra_params,
            )
            await safe_ctx_info(ctx, f"serp.search q={q!r} engine={engine} (input={engine_in}) num={num} start={start} format={fmt}")
            try:
                # Use new namespace API
                data = await client.serp.search(req)
            except (ThordataNetworkError, ThordataAPIError) as e:
                msg = str(e)
                
                # Check for parameter error (often caused by special characters)
                if "Parameter error" in msg or ("400" in msg and "bad request" in msg.lower()):
                    # Provide more helpful error message for special characters
                    if has_special and detected_special:
                        return error_response(
                            tool="serp",
                            input={"action": action, "params": p},
                            error_type="validation_error",
                            code="E4001",
                            message=f"Query contains special characters that may not be supported: {', '.join(repr(c) for c in detected_special)}. Try removing or escaping these characters.",
                            details={"query": q, "special_chars_detected": detected_special, "raw_error": msg, "suggestion": "Remove or escape special characters, or use URL encoding"},
                        )
                
                if "Invalid tbm parameter" in msg or "invalid tbm parameter" in msg:
                    return error_response(
                        tool="serp",
                        input={"action": "search", "params": p},
                        error_type="validation_error",
                        code="E4001",
                        message="Invalid tbm (search type) parameter for SERP.",
                        details={
                            "tbm": p.get("tbm"),
                            "engine": engine,
                            "engine_input": engine_in,
                            "hint": "The upstream SERP endpoint rejected 'tbm'. Try removing tbm/search_type, or use engine-specific modes (e.g. google_images/google_news/google_videos/google_shopping).",
                            "examples": {"engine": ["google", "google_images", "google_news", "google_videos", "google_shopping"], "tbm": ["images", "news", "videos", "shops", "local", "patents"]},
                        },
                    )
                raise
            if fmt in {"light_json", "light"}:
                data = _to_light_json(data)

            # Add diagnostics for empty/no-result responses (common UX issue)
            organic = None
            if isinstance(data, dict):
                organic = data.get("organic")
            meta = {
                "engine": engine,
                "q": q,
                "num": num,
                "start": start,
                "format": fmt,
                "has_organic": isinstance(organic, list) and len(organic) > 0,
                "organic_count": len(organic) if isinstance(organic, list) else None,
            }

            if isinstance(organic, list) and len(organic) == 0:
                return ok_response(
                    tool="serp",
                    input={"action": "search", "params": p},
                    output={"_meta": meta, **data},
                )
            if isinstance(data, dict):
                return ok_response(
                    tool="serp",
                    input={"action": "search", "params": p},
                    output={"_meta": meta, **data},
                )
            return ok_response(tool="serp", input={"action": "search", "params": p}, output={"_meta": meta, "data": data})

        if a == "batch_search":
            reqs = p.get("requests")
            if not isinstance(reqs, list) or not reqs:
                return error_response(tool="serp", input={"action": action, "params": p}, error_type="validation_error", code="E4001", message="Missing requests[]")
            concurrency = int(p.get("concurrency", 5))
            concurrency = max(1, min(concurrency, 20))
            fmt = str(p.get("format", "json")).strip().lower()
            sdk_fmt = "json" if fmt in {"json", "light_json", "light"} else ("both" if fmt in {"both", "json+html", "2"} else "html")
            from thordata.types import SerpRequest

            sem = asyncio.Semaphore(concurrency)

            async def _one(i: int, r: dict[str, Any]) -> dict[str, Any]:
                q = str(r.get("q", r.get("query", "")))
                if not q:
                    return {"index": i, "ok": False, "error": {"type": "validation_error", "message": "Missing q"}}
                try:
                    engine_in = str(r.get("engine", "google")).strip() or "google"
                    num = int(r.get("num", 10))
                    start = int(r.get("start", 0))
                    tbm_raw = r.get("tbm")
                    tbm_lower = tbm_raw.strip().lower() if isinstance(tbm_raw, str) else None
                    engine = engine_in
                    if engine_in.lower() == "google" and tbm_lower in {"images", "news", "videos", "shops", "shopping"}:
                        engine_map = {
                            "images": "google_images",
                            "news": "google_news",
                            "videos": "google_videos",
                            "shops": "google_shopping",
                            "shopping": "google_shopping",
                        }
                        engine = engine_map[tbm_lower]
                    if isinstance(tbm_raw, str):
                        tbm_alias = {"image": "images", "video": "videos", "shop": "shops"}
                        tbm_norm = tbm_alias.get(tbm_lower)
                        if tbm_norm:
                            r = dict(r)
                            r["tbm"] = tbm_norm
                    extra_params = r.get("extra_params") if isinstance(r.get("extra_params"), dict) else {}
                    if r.get("ai_overview") is not None:
                        extra_params = dict(extra_params)
                        extra_params["ai_overview"] = r.get("ai_overview")
                    for k in ("safe", "nfpr", "filter", "tbs", "ibp", "lsig", "si", "uds"):
                        if r.get(k) is not None:
                            extra_params = dict(extra_params)
                            extra_params[k] = r.get(k)
                    async with sem:
                        req = SerpRequest(
                            query=q,
                            engine=engine,
                            num=num,
                            start=start,
                            device=r.get("device"),
                            output_format=sdk_fmt,
                            render_js=r.get("render_js"),
                            no_cache=r.get("no_cache"),
                            google_domain=r.get("google_domain"),
                            country=r.get("gl"),
                            language=r.get("hl"),
                            countries_filter=r.get("cr"),
                            languages_filter=r.get("lr"),
                            location=r.get("location"),
                            uule=r.get("uule"),
                            search_type=r.get("tbm"),
                            ludocid=r.get("ludocid"),
                            kgmid=r.get("kgmid"),
                            extra_params=extra_params,
                        )
                        try:
                            # Use new namespace API
                            data = await client.serp.search(req)
                        except Exception as e:
                            msg = str(e)
                            if "Invalid tbm parameter" in msg or "invalid tbm parameter" in msg:
                                return {
                                    "index": i,
                                    "ok": False,
                                    "q": q,
                                    "error": {
                                        "type": "validation_error",
                                        "message": "Invalid tbm (search type) parameter for SERP.",
                                        "details": {"tbm": r.get("tbm")},
                                    },
                                }
                            raise
                    if fmt in {"light_json", "light"}:
                        data = _to_light_json(data)
                    return {"index": i, "ok": True, "q": q, "output": data}
                except Exception as e:
                    return {"index": i, "ok": False, "q": q, "error": str(e)}

            await safe_ctx_info(ctx, f"serp.batch_search count={len(reqs)} concurrency={concurrency} format={fmt}")
            results = await asyncio.gather(*[_one(i, r if isinstance(r, dict) else {}) for i, r in enumerate(reqs)], return_exceptions=False)
            return ok_response(tool="serp", input={"action": "batch_search", "params": p}, output={"results": results})

        return error_response(
            tool="serp",
            input={"action": action, "params": p},
            error_type="validation_error",
            code="E4001",
            message=f"Unknown action '{action}'. Supported actions: 'search', 'batch_search'",
        )

    if _allow("serp"):
        @mcp.tool(
            name="serp",
            description=(
                "Low-level SERP scraper with full parameter control. "
                "Provides advanced SERP operations with complete parameter access. "
                "Prefer search_engine for minimal, LLM-friendly output."
                "\n\n"
                "Parameters:\n"
                "- action (required): Action to perform - 'search' or 'batch_search'\n"
                "- params (required): Parameters dictionary:\n"
                "  - For 'search': {'q': 'query string', 'num': 10, 'engine': 'google', 'format': 'light_json', ...}\n"
                "  - For 'batch_search': {'requests': [{'q': 'query1'}, ...], 'concurrency': 5}\n"
                "\n"
                "Examples:\n"
                "- serp(action='search', params={'q': 'Python programming', 'num': 10, 'engine': 'google'})\n"
                "- serp(action='batch_search', params={'requests': [{'q': 'query1'}, {'q': 'query2'}], 'concurrency': 3})\n"
                "\n"
                "Note: This tool is enabled by default. Use it for advanced SERP operations and batch searches."
            ),
        )
        @handle_mcp_errors
        async def serp_wrapper(
            action: str,
            *,
            params: dict[str, Any],
            ctx: Optional[Context] = None,
        ) -> dict[str, Any]:
            """Wrapper for serp tool with explicit params parameter."""
            return await serp(action=action, params=params, ctx=ctx)

    # -------------------------
    # WEB UNLOCKER (compact)
    # -------------------------
    @mcp.tool(
        name="unlocker",
        description=(
            "WEB UNLOCKER (Universal Scrape): Fetch and unlock any webpage. "
            "Supports JavaScript rendering, custom headers, cookies, and multiple output formats (HTML, Markdown, PNG). "
            "Advanced options: block_resources (script/image/video), wait_for (CSS selector), follow_redirect, clean_content (js/css)."
            "\n\n"
            "Parameters:\n"
            "- url (required): Target URL to scrape\n"
            "- js_render (default: False): Enable JavaScript rendering for dynamic pages\n"
            "- output_format (default: 'html'): Output format - 'html', 'markdown', or 'png'\n"
            "- country: Country code for geolocation (e.g., 'US', 'JP')\n"
            "- wait_ms: Wait time in milliseconds before capture (accepts int or string)\n"
            "- wait_for: CSS selector or text to wait for before capture\n"
            "- follow_redirect: Follow HTTP redirects (default: True)\n"
            "- clean_content: Remove JavaScript/CSS from HTML (e.g., 'js,css')\n"
            "- block_resources: Block resource types ('script', 'image', 'video')\n"
            "- headers: Custom HTTP headers (array of strings, e.g., ['User-Agent: ...'])\n"
            "- cookies: Custom cookies (array of strings, e.g., ['name=value'])\n"
            "\n"
            "Examples:\n"
            "- unlocker(url='https://example.com', js_render=True)\n"
            "- unlocker(url='https://example.com', output_format='markdown')\n"
            "- unlocker(url='https://example.com', wait_for='.content', wait_ms=2000)\n"
            "\n"
            "For batch scraping multiple URLs, use unlocker_batch tool (enabled by default)."
        ),
    )
    @handle_mcp_errors
    async def unlocker(
        url: str,
        *,
        js_render: bool = False,
        output_format: str = "html",
        country: str | None = None,
        wait_ms: int | str | None = None,
        wait_for: str | None = None,
        follow_redirect: bool | None = None,
        clean_content: str | None = None,
        block_resources: str | None = None,
        headers: list[str] | None = None,
        cookies: list[str] | None = None,
        ctx: Optional[Context] = None,
    ) -> dict[str, Any]:
        """WEB UNLOCKER: Fetch and unlock any webpage.
        
        Note: wait_ms accepts integer or string (will be converted to int).
        
        Args:
            url: Target URL to scrape
            js_render: Enable JavaScript rendering (default: False)
            output_format: Output format - "html", "markdown", or "png" (default: "html")
            country: Country code for geolocation (optional)
            wait_ms: Wait time in milliseconds before capture (optional)
            wait_for: CSS selector or text to wait for (optional)
            follow_redirect: Follow redirects (optional)
            clean_content: Clean JavaScript/CSS from responses (optional, e.g., "js,css")
        """
        # Normalize wait_ms - accept int or string
        if wait_ms is not None:
            try:
                wait_ms = int(wait_ms) if isinstance(wait_ms, (int, str)) else None
            except (ValueError, TypeError):
                wait_ms = None
        
        # Validate and normalize URL
        url = str(url).strip()
        if not url:
            # Build minimal input dict for error response
            input_dict: dict[str, Any] = {
                "url": url,
                "js_render": js_render,
                "output_format": output_format,
            }
            
            return error_response(
                tool="unlocker",
                input=input_dict,
                error_type="validation_error",
                code="E4001",
                message="URL parameter is required and cannot be empty",
            )
        
        # Normalize URL: encode special characters in path and query
        try:
            parsed = urlparse(url)
            # Encode path and query components to handle special characters
            if parsed.path:
                # Split path into segments and encode each
                path_parts = parsed.path.split('/')
                encoded_path = '/'.join(quote(part, safe='/') for part in path_parts)
            else:
                encoded_path = parsed.path
            
            if parsed.query:
                # Encode query string properly
                query_parts = []
                for param in parsed.query.split('&'):
                    if '=' in param:
                        key, value = param.split('=', 1)
                        query_parts.append(f"{quote(key, safe='')}={quote(value, safe='')}")
                    else:
                        query_parts.append(quote(param, safe=''))
                encoded_query = '&'.join(query_parts)
            else:
                encoded_query = parsed.query
            
            # Reconstruct URL with encoded components
            normalized_url = urlunparse((
                parsed.scheme,
                parsed.netloc,
                encoded_path,
                parsed.params,
                encoded_query,
                parsed.fragment
            ))
        except Exception:
            # If URL parsing fails, use original URL (let SDK handle it)
            normalized_url = url
        
        client = await ServerContext.get_client()
        
        # Normalize output format
        fmt = str(output_format or "html").strip().lower()
        
        # Normalize wait_ms to wait_time
        wait = int(wait_ms) if wait_ms is not None else None
        
        # Build extra_params for advanced options - only add non-None values
        extra_params: dict[str, Any] = {}
        if follow_redirect is not None:
            extra_params["follow_redirect"] = follow_redirect
        if clean_content:
            extra_params["clean_content"] = clean_content
        if block_resources:
            extra_params["block_resources"] = block_resources
        if headers:
            extra_params["headers"] = headers
        if cookies:
            extra_params["cookies"] = cookies
        
        # Handle markdown output format
        fetch_format = "html" if fmt in {"markdown", "md"} else fmt
        if fmt in {"markdown", "md"}:
            # Auto-add clean_content for markdown
            cc = extra_params.get("clean_content", "")
            if isinstance(cc, str) and cc.strip():
                parts = [x.strip() for x in cc.split(",") if x.strip()]
            else:
                parts = []
            for x in ("js", "css"):
                if x not in parts:
                    parts.append(x)
            extra_params["clean_content"] = ",".join(parts)
        
        await safe_ctx_info(ctx, f"unlocker url={normalized_url!r} format={fmt} js_render={js_render}")
        
        with PerformanceTimer(tool="unlocker", url=normalized_url):
            try:
                # Use new namespace API
                data = await client.universal.scrape_async(
                    url=normalized_url,
                    js_render=js_render,
                    country=country,
                    wait_for=wait_for,
                    wait_time=wait,
                    output_format=fetch_format,
                    block_resources=block_resources,
                    **extra_params,
                )
            except (ThordataNetworkError, ThordataAPIError) as e:
                # Classify error and provide detailed error message
                et, ec = _classify_error(e)
                error_msg = str(e)
                
                # Check for HTTP status codes in error message
                status_code = None
                if "404" in error_msg or "not found" in error_msg.lower():
                    status_code = 404
                    et = "not_found"
                    ec = "E3003"
                    error_msg = f"Page not found (404): {normalized_url}"
                elif "500" in error_msg or "internal server error" in error_msg.lower():
                    status_code = 500
                    et = "upstream_internal_error"
                    ec = "E2106"
                    error_msg = f"Server error (500): {normalized_url}"
                elif "403" in error_msg or "forbidden" in error_msg.lower():
                    status_code = 403
                    et = "permission_denied"
                    ec = "E1004"
                    error_msg = f"Access forbidden (403): {normalized_url}"
                elif "400" in error_msg or "bad request" in error_msg.lower():
                    status_code = 400
                    et = "validation_error"
                    ec = "E4001"
                    error_msg = f"Bad request (400): {normalized_url}. This may be due to special characters in the URL."
                
                # Build input dict efficiently
                input_dict: dict[str, Any] = {
                    "url": url,  # Use original URL in response
                    "js_render": js_render,
                    "output_format": output_format,
                }
                optional_inputs = {
                    "country": country,
                    "wait_ms": wait_ms,
                    "wait_for": wait_for,
                }
                for key, value in optional_inputs.items():
                    if value is not None:
                        input_dict[key] = value
                
                return error_response(
                    tool="unlocker",
                    input=input_dict,
                    error_type=et,
                    code=ec,
                    message=error_msg,
                    details={"url": normalized_url, "original_url": url, "status_code": status_code, "raw_error": str(e)},
                )
            except Exception as e:
                msg = str(e)
                if "Attempt to decode JSON" in msg or "unexpected mimetype: text/html" in msg:
                    return error_response(
                        tool="unlocker",
                        input={"url": url, "js_render": js_render, "output_format": output_format},
                        error_type="upstream_internal_error",
                        code="E2106",
                        message="Universal API returned a non-JSON error page (likely gateway/upstream failure).",
                        details={"url": normalized_url, "error": msg},
                    )
                # Re-raise unexpected errors
                raise
        
        # Handle PNG output
        if fetch_format == "png" or isinstance(data, (bytes, bytearray)):
            import base64
            if isinstance(data, (bytes, bytearray)):
                if len(data) == 0:
                    # Build input dict efficiently - only include non-None values
                    input_dict: dict[str, Any] = {
                        "url": url,
                        "js_render": js_render,
                        "output_format": output_format,
                    }
                    optional_inputs = {
                        "country": country,
                        "wait_ms": wait_ms,
                        "wait_for": wait_for,
                        "follow_redirect": follow_redirect,
                        "clean_content": clean_content,
                        "block_resources": block_resources,
                        "headers": headers,
                        "cookies": cookies,
                    }
                    for key, value in optional_inputs.items():
                        if value is not None:
                            input_dict[key] = value
                    
                    return error_response(
                        tool="unlocker",
                        input=input_dict,
                        error_type="unexpected_error",
                        code="E9000",
                        message="Empty PNG data received. Try enabling js_render=True for JavaScript-rendered pages.",
                        details={"url": url, "output_format": output_format, "js_render": js_render},
                    )
                png_base64 = base64.b64encode(data).decode("utf-8")
                size = len(data)
            else:
                png_base64 = str(data)
                size = None
            return ok_response(
                tool="unlocker",
                input={
                    "url": url, "js_render": js_render, "output_format": output_format,
                    "country": country, "wait_ms": wait_ms, "wait_for": wait_for,
                    "follow_redirect": follow_redirect, "clean_content": clean_content,
                    "block_resources": block_resources, "headers": headers, "cookies": cookies
                },
                output={"png_base64": png_base64, "size": size, "format": "png"},
            )
        
        # Handle HTML/Markdown output
        html = str(data) if not isinstance(data, str) else data
        
        # Check for empty content (might indicate HTTP 404/500)
        # Some HTTP error pages return empty content instead of raising exceptions
        # Only treat 400+ status codes as errors, 200-299 are success codes
        if not html or html.strip() == "":
            # Check if URL looks like an error endpoint (e.g., httpbin.org/status/404)
            import re
            status_match = re.search(r'/status/(\d+)', url.lower())
            if status_match:
                status_code = int(status_match.group(1))
                # Only treat 400+ status codes as errors
                # 200-299 are success codes (even if content is empty)
                if status_code >= 400:
                    # Build input dict efficiently
                    input_dict: dict[str, Any] = {
                        "url": url,
                        "js_render": js_render,
                        "output_format": output_format,
                    }
                    optional_inputs = {
                        "country": country,
                        "wait_ms": wait_ms,
                        "wait_for": wait_for,
                    }
                    for key, value in optional_inputs.items():
                        if value is not None:
                            input_dict[key] = value
                    
                    error_type = "not_found" if status_code == 404 else "upstream_internal_error" if status_code >= 500 else "task_failed"
                    error_code = "E3003" if status_code == 404 else "E2106" if status_code >= 500 else "E3001"
                    
                    return error_response(
                        tool="unlocker",
                        input=input_dict,
                        error_type=error_type,
                        code=error_code,
                        message=f"HTTP {status_code} error: Page returned empty content. This may indicate the page does not exist or the server encountered an error.",
                        details={"url": normalized_url, "status_code": status_code, "note": "The API returned empty content instead of an error response"},
                    )
                # For 200-299, empty content is acceptable (success but no content)
        
        if fmt in {"markdown", "md"}:
            from thordata_mcp.utils import html_to_markdown_clean, truncate_content
            md = html_to_markdown_clean(html)
            md = truncate_content(md, max_length=20_000)
            
            # Check if markdown is empty after conversion
            if not md or md.strip() == "":
                # This might indicate an error page or empty content
                # Provide a warning but still return the result
                pass
            # Build input dict efficiently - only include non-None values
            input_dict: dict[str, Any] = {
                "url": url,
                "js_render": js_render,
                "output_format": output_format,
            }
            optional_inputs = {
                "country": country,
                "wait_ms": wait_ms,
                "wait_for": wait_for,
                "follow_redirect": follow_redirect,
                "clean_content": clean_content,
                "block_resources": block_resources,
                "headers": headers,
                "cookies": cookies,
            }
            for key, value in optional_inputs.items():
                if value is not None:
                    input_dict[key] = value
            
            return ok_response(
                tool="unlocker",
                input=input_dict,
                output={"markdown": md},
            )
        
        # Build input dict efficiently - only include non-None values
        input_dict: dict[str, Any] = {
            "url": url,
            "js_render": js_render,
            "output_format": output_format,
        }
        optional_inputs = {
            "country": country,
            "wait_ms": wait_ms,
            "wait_for": wait_for,
            "follow_redirect": follow_redirect,
            "clean_content": clean_content,
            "block_resources": block_resources,
            "headers": headers,
            "cookies": cookies,
        }
        for key, value in optional_inputs.items():
            if value is not None:
                input_dict[key] = value
        
        return ok_response(
            tool="unlocker",
            input=input_dict,
            output={"html": html},
        )

    # -------------------------
    # UNLOCKER BATCH (compact)
    # -------------------------
    if _allow("unlocker_batch"):
        @mcp.tool(
            name="unlocker_batch",
            description=(
                "Batch web scraping: Fetch multiple URLs concurrently via Universal Scrape. "
                "Each request supports the same parameters as unlocker tool. "
                "Returns results for each URL with index, status, and output."
                "\n\n"
                "Parameters:\n"
                "- requests (required): Array of request objects, each with 'url' and optional parameters:\n"
                "  - url (required): Target URL to scrape\n"
                "  - js_render (default: True): Enable JavaScript rendering\n"
                "  - output_format (default: 'html'): Output format ('html', 'markdown', 'png')\n"
                "  - country: Country code for geolocation\n"
                "  - wait_ms: Wait time in milliseconds\n"
                "  - wait_for: CSS selector or text to wait for\n"
                "  - block_resources: Block resources ('script', 'image', 'video')\n"
                "  - headers: Custom headers (array of strings)\n"
                "  - cookies: Custom cookies (array of strings)\n"
                "- concurrency (default: 5): Number of concurrent requests (1-20)\n"
                "\n"
                "Example:\n"
                '{"requests": [{"url": "https://example.com", "js_render": true}, {"url": "https://example.org"}], "concurrency": 3}'
                "\n\n"
                "Note: This tool requires explicit enablement via THORDATA_TOOLS=unlocker_batch or THORDATA_MODE=pro"
            ),
        )
        @handle_mcp_errors
        async def unlocker_batch(
            requests: list[dict[str, Any]],
            *,
            concurrency: int = 5,
            ctx: Optional[Context] = None,
        ) -> dict[str, Any]:
            """Batch web scraping via Universal Scrape."""
            concurrency = max(1, min(int(concurrency), 20))
            client = await ServerContext.get_client()
            sem = asyncio.Semaphore(concurrency)

            async def _one(i: int, r: dict[str, Any]) -> dict[str, Any]:
                url = str(r.get("url", ""))
                if not url:
                    return {
                        "index": i,
                        "ok": False,
                        "url": url,
                        "error": {
                            "type": "validation_error",
                            "code": "E4001",
                            "message": "Missing url parameter"
                        }
                    }
                
                # Normalize URL: encode special characters
                try:
                    parsed = urlparse(url)
                    if parsed.path:
                        path_parts = parsed.path.split('/')
                        encoded_path = '/'.join(quote(part, safe='/') for part in path_parts)
                    else:
                        encoded_path = parsed.path
                    
                    if parsed.query:
                        query_parts = []
                        for param in parsed.query.split('&'):
                            if '=' in param:
                                key, value = param.split('=', 1)
                                query_parts.append(f"{quote(key, safe='')}={quote(value, safe='')}")
                            else:
                                query_parts.append(quote(param, safe=''))
                        encoded_query = '&'.join(query_parts)
                    else:
                        encoded_query = parsed.query
                    
                    normalized_url = urlunparse((
                        parsed.scheme,
                        parsed.netloc,
                        encoded_path,
                        parsed.params,
                        encoded_query,
                        parsed.fragment
                    ))
                except Exception:
                    normalized_url = url
                
                output_format = str(r.get("output_format", "html"))
                js_render = bool(r.get("js_render", True))
                country = r.get("country")
                block_resources = r.get("block_resources")
                wait_ms = r.get("wait_ms")
                wait_for = r.get("wait_for")
                max_chars = int(r.get("max_chars", 20_000))
                wait = int(wait_ms) if isinstance(wait_ms, (int, float)) else None
                extra_params = r.get("extra_params") or {}
                if not isinstance(extra_params, dict):
                    extra_params = {}
                fmt = (output_format or "html").strip().lower()
                fetch_format = "html" if fmt in {"markdown", "md"} else fmt

                # Handle extra parameters
                if r.get("follow_redirect") is not None:
                    extra_params["follow_redirect"] = r.get("follow_redirect")
                if r.get("clean_content"):
                    extra_params["clean_content"] = r.get("clean_content")
                if r.get("headers"):
                    extra_params["headers"] = r.get("headers")
                if r.get("cookies"):
                    extra_params["cookies"] = r.get("cookies")
                if block_resources:
                    extra_params["block_resources"] = block_resources

                async with sem:
                    try:
                        data = await client.universal.scrape_async(
                            url=normalized_url,
                            js_render=js_render,
                            country=country,
                            wait_for=wait_for,
                            wait_time=wait,
                            output_format=fetch_format,
                            block_resources=block_resources,
                            **extra_params,
                        )
                    except (ThordataNetworkError, ThordataAPIError) as e:
                        et, ec = _classify_error(e)
                        error_msg = str(e)
                        
                        # Check for HTTP status codes
                        status_code = None
                        if "404" in error_msg or "not found" in error_msg.lower():
                            status_code = 404
                            et = "not_found"
                            ec = "E3003"
                            error_msg = f"Page not found (404): {normalized_url}"
                        elif "500" in error_msg or "internal server error" in error_msg.lower():
                            status_code = 500
                            et = "upstream_internal_error"
                            ec = "E2106"
                            error_msg = f"Server error (500): {normalized_url}"
                        elif "403" in error_msg or "forbidden" in error_msg.lower():
                            status_code = 403
                            et = "permission_denied"
                            ec = "E1004"
                            error_msg = f"Access forbidden (403): {normalized_url}"
                        elif "400" in error_msg or "bad request" in error_msg.lower():
                            status_code = 400
                            et = "validation_error"
                            ec = "E4001"
                            error_msg = f"Bad request (400): {normalized_url}"
                        
                        return {
                            "index": i,
                            "ok": False,
                            "url": url,  # Return original URL
                            "error": {
                                "type": et,
                                "code": ec,
                                "message": error_msg,
                                "status_code": status_code,
                                "normalized_url": normalized_url,
                            }
                        }

                if fetch_format == "png":
                    import base64
                    if isinstance(data, (bytes, bytearray)):
                        png_base64 = base64.b64encode(data).decode("utf-8")
                        size = len(data)
                    else:
                        png_base64 = str(data)
                        size = None
                    return {"index": i, "ok": True, "url": url, "output": {"png_base64": png_base64, "size": size, "format": "png"}}

                html = str(data) if not isinstance(data, str) else data
                
                # Check for empty content (might indicate HTTP 404/500)
                # Only treat 400+ status codes as errors
                if not html or html.strip() == "":
                    import re
                    status_match = re.search(r'/status/(\d+)', url.lower())
                    if status_match:
                        status_code = int(status_match.group(1))
                        # Only treat 400+ status codes as errors
                        if status_code >= 400:
                            error_type = "not_found" if status_code == 404 else "upstream_internal_error" if status_code >= 500 else "task_failed"
                            error_code = "E3003" if status_code == 404 else "E2106" if status_code >= 500 else "E3001"
                            
                            return {
                                "index": i,
                                "ok": False,
                                "url": url,
                                "error": {
                                    "type": error_type,
                                    "code": error_code,
                                    "message": f"HTTP {status_code} error: Page returned empty content. This may indicate the page does not exist or the server encountered an error.",
                                    "status_code": status_code,
                                }
                            }
                
                if fmt in {"markdown", "md"}:
                    from thordata_mcp.utils import html_to_markdown_clean, truncate_content
                    md = html_to_markdown_clean(html)
                    md = truncate_content(md, max_length=max_chars)
                    return {"index": i, "ok": True, "url": url, "output": {"markdown": md}}

                return {"index": i, "ok": True, "url": url, "output": {"html": html}}

            await safe_ctx_info(ctx, f"unlocker_batch count={len(requests)} concurrency={concurrency}")
            results = await asyncio.gather(*[_one(i, r) for i, r in enumerate(requests)])
            return ok_response(
                tool="unlocker_batch",
                input={"count": len(requests), "concurrency": concurrency},
                output={"results": results},
            )

    # -------------------------
    # WEB SCRAPER (compact)
    # -------------------------
    if _allow("web_scraper"):
        @mcp.tool(
            name="web_scraper",
            description=(
                "WEB SCRAPER TASKS: action in {catalog, groups, spiders, example, run, batch_run, "
                "raw_run, raw_batch_run, list_tasks, status, status_batch, wait, result, result_batch, cancel}. "
                "Use action='catalog' to discover 100+ pre-built scraping tools including Amazon, eBay, and more. "
                "\n\n"
                "Common workflow:\n"
                "1. catalog: Discover available tools (e.g., search for 'amazon')\n"
                "2. example: Get parameter examples for a tool\n"
                "3. run: Execute a scraping task with wait=true for immediate results\n"
                "4. result: Get task results by task_id\n"
                "\n"
                "Note: This tool requires explicit enablement via THORDATA_TOOLS=web_scraper or THORDATA_MODE=pro"
            ),
        )
        @handle_mcp_errors
        async def web_scraper(
            action: str,
            *,
            params: dict[str, Any] | None = None,
            ctx: Optional[Context] = None,
        ) -> dict[str, Any]:
            """WEB SCRAPER: action covers catalog/groups/run/batch_run/status/wait/result/list_tasks and batch helpers.
        
        Args:
            action: Action to perform - "catalog", "groups", "run", "batch_run", "status", "wait", "result", "list_tasks", etc.
            params: Parameters dictionary. Varies by action:
                   - "catalog": {"group": "...", "keyword": "...", "limit": 100, "offset": 0}
                   - "run": {"tool": "tool_key", "params": {...}, "wait": true, "file_type": "json"}
                   - "status": {"task_id": "..."}
                   - etc.
        
        Examples:
            web_scraper(action="catalog", params={"limit": 20})
            web_scraper(action="run", params={"tool": "thordata.tools.ecommerce.Amazon.ProductByUrl", "params": {"url": "https://amazon.com/..."}})
            """
            # Normalize params with enhanced error messages
            try:
                p = normalize_params(params, "web_scraper", action)
            except ValueError as e:
                if "JSON" in str(e):
                    return create_params_error("web_scraper", action, params, str(e))
                else:
                    return create_params_error("web_scraper", action, params, str(e))
            
            a = (action or "").strip().lower()
            if not a:
                return error_response(
                    tool="web_scraper",
                    input={"action": action, "params": p},
                    error_type="validation_error",
                    code="E4001",
                    message="action is required",
                )
            
            client = await ServerContext.get_client()

            if a == "groups":
                # Reuse helper via full module: simply call web_scraper.groups by computing from catalog
                # We use web_scraper.catalog meta/groups via _catalog
                page, meta = _catalog(group=None, keyword=None, limit=1, offset=0)
                return ok_response(tool="web_scraper", input={"action": "groups", "params": p}, output={"groups": meta.get("groups"), "total": meta.get("total")})

            if a in {"spiders", "spider_ids", "ids"}:
                # Convenience: return the full list of spider_id mappings without huge field schemas.
                limit = max(1, min(int(p.get("limit", 500)), 2000))
                offset = max(0, int(p.get("offset", 0)))
                page, meta = _catalog(group=p.get("group"), keyword=p.get("keyword"), limit=limit, offset=offset)
                items = []
                for t in page:
                    s = tool_schema(t)
                    items.append(
                        {
                            "tool_key": s.get("tool_key"),
                            "spider_id": s.get("spider_id"),
                            "spider_name": s.get("spider_name"),
                            "group": s.get("group"),
                        }
                    )
                return ok_response(tool="web_scraper", input={"action": a, "params": p}, output={"items": items, "meta": meta})

            if a == "catalog":
                # Tool discovery is configurable to reduce LLM tool selection noise.
                # - mode=curated: only allow groups from THORDATA_TASKS_GROUPS
                # - mode=all: list everything
                cfg = get_settings()
                mode = str(getattr(cfg, "THORDATA_TASKS_LIST_MODE", "curated") or "curated").strip().lower()
                groups_allow = [g.strip().lower() for g in (getattr(cfg, "THORDATA_TASKS_GROUPS", "") or "").split(",") if g.strip()]

                # Respect explicit group filter provided by user
                group_in = p.get("group")
                group = str(group_in).strip() if group_in is not None else None
                group = group or None

                # If curated, and no group provided, default to first allowed group to keep list small.
                # Users can still browse other groups by passing params.group.
                if mode == "curated" and not group and groups_allow:
                    group = groups_allow[0]

                # If curated + group provided but not allowed, return helpful error
                if mode == "curated" and group and groups_allow and group.lower() not in groups_allow:
                    return error_response(
                        tool="web_scraper",
                        input={"action": "catalog", "params": p},
                        error_type="not_allowed",
                        code="E4010",
                        message="Group not allowed in curated mode.",
                        details={
                            "mode": mode,
                            "allowed_groups": groups_allow,
                            "requested_group": group,
                            "tip": "Set THORDATA_TASKS_LIST_MODE=all to browse all groups, or update THORDATA_TASKS_GROUPS.",
                        },
                    )

                limit_default = int(getattr(cfg, "THORDATA_TASKS_LIST_DEFAULT_LIMIT", 60) or 60)
                limit = max(1, min(int(p.get("limit", limit_default)), 500))
                offset = max(0, int(p.get("offset", 0)))
                page, meta = _catalog(group=group, keyword=p.get("keyword"), limit=limit, offset=offset)

                meta = dict(meta)
                meta.update(
                    {
                        "mode": mode,
                        "allowed_groups": groups_allow,
                        "effective_group": group,
                        "how_to_show_all": "Set THORDATA_TASKS_LIST_MODE=all",
                    }
                )

                return ok_response(
                    tool="web_scraper",
                    input={"action": "catalog", "params": {**p, "group": group} if group else p},
                    output={"tools": [tool_schema(t) for t in page], "meta": meta},
                )

            if a in {"example", "template"}:
                tool = str(p.get("tool", "")) or str(p.get("tool_key", ""))
                if not tool:
                    return error_response(tool="web_scraper", input={"action": a, "params": p}, error_type="validation_error", code="E4001", message="Missing tool (tool_key)")
                # Ensure tool exists and produce its schema + minimal params template.
                from .product import _ensure_tools as _ensure  # local import to avoid cycles
                _, tools_map = _ensure()
                t = tools_map.get(tool)
                if not t:
                    return error_response(tool="web_scraper", input={"action": a, "params": p}, error_type="invalid_tool", code="E4003", message="Unknown tool key. Use web_scraper.catalog to discover valid keys.")
                schema = tool_schema(t)
                params_template = _build_params_template(schema)
                spider_id = schema.get("spider_id")
                spider_name = schema.get("spider_name")

                # LLM-oriented notes: explain the two main calling styles.
                notes: list[str] = [
                    "Step 1: Use web_scraper.catalog to discover tools (filter by keyword/group).",
                    "Step 2: Use web_scraper.example to get this params_template, then fill placeholders like <field> with real values.",
                    "Step 3: Call web_scraper.run with {'tool': tool_key, 'params': {...}, 'wait': true} for a single task, or web_scraper.batch_run for many.",
                ]
                if spider_id and spider_name:
                    # Many dashboard examples in documentation use builder/video_builder + spider_id.
                    notes.append(
                        "Alternative: For full Dashboard parity, you can call web_scraper.raw_run with "
                        "{'builder': 'builder' or 'video_builder', 'spider_name': spider_name, "
                        "'spider_id': spider_id, 'spider_parameters': [...]}. Use this to mirror curl examples "
                        "from the official web scraper tasks documentation."
                    )

                return ok_response(
                    tool="web_scraper",
                    input={"action": a, "params": {"tool": tool}},
                    output={
                        "tool": tool,
                        "spider_id": spider_id,
                        "spider_name": spider_name,
                        "group": schema.get("group"),
                        "params_template": params_template,
                        "notes": notes,
                    },
                )

            if a in {"raw_run", "raw_batch_run"}:
                # Ultimate fallback for 100% Dashboard parity: run by spider_id/spider_name directly,
                # even if SDK doesn't provide a ToolRequest class for it.

                async def _one(raw: dict[str, Any]) -> dict[str, Any]:
                    spider_name = str(raw.get("spider_name", "") or raw.get("name", ""))
                    spider_id = str(raw.get("spider_id", "") or raw.get("id", ""))
                    if not spider_name or not spider_id:
                        return {"ok": False, "error": {"type": "validation_error", "message": "Missing spider_name or spider_id"}}

                    builder = str(raw.get("builder", "builder")).strip().lower()
                    wait = bool(raw.get("wait", True))
                    max_wait_seconds = int(raw.get("max_wait_seconds", 300))
                    file_type = str(raw.get("file_type", "json"))
                    include_errors = bool(raw.get("include_errors", True))
                    file_name = raw.get("file_name")
                    data_format = raw.get("data_format")  # Support json/csv/xlsx output formats

                    # spider_parameters can be dict/list or JSON string
                    sp = raw.get("spider_parameters", raw.get("parameters"))
                    if isinstance(sp, str):
                        try:
                            sp = json.loads(sp) if sp else {}
                        except Exception:
                            sp = {"raw": sp}
                    if isinstance(sp, dict):
                        sp_list: list[dict[str, Any]] = [sp]
                    elif isinstance(sp, list):
                        sp_list = [x for x in sp if isinstance(x, dict)]
                        if not sp_list:
                            sp_list = [{}]
                    else:
                        sp_list = [{}]

                    # spider_universal: for builder universal params or video common_settings
                    su = raw.get("spider_universal") or raw.get("universal_params") or raw.get("common_settings")
                    if isinstance(su, str):
                        try:
                            su = json.loads(su) if su else None
                        except Exception:
                            su = None
                    su_dict = su if isinstance(su, dict) else None

                    # Lazy import types from SDK
                    from thordata.types.task import ScraperTaskConfig, VideoTaskConfig
                    from thordata.types.common import CommonSettings

                    # Generate file_name if missing (mirror SDK behavior)
                    if not file_name:
                        import uuid
                        short_id = uuid.uuid4().hex[:8]
                        file_name = f"{spider_id}_{short_id}"

                    await safe_ctx_info(ctx, f"web_scraper.{a} spider_id={spider_id} builder={builder} wait={wait}")

                    # Create task via correct builder endpoint
                    if builder in {"video_builder", "video"}:
                        # Defensive filtering: CommonSettings in the SDK may not include every
                        # key shown in external documentation (e.g. some newer fields like
                        # "kilohertz" / "bitrate" may not yet exist in this SDK version).
                        # Passing unknown keys would raise "unexpected keyword argument" errors,
                        # so we restrict to the dataclass' declared fields.
                        cs_input: dict[str, Any] = {}
                        if su_dict:
                            allowed_keys = getattr(CommonSettings, "__dataclass_fields__", {}).keys()
                            cs_input = {k: v for k, v in su_dict.items() if k in allowed_keys}
                        cs = CommonSettings(**cs_input)
                        config = VideoTaskConfig(
                            file_name=str(file_name),
                            spider_id=spider_id,
                            spider_name=spider_name,
                            parameters=sp_list if len(sp_list) > 1 else sp_list[0],
                            common_settings=cs,
                            include_errors=include_errors,
                        )
                        # Use new namespace API
                        task_id = await client.scraper.create_task_async(
                            file_name=str(file_name),
                            spider_id=spider_id,
                            spider_name=spider_name,
                            parameters=sp_list if len(sp_list) > 1 else sp_list[0],
                            common_settings=cs,
                            include_errors=include_errors,
                            data_format=data_format,  # Support json/csv/xlsx output formats
                        )
                    else:
                        # Use new namespace API
                        task_id = await client.scraper.create_task_async(
                            file_name=str(file_name),
                            spider_id=spider_id,
                            spider_name=spider_name,
                            parameters=sp_list if len(sp_list) > 1 else sp_list[0],
                            common_settings=su_dict,  # universal_params mapped to common_settings
                            include_errors=include_errors,
                            data_format=data_format,  # Support json/csv/xlsx output formats
                        )

                    result: dict[str, Any] = {"task_id": task_id, "spider_id": spider_id, "spider_name": spider_name}
                    if wait:
                        status = await client.wait_for_task(task_id, max_wait=max_wait_seconds)
                        status_s = str(status)
                        result["status"] = status_s
                        if status_s.strip().lower() in {"ready", "success", "finished", "succeeded", "task succeeded", "task_succeeded"}:
                            dl = await client.get_task_result(task_id, file_type=file_type)
                            from thordata_mcp.utils import enrich_download_url
                            result["download_url"] = enrich_download_url(dl, task_id=task_id, file_type=file_type)
                    return {"ok": True, "output": result}

                if a == "raw_run":
                    out = await _one(p)
                    if out.get("ok") is True:
                        return ok_response(tool="web_scraper", input={"action": a, "params": p}, output=out["output"])
                    return error_response(tool="web_scraper", input={"action": a, "params": p}, error_type="validation_error", code="E4001", message="raw_run failed", details=out.get("error"))

                reqs = p.get("requests")
                if not isinstance(reqs, list) or not reqs:
                    return error_response(tool="web_scraper", input={"action": a, "params": p}, error_type="validation_error", code="E4001", message="Missing requests[]")
                concurrency = max(1, min(int(p.get("concurrency", 5)), 20))
                sem = asyncio.Semaphore(concurrency)

                async def _wrap(i: int, r: Any) -> dict[str, Any]:
                    raw = r if isinstance(r, dict) else {}
                    async with sem:
                        one = await _one(raw)
                    return {"index": i, **one}

                results = await asyncio.gather(*[_wrap(i, r) for i, r in enumerate(reqs)], return_exceptions=False)
                return ok_response(tool="web_scraper", input={"action": a, "params": {"count": len(reqs), "concurrency": concurrency}}, output={"results": results})

            if a == "run":
                tool = str(p.get("tool", ""))
                if not tool:
                    return error_response(
                        tool="web_scraper",
                        input={"action": action, "params": p},
                        error_type="validation_error",
                        code="E4001",
                        message="Missing tool",
                        details={
                            "missing_fields": ["tool"],
                            "next_step": "Call web_scraper(action='catalog', params={'keyword': '...'}) to discover tool_key",
                        },
                    )
                params_dict = p.get("params") if isinstance(p.get("params"), dict) else None
                param_json = p.get("param_json")
                if params_dict is None:
                    if isinstance(param_json, str) and param_json:
                        try:
                            params_dict = json.loads(param_json)
                        except json.JSONDecodeError as e:
                            return error_response(
                                tool="web_scraper",
                                input={"action": action, "params": p},
                                error_type="json_error",
                                code="E4002",
                                message=str(e),
                            )
                    else:
                        params_dict = {}
                wait = bool(p.get("wait", True))

                # Validate required fields based on tool schema
                from .product import _ensure_tools as _ensure
                _, tools_map = _ensure()
                t = tools_map.get(tool)
                if not t:
                    return error_response(
                        tool="web_scraper",
                        input={"action": action, "params": p},
                        error_type="invalid_tool",
                        code="E4003",
                        message="Unknown tool key. Use web_scraper.catalog to discover valid keys.",
                    )
                schema = tool_schema(t)
                fields = schema.get("fields", {})
                missing_fields = []
                params_template = {}
                for key, meta in fields.items():
                    required = bool(meta.get("required"))
                    if required and (params_dict is None or key not in params_dict or params_dict.get(key) in (None, "", [])):
                        missing_fields.append(key)
                    # Build minimal template for missing fields
                    if required and key not in (params_dict or {}):
                        default = meta.get("default")
                        typ = str(meta.get("type", "")).lower()
                        if "dict" in typ:
                            params_template[key] = {}
                        elif "list" in typ:
                            params_template[key] = []
                        elif default is not None:
                            params_template[key] = default
                        else:
                            params_template[key] = f"<{key}>"

                if missing_fields:
                    return error_response(
                        tool="web_scraper",
                        input={"action": action, "params": p},
                        error_type="validation_error",
                        code="E4001",
                        message="Missing required fields for tool params",
                        details={
                            "tool": tool,
                            "missing_fields": missing_fields,
                            "params_template": params_template,
                            "tip": f"Run web_scraper(action='example', params={{'tool': '{tool}'}}) to see full template",
                        },
                    )
                wait = bool(p.get("wait", True))

                # Execution-layer allowlist (optional safety)
                allowlist = getattr(settings, "THORDATA_TASKS_ALLOWLIST", "")
                if allowlist and allowlist.strip():
                    allowed_prefixes = [prefix.strip().lower() for prefix in allowlist.split(",") if prefix.strip()]
                    allowed_exact = [exact.strip() for exact in allowlist.split(",") if exact.strip()]
                    tool_lower = tool.lower()
                    if not any(tool_lower.startswith(p) for p in allowed_prefixes) and tool_lower not in allowed_exact:
                        return error_response(
                            tool="web_scraper",
                            input={"action": action, "params": p},
                            error_type="not_allowed",
                            code="E4011",
                            message="Tool not allowed by allowlist.",
                            details={
                                "tool": tool,
                                "allowlist": allowlist,
                                "tip": "Update THORDATA_TASKS_ALLOWLIST or set THORDATA_TASKS_LIST_MODE=all to bypass.",
                            },
                        )
                wait = bool(p.get("wait", True))
                max_wait_seconds = int(p.get("max_wait_seconds", 300))
                file_type = str(p.get("file_type", "json"))
                return await _run_web_scraper_tool(tool=tool, params=params_dict, wait=wait, max_wait_seconds=max_wait_seconds, file_type=file_type, ctx=ctx)

            if a == "batch_run":
                reqs = p.get("requests")
                if not isinstance(reqs, list) or not reqs:
                    return error_response(tool="web_scraper", input={"action": action, "params": p}, error_type="validation_error", code="E4001", message="Missing requests[]")
                concurrency = max(1, min(int(p.get("concurrency", 5)), 20))
                wait = bool(p.get("wait", True))
                max_wait_seconds = int(p.get("max_wait_seconds", 300))
                file_type = str(p.get("file_type", "json"))
                sem = asyncio.Semaphore(concurrency)

                async def _one(i: int, r: dict[str, Any]) -> dict[str, Any]:
                    tool = str(r.get("tool", ""))
                    if not tool:
                        return {"index": i, "ok": False, "error": {"type": "validation_error", "message": "Missing tool"}}
                    params_dict = r.get("params") if isinstance(r.get("params"), dict) else {}
                    async with sem:
                        out = await _run_web_scraper_tool(tool=tool, params=params_dict, wait=wait, max_wait_seconds=max_wait_seconds, file_type=file_type, ctx=ctx)
                    # compact per-item
                    if out.get("ok") is True and isinstance(out.get("output"), dict):
                        o = out["output"]
                        out["output"] = {k: o.get(k) for k in ("task_id", "spider_id", "spider_name", "status", "download_url") if k in o}
                    return {"index": i, **out}

                await safe_ctx_info(ctx, f"web_scraper.batch_run count={len(reqs)} concurrency={concurrency}")
                results = await asyncio.gather(*[_one(i, r if isinstance(r, dict) else {}) for i, r in enumerate(reqs)])
                return ok_response(tool="web_scraper", input={"action": "batch_run", "params": p}, output={"results": results})

            if a == "list_tasks":
                page = max(1, int(p.get("page", 1)))
                size = max(1, min(int(p.get("size", 20)), 200))
                data = await client.list_tasks(page=page, size=size)
                return ok_response(tool="web_scraper", input={"action": "list_tasks", "params": p}, output=data)

            if a == "status":
                tid = str(p.get("task_id", ""))
                if not tid:
                    return error_response(tool="web_scraper", input={"action": action, "params": p}, error_type="validation_error", code="E4001", message="Missing task_id")
                s = await client.get_task_status(tid)
                return ok_response(tool="web_scraper", input={"action": "status", "params": p}, output={"task_id": tid, "status": str(s)})

            if a == "status_batch":
                tids = p.get("task_ids")
                if not isinstance(tids, list) or not tids:
                    return error_response(tool="web_scraper", input={"action": action, "params": p}, error_type="validation_error", code="E4001", message="Missing task_ids[]")
                results = []
                for tid in [str(x) for x in tids[:200]]:
                    try:
                        s = await client.get_task_status(tid)
                        results.append({"task_id": tid, "ok": True, "status": str(s)})
                    except Exception as e:
                        results.append({"task_id": tid, "ok": False, "error": {"message": str(e)}})
                return ok_response(tool="web_scraper", input={"action": "status_batch", "params": {"count": len(tids)}}, output={"results": results})

            if a == "wait":
                tid = str(p.get("task_id", ""))
                if not tid:
                    return error_response(tool="web_scraper", input={"action": action, "params": p}, error_type="validation_error", code="E4001", message="Missing task_id")
                poll = float(p.get("poll_interval_seconds", 5.0))
                max_wait = float(p.get("max_wait_seconds", 600.0))
                s = await client.wait_for_task(tid, poll_interval=poll, max_wait=max_wait)
                return ok_response(tool="web_scraper", input={"action": "wait", "params": p}, output={"task_id": tid, "status": str(s)})

            if a == "result":
                tid = str(p.get("task_id", ""))
                if not tid:
                    return error_response(tool="web_scraper", input={"action": action, "params": p}, error_type="validation_error", code="E4001", message="Missing task_id")
                file_type = str(p.get("file_type", "json"))
                preview = bool(p.get("preview", True))
                preview_max_chars = int(p.get("preview_max_chars", 20_000))
                dl = await client.get_task_result(tid, file_type=file_type)
                from thordata_mcp.utils import enrich_download_url

                dl = enrich_download_url(dl, task_id=tid, file_type=file_type)
                preview_obj = None
                structured = None
                if preview and file_type.lower() == "json":
                    preview_obj = await _fetch_json_preview(dl, max_chars=preview_max_chars)
                    if preview_obj.get("ok") is True:
                        data = preview_obj.get("data")
                        if isinstance(data, list) and data:
                            structured = _normalize_record(data[0])
                        elif isinstance(data, dict):
                            structured = _normalize_record(data)
                return ok_response(tool="web_scraper", input={"action": "result", "params": p}, output={"task_id": tid, "download_url": dl, "preview": preview_obj, "structured": structured})

            if a == "result_batch":
                tids = p.get("task_ids")
                if not isinstance(tids, list) or not tids:
                    return error_response(tool="web_scraper", input={"action": action, "params": p}, error_type="validation_error", code="E4001", message="Missing task_ids[]")
                file_type = str(p.get("file_type", "json"))
                preview = bool(p.get("preview", False))
                preview_max_chars = int(p.get("preview_max_chars", 20_000))
                from thordata_mcp.utils import enrich_download_url

                results = []
                for tid in [str(x) for x in tids[:100]]:
                    try:
                        dl = await client.get_task_result(tid, file_type=file_type)
                        dl = enrich_download_url(dl, task_id=tid, file_type=file_type)
                        prev = None
                        structured = None
                        if preview and file_type.lower() == "json":
                            prev = await _fetch_json_preview(dl, max_chars=preview_max_chars)
                            if prev.get("ok") is True:
                                data = prev.get("data")
                                if isinstance(data, list) and data:
                                    structured = _normalize_record(data[0])
                                elif isinstance(data, dict):
                                    structured = _normalize_record(data)
                        results.append({"task_id": tid, "ok": True, "download_url": dl, "preview": prev, "structured": structured})
                    except Exception as e:
                        results.append({"task_id": tid, "ok": False, "error": {"message": str(e)}})
                return ok_response(tool="web_scraper", input={"action": "result_batch", "params": {"count": len(tids)}}, output={"results": results})

            if a == "cancel":
                # Public spec currently doesn't provide cancel; keep clear error
                tid = str(p.get("task_id", ""))
                return error_response(tool="web_scraper", input={"action": "cancel", "params": p}, error_type="not_supported", code="E4005", message="Cancel endpoint not available in public Tasks API.", details={"task_id": tid})

            return error_response(
            tool="web_scraper",
            input={"action": action, "params": p},
            error_type="validation_error",
            code="E4001",
            message=(
                f"Unknown action '{action}'. Supported actions: "
                "'catalog', 'groups', 'spiders', 'spider_ids', 'ids', "
                "'example', 'template', "
                "'run', 'batch_run', "
                "'raw_run', 'raw_batch_run', "
                "'list_tasks', 'status', 'status_batch', 'wait', "
                "'result', 'result_batch', 'cancel'"
            ),
        )


    # -------------------------
    # WEB SCRAPER HELP (UX helper)
    # -------------------------
    if _allow("web_scraper.help"):
        mcp.tool(
            name="web_scraper.help",
            description=(
                "Explain how to use web_scraper actions (catalog/example/run/batch_run/raw_run/...). "
                "Use this as a quick reference for LLMs and users."
            ),
        )(handle_mcp_errors(web_scraper_help))
    async def web_scraper_help() -> dict[str, Any]:
        """Return a high-level usage guide for web_scraper.* actions."""
        guide = {
            "recommended_flow": [
                "1. Discover tools: call web_scraper with action='catalog' (and optional group/keyword/limit/offset).",
                "2. Inspect a tool: call web_scraper with action='example' to get params_template and metadata.",
                "3. Run a single task: call web_scraper with action='run' and provide tool + params.",
                "4. Run many tasks: call web_scraper with action='batch_run' and a list of {tool, params}.",
                "5. Get status/result: call web_scraper with action='status'/'wait'/'result' (or their *_batch variants).",
            ],
            "quick_example": {
                "catalog": {"action": "catalog", "params": {"keyword": "amazon_product_by-url", "limit": 5}},
                "example": {"action": "example", "params": {"tool": "<tool_key_from_catalog>"}},
                "run": {
                    "action": "run",
                    "params": {
                        "tool": "<tool_key_from_catalog>",
                        "params": {"<field>": "<value>"},
                        "wait": True,
                        "file_type": "json",
                    },
                },
                "result": {"action": "result", "params": {"task_id": "<task_id>", "file_type": "json", "preview": True}},
            },
            "when_to_use_raw_run": [
                "Use action='raw_run' or 'raw_batch_run' when you only know spider_name/spider_id from Dashboard docs, "
                "or when a spider does not yet have a dedicated SDK ToolRequest.",
                "These actions mirror the 'builder' / 'video_builder' curl examples: you pass spider_id, spider_name, "
                "spider_parameters and optional spider_universal/common_settings directly.",
            ],
            "raw_run_cheatsheet": {
                "builder": {
                    "action": "raw_run",
                    "params": {
                        "builder": "builder",
                        "spider_name": "<spider_name>",
                        "spider_id": "<spider_id>",
                        "spider_parameters": [{"<param>": "<value>"}],
                        "spider_universal": {"<universal_param>": "<value>"},
                        "wait": True,
                        "file_type": "json",
                        "include_errors": True,
                    },
                },
                "video_builder": {
                    "action": "raw_run",
                    "params": {
                        "builder": "video_builder",
                        "spider_name": "<spider_name>",
                        "spider_id": "<spider_id>",
                        "spider_parameters": [{"<param>": "<value>"}],
                        "common_settings": {"<common_setting>": "<value>"},
                        "wait": True,
                        "file_type": "json",
                        "include_errors": True,
                    },
                },
                "curl_mapping": [
                    "curl builder/video_builder → params.builder",
                    "curl spider_name → params.spider_name",
                    "curl spider_id → params.spider_id",
                    "curl spider_parameters → params.spider_parameters (dict or list[dict])",
                    "curl spider_universal → params.spider_universal (builder only)",
                    "curl common_settings → params.common_settings (video_builder only)",
                ],
            },
            "llm_tips": [
                "If you know a tool_key: catalog → example → run/batch_run (best schema, safer defaults).",
                "If you only have a URL and you're unsure which task fits: try smart_scrape(url=...) first (structured if possible, else unlocker).",
                "If catalog cannot find a matching tool by keyword/group: try web_scraper.spiders with a broader keyword (e.g. domain name) to confirm whether the spider_id exists in this MCP build.",
                "If the spider_id is not present in catalog/spiders: treat it as NOT SUPPORTED by this MCP build. Next best action is to use unlocker.fetch (or smart_scrape with prefer_structured=false) to still get content, then extract fields from HTML/Markdown.",
                "When a structured task fails but unlocker succeeds: include the URL + tool_key/spider_id + error.message in your report; it usually indicates site changes or anti-bot and we can improve routing/tool defaults.",
                "If run/raw_run returns task_id: use web_scraper.status / wait / result to poll and fetch outputs.",
            ],
        }
        return ok_response(tool="web_scraper.help", input={}, output=guide)

    # -------------------------
    # BROWSER SCRAPER (compact)
    # -------------------------
    @mcp.tool(
        name="browser",
        description=(
            "BROWSER SCRAPER (Playwright): Navigate to a URL and capture a snapshot of the page. "
            "Returns ARIA accessibility tree for AI-friendly page interaction. "
            "Perfect for JavaScript-heavy pages that require full browser rendering."
            "\n\n"
            "Key Features:\n"
            "- 🌐 Full browser rendering: Executes JavaScript, handles dynamic content\n"
            "- ♿ ARIA accessibility tree: Structured representation for AI understanding\n"
            "- 📸 DOM snapshot: Optional full DOM tree for detailed analysis\n"
            "- 🎯 Filtered output: Removes noise, focuses on meaningful content\n"
            "\n"
            "Parameters:\n"
            "- url (required): Target URL to navigate and capture\n"
            "- filtered (default: True): Return filtered ARIA snapshot (removes noise, focuses on meaningful content)\n"
            "- mode (default: 'accessibility'): Snapshot mode ('accessibility' or 'dom')\n"
            "- max_items (default: 100): Maximum number of items in snapshot (1-500)\n"
            "- max_chars (default: 20000): Maximum characters in snapshot text (prevents context overflow)\n"
            "- include_dom (default: False): Include DOM snapshot in addition to ARIA (for detailed analysis)\n"
            "\n"
            "Examples:\n"
            "- browser(url='https://example.com')  # Basic snapshot\n"
            "- browser(url='https://example.com', filtered=True, max_items=50)  # Compact snapshot\n"
            "- browser(url='https://example.com', include_dom=True, max_chars=10000)  # Full DOM analysis\n"
            "\n"
            "Use Cases:\n"
            "- JavaScript-heavy SPAs (Single Page Applications)\n"
            "- Pages requiring user interaction simulation\n"
            "- Complex dynamic content that unlocker cannot handle\n"
            "- Accessibility analysis and testing\n"
            "\n"
            "Note: Requires THORDATA_BROWSER_USERNAME and THORDATA_BROWSER_PASSWORD to be set."
        ),
    )
    @handle_mcp_errors
    async def browser(
        url: str,
        *,
        filtered: bool = True,
        mode: str = "accessibility",
        max_items: int = 100,
        max_chars: int = 20000,
        include_dom: bool = False,
        ctx: Optional[Context] = None,
    ) -> dict[str, Any]:
        """BROWSER SCRAPER: Capture browser snapshots with ARIA accessibility tree.
        
        Args:
            url: Target URL to navigate and capture
            filtered: Return filtered ARIA snapshot (default: True)
            mode: Snapshot mode - "accessibility" or "dom" (default: "accessibility")
            max_items: Maximum number of items in snapshot (default: 100, max: 500)
            max_chars: Maximum characters in snapshot text (default: 20000)
            include_dom: Include DOM snapshot in addition to ARIA (default: False)
        """
        # Validate URL
        url = str(url).strip()
        if not url:
            return error_response(
                tool="browser",
                input={"url": url, "filtered": filtered},
                error_type="validation_error",
                code="E4001",
                message="URL parameter is required and cannot be empty",
            )
        
        # Validate max_items
        if max_items < 1 or max_items > 500:
            return error_response(
                tool="browser",
                input={"url": url, "max_items": max_items},
                error_type="validation_error",
                code="E4001",
                message="max_items must be between 1 and 500",
                details={"max_items": max_items},
            )
        
        # Credentials check
        user = settings.THORDATA_BROWSER_USERNAME
        pwd = settings.THORDATA_BROWSER_PASSWORD
        if not user or not pwd:
            return error_response(
                tool="browser",
                input={"url": url, "filtered": filtered},
                error_type="config_error",
                code="E1001",
                message="Missing browser credentials. Set THORDATA_BROWSER_USERNAME and THORDATA_BROWSER_PASSWORD.",
            )
        
        # Get browser session and navigate to URL
        session = await ServerContext.get_browser_session()
        page = await session.get_page(url)
        if page.url != url:
            await page.goto(url, timeout=120_000)
        
        # Capture snapshot
        data = await session.capture_snapshot(filtered=filtered, mode=mode, max_items=max_items, include_dom=include_dom)
        
        # Apply an additional safety max_chars guard to avoid flooding context
        aria_snapshot = truncate_content(str(data.get("aria_snapshot", "")), max_length=max_chars)
        dom_snapshot = data.get("dom_snapshot")
        dom_snapshot = truncate_content(str(dom_snapshot), max_length=max_chars) if dom_snapshot else None
        meta = data.get("_meta") if isinstance(data, dict) else None
        
        return ok_response(
            tool="browser",
            input={"url": url, "filtered": filtered, "mode": mode, "max_items": max_items, "max_chars": max_chars, "include_dom": include_dom},
            output={
                "url": data.get("url"),
                "title": data.get("title"),
                "aria_snapshot": aria_snapshot,
                "dom_snapshot": dom_snapshot,
                "_meta": meta,
            },
        )

    # -------------------------
    # SMART SCRAPE (compact)
    # -------------------------
    @mcp.tool(
        name="smart_scrape",
        description=(
            "Intelligent web scraping: Automatically selects the best scraping method for any URL. "
            "Can automatically discover and use 100+ pre-built Web Scraper tools (Amazon products, GitHub repos, YouTube videos, etc.) "
            "or fallback to Universal Scrape. Always returns structured data when possible."
            "\n\n"
            "Key Features:\n"
            "- 🎯 Auto-discovery: Automatically matches URLs to 100+ pre-built Web Scraper tools\n"
            "- 🔍 Smart routing: Google/Bing search → SERP API, Product pages → Structured extractors, Others → Universal Scrape\n"
            "- 📊 Structured output: Returns structured JSON data for e-commerce, social media, video platforms, etc.\n"
            "- 🔄 Fallback chain: Web Scraper → SERP → Universal Scrape (ensures 100% success rate)\n"
            "\n"
            "Parameters:\n"
            "- url (required): Target URL to scrape\n"
            "- prefer_structured (default: True): Prefer structured data extraction over raw HTML\n"
            "- preview (default: True): Include raw HTML/JSON preview in response\n"
            "- preview_max_chars (default: 20000): Maximum characters in preview (1-100000)\n"
            "- max_wait_seconds (default: 300): Maximum wait time for task completion\n"
            "- unlocker_output (default: 'markdown'): Output format when using Unlocker fallback\n"
            "\n"
            "Examples:\n"
            "- smart_scrape(url='https://amazon.com/dp/B08N5WRWNW')  # Auto-detects Amazon product tool\n"
            "- smart_scrape(url='https://github.com/user/repo')  # Auto-detects GitHub repo tool\n"
            "- smart_scrape(url='https://youtube.com/watch?v=...')  # Auto-detects YouTube video tool\n"
            "- smart_scrape(url='https://google.com/search?q=test')  # Routes to SERP API\n"
            "- smart_scrape(url='https://example.com')  # Falls back to Universal Scrape\n"
            "\n"
            "Supported Pre-built Tools (auto-discovered):\n"
            "- E-commerce: Amazon, Walmart, eBay, Google Shopping products\n"
            "- Social: GitHub repositories, YouTube videos, Twitter/X posts\n"
            "- News: News articles from major publishers\n"
            "- And 90+ more tools - use web_scraper(action='catalog') to see full list"
        ),
    )
    @handle_mcp_errors
    async def smart_scrape(
        url: str,
        *,
        prefer_structured: bool = True,
        preview: bool = True,
        preview_max_chars: int = 20_000,
        max_wait_seconds: int = 300,
        unlocker_output: str = "markdown",
        ctx: Optional[Context] = None,
    ) -> dict[str, Any]:
        """Auto-pick a Web Scraper task for URL; fallback to Unlocker. Always returns structured."""
        # Basic schema-style guards for numeric params
        if preview_max_chars <= 0 or preview_max_chars > 100_000:
            return error_response(
                tool="smart_scrape",
                input={"url": url, "prefer_structured": prefer_structured, "preview": preview, "preview_max_chars": preview_max_chars},
                error_type="validation_error",
                code="E4001",
                message="preview_max_chars must be between 1 and 100000",
                details={"preview_max_chars": preview_max_chars},
            )
        if max_wait_seconds <= 0 or max_wait_seconds > 600:
            return error_response(
                tool="smart_scrape",
                input={"url": url, "prefer_structured": prefer_structured, "preview": preview, "max_wait_seconds": max_wait_seconds},
                error_type="validation_error",
                code="E4001",
                message="max_wait_seconds must be between 1 and 600",
                details={"max_wait_seconds": max_wait_seconds},
            )
        await safe_ctx_info(ctx, f"smart_scrape url={url!r} prefer_structured={prefer_structured}")
        host = _hostname(url)
        url_lower = url.lower()
        tried: list[dict[str, Any]] = []

        # Special-case: Google search pages are best handled by SERP (more reliable than Unlocker).
        if prefer_structured:
            def _is_google_search_local(u: str) -> tuple[bool, str | None]:
                try:
                    from urllib.parse import urlparse, parse_qs

                    p0 = urlparse(u)
                    h0 = (p0.hostname or "").lower()
                    if h0.startswith("www."):
                        h0 = h0[4:]
                    if h0 != "google.com":
                        return (False, None)
                    if p0.path != "/search":
                        return (False, None)
                    qs0 = parse_qs(p0.query or "")
                    q0 = (qs0.get("q") or [""])[0].strip()
                    return (bool(q0), q0 or None)
                except Exception:
                    return (False, None)

            is_g, q = _is_google_search_local(url)
            if is_g:
                await safe_ctx_info(ctx, f"smart_scrape: Google search detected, routing to SERP q={q!r}")
                try:
                    from thordata.types import SerpRequest
                    from thordata.types import Engine as EngineEnum
                    client = await ServerContext.get_client()
                    req = SerpRequest(
                        query=str(q or ""),
                        engine=EngineEnum.GOOGLE,
                        num=10,
                        start=0,
                        country=None,
                        language=None,
                        google_domain="google.com",
                        extra_params={},
                    )
                    # Use new namespace API
                    data = await client.serp_search_advanced(req)
                    serp_preview = None
                    if preview:
                        raw = truncate_content(str(data), max_length=int(preview_max_chars))
                        serp_preview = {"format": "light_json", "raw": raw}
                    # Build input dict efficiently - only include non-None values
                    input_dict: dict[str, Any] = {
                        "url": url,
                        "prefer_structured": prefer_structured,
                        "preview": preview,
                    }
                    optional_inputs = {
                        "preview_max_chars": preview_max_chars,
                        "max_wait_seconds": max_wait_seconds,
                        "unlocker_output": unlocker_output,
                    }
                    for key, value in optional_inputs.items():
                        if value is not None:
                            input_dict[key] = value
                    
                    return ok_response(
                        tool="smart_scrape",
                        input=input_dict,
                        output={
                            "path": "SERP",
                            "serp": {"engine": "google", "q": q, "num": 10, "start": 0},
                            "result": data,
                            "structured": {"url": url, "query": q, "engine": "google"},
                            "preview": serp_preview,
                            "candidates": [],
                            "tried": tried,
                        },
                    )
                except Exception as e:
                    err_msg = str(e)
                    tried.append({"path": "SERP", "engine": "google", "q": q, "ok": False, "error": err_msg})
                    await safe_ctx_info(ctx, f"smart_scrape: SERP routing failed, falling back. err={e}")

        # Match product.py behavior: for certain URLs, don't even attempt Web Scraper.
        # - Google search pages: prefer SERP / Unlocker
        # - Generic/example domains: never pick marketplace/product tools
        skip_web_scraper = False
        if host == "google.com" and "/search" in url_lower:
            skip_web_scraper = True
        generic_domains = {"example.com", "example.org", "example.net", "test.com", "localhost"}
        if host in generic_domains or (host and host.endswith(".example.com")):
            skip_web_scraper = True

        selected_tool: str | None = None
        selected_params: dict[str, Any] = {}
        candidates: list[tuple[str, dict[str, Any]]] = []
        if not skip_web_scraper:
            selected_tool, selected_params = _guess_tool_for_url(url)
            # Only keep guessed tool if it exists in tool map (avoid invalid hardcode drift)
            from .product import _ensure_tools as _ensure  # local import to avoid cycles

            _, tools_map = _ensure()
            if selected_tool and selected_tool in tools_map:
                candidates.append((selected_tool, selected_params))

            if not candidates:
                candidate_keys = _candidate_tools_for_url(url, limit=3)
                # Filter out obviously wrong tools (like GitHub for non-GitHub URLs)
                filtered_candidates: list[str] = []
                for k in candidate_keys:
                    lk = k.lower()
                    if "github" in lk and host and "github" not in host.lower():
                        continue
                    if "repository" in lk and host and "github" not in host.lower() and "gitlab" not in host.lower():
                        continue
                    if "amazon" in lk and host and "amazon" not in host.lower():
                        continue
                    if "walmart" in lk and host and "walmart" not in host.lower():
                        continue
                    if ("googleshopping" in lk or "google.shopping" in lk) and (host == "google.com" or "/search" in url_lower):
                        continue
                    filtered_candidates.append(k)

                for k in filtered_candidates:
                    candidates.append((k, {"url": url}))
        else:
            await safe_ctx_info(ctx, f"smart_scrape: skipping Web Scraper for host={host!r} url={url!r}")

        if prefer_structured and candidates:
            for tool, params in candidates[:3]:
                r = await _run_web_scraper_tool(tool=tool, params=params, wait=True, max_wait_seconds=max_wait_seconds, file_type="json", ctx=ctx)
                # Check if task succeeded (status should be Ready/Success, not Failed)
                result_obj = r.get("output") if isinstance(r.get("output"), dict) else {}
                status = result_obj.get("status", "").lower() if isinstance(result_obj, dict) else ""
                
                # If status is Failed, don't try more Web Scraper tools - go to Unlocker
                # Also check if r.get("ok") is False, which indicates the tool call itself failed
                if status == "failed" or r.get("ok") is False:
                    error_info = r.get("error") if isinstance(r.get("error"), dict) else {}
                    error_msg = error_info.get("message") if isinstance(error_info, dict) else str(r.get("error", ""))
                    await safe_ctx_info(ctx, f"smart_scrape: Web Scraper tool {tool} failed (status={status}, ok={r.get('ok')}, error={error_msg}), falling back to Unlocker")
                    tried.append({
                        "tool": tool,
                        "ok": r.get("ok"),
                        "status": status,
                        "error": error_msg if error_msg else r.get("error"),
                        "details": error_info if isinstance(error_info, dict) else None,
                    })
                    break  # Exit loop and go to Unlocker fallback
                
                # Only return success if both ok is True AND status is not failed
                if r.get("ok") is True and status not in {"failed", "error", "failure"}:
                    out = r.get("output") if isinstance(r.get("output"), dict) else {}
                    dl = out.get("download_url") if isinstance(out, dict) else None
                    preview_obj = None
                    structured = {"url": url}
                    if preview and isinstance(dl, str) and dl:
                        preview_obj = await _fetch_json_preview(dl, max_chars=int(preview_max_chars))
                        # Try to use preview data even if JSON parsing failed but we have raw data
                        if preview_obj.get("ok") is True:
                            data = preview_obj.get("data")
                            if isinstance(data, list) and data:
                                structured = _normalize_record(data[0], url=url)
                            elif isinstance(data, dict):
                                structured = _normalize_record(data, url=url)
                        elif preview_obj.get("status") == 200 and preview_obj.get("raw"):
                            # JSON parsing failed but we have raw data - try to extract basic info
                            raw = preview_obj.get("raw", "")
                            if raw:
                                # Try to extract basic fields from raw text if possible
                                structured = {"url": url, "raw_preview": raw[:500]}  # Limit raw preview size
                    return ok_response(
                        tool="smart_scrape",
                        input={"url": url, "prefer_structured": prefer_structured, "preview": preview},
                        output={
                            "path": "WEB_SCRAPER",
                            "selected_tool": tool,
                            "selected_params": params,
                            "result": out,
                            "structured": structured,
                            "preview": preview_obj,
                            "candidates": [c[0] for c in candidates],
                            "tried": tried,
                        },
                    )
                error_info = r.get("error") if isinstance(r.get("error"), dict) else {}
                error_msg = error_info.get("message") if isinstance(error_info, dict) else str(r.get("error", ""))
                tried.append({
                    "tool": tool,
                    "ok": r.get("ok"),
                    "status": status,
                    "error": error_msg if error_msg else r.get("error"),
                    "details": error_info if isinstance(error_info, dict) else None,
                })

        client = await ServerContext.get_client()
        try:
            with PerformanceTimer(tool="smart_scrape.unlocker", url=url):
                # Use new namespace API
                html = await client.universal.scrape_async(url=url, js_render=True, output_format="html", wait_for=".content")
            html_str = str(html) if not isinstance(html, str) else html
            extracted = _extract_structured_from_html(html_str) if html_str else {}
            structured = _normalize_extracted(extracted, url=url)
            # Token-efficient preview
            preview_obj: dict[str, Any] | None = None
            out_mode = (unlocker_output or "markdown").strip().lower()
            if out_mode not in {"markdown", "md", "html"}:
                out_mode = "markdown"
            if preview:
                if out_mode in {"markdown", "md"}:
                    md = html_to_markdown_clean(html_str)
                    md = truncate_content(md, max_length=int(preview_max_chars))
                    preview_obj = {"format": "markdown", "raw": md}
                else:
                    preview_obj = {"format": "html", "raw": truncate_content(html_str, max_length=int(preview_max_chars))}
            # Build input dict efficiently - only include non-None values
            input_dict: dict[str, Any] = {
                "url": url,
                "prefer_structured": prefer_structured,
                "preview": preview,
            }
            optional_inputs = {
                "preview_max_chars": preview_max_chars,
                "max_wait_seconds": max_wait_seconds,
                "unlocker_output": unlocker_output,
            }
            for key, value in optional_inputs.items():
                if value is not None:
                    input_dict[key] = value
            
            return ok_response(
                tool="smart_scrape",
                input=input_dict,
                output={
                    "path": "WEB_UNLOCKER",
                    "preview": preview_obj,
                    "extracted": extracted,
                    "structured": structured,
                    "selected_tool": selected_tool,
                    "selected_params": selected_params,
                    "candidates": [c[0] for c in candidates],
                    "tried": tried,
                },
            )
        except asyncio.TimeoutError as e:
            # Handle timeout specifically
            await safe_ctx_info(ctx, f"smart_scrape: Unlocker timed out: {e}")
            return error_response(
                tool="smart_scrape",
                input={"url": url, "prefer_structured": prefer_structured, "preview": preview},
                error_type="timeout_error",
                code="E2003",
                message=f"Unlocker request timed out. The page may be slow to load or blocked.",
                details={
                    "selected_tool": selected_tool,
                    "candidates": [c[0] for c in candidates],
                    "tried": tried,
                },
            )
        except Exception as e:
            # If Unlocker also fails, return error with context
            await safe_ctx_info(ctx, f"smart_scrape: Unlocker also failed: {e}")
            error_msg = str(e)
            # Extract more useful error information
            if "504" in error_msg or "Gateway Timeout" in error_msg:
                error_type = "timeout_error"
                error_code = "E2003"
                error_message = f"Unlocker request timed out (504 Gateway Timeout). The page may be slow to load or blocked."
            elif "timeout" in error_msg.lower():
                error_type = "timeout_error"
                error_code = "E2003"
                error_message = f"Unlocker request timed out: {error_msg}"
            else:
                error_type = "network_error"
                error_code = "E2002"
                error_message = f"Both Web Scraper and Unlocker failed. Last error: {error_msg}"
            return error_response(
                tool="smart_scrape",
                input={"url": url, "prefer_structured": prefer_structured, "preview": preview},
                error_type=error_type,
                code=error_code,
                message=error_message,
                details={
                    "selected_tool": selected_tool,
                    "candidates": [c[0] for c in candidates],
                    "tried": tried,
                },
            )

