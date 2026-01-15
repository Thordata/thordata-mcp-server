import html2text
from markdownify import markdownify as md

def html_to_markdown_clean(html: str) -> str:
    """
    Convert HTML to Markdown using a hybrid approach for best LLM readability.
    """
    try:
        # 优先使用 markdownify，它处理表格和链接更好
        text = md(html, heading_style="ATX", strip=["script", "style"])
        
        # 简单的后处理：去除过多的空行
        lines = [line.rstrip() for line in text.splitlines()]
        text = "\n".join(line for line in lines if line)
        
        return text
    except Exception:
        # 降级方案
        h = html2text.HTML2Text()
        h.ignore_links = False
        return h.handle(html)

def truncate_content(content: str, max_length: int = 15000) -> str:
    if len(content) <= max_length:
        return content
    return content[:max_length] + f"\n\n... [Content Truncated, original length: {len(content)} chars]"