import logging
import functools
from typing import Callable, Any
import html2text
from markdownify import markdownify as md
from thordata import ThordataAPIError, ThordataConfigError, ThordataNetworkError

logger = logging.getLogger("thordata_mcp")


def ok_response(*, tool: str, input: dict[str, Any], output: Any) -> dict[str, Any]:
    return {"ok": True, "tool": tool, "input": input, "output": output}


def error_response(
    *,
    tool: str,
    input: dict[str, Any],
    error_type: str,
    message: str,
    details: Any | None = None,
) -> dict[str, Any]:
    return {
        "ok": False,
        "tool": tool,
        "input": input,
        "error": {"type": error_type, "message": message, "details": details},
    }

def handle_mcp_errors(func: Callable) -> Callable:
    """
    Decorator to catch SDK errors and return structured, LLM-friendly dict outputs.
    """
    @functools.wraps(func)
    async def wrapper(*args, **kwargs) -> dict[str, Any]:
        try:
            return await func(*args, **kwargs)
        except ThordataConfigError as e:
            logger.error("Config error in %s: %s", func.__name__, e)
            tool = func.__name__
            safe_input = {k: v for k, v in kwargs.items() if k != "ctx"}
            return error_response(
                tool=tool,
                input=safe_input,
                error_type="config_error",
                message="Missing or invalid credentials. Please check your .env configuration.",
                details=str(e),
            )
        except ThordataAPIError as e:
            logger.error("API error in %s: %s", func.__name__, e)
            tool = func.__name__
            safe_input = {k: v for k, v in kwargs.items() if k != "ctx"}
            msg = getattr(e, "message", str(e))
            payload = getattr(e, "payload", None)
            if isinstance(payload, dict):
                msg = payload.get("msg", msg)
            return error_response(
                tool=tool,
                input=safe_input,
                error_type="api_error",
                message=msg,
                details={"code": getattr(e, "code", None), "payload": payload},
            )
        except ThordataNetworkError as e:
            err_str = str(e)
            if "Task" in err_str and "failed with status" in err_str:
                logger.error("Task failure in %s: %s", func.__name__, e)
                tool = func.__name__
                safe_input = {k: v for k, v in kwargs.items() if k != "ctx"}
                return error_response(
                    tool=tool,
                    input=safe_input,
                    error_type="task_failed",
                    message="Scraping task failed. The target site may have blocked the request or the content is unavailable.",
                    details=err_str,
                )
            
            logger.error("Network error in %s: %s", func.__name__, e)
            tool = func.__name__
            safe_input = {k: v for k, v in kwargs.items() if k != "ctx"}
            return error_response(
                tool=tool,
                input=safe_input,
                error_type="network_error",
                message="Network error: could not reach Thordata services. Please retry.",
                details=err_str,
            )
        except Exception as e:
            logger.exception("Unexpected error in %s", func.__name__)
            tool = func.__name__
            safe_input = {k: v for k, v in kwargs.items() if k != "ctx"}
            return error_response(
                tool=tool,
                input=safe_input,
                error_type="unexpected_error",
                message=str(e),
            )
    return wrapper

def html_to_markdown_clean(html: str) -> str:
    try:
        text = md(html, heading_style="ATX", strip=["script", "style", "nav", "footer", "iframe"])
        lines = [line.rstrip() for line in text.splitlines()]
        text = "\n".join(line for line in lines if line)
        return text
    except Exception:
        h = html2text.HTML2Text()
        h.ignore_links = False
        return h.handle(html)

def truncate_content(content: str, max_length: int = 20000) -> str:
    if len(content) <= max_length:
        return content
    return content[:max_length] + f"\n\n... [Content Truncated, original length: {len(content)} chars]"