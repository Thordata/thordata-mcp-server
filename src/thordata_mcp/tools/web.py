from typing import Optional
from mcp.server.fastmcp import FastMCP, Context
from thordata import AsyncThordataClient
from ..config import settings
from ..utils import html_to_markdown_clean, truncate_content

def register(mcp: FastMCP):
    """Register general web capabilities."""
    
    @mcp.tool()
    async def google_search(query: str, num: int = 5, ctx: Optional[Context] = None) -> str:
        """
        Search Google for real-time information.
        Args:
            query: Search keywords.
            num: Number of results (default 5).
        """
        async with AsyncThordataClient(scraper_token=settings.THORDATA_SCRAPER_TOKEN) as client:
            try:
                results = await client.serp_search(query=query, engine="google", num=num)
                organic = results.get("organic", [])
                if not organic:
                    return "No results found."
                
                # 格式化为 Markdown 列表，节省 Token
                output = []
                for item in organic:
                    title = item.get("title", "No Title")
                    link = item.get("link", "#")
                    snippet = item.get("snippet", "")
                    output.append(f"### [{title}]({link})\n{snippet}\n")
                
                return "\n".join(output)
            except Exception as e:
                return f"Error performing search: {str(e)}"

    @mcp.tool()
    async def read_url(url: str, ctx: Optional[Context] = None) -> str:
        """
        Visit a webpage and extract its content as clean Markdown.
        Capable of rendering JavaScript (SPA/React sites).
        """
        if ctx: await ctx.info(f"Reading URL: {url}")
            
        async with AsyncThordataClient(scraper_token=settings.THORDATA_SCRAPER_TOKEN) as client:
            try:
                html = await client.universal_scrape(
                    url=url,
                    js_render=True, # 默认开启 JS 渲染，保证兼容性
                    output_format="html"
                )
                markdown = html_to_markdown_clean(str(html))
                return truncate_content(markdown)
            except Exception as e:
                return f"Error reading page: {str(e)}"