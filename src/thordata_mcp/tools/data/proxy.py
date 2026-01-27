"""Proxy Network request tools.

These tools allow the LLM to fetch arbitrary URLs through Thordata's Proxy
Network. BrightData/Oxylabs equivalents expose similar capabilities and are a
core differentiator for competitive scraping products.

Notes:
- HTTPS proxying via aiohttp is not fully supported in the SDK; requests to HTTPS
  targets may raise a ThordataConfigError.
- Response body is truncated to avoid overwhelming the model.
"""

from __future__ import annotations

import json
from typing import Any, Optional

from mcp.server.fastmcp import Context, FastMCP
from thordata import AsyncThordataClient, ThordataConfigError, ThordataNetworkError

from ...config import settings
from ...utils import handle_mcp_errors, ok_response, truncate_content

_MAX_BODY_CHARS = 20_000


def _build_default_proxy_env() -> None:
    """Ensure proxy credentials are present in environment variables."""
    import os

    if settings.THORDATA_RESIDENTIAL_USERNAME and settings.THORDATA_RESIDENTIAL_PASSWORD:
        os.environ.setdefault("THORDATA_RESIDENTIAL_USERNAME", settings.THORDATA_RESIDENTIAL_USERNAME)
        os.environ.setdefault("THORDATA_RESIDENTIAL_PASSWORD", settings.THORDATA_RESIDENTIAL_PASSWORD)
    elif settings.THORDATA_BROWSER_USERNAME and settings.THORDATA_BROWSER_PASSWORD:
        os.environ.setdefault("THORDATA_RESIDENTIAL_USERNAME", settings.THORDATA_BROWSER_USERNAME)
        os.environ.setdefault("THORDATA_RESIDENTIAL_PASSWORD", settings.THORDATA_BROWSER_PASSWORD)


async def _proxy_request(method: str, url: str, **kwargs: Any) -> tuple[int, dict[str, Any], str]:
    _build_default_proxy_env()
    async with AsyncThordataClient() as client:
        try:
            resp = await (client.get(url, **kwargs) if method == "GET" else client.post(url, **kwargs))
        except ThordataConfigError as e:
            raise e
        except Exception as e:  # pragma: no cover
            raise ThordataNetworkError(str(e)) from e

        status = resp.status
        headers = {k: v for k, v in resp.headers.items()}
        text = await resp.text()
        return status, headers, text


def register(mcp: FastMCP) -> None:
    """Register Proxy Network request tools (GET/POST)."""

    @mcp.tool(name="proxy.request.get")
    @handle_mcp_errors
    async def proxy_request_get(url: str, *, ctx: Optional[Context] = None) -> dict[str, Any]:
        """Fetch a URL through Thordata's Proxy Network using GET."""
        if ctx:
            await ctx.info(f"Proxy GET {url[:100]}")
        status, headers, body = await _proxy_request("GET", url)
        return ok_response(
            tool="proxy.request.get",
            input={"url": url},
            output={
                "status_code": status,
                "headers": headers,
                "body": truncate_content(body, _MAX_BODY_CHARS),
            },
        )

    @mcp.tool(name="proxy.request.post")
    @handle_mcp_errors
    async def proxy_request_post(
        url: str,
        *,
        data: str | dict[str, Any] | None = None,
        json_data: Any | None = None,
        ctx: Optional[Context] = None,
    ) -> dict[str, Any]:
        """Fetch a URL through Thordata's Proxy Network using POST.

        This endpoint is tolerant to common caller mistakes:
        - If `data` is a dict, it will be JSON-serialized.
        - If `json_data` is provided, it will be forwarded as JSON.
        """
        if ctx:
            await ctx.info(f"Proxy POST {url[:100]}")

        kwargs: dict[str, Any] = {}
        if json_data is not None:
            kwargs["json"] = json_data
        elif isinstance(data, dict):
            kwargs["data"] = json.dumps(data)
            kwargs.setdefault("headers", {"Content-Type": "application/json"})
        elif data is not None:
            kwargs["data"] = data

        status, headers, body = await _proxy_request("POST", url, **kwargs)
        return ok_response(
            tool="proxy.request.post",
            input={
                "url": url,
                "data_type": type(data).__name__ if data is not None else None,
                "has_json": json_data is not None,
            },
            output={
                "status_code": status,
                "headers": headers,
                "body": truncate_content(body, _MAX_BODY_CHARS),
            },
        )
