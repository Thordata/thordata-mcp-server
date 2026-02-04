"""Common utility helpers for Thordata MCP tools."""
from __future__ import annotations

import functools
import html2text
import json
import logging
import uuid
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
# Enhanced error diagnostics
# ---------------------------------------------------------------------------

def get_error_suggestion(error_type: str, url: Optional[str] = None) -> str:
    """
    Provide helpful suggestions based on error type.

    Args:
        error_type: Type of error encountered
        url: Optional URL that caused the error

    Returns:
        Helpful suggestion string
    """
    suggestions = {
        "timeout": "The request timed out. Try enabling JS rendering or check if the site is accessible.",
        "blocked": "The request was blocked (403/CAPTCHA). The site may have anti-bot protection.",
        "parse_failed": "Failed to parse the response. The site structure may have changed.",
        "not_found": "The requested resource was not found (404).",
        "upstream_timeout": "The upstream service timed out (504). Try again later.",
        "upstream_internal_error": "The upstream service encountered an error (500). Try again later.",
        "network_error": "Network error occurred. Check your internet connection and Thordata service status.",
        "config_error": "Configuration error. Check your API credentials in .env file.",
        "auth_error": "Authentication failed. Verify THORDATA_PUBLIC_TOKEN/THORDATA_PUBLIC_KEY/THORDATA_SCRAPER_TOKEN in .env match your Dashboard credentials.",
        "validation_error": "Parameter validation failed. Ensure 'params' is a dictionary object, not a string. Example: params={'url': 'https://example.com'}",
        "json_error": "Invalid JSON in params. Use dictionary format: params={'url': 'https://example.com'} or valid JSON string: params='{\"url\":\"https://example.com\"}'",
    }

    suggestion = suggestions.get(error_type, "An unexpected error occurred.")

    if url and error_type == "timeout":
        suggestion += f" URL: {url}"

    return suggestion


def diagnose_scraping_error(error: Exception, url: Optional[str] = None) -> dict[str, Any]:
    """
    Diagnose a scraping error and provide detailed information.

    Args:
        error: The exception that occurred
        url: Optional URL that was being scraped

    Returns:
        Dictionary with diagnostic information
    """
    error_info = {
        "error_type": type(error).__name__,
        "error_message": str(error),
        "url": url,
        "timestamp": logging.Formatter().formatTime(logging.LogRecord(
            name="", level=0, pathname="", lineno=0,
            msg="", args=(), exc_info=None
        )),
    }

    # Add specific diagnostics based on error type
    if isinstance(error, ThordataAPIError):
        error_info["api_code"] = getattr(error, "code", None)
        error_info["api_payload"] = getattr(error, "payload", None)
        # Provide a best-effort suggestion based on backend error content.
        payload = error_info.get("api_payload")
        msg = str(getattr(error, "message", str(error)) or "")
        payload_s = ""
        if isinstance(payload, dict):
            payload_s = " ".join(str(v) for v in payload.values())
        combined = f"{msg} {payload_s}".lower()
        if "sign authentication failed" in combined or "authentication failed" in combined or "invalid signature" in combined:
            error_info["suggestion"] = get_error_suggestion("auth_error", url)
        else:
            error_info["suggestion"] = get_error_suggestion("upstream_internal_error", url)
    elif isinstance(error, ThordataNetworkError):
        error_info["suggestion"] = get_error_suggestion("network_error", url)
    elif isinstance(error, ThordataConfigError):
        error_info["suggestion"] = get_error_suggestion("config_error", url)
    elif "timeout" in str(error).lower():
        error_info["suggestion"] = get_error_suggestion("timeout", url)
    elif isinstance(error, ValueError) and "params" in str(error).lower():
        error_info["suggestion"] = get_error_suggestion("validation_error", url)
    elif isinstance(error, json.JSONDecodeError) and "params" in str(error).lower():
        error_info["suggestion"] = get_error_suggestion("json_error", url)
    else:
        error_info["suggestion"] = "An unexpected error occurred. Check logs for details."

    return error_info


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

def ok_response(
    *,
    tool: str,
    input: dict[str, Any],
    output: Any,
    request_id: str | None = None,
) -> dict[str, Any]:
    rid = request_id or uuid.uuid4().hex
    return {"ok": True, "tool": tool, "request_id": rid, "input": input, "output": output}


def error_response(
    *,
    tool: str,
    input: dict[str, Any],
    error_type: str,
    message: str,
    details: Any | None = None,
    code: str = "E0000",
    request_id: str | None = None,
) -> dict[str, Any]:
    """Return a standardized error dict with machine-readable code."""
    rid = request_id or uuid.uuid4().hex
    return {
        "ok": False,
        "tool": tool,
        "request_id": rid,
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
            elif "sign authentication failed" in msg_l or "authentication failed" in msg_l or "invalid signature" in msg_l:
                error_type = "auth_error"
                norm_code = "E1002"
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

            # Attach richer diagnostics without breaking existing callers
            url = None
            if "url" in kwargs:
                url = kwargs.get("url")
            elif "params" in kwargs and isinstance(kwargs.get("params"), dict):
                url = kwargs["params"].get("url")

            diagnostic = diagnose_scraping_error(e, url=url)
            return error_response(
                tool=func.__name__,
                input={k: v for k, v in kwargs.items() if k != "ctx"},
                error_type=error_type,
                code=norm_code,
                message=msg,
                details={"code": code, "payload": payload, "diagnostic": diagnostic},
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

            url = None
            if "url" in kwargs:
                url = kwargs.get("url")
            elif "params" in kwargs and isinstance(kwargs.get("params"), dict):
                url = kwargs["params"].get("url")

            diagnostic = diagnose_scraping_error(e, url=url)
            return error_response(
                tool=func.__name__,
                input={k: v for k, v in kwargs.items() if k != "ctx"},
                error_type=err_type,
                code=error_code,
                message=msg,
                details={"raw_error": err_str, "diagnostic": diagnostic},
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

def _strip_large_data_urls(html: str, *, max_keep_chars: int = 256) -> str:
    """Remove large inlined data: URLs (base64 fonts/images) to reduce token bloat.

    Keeps small data URLs (<= max_keep_chars) to avoid breaking tiny icons.
    """
    import re

    def _repl(m: re.Match[str]) -> str:
        s = m.group(0)
        if len(s) <= max_keep_chars:
            return s
        return 'data:...'

    # Replace any data:... sequences inside quotes.
    return re.sub(r"data:[^\s\"']+", _repl, html)


def _extract_readable_html(html: str) -> str:
    """Best-effort extraction of main readable content.

    Prefer <main> or <article>. Fall back to full document if not found.
    """
    import re

    # Very lightweight heuristics (no extra deps): keep the largest <main>/<article> block.
    candidates: list[str] = []
    for tag in ("main", "article"):
        pattern = re.compile(rf"<{tag}[^>]*>([\\s\\S]*?)</{tag}>", re.IGNORECASE)
        for m in pattern.finditer(html):
            block = m.group(0)
            if block:
                candidates.append(block)
    if not candidates:
        return html
    candidates.sort(key=len, reverse=True)
    return candidates[0]


def html_to_markdown_clean(html: str) -> str:
    try:
        html = _strip_large_data_urls(html)
        html = _extract_readable_html(html)
        text = md(html, heading_style="ATX", strip=["script", "style", "noscript", "nav", "footer", "iframe", "svg"])
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
