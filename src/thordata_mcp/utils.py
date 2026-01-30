"""Common utility helpers for Thordata MCP tools."""
from __future__ import annotations

import functools
import html2text
import logging
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
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
            code = getattr(e, "code", None)
            # Try to normalize common backend codes/messages for better UX
            error_type = "api_error"
            norm_code = "E2001"
            msg_l = str(msg).lower()
            if isinstance(payload, dict):
                msg = payload.get("msg", msg)
                # Some backend errors embed more detail in payload fields
                if isinstance(payload.get("error"), str) and not msg:
                    msg = payload["error"]
                if isinstance(payload.get("message"), str) and not msg:
                    msg = payload["message"]
            # Heuristics for frequent categories
            if "captcha" in msg_l or "403" in msg_l:
                error_type = "blocked"
                norm_code = "E2101"
            elif "not collected" in msg_l or "failed to parse" in msg_l:
                error_type = "parse_failed"
                norm_code = "E2102"
            elif "not exist" in msg_l or "404" in msg_l:
                error_type = "not_found"
                norm_code = "E2104"
            elif "504" in msg_l or "gateway timeout" in msg_l:
                error_type = "upstream_timeout"
                norm_code = "E2105"
            elif "500" in msg_l or "internal server error" in msg_l:
                error_type = "upstream_internal_error"
                norm_code = "E2106"
            elif "subtitles_error" in msg_l or "unable to download api page" in msg_l:
                error_type = "media_backend_error"
                norm_code = "E2107"
            return error_response(
                tool=func.__name__,
                input={k: v for k, v in kwargs.items() if k != "ctx"},
                error_type=error_type,
                code=norm_code,
                message=msg,
                details={"code": code, "payload": payload},
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
            # Use logger.error instead of logger.exception to avoid rich traceback issues
            logger.error("Unexpected error in %s: %s", func.__name__, str(e), exc_info=False)
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


# ---------------------------------------------------------------------------
# Download URL helpers
# ---------------------------------------------------------------------------

def enrich_download_url(download_url: str, *, task_id: str | None = None, file_type: str | None = None) -> str:
    """Ensure returned download URLs are directly usable in a browser.

    Some SDK / backend paths may return a URL missing required query params such as
    `api_key` and `plat`, leading to {"error":"Missing necessary parameters."}.
    """
    try:
        from .config import settings
    except Exception:  # pragma: no cover
        settings = None  # type: ignore[assignment]

    token = getattr(settings, "THORDATA_SCRAPER_TOKEN", None) if settings else None
    plat = getattr(settings, "THORDATA_DOWNLOAD_PLAT", "1") if settings else "1"
    base = getattr(settings, "THORDATA_DOWNLOAD_BASE_URL", "https://scraperapi.thordata.com/download") if settings else "https://scraperapi.thordata.com/download"

    # If we can't enrich (no token), return as-is.
    if not token:
        return download_url

    parsed = urlparse(download_url)
    qs = dict(parse_qsl(parsed.query, keep_blank_values=True))

    # Backfill known parameters
    if "api_key" not in qs:
        qs["api_key"] = token
    if "plat" not in qs and plat:
        qs["plat"] = plat
    if "task_id" not in qs and task_id:
        qs["task_id"] = task_id
    if "type" not in qs and file_type:
        qs["type"] = file_type

    # If SDK returned a relative/alternate host, normalize to configured base
    if not parsed.scheme or not parsed.netloc:
        parsed = urlparse(base)
    elif parsed.path.rstrip("/") != urlparse(base).path.rstrip("/"):
        # Keep original host, only fix query; unless path looks non-download
        pass

    new_query = urlencode(qs, doseq=True)
    new_parsed = parsed._replace(query=new_query)
    # If original URL had a different host/path but is a valid absolute URL, preserve them.
    if parsed.scheme and parsed.netloc and urlparse(download_url).scheme and urlparse(download_url).netloc:
        orig = urlparse(download_url)
        new_parsed = orig._replace(query=new_query)

    return urlunparse(new_parsed)
