from __future__ import annotations

import json
from typing import Any, List

from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from mcp.server.fastmcp import FastMCP

__all__ = ["create_debug_routes"]


def _json_body(request: Request) -> dict[str, Any]:
    try:
        return json.loads(request._body.decode("utf-8")) if hasattr(request, "_body") else {}
    except Exception:
        return {}


def _jsonify(data: Any) -> Any:
    """Best-effort make data JSON serializable."""
    if isinstance(data, (str, int, float, bool)) or data is None:
        return data
    if isinstance(data, dict):
        return {k: _jsonify(v) for k, v in data.items()}
    if isinstance(data, list):
        return [_jsonify(i) for i in data]
    if hasattr(data, "model_dump"):
        return _jsonify(data.model_dump())  # pydantic BaseModel
    return str(data)


def create_debug_routes(mcp_app: FastMCP, base_path: str = "/debug") -> List[Route]:
    """Return Starlette Route objects for debug API."""

    async def list_tools(request: Request) -> Response:
        tools_raw = await mcp_app.list_tools()
        tools: list[dict[str, Any]] = []
        for t in tools_raw:
            if isinstance(t, dict):
                tools.append(t)
            else:
                tools.append({
                    "name": getattr(t, "name", None),
                    "description": getattr(t, "description", None),
                })
        return JSONResponse({"ok": True, "tools": tools})

    async def call_tool(request: Request) -> Response:
        payload = await request.json() if request.headers.get("content-type","").startswith("application/json") else _json_body(request)
        name = payload.get("name")
        tool_input = payload.get("input") or {}
        if not isinstance(name, str):
            return JSONResponse({"ok": False, "error": "Missing tool name"}, status_code=400)
        if not isinstance(tool_input, dict):
            return JSONResponse({"ok": False, "error": "input must be object"}, status_code=400)
        try:
            # Use internal tool manager to bypass ContentBlock objects
            tool_manager = getattr(mcp_app, "_tool_manager", None)
            if tool_manager is None:
                return JSONResponse({"ok": False, "error": "Tool manager not available"}, status_code=500)
            result = await tool_manager.call_tool(name, tool_input, context=None, convert_result=False)
            return JSONResponse({"ok": True, "tool": name, "input": tool_input, "result": _jsonify(result)})
        except Exception as e:
            return JSONResponse({"ok": False, "error": str(e)}, status_code=500)

    return [
        Route(f"{base_path}/tools/list", list_tools, methods=["POST"]),
        Route(f"{base_path}/tools/call", call_tool, methods=["POST"]),
    ]
