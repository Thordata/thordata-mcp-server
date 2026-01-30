from __future__ import annotations

import asyncio
import json
from typing import Any, Optional

from mcp.server.fastmcp import Context, FastMCP

from thordata_mcp.config import settings
from thordata_mcp.context import ServerContext
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
    _extract_structured_from_html,
    _fetch_json_preview,
    _guess_tool_for_url,
    _hostname,
    _normalize_extracted,
    _normalize_record,
    _run_web_scraper_tool,
    _to_light_json,
)


def register(mcp: FastMCP) -> None:
    """Register the compact product surface (competitor-style).

    Only 5 top-level tools are exposed:
    - serp
    - unlocker
    - web_scraper
    - browser
    - smart_scrape
    """

    # -------------------------
    # SERP (compact)
    # -------------------------
    @mcp.tool(name="serp")
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
        # Normalize params: handle None, empty dict, or string (JSON)
        if params is None:
            p = {}
        elif isinstance(params, str):
            try:
                p = json.loads(params)
            except json.JSONDecodeError as e:
                return error_response(
                    tool="serp",
                    input={"action": action, "params": params},
                    error_type="json_error",
                    code="E4002",
                    message=f"Invalid JSON in params: {e}",
                )
        elif isinstance(params, dict):
            p = params
        else:
            return error_response(
                tool="serp",
                input={"action": action, "params": params},
                error_type="validation_error",
                code="E4001",
                message="params must be a dictionary or JSON string",
            )
        
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
            engine = str(p.get("engine", "google"))
            num = int(p.get("num", 10))
            start = int(p.get("start", 0))
            fmt = str(p.get("format", "json")).strip().lower()
            # Leverage SerpRequest mapping via SDK by calling full tool through request object
            from thordata.types import SerpRequest
            from thordata.types import Engine as EngineEnum

            sdk_fmt = "json" if fmt in {"json", "light_json", "light"} else ("both" if fmt in {"both", "json+html", "2"} else "html")
            extra_params = p.get("extra_params") if isinstance(p.get("extra_params"), dict) else {}
            if p.get("ai_overview") is not None:
                extra_params = dict(extra_params)
                extra_params["ai_overview"] = p.get("ai_overview")
            req = SerpRequest(
                query=q,
                engine=getattr(EngineEnum, engine.upper(), EngineEnum.GOOGLE),
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
            await safe_ctx_info(ctx, f"serp.search q={q!r} engine={engine} num={num} start={start} format={fmt}")
            data = await client.serp_search_advanced(req)
            if fmt in {"light_json", "light"}:
                data = _to_light_json(data)
            return ok_response(tool="serp", input={"action": "search", "params": p}, output=data)

        if a == "batch_search":
            reqs = p.get("requests")
            if not isinstance(reqs, list) or not reqs:
                return error_response(tool="serp", input={"action": action, "params": p}, error_type="validation_error", code="E4001", message="Missing requests[]")
            concurrency = int(p.get("concurrency", 5))
            concurrency = max(1, min(concurrency, 20))
            fmt = str(p.get("format", "json")).strip().lower()
            sdk_fmt = "json" if fmt in {"json", "light_json", "light"} else ("both" if fmt in {"both", "json+html", "2"} else "html")
            from thordata.types import SerpRequest
            from thordata.types import Engine as EngineEnum

            sem = asyncio.Semaphore(concurrency)

            async def _one(i: int, r: dict[str, Any]) -> dict[str, Any]:
                q = str(r.get("q", r.get("query", "")))
                if not q:
                    return {"index": i, "ok": False, "error": {"type": "validation_error", "message": "Missing q"}}
                try:
                    engine = str(r.get("engine", "google"))
                    num = int(r.get("num", 10))
                    start = int(r.get("start", 0))
                    extra_params = r.get("extra_params") if isinstance(r.get("extra_params"), dict) else {}
                    if r.get("ai_overview") is not None:
                        extra_params = dict(extra_params)
                        extra_params["ai_overview"] = r.get("ai_overview")
                    async with sem:
                        req = SerpRequest(
                            query=q,
                            engine=getattr(EngineEnum, engine.upper(), EngineEnum.GOOGLE),
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
                        data = await client.serp_search_advanced(req)
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

    # -------------------------
    # WEB UNLOCKER (compact)
    # -------------------------
    @mcp.tool(name="unlocker")
    @handle_mcp_errors
    async def unlocker(
        action: str,
        *,
        params: dict[str, Any] | None = None,
        ctx: Optional[Context] = None,
    ) -> dict[str, Any]:
        """WEB UNLOCKER: action in {fetch, batch_fetch}.
        
        Args:
            action: Action to perform - "fetch" or "batch_fetch"
            params: Parameters dictionary. For "fetch": {"url": "https://...", "js_render": true, "output_format": "html", ...}
                   For "batch_fetch": {"requests": [{"url": "https://..."}, ...], "concurrency": 5}
        
        Examples:
            unlocker(action="fetch", params={"url": "https://www.google.com", "js_render": true})
            unlocker(action="batch_fetch", params={"requests": [{"url": "https://example.com"}], "concurrency": 5})
        """
        # Normalize params: handle None, empty dict, or string (JSON)
        if params is None:
            p = {}
        elif isinstance(params, str):
            try:
                p = json.loads(params)
            except json.JSONDecodeError as e:
                return error_response(
                    tool="unlocker",
                    input={"action": action, "params": params},
                    error_type="json_error",
                    code="E4002",
                    message=f"Invalid JSON in params: {e}",
                )
        elif isinstance(params, dict):
            p = params
        else:
            return error_response(
                tool="unlocker",
                input={"action": action, "params": params},
                error_type="validation_error",
                code="E4001",
                message="params must be a dictionary or JSON string",
            )
        
        a = (action or "").strip().lower()
        if not a:
            return error_response(
                tool="unlocker",
                input={"action": action, "params": p},
                error_type="validation_error",
                code="E4001",
                message="action is required",
            )
        
        client = await ServerContext.get_client()

        if a == "fetch":
            url = str(p.get("url", ""))
            if not url:
                return error_response(tool="unlocker", input={"action": action, "params": p}, error_type="validation_error", code="E4001", message="Missing url")
            fmt = str(p.get("output_format", "html")).strip().lower()
            js_render = bool(p.get("js_render", True))
            wait_ms = p.get("wait_ms")
            wait_seconds = int(wait_ms / 1000) if isinstance(wait_ms, (int, float)) else None
            country = p.get("country")
            block_resources = p.get("block_resources")
            wait_for = p.get("wait_for")
            max_chars = int(p.get("max_chars", 20_000))
            clean_content = p.get("clean_content")  # e.g., "js,css" or ["js", "css"]
            headers = p.get("headers")  # Custom headers (list of dicts or dict)
            cookies = p.get("cookies")  # Custom cookies (list of dicts or string)
            extra_params = p.get("extra_params") if isinstance(p.get("extra_params"), dict) else {}
            
            # Handle clean_content: can be string (comma-separated) or list
            if clean_content:
                if isinstance(clean_content, str):
                    clean_content_list = [c.strip() for c in clean_content.split(",")]
                elif isinstance(clean_content, list):
                    clean_content_list = clean_content
                else:
                    clean_content_list = None
                if clean_content_list:
                    extra_params["clean_content"] = ",".join(clean_content_list)
            
            # Handle headers: can be list of dicts [{"name": "...", "value": "..."}] or dict
            if headers:
                if isinstance(headers, list):
                    # Convert list of dicts to proper format if needed
                    extra_params["headers"] = headers
                elif isinstance(headers, dict):
                    # Convert dict to list format
                    extra_params["headers"] = [{"name": k, "value": v} for k, v in headers.items()]
            
            # Handle cookies: can be list of dicts [{"name": "...", "value": "..."}] or string
            if cookies:
                if isinstance(cookies, str):
                    extra_params["cookies"] = cookies
                elif isinstance(cookies, list):
                    # Convert list of dicts to string format if needed
                    cookie_strs = []
                    for c in cookies:
                        if isinstance(c, dict):
                            cookie_strs.append(f"{c.get('name', '')}={c.get('value', '')}")
                        else:
                            cookie_strs.append(str(c))
                    extra_params["cookies"] = "; ".join(cookie_strs)
            
            fetch_format = "html" if fmt in {"markdown", "md"} else fmt
            await safe_ctx_info(ctx, f"unlocker.fetch url={url!r} format={fmt} js_render={js_render}")
            data = await client.universal_scrape(
                url=url,
                js_render=js_render,
                output_format=fetch_format,
                country=country,
                block_resources=block_resources,
                wait=wait_seconds,
                wait_for=wait_for,
                **extra_params,
            )
            if fetch_format == "png":
                import base64

                if isinstance(data, (bytes, bytearray)):
                    png_base64 = base64.b64encode(data).decode("utf-8")
                    size = len(data)
                else:
                    png_base64 = str(data)
                    size = None
                return ok_response(tool="unlocker", input={"action": "fetch", "params": p}, output={"png_base64": png_base64, "size": size, "format": "png"})
            html = str(data) if not isinstance(data, str) else data
            if fmt in {"markdown", "md"}:
                md = html_to_markdown_clean(html)
                md = truncate_content(md, max_length=max_chars)
                return ok_response(tool="unlocker", input={"action": "fetch", "params": p}, output={"markdown": md})
            return ok_response(tool="unlocker", input={"action": "fetch", "params": p}, output={"html": html})

        if a == "batch_fetch":
            reqs = p.get("requests")
            if not isinstance(reqs, list) or not reqs:
                return error_response(tool="unlocker", input={"action": action, "params": p}, error_type="validation_error", code="E4001", message="Missing requests[]")
            concurrency = int(p.get("concurrency", 5))
            concurrency = max(1, min(concurrency, 20))
            sem = asyncio.Semaphore(concurrency)

            async def _one(i: int, r: dict[str, Any]) -> dict[str, Any]:
                url = str(r.get("url", ""))
                if not url:
                    return {"index": i, "ok": False, "error": {"type": "validation_error", "message": "Missing url"}}
                fmt = str(r.get("output_format", "html")).strip().lower()
                fetch_format = "html" if fmt in {"markdown", "md"} else fmt
                js_render = bool(r.get("js_render", True))
                wait_ms = r.get("wait_ms")
                wait_seconds = int(wait_ms / 1000) if isinstance(wait_ms, (int, float)) else None
                extra_params = r.get("extra_params") if isinstance(r.get("extra_params"), dict) else {}
                async with sem:
                    data = await client.universal_scrape(
                        url=url,
                        js_render=js_render,
                        output_format=fetch_format,
                        country=r.get("country"),
                        block_resources=r.get("block_resources"),
                        wait=wait_seconds,
                        wait_for=r.get("wait_for"),
                        **extra_params,
                    )
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
                if fmt in {"markdown", "md"}:
                    md = html_to_markdown_clean(html)
                    md = truncate_content(md, max_length=int(r.get("max_chars", 20_000)))
                    return {"index": i, "ok": True, "url": url, "output": {"markdown": md}}
                return {"index": i, "ok": True, "url": url, "output": {"html": html}}

            await safe_ctx_info(ctx, f"unlocker.batch_fetch count={len(reqs)} concurrency={concurrency}")
            results = await asyncio.gather(*[_one(i, r if isinstance(r, dict) else {}) for i, r in enumerate(reqs)])
            return ok_response(tool="unlocker", input={"action": "batch_fetch", "params": p}, output={"results": results})

        return error_response(
            tool="unlocker",
            input={"action": action, "params": p},
            error_type="validation_error",
            code="E4001",
            message=f"Unknown action '{action}'. Supported actions: 'fetch', 'batch_fetch'",
        )

    # -------------------------
    # WEB SCRAPER (compact)
    # -------------------------
    @mcp.tool(name="web_scraper")
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
        # Normalize params: handle None, empty dict, or string (JSON)
        if params is None:
            p = {}
        elif isinstance(params, str):
            try:
                p = json.loads(params)
            except json.JSONDecodeError as e:
                return error_response(
                    tool="web_scraper",
                    input={"action": action, "params": params},
                    error_type="json_error",
                    code="E4002",
                    message=f"Invalid JSON in params: {e}",
                )
        elif isinstance(params, dict):
            p = params
        else:
            return error_response(
                tool="web_scraper",
                input={"action": action, "params": params},
                error_type="validation_error",
                code="E4001",
                message="params must be a dictionary or JSON string",
            )
        
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

        if a == "catalog":
            limit = max(1, min(int(p.get("limit", 100)), 500))
            offset = max(0, int(p.get("offset", 0)))
            page, meta = _catalog(group=p.get("group"), keyword=p.get("keyword"), limit=limit, offset=offset)
            return ok_response(tool="web_scraper", input={"action": "catalog", "params": p}, output={"tools": [tool_schema(t) for t in page], "meta": meta})

        if a == "run":
            tool = str(p.get("tool", ""))
            if not tool:
                return error_response(tool="web_scraper", input={"action": action, "params": p}, error_type="validation_error", code="E4001", message="Missing tool")
            params_dict = p.get("params") if isinstance(p.get("params"), dict) else None
            param_json = p.get("param_json")
            if params_dict is None:
                if isinstance(param_json, str) and param_json:
                    try:
                        params_dict = json.loads(param_json)
                    except json.JSONDecodeError as e:
                        return error_response(tool="web_scraper", input={"action": action, "params": p}, error_type="json_error", code="E4002", message=str(e))
                else:
                    params_dict = {}
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
            message=f"Unknown action '{action}'. Supported actions: 'catalog', 'groups', 'run', 'batch_run', 'status', 'wait', 'result', 'list_tasks', 'status_batch', 'result_batch', 'cancel'",
        )

    # -------------------------
    # BROWSER SCRAPER (compact)
    # -------------------------
    @mcp.tool(name="browser")
    @handle_mcp_errors
    async def browser(
        action: str,
        *,
        params: dict[str, Any] | None = None,
        ctx: Optional[Context] = None,
    ) -> dict[str, Any]:
        """BROWSER SCRAPER: action in {navigate, snapshot}.
        
        Args:
            action: Action to perform - "navigate" or "snapshot"
            params: Parameters dictionary. For "navigate": {"url": "https://..."}
                   For "snapshot": {"filtered": true}
        
        Examples:
            browser(action="navigate", params={"url": "https://www.google.com"})
            browser(action="snapshot", params={"filtered": true})
        """
        # Normalize params: handle None, empty dict, or string (JSON)
        if params is None:
            p = {}
        elif isinstance(params, str):
            try:
                p = json.loads(params)
            except json.JSONDecodeError as e:
                return error_response(
                    tool="browser",
                    input={"action": action, "params": params},
                    error_type="json_error",
                    code="E4002",
                    message=f"Invalid JSON in params: {e}",
                )
        elif isinstance(params, dict):
            p = params
        else:
            return error_response(
                tool="browser",
                input={"action": action, "params": params},
                error_type="validation_error",
                code="E4001",
                message="params must be a dictionary or JSON string",
            )
        
        a = (action or "").strip().lower()
        if not a:
            return error_response(
                tool="browser",
                input={"action": action, "params": p},
                error_type="validation_error",
                code="E4001",
                message="action is required",
            )
        
        # Credentials check
        user = settings.THORDATA_BROWSER_USERNAME
        pwd = settings.THORDATA_BROWSER_PASSWORD
        if not user or not pwd:
            return error_response(
                tool="browser",
                input={"action": action, "params": p},
                error_type="config_error",
                code="E1001",
                message="Missing browser credentials. Set THORDATA_BROWSER_USERNAME and THORDATA_BROWSER_PASSWORD.",
            )
        session = await ServerContext.get_browser_session()
        if a == "navigate":
            url = str(p.get("url", ""))
            if not url:
                return error_response(tool="browser", input={"action": action, "params": p}, error_type="validation_error", code="E4001", message="Missing url")
            page = await session.get_page(url)
            if page.url != url:
                await page.goto(url, timeout=120_000)
            title = await page.title()
            return ok_response(tool="browser", input={"action": "navigate", "params": p}, output={"url": page.url, "title": title})
        if a == "snapshot":
            filtered = bool(p.get("filtered", True))
            data = await session.capture_snapshot(filtered=filtered)
            aria_snapshot = truncate_content(str(data.get("aria_snapshot", "")))
            dom_snapshot = data.get("dom_snapshot")
            dom_snapshot = truncate_content(str(dom_snapshot)) if dom_snapshot else None
            return ok_response(
                tool="browser",
                input={"action": "snapshot", "params": p},
                output={
                    "url": data.get("url"),
                    "title": data.get("title"),
                    "aria_snapshot": aria_snapshot,
                    "dom_snapshot": dom_snapshot,
                },
            )
        return error_response(
            tool="browser",
            input={"action": action, "params": p},
            error_type="validation_error",
            code="E4001",
            message=f"Unknown action '{action}'. Supported actions: 'navigate', 'snapshot'",
        )

    # -------------------------
    # SMART SCRAPE (compact)
    # -------------------------
    @mcp.tool(name="smart_scrape")
    @handle_mcp_errors
    async def smart_scrape(
        url: str,
        *,
        prefer_structured: bool = True,
        preview: bool = True,
        preview_max_chars: int = 20_000,
        max_wait_seconds: int = 300,
        ctx: Optional[Context] = None,
    ) -> dict[str, Any]:
        """Auto-pick a Web Scraper task for URL; fallback to Unlocker. Always returns structured."""
        await safe_ctx_info(ctx, f"smart_scrape url={url!r} prefer_structured={prefer_structured}")
        host = _hostname(url)
        url_lower = url.lower()

        # Special-case: Google search pages are best handled by SERP (more reliable than Unlocker).
        if prefer_structured:
            from .product import _extract_google_search_query as _extract_q
            from .product import _is_google_search_url as _is_gsearch

            if _is_gsearch(url):
                q = _extract_q(url)
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
                        gl=None,
                        hl=None,
                        location=None,
                        uule=None,
                        ludocid=None,
                        kgmid=None,
                        extra_params={},
                    )
                    data = await client.serp_search_advanced(req)
                    return ok_response(
                        tool="smart_scrape",
                        input={"url": url, "prefer_structured": prefer_structured, "preview": preview},
                        output={
                            "path": "SERP",
                            "serp": {"engine": "google", "q": q, "num": 10, "start": 0},
                            "result": data,
                            "structured": {"url": url, "query": q, "engine": "google"},
                            "candidates": [],
                            "tried": [],
                        },
                    )
                except Exception as e:
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
            tried: list[dict[str, Any]] = []
            for tool, params in candidates[:3]:
                r = await _run_web_scraper_tool(tool=tool, params=params, wait=True, max_wait_seconds=max_wait_seconds, file_type="json", ctx=ctx)
                # Check if task succeeded (status should be Ready/Success, not Failed)
                result_obj = r.get("output") if isinstance(r.get("output"), dict) else {}
                status = result_obj.get("status", "").lower() if isinstance(result_obj, dict) else ""
                
                # If status is Failed, don't try more Web Scraper tools - go to Unlocker
                # Also check if r.get("ok") is False, which indicates the tool call itself failed
                if status == "failed" or r.get("ok") is False:
                    await safe_ctx_info(ctx, f"smart_scrape: Web Scraper tool {tool} failed (status={status}, ok={r.get('ok')}), falling back to Unlocker")
                    tried.append({
                        "tool": tool,
                        "ok": r.get("ok"),
                        "status": status,
                        "error": r.get("error"),
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
                        output={"path": "WEB_SCRAPER", "selected_tool": tool, "selected_params": params, "result": out, "structured": structured, "preview": preview_obj, "tried": tried},
                    )
                tried.append({"tool": tool, "ok": r.get("ok"), "status": status, "error": r.get("error")})

        client = await ServerContext.get_client()
        try:
            html = await client.universal_scrape(url=url, js_render=True, output_format="html")
            html_str = str(html) if not isinstance(html, str) else html
            extracted = _extract_structured_from_html(html_str) if html_str else {}
            structured = _normalize_extracted(extracted, url=url)
            return ok_response(
                tool="smart_scrape",
                input={"url": url, "prefer_structured": prefer_structured, "preview": preview},
                output={
                    "path": "WEB_UNLOCKER",
                    "unlocker": {"html": html_str},
                    "extracted": extracted,
                    "structured": structured,
                    "selected_tool": selected_tool,
                    "selected_params": selected_params,
                    "candidates": [c[0] for c in candidates],
                    "tried": tried if "tried" in locals() else [],
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
                    "tried": tried if "tried" in locals() else [],
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
                    "tried": tried if "tried" in locals() else [],
                },
            )

