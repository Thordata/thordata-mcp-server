import logging
import functools
from typing import Callable, Any
import html2text
from markdownify import markdownify as md
from thordata import ThordataAPIError, ThordataConfigError, ThordataNetworkError

# 设置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("thordata_mcp")

def handle_mcp_errors(func: Callable) -> Callable:
    """
    Decorator to catch SDK errors and return LLM-friendly error messages.
    """
    @functools.wraps(func)
    async def wrapper(*args, **kwargs) -> str:
        try:
            return await func(*args, **kwargs)
        except ThordataConfigError as e:
            logger.error(f"Config Error in {func.__name__}: {e}")
            return f"❌ Configuration Error: Missing API Tokens. Please check your .env file. ({str(e)})"
        except ThordataAPIError as e:
            # 这是一个 API 业务层面的错误 (如 Task Failed, 余额不足)
            logger.error(f"API Error in {func.__name__}: {e}")
            msg = e.message
            if e.payload and isinstance(e.payload, dict):
                msg = e.payload.get('msg', msg)
            return f"❌ API Task Failed: {msg} (Code: {e.code})"
        except ThordataNetworkError as e:
            # 这是真正的网络错误 (连接超时, DNS失败)
            # 但要注意：SDK 的 run_task 抛出 ThordataNetworkError 包含了 "Task failed with status: ..."
            # 我们需要区分这两种情况
            err_str = str(e)
            if "Task" in err_str and "failed with status" in err_str:
                 logger.error(f"Task Failed Logic: {e}")
                 return f"❌ Scraping Task Failed: The target site may have blocked the request or the content is unavailable. ({err_str})"
            
            logger.error(f"Network Error in {func.__name__}: {e}")
            return f"❌ Network Connection Error: Could not reach ThorData servers. Please retry."
        except Exception as e:
            logger.exception(f"Unexpected Error in {func.__name__}")
            return f"❌ Unexpected Error: {str(e)}"
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