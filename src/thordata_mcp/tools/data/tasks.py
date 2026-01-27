from __future__ import annotations

import dataclasses
import inspect
from typing import Any, Optional

from mcp.server.fastmcp import Context, FastMCP
from thordata import AsyncThordataClient
from thordata.tools import ToolRequest

from ...config import settings
from ...utils import handle_mcp_errors, ok_response


def _iter_tool_request_types() -> list[type[ToolRequest]]:
    """
    Enumerate all ToolRequest / VideoToolRequest dataclass types exposed by thordata.tools.

    In the SDK, tools are organized as:
      thordata.tools.Amazon.ProductByAsin, thordata.tools.YouTube.VideoDownload, ...
    Those nested classes are dataclasses inheriting ToolRequest.
    """
    import thordata.tools as tools_module

    out: list[type[ToolRequest]] = []

    def walk(obj: Any) -> None:
        for _, member in inspect.getmembers(obj):
            if inspect.isclass(member):
                # Skip base classes
                if member is ToolRequest:
                    continue
                if issubclass(member, ToolRequest) and dataclasses.is_dataclass(member):
                    out.append(member)
                else:
                    # Namespace classes like Amazon/GoogleMaps contain nested ToolRequest classes
                    walk(member)

    walk(tools_module)

    # Deterministic ordering
    out.sort(key=lambda t: f"{t.__module__}.{t.__qualname__}")
    return out


def _tool_key(t: type[ToolRequest]) -> str:
    # e.g. "thordata.tools.ecommerce.Amazon.ProductByAsin"
    return f"{t.__module__}.{t.__qualname__}"


def _tool_schema(t: type[ToolRequest]) -> dict[str, Any]:
    fields: dict[str, Any] = {}
    for name, f in t.__dataclass_fields__.items():  # type: ignore[attr-defined]
        fields[name] = {
            "type": getattr(getattr(f.type, "__name__", None), "lower", lambda: str(f.type))(),
            "default": None if f.default is dataclasses.MISSING else f.default,
        }
    return {
        "key": _tool_key(t),
        "spider_id": getattr(t, "SPIDER_ID", None),
        "spider_name": getattr(t, "SPIDER_NAME", None),
        "fields": fields,
    }


def register(mcp: FastMCP) -> None:
    """Register Web Scraper Tasks tools (100% SDK coverage via generic runner + discovery)."""

    @mcp.tool(name="tasks.list")
    @handle_mcp_errors
    async def tasks_list_tools(ctx: Optional[Context] = None) -> dict[str, Any]:
        """List all available SDK tool request types and their parameter schemas."""
        tools = _iter_tool_request_types()
        if ctx:
            await ctx.info(f"Discovered {len(tools)} SDK tools.")
        return ok_response(
            tool="tasks.list",
            input={},
            output={"tools": [_tool_schema(t) for t in tools]},
        )

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
        """Run a Web Scraper SDK tool by key and return task details."""
        tools = {_tool_key(t): t for t in _iter_tool_request_types()}
        t = tools.get(tool)
        if not t:
            return {
                "ok": False,
                "tool": "tasks.run",
                "input": {"tool": tool, "params": params},
                "error": {
                    "type": "invalid_tool",
                    "message": "Unknown tool key. Use tasks.list to discover valid keys.",
                },
            }

        if ctx:
            await ctx.info(f"Running SDK tool: {tool}")

        tool_request = t(**params)  # type: ignore[misc]

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

            return ok_response(
                tool="tasks.run",
                input={
                    "tool": tool,
                    "params": params,
                    "wait": wait,
                    "max_wait_seconds": max_wait_seconds,
                    "file_type": file_type,
                },
                output=result,
            )

    @mcp.tool(name="tasks.status")
    @handle_mcp_errors
    async def tasks_status(task_id: str, *, ctx: Optional[Context] = None) -> dict[str, Any]:
        """Get task status."""
        if ctx:
            await ctx.info(f"Getting task status: {task_id}")

        async with AsyncThordataClient(
            scraper_token=settings.THORDATA_SCRAPER_TOKEN,
            public_token=settings.THORDATA_PUBLIC_TOKEN,
            public_key=settings.THORDATA_PUBLIC_KEY,
        ) as client:
            status = await client.get_task_status(task_id)
            return ok_response(
                tool="tasks.status",
                input={"task_id": task_id},
                output={"task_id": task_id, "status": status},
            )

    @mcp.tool(name="tasks.wait")
    @handle_mcp_errors
    async def tasks_wait(
        task_id: str,
        *,
        poll_interval_seconds: float = 5.0,
        max_wait_seconds: float = 600.0,
        ctx: Optional[Context] = None,
    ) -> dict[str, Any]:
        """Wait until a task reaches a terminal status."""
        if ctx:
            await ctx.info(
                f"Waiting for task: {task_id} poll_interval={poll_interval_seconds} max_wait={max_wait_seconds}"
            )

        async with AsyncThordataClient(
            scraper_token=settings.THORDATA_SCRAPER_TOKEN,
            public_token=settings.THORDATA_PUBLIC_TOKEN,
            public_key=settings.THORDATA_PUBLIC_KEY,
        ) as client:
            status = await client.wait_for_task(
                task_id, poll_interval=poll_interval_seconds, max_wait=max_wait_seconds
            )
            return ok_response(
                tool="tasks.wait",
                input={
                    "task_id": task_id,
                    "poll_interval_seconds": poll_interval_seconds,
                    "max_wait_seconds": max_wait_seconds,
                },
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
        """Get a task result download URL."""
        if ctx:
            await ctx.info(f"Getting task result: {task_id} file_type={file_type}")

        async with AsyncThordataClient(
            scraper_token=settings.THORDATA_SCRAPER_TOKEN,
            public_token=settings.THORDATA_PUBLIC_TOKEN,
            public_key=settings.THORDATA_PUBLIC_KEY,
        ) as client:
            download_url = await client.get_task_result(task_id, file_type=file_type)
            return ok_response(
                tool="tasks.result",
                input={"task_id": task_id, "file_type": file_type},
                output={"task_id": task_id, "download_url": download_url},
            )