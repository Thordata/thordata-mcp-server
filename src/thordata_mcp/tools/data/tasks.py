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
from ...utils import handle_mcp_errors, ok_response, safe_ctx_info, enrich_download_url
from ..utils import iter_tool_request_types, tool_key, tool_schema, tool_group_from_key, matches_any_prefix_or_exact

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
    async def tasks_list(
        *,
        mode: str | None = None,
        group: str | None = None,
        keyword: str | None = None,
        limit: int | None = None,
        offset: int = 0,
        ctx: Optional[Context] = None,
    ) -> dict[str, Any]:
        all_tools = _ensure_cache()
        resolved_mode = (mode or settings.THORDATA_TASKS_LIST_MODE or "curated").strip().lower()
        resolved_limit = int(limit if limit is not None else settings.THORDATA_TASKS_LIST_DEFAULT_LIMIT)
        resolved_limit = max(1, min(resolved_limit, 500))
        resolved_offset = max(0, int(offset))

        groups_allow = [g.strip().lower() for g in (settings.THORDATA_TASKS_GROUPS or "").split(",") if g.strip()]

        def _matches(t: type[ToolRequest]) -> bool:
            k = tool_key(t)
            g = tool_group_from_key(k).lower()
            if resolved_mode != "all" and groups_allow and g not in groups_allow:
                return False
            if group and g != group.strip().lower():
                return False
            if keyword:
                kw = keyword.strip().lower()
                if kw and (kw not in k.lower()) and (kw not in (getattr(t, "SPIDER_ID", "") or "").lower()) and (kw not in (getattr(t, "SPIDER_NAME", "") or "").lower()):
                    return False
            return True

        filtered = [t for t in all_tools if _matches(t)]
        total = len(filtered)
        page = filtered[resolved_offset : resolved_offset + resolved_limit]

        # basic group stats for UX
        group_counts: dict[str, int] = {}
        for t in filtered:
            g = tool_group_from_key(tool_key(t))
            group_counts[g] = group_counts.get(g, 0) + 1

        await safe_ctx_info(ctx, f"tasks.list mode={resolved_mode} total={total} offset={resolved_offset} limit={resolved_limit}")
        return ok_response(
            tool="tasks.list",
            input={"mode": resolved_mode, "group": group, "keyword": keyword, "limit": resolved_limit, "offset": resolved_offset},
            output={
                "tools": [tool_schema(t) for t in page],
                "meta": {"total": total, "returned": len(page), "offset": resolved_offset, "limit": resolved_limit, "groups": group_counts},
            },
        )

    @mcp.tool(name="tasks.groups")
    @handle_mcp_errors
    async def tasks_groups(ctx: Optional[Context] = None) -> dict[str, Any]:
        """Return discovered tool groups and counts (for UX/discovery)."""
        all_tools = _ensure_cache()
        group_counts: dict[str, int] = {}
        for t in all_tools:
            g = tool_group_from_key(tool_key(t))
            group_counts[g] = group_counts.get(g, 0) + 1
        await safe_ctx_info(ctx, f"tasks.groups groups={len(group_counts)} tools={len(all_tools)}")
        return ok_response(
            tool="tasks.groups",
            input={},
            output={"groups": [{"id": k, "count": v} for k, v in sorted(group_counts.items())], "total": len(all_tools)},
        )


def register(mcp: FastMCP) -> None:
    tools_cache: list[type[ToolRequest]] | None = None  # lazy cache

    def _ensure_cache() -> list[type[ToolRequest]]:
        nonlocal tools_cache
        if tools_cache is None:
            tools_cache = iter_tool_request_types()
        return tools_cache

    # ────────────────────────────────────────────────────────────
    # tasks.list
    # ────────────────────────────────────────────────────────────
    @mcp.tool(name="tasks.list")
    @handle_mcp_errors
    async def tasks_list(
        *,
        mode: str | None = None,
        group: str | None = None,
        keyword: str | None = None,
        limit: int | None = None,
        offset: int = 0,
        ctx: Optional[Context] = None,
    ) -> dict[str, Any]:
        all_tools = _ensure_cache()
        resolved_mode = (mode or settings.THORDATA_TASKS_LIST_MODE or "curated").strip().lower()
        resolved_limit = int(limit if limit is not None else settings.THORDATA_TASKS_LIST_DEFAULT_LIMIT)
        resolved_limit = max(1, min(resolved_limit, 500))
        resolved_offset = max(0, int(offset))

        groups_allow = [g.strip().lower() for g in (settings.THORDATA_TASKS_GROUPS or "").split(",") if g.strip()]

        def _matches(t: type[ToolRequest]) -> bool:
            k = tool_key(t)
            g = tool_group_from_key(k).lower()
            if resolved_mode != "all" and groups_allow and g not in groups_allow:
                return False
            if group and g != group.strip().lower():
                return False
            if keyword:
                kw = keyword.strip().lower()
                if kw and (kw not in k.lower()) and (kw not in (getattr(t, "SPIDER_ID", "") or "").lower()) and (kw not in (getattr(t, "SPIDER_NAME", "") or "").lower()):
                    return False
            return True

        filtered = [t for t in all_tools if _matches(t)]
        total = len(filtered)
        page = filtered[resolved_offset : resolved_offset + resolved_limit]

        group_counts: dict[str, int] = {}
        for t in filtered:
            g = tool_group_from_key(tool_key(t))
            group_counts[g] = group_counts.get(g, 0) + 1

        await safe_ctx_info(ctx, f"tasks.list mode={resolved_mode} total={total} offset={resolved_offset} limit={resolved_limit}")
        return ok_response(
            tool="tasks.list",
            input={"mode": resolved_mode, "group": group, "keyword": keyword, "limit": resolved_limit, "offset": resolved_offset},
            output={
                "tools": [tool_schema(t) for t in page],
                "meta": {"total": total, "returned": len(page), "offset": resolved_offset, "limit": resolved_limit, "groups": group_counts},
            },
        )

    @mcp.tool(name="tasks.groups")
    @handle_mcp_errors
    async def tasks_groups(ctx: Optional[Context] = None) -> dict[str, Any]:
        """Return discovered tool groups and counts (for UX/discovery)."""
        all_tools = _ensure_cache()
        group_counts: dict[str, int] = {}
        for t in all_tools:
            g = tool_group_from_key(tool_key(t))
            group_counts[g] = group_counts.get(g, 0) + 1
        await safe_ctx_info(ctx, f"tasks.groups groups={len(group_counts)} tools={len(all_tools)}")
        return ok_response(
            tool="tasks.groups",
            input={},
            output={"groups": [{"id": k, "count": v} for k, v in sorted(group_counts.items())], "total": len(all_tools)},
        )

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
        # Optional allowlist enforcement (keeps LLM from randomly calling obscure tools)
        allow_raw = (settings.THORDATA_TASKS_ALLOWLIST or "").strip()
        if allow_raw:
            allow = [x.strip() for x in allow_raw.split(",") if x.strip()]
            if not matches_any_prefix_or_exact(tool_key, allow):
                return {
                    "ok": False,
                    "tool": "tasks.run",
                    "input": {"tool": tool_key, "params": params},
                    "error": {
                        "type": "not_allowed",
                        "message": "Tool is not allowed by server allowlist configuration.",
                        "details": {"tool": tool_key},
                    },
                }
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
                    result["download_url"] = enrich_download_url(download_url, task_id=task_id, file_type=file_type)
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
                output={"task_id": task_id, "download_url": enrich_download_url(download_url, task_id=task_id, file_type=file_type)},
            )
