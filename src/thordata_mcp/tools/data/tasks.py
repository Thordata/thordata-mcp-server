"""Web Scraper Tasks tools – 100 % SDK coverage.

Exposes:
  tasks.list            – enumerate SDK ToolRequest classes
  tasks.run             – run tool (with params dict)
  tasks.run_simple      – same as run but takes param_json (string) for easy LLM use
  tasks.status / wait / result – lifecycle helpers
"""
from __future__ import annotations

import dataclasses
import inspect
import json
import sys
import importlib
import pkgutil
from typing import Any, Optional

from mcp.server.fastmcp import Context, FastMCP
from thordata import AsyncThordataClient
from thordata.tools import ToolRequest

from ...config import settings
from ...utils import handle_mcp_errors, ok_response, safe_ctx_info
from ..utils import iter_tool_request_types, tool_key, tool_schema

# Increase recursion limit to avoid "maximum recursion depth" on Windows
sys.setrecursionlimit(max(sys.getrecursionlimit(), 5000))


# ---------------------------------------------------------------------------
# MCP tool registrations
# ---------------------------------------------------------------------------

def register_list_only(mcp: FastMCP) -> None:
    """Register only tasks.list tool (for core mode)."""
    tools_cache: list[type[ToolRequest]] | None = None  # lazy cache

    def _ensure_cache() -> list[type[ToolRequest]]:
        nonlocal tools_cache
        if tools_cache is None:
            tools_cache = iter_tool_request_types()
        return tools_cache

    @mcp.tool(name="tasks.list")
    @handle_mcp_errors
    async def tasks_list(ctx: Optional[Context] = None) -> dict[str, Any]:
        all_tools = _ensure_cache()
        await safe_ctx_info(ctx, f"Discovered {len(all_tools)} SDK tools.")
        return ok_response(tool="tasks.list", input={}, output={"tools": [tool_schema(t) for t in all_tools]})


def register(mcp: FastMCP) -> None:
    tools_cache: list[type[ToolRequest]] | None = None  # lazy cache

    def _ensure_cache() -> list[type[ToolRequest]]:
        nonlocal tools_cache
        if tools_cache is None:
            tools_cache = _iter_tool_request_types()
        return tools_cache

    # ────────────────────────────────────────────────────────────
    # tasks.list
    # ────────────────────────────────────────────────────────────
    @mcp.tool(name="tasks.list")
    @handle_mcp_errors
    async def tasks_list(ctx: Optional[Context] = None) -> dict[str, Any]:
        all_tools = _ensure_cache()
        await safe_ctx_info(ctx, f"Discovered {len(all_tools)} SDK tools.")
        return ok_response(tool="tasks.list", input={}, output={"tools": [_tool_schema(t) for t in all_tools]})

    # ────────────────────────────────────────────────────────────
    # core runner – tasks.run
    # ────────────────────────────────────────────────────────────
    async def _run_tool(
        *,
        tool_key: str,
        params: dict[str, Any],
        wait: bool,
        max_wait_seconds: int,
        file_type: str,
        ctx: Optional[Context],
    ) -> dict[str, Any]:
        tools_map = {tool_key(t): t for t in _ensure_cache()}
        t = tools_map.get(tool_key)
        if not t:
            return {
                "ok": False,
                "tool": "tasks.run",
                "input": {"tool": tool_key, "params": params},
                "error": {
                    "type": "invalid_tool",
                    "message": "Unknown tool key. Use tasks.list to discover valid keys.",
                },
            }
        tool_request = t(**params)  # type: ignore[misc]
        await safe_ctx_info(ctx, f"Running SDK tool: {tool_key}")
        async with AsyncThordataClient(
            scraper_token=settings.THORDATA_SCRAPER_TOKEN,
            public_token=settings.THORDATA_PUBLIC_TOKEN,
            public_key=settings.THORDATA_PUBLIC_KEY,
        ) as client:
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
            return result

    @mcp.tool(name="tasks.run")
    @handle_mcp_errors
    async def tasks_run(
        tool: str,
        params: dict[str, Any],
        *,
        wait: bool = True,
        max_wait_seconds: int = 300,
        file_type: str = "json",
        ctx: Optional[Context] = None,
    ) -> dict[str, Any]:
        output = await _run_tool(
            tool_key=tool,
            params=params,
            wait=wait,
            max_wait_seconds=max_wait_seconds,
            file_type=file_type,
            ctx=ctx,
        )
        return ok_response(
            tool="tasks.run",
            input={"tool": tool, "params": params, "wait": wait},
            output=output,
        )

    # ────────────────────────────────────────────────────────────
    # run_simple – pass params as JSON string (for LLM convenience)
    # ────────────────────────────────────────────────────────────
    @mcp.tool(name="tasks.run_simple")
    @handle_mcp_errors
    async def tasks_run_simple(
        tool: str,
        param_json: str = "{}",
        *,
        wait: bool = True,
        file_type: str = "json",
        max_wait_seconds: int = 300,
        ctx: Optional[Context] = None,
    ) -> dict[str, Any]:
        try:
            params_dict = json.loads(param_json) if param_json else {}
        except json.JSONDecodeError as e:
            return {
                "ok": False,
                "tool": "tasks.run_simple",
                "input": {"tool": tool, "param_json": param_json},
                "error": {"type": "json_error", "message": str(e)},
            }
        output = await _run_tool(
            tool_key=tool,
            params=params_dict,
            wait=wait,
            max_wait_seconds=max_wait_seconds,
            file_type=file_type,
            ctx=ctx,
        )
        return ok_response(
            tool="tasks.run_simple",
            input={"tool": tool, "param_json": param_json, "wait": wait},
            output=output,
        )

    # ────────────────────────────────────────────────────────────
    # status / wait / result helpers (unchanged)
    # ────────────────────────────────────────────────────────────
    @mcp.tool(name="tasks.status")
    @handle_mcp_errors
    async def tasks_status(task_id: str, *, ctx: Optional[Context] = None) -> dict[str, Any]:
        await safe_ctx_info(ctx, f"Getting task status: {task_id}")
        async with AsyncThordataClient(
            scraper_token=settings.THORDATA_SCRAPER_TOKEN,
            public_token=settings.THORDATA_PUBLIC_TOKEN,
            public_key=settings.THORDATA_PUBLIC_KEY,
        ) as client:
            status = await client.get_task_status(task_id)
            return ok_response(tool="tasks.status", input={"task_id": task_id}, output={"task_id": task_id, "status": status})

    @mcp.tool(name="tasks.wait")
    @handle_mcp_errors
    async def tasks_wait(
        task_id: str,
        *,
        poll_interval_seconds: float = 5.0,
        max_wait_seconds: float = 600.0,
        ctx: Optional[Context] = None,
    ) -> dict[str, Any]:
        await safe_ctx_info(ctx, f"Waiting for task {task_id}")
        async with AsyncThordataClient(
            scraper_token=settings.THORDATA_SCRAPER_TOKEN,
            public_token=settings.THORDATA_PUBLIC_TOKEN,
            public_key=settings.THORDATA_PUBLIC_KEY,
        ) as client:
            status = await client.wait_for_task(task_id, poll_interval=poll_interval_seconds, max_wait=max_wait_seconds)
            return ok_response(
                tool="tasks.wait",
                input={"task_id": task_id},
                output={"task_id": task_id, "status": status},
            )

    @mcp.tool(name="tasks.result")
    @handle_mcp_errors
    async def tasks_result(
        task_id: str,
        *,
        file_type: str = "json",
        ctx: Optional[Context] = None,
    ) -> dict[str, Any]:
        await safe_ctx_info(ctx, f"Getting result for {task_id}")
        async with AsyncThordataClient(
            scraper_token=settings.THORDATA_SCRAPER_TOKEN,
            public_token=settings.THORDATA_PUBLIC_TOKEN,
            public_key=settings.THORDATA_PUBLIC_KEY,
        ) as client:
            download_url = await client.get_task_result(task_id, file_type=file_type)
            return ok_response(
                tool="tasks.result",
                input={"task_id": task_id},
                output={"task_id": task_id, "download_url": download_url},
            )
