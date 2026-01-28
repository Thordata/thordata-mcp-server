from __future__ import annotations

import asyncio
import dataclasses
import inspect
import json
from typing import Any, Optional

from mcp.server.fastmcp import Context, FastMCP
from thordata.types import Engine, SerpRequest
from thordata.tools import ToolRequest

from ..utils import handle_mcp_errors, ok_response, error_response, safe_ctx_info

def register(mcp: FastMCP) -> None:
    """Register high-level entrypoint tools.

    These provide a small surface area similar to competitor MCP servers:
    - search: SERP single/batch
    - scrape: Universal single/batch
    - task_run: Web Scraper Tasks runner (string params)

    Implementation intentionally avoids calling `mcp.call_tool()` to keep debug HTTP
    invocations stable (no request context required).
    """

    # ---------------------------------------------------------------------
    # search
    # ---------------------------------------------------------------------
    @mcp.tool(name="search")
    @handle_mcp_errors
    async def search(
        query: str | None = None,
        *,
        requests: list[dict[str, Any]] | None = None,
        num: int = 10,
        concurrency: int = 5,
        output_format: str = "json",
        ctx: Optional[Context] = None,
    ) -> dict[str, Any]:
        """Search using SERP API. Supports single or batch queries.
        
        Args:
            query: Single search query (if not using batch)
            requests: List of search requests for batch mode
            num: Number of results per query (default: 10)
            concurrency: Max concurrent requests for batch (default: 5, max: 20)
            output_format: "json" (structured JSON) or "html" (raw HTML)
                           Note: SDK supports "json", "html", or "both" (returns both formats)
        """
        if (not query) and not requests:
            return error_response(
                tool="search",
                input={"query": query, "requests": requests},
                error_type="validation_error",
                code="E4001",
                message="Provide query or requests",
            )

        if concurrency < 1:
            concurrency = 1
        if concurrency > 20:
            concurrency = 20

        from thordata_mcp.context import ServerContext

        client = await ServerContext.get_client()
        if requests:
            sem = asyncio.Semaphore(concurrency)

            async def _one(i: int, r: dict[str, Any]) -> dict[str, Any]:
                q = str(r.get("query", ""))
                if not q:
                    return {"index": i, "ok": False, "error": {"type": "validation_error", "message": "Missing query"}}
                n = int(r.get("num", num))
                eng = r.get("engine", Engine.GOOGLE)
                async with sem:
                    req = SerpRequest(query=q, engine=eng, num=n, output_format=output_format)
                    data = await client.serp_search_advanced(req)
                    return {"index": i, "ok": True, "query": q, "output": data}

            await safe_ctx_info(ctx, f"search batch count={len(requests)} concurrency={concurrency}")

            results = await asyncio.gather(*[_one(i, r) for i, r in enumerate(requests)])
            return ok_response(
                tool="search",
                input={"mode": "batch", "count": len(requests), "concurrency": concurrency, "output_format": output_format},
                output={"results": results},
            )

        req = SerpRequest(query=str(query), engine=Engine.GOOGLE, num=num, output_format=output_format)
        data = await client.serp_search_advanced(req)
        return ok_response(
            tool="search",
            input={"mode": "single", "query": query, "num": num, "output_format": output_format},
            output=data,
        )

    # ---------------------------------------------------------------------
    # scrape
    # ---------------------------------------------------------------------
    @mcp.tool(name="scrape")
    @handle_mcp_errors
    async def scrape(
        url: str | None = None,
        *,
        requests: list[dict[str, Any]] | None = None,
        output_format: str = "html",
        js_render: bool = False,
        wait_ms: int | None = None,
        concurrency: int = 5,
        ctx: Optional[Context] = None,
    ) -> dict[str, Any]:
        if (not url) and not requests:
            return error_response(
                tool="scrape",
                input={"url": url, "requests": requests},
                error_type="validation_error",
                code="E4001",
                message="Provide url or requests",
            )

        if concurrency < 1:
            concurrency = 1
        if concurrency > 20:
            concurrency = 20

        from thordata_mcp.context import ServerContext

        client = await ServerContext.get_client()
        if requests:
            sem = asyncio.Semaphore(concurrency)

            async def _one(i: int, r: dict[str, Any]) -> dict[str, Any]:
                u = str(r.get("url", ""))
                if not u:
                    return {"index": i, "ok": False, "error": {"type": "validation_error", "message": "Missing url"}}

                fmt = str(r.get("output_format", output_format))
                render = bool(r.get("js_render", js_render))
                wms = r.get("wait_ms", wait_ms)
                wait_seconds = int(wms / 1000) if isinstance(wms, (int, float)) else None
                extra_params = r.get("extra_params") or {}
                if not isinstance(extra_params, dict):
                    extra_params = {}

                async with sem:
                    data = await client.universal_scrape(
                        url=u,
                        js_render=render,
                        output_format=fmt,
                        wait=wait_seconds,
                        **extra_params,
                    )

                    if fmt.lower() == "png":
                        # Convert PNG bytes to base64 string for JSON serialization
                        import base64
                        if isinstance(data, (bytes, bytearray)):
                            png_base64 = base64.b64encode(data).decode("utf-8")
                            size = len(data)
                        else:
                            png_base64 = str(data)
                            size = None
                        return {"index": i, "ok": True, "url": u, "output": {"png_base64": png_base64, "size": size, "format": "png"}}

                html = str(data) if not isinstance(data, str) else data
                return {"index": i, "ok": True, "url": u, "output": {"html": html}}

            await safe_ctx_info(ctx, f"scrape batch count={len(requests)} concurrency={concurrency}")

            results = await asyncio.gather(*[_one(i, r) for i, r in enumerate(requests)])
            return ok_response(
                tool="scrape",
                input={"mode": "batch", "count": len(requests), "concurrency": concurrency},
                output={"results": results},
            )

        wait_seconds = int(wait_ms / 1000) if wait_ms is not None else None
        data = await client.universal_scrape(
            url=str(url),
            js_render=js_render,
            output_format=output_format,
            wait=wait_seconds,
        )
        if output_format.lower() == "png":
            # Convert PNG bytes to base64 string for JSON serialization
            import base64
            if isinstance(data, (bytes, bytearray)):
                png_base64 = base64.b64encode(data).decode("utf-8")
                size = len(data)
            else:
                png_base64 = str(data)
                size = None
            return ok_response(
                tool="scrape",
                input={"mode": "single", "url": url, "output_format": output_format},
                output={"png_base64": png_base64, "size": size, "format": "png"},
            )
        html = str(data) if not isinstance(data, str) else data
        return ok_response(
            tool="scrape",
            input={"mode": "single", "url": url, "output_format": output_format},
            output={"html": html},
        )

    # ---------------------------------------------------------------------
    # task_run (string params)
    # ---------------------------------------------------------------------
    # Shared tool discovery utilities live in thordata_mcp.tools.utils
    from .utils import iter_tool_request_types, tool_key

    @mcp.tool(name="task_run")
    @handle_mcp_errors
    async def task_run(
        tool: str,
        *,
        param_json: str = "{}",
        wait: bool = True,
        file_type: str = "json",
        max_wait_seconds: int = 300,
        ctx: Optional[Context] = None,
    ) -> dict[str, Any]:
        try:
            params = json.loads(param_json) if param_json else {}
        except json.JSONDecodeError as e:
            return error_response(
                tool="task_run",
                input={"tool": tool, "param_json": param_json},
                error_type="json_error",
                code="E4002",
                message=str(e),
            )

        tools_map = {tool_key(t): t for t in iter_tool_request_types()}
        t = tools_map.get(tool)
        if not t:
            return error_response(
                tool="task_run",
                input={"tool": tool},
                error_type="invalid_tool",
                code="E4003",
                message="Unknown tool key. Use tasks.list to discover valid keys.",
            )

        # Handle common_settings for video tools (YouTube, etc.)
        from thordata.tools.base import VideoToolRequest
        from thordata.types.common import CommonSettings
        
        if issubclass(t, VideoToolRequest) and "common_settings" in params:
            # Convert common_settings dict to CommonSettings object
            cs_dict = params.pop("common_settings", {})
            if isinstance(cs_dict, dict):
                params["common_settings"] = CommonSettings(**cs_dict)
        
        tool_request = t(**params)  # type: ignore[misc]

        from thordata_mcp.context import ServerContext

        client = await ServerContext.get_client()
        task_id = await client.run_tool(tool_request)

        result: dict[str, Any] = {
            "task_id": task_id,
            "spider_id": tool_request.get_spider_id(),
            "spider_name": tool_request.get_spider_name(),
        }

        if wait:
            status = await client.wait_for_task(task_id, max_wait=max_wait_seconds)
            result["status"] = status
            if str(status).lower() in {"ready", "success", "finished"}:
                download_url = await client.get_task_result(task_id, file_type=file_type)
                result["download_url"] = download_url

        return ok_response(
            tool="task_run",
            input={"tool": tool, "wait": wait, "file_type": file_type, "max_wait_seconds": max_wait_seconds},
            output=result,
        )
