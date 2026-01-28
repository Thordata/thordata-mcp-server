"""Common utility helpers for Thordata MCP tools."""
from __future__ import annotations

import functools
import html2text
import logging
from typing import Any, Callable, Optional

from markdownify import markdownify as md
from thordata import (
    ThordataAPIError,
    ThordataConfigError,
    ThordataNetworkError,
)

logger = logging.getLogger("thordata_mcp")


# ---------------------------------------------------------------------------
# Safe Context helpers (for HTTP mode compatibility)
# ---------------------------------------------------------------------------

async def safe_ctx_info(ctx: Optional[Any], message: str) -> None:
    """Safely call ctx.info() if context is available and valid.
    
    In HTTP mode, ctx may exist but not be a valid MCP Context,
    so we wrap the call in try-except to avoid errors.
    """
    if ctx is None:
        return
    try:
        await ctx.info(message)
    except (ValueError, AttributeError):
        # Context not available (e.g., HTTP mode) - silently skip
        pass


# ---------------------------------------------------------------------------
# Structured response helpers (LLM-friendly)
# ---------------------------------------------------------------------------

def ok_response(*, tool: str, input: dict[str, Any], output: Any) -> dict[str, Any]:
    return {"ok": True, "tool": tool, "input": input, "output": output}


def error_response(
    *,
    tool: str,
    input: dict[str, Any],
    error_type: str,
    message: str,
    details: Any | None = None,
    code: str = "E0000",
) -> dict[str, Any]:
    """Return a standardized error dict with machine-readable code."""
    return {
        "ok": False,
        "tool": tool,
        "input": input,
        "error": {"type": error_type, "code": code, "message": message, "details": details},
    }


# ---------------------------------------------------------------------------
# Decorator to convert SDK exceptions to structured output
# ---------------------------------------------------------------------------

def handle_mcp_errors(func: Callable) -> Callable:  # noqa: D401
    """Wrap a tool so it always returns dict instead of raising SDK errors."""

    @functools.wraps(func)
    async def wrapper(*args, **kwargs):  # type: ignore[return-value]
        try:
            return await func(*args, **kwargs)
        except ThordataConfigError as e:
            logger.error("Config error in %s: %s", func.__name__, e)
            return error_response(
                tool=func.__name__,
                input={k: v for k, v in kwargs.items() if k != "ctx"},
                error_type="config_error",
                code="E1001",
                message="Missing or invalid credentials.",
                details=str(e),
            )
        except ThordataAPIError as e:
            logger.error("API error in %s: %s", func.__name__, e)
            msg = getattr(e, "message", str(e))
            payload = getattr(e, "payload", None)
            if isinstance(payload, dict):
                msg = payload.get("msg", msg)
            return error_response(
                tool=func.__name__,
                input={k: v for k, v in kwargs.items() if k != "ctx"},
                error_type="api_error",
                code="E2001",
                message=msg,
                details={"code": getattr(e, "code", None), "payload": payload},
            )
        except ThordataNetworkError as e:
            err_str = str(e)
            if "Task" in err_str and "failed" in err_str:
                error_code = "E3001"
                err_type = "task_failed"
                msg = "Scraping task failed."
            else:
                error_code = "E2002"
                err_type = "network_error"
                msg = "Network error: could not reach Thordata services."
            return error_response(
                tool=func.__name__,
                input={k: v for k, v in kwargs.items() if k != "ctx"},
                error_type=err_type,
                code=error_code,
                message=msg,
                details=err_str,
            )
        except Exception as e:  # pragma: no cover
            logger.exception("Unexpected error in %s", func.__name__)
            return error_response(
                tool=func.__name__,
                input={k: v for k, v in kwargs.items() if k != "ctx"},
                error_type="unexpected_error",
                code="E9000",
                message=str(e),
            )

    return wrapper


# ---------------------------------------------------------------------------
# Helpers for HTML → Markdown & truncation
# ---------------------------------------------------------------------------

def html_to_markdown_clean(html: str) -> str:
    try:
        text = md(html, heading_style="ATX", strip=["script", "style", "nav", "footer", "iframe"])
        lines = [line.rstrip() for line in text.splitlines()]
        return "\n".join(line for line in lines if line)
    except Exception:
        h = html2text.HTML2Text()
        h.ignore_links = False
        return h.handle(html)


def truncate_content(content: str, max_length: int = 20_000) -> str:
    if len(content) <= max_length:
        return content
    return content[:max_length] + f"\n\n... [Content Truncated, original length: {len(content)} chars]"
