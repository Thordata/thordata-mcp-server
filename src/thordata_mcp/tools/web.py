import asyncio
from typing import Optional, List
from mcp.server.fastmcp import FastMCP, Context
from thordata import AsyncThordataClient
from ..config import settings
from ..utils import html_to_markdown_clean, truncate_content, handle_mcp_errors

def register(mcp: FastMCP):
    """Register general web capabilities."""
    
    @mcp.tool()
    @handle_mcp_errors
    async def google_search(query: str, num: int = 5, ctx: Optional[Context] = None) -> str:
        """
        Search Google for real-time information.
        
        Args:
            query: Search keywords.
            num: Number of results (default 5, max 10).
        """
        async with AsyncThordataClient(scraper_token=settings.THORDATA_SCRAPER_TOKEN) as client:
            if ctx: await ctx.info(f"Searching Google: {query}")
            
            results = await client.serp_search(query=query, engine="google", num=num)
            organic = results.get("organic", [])
            
            if not organic:
                return "No results found."
            
            # 格式化为 Markdown 列表，包含引用链接
            output = []
            for i, item in enumerate(organic, 1):
                title = item.get("title", "No Title")
                link = item.get("link", "#")
                snippet = item.get("snippet", "No description available.")
                output.append(f"{i}. **[{title}]({link})**\n   {snippet}")
            
            return "\n\n".join(output)

    @mcp.tool()
    @handle_mcp_errors
    async def read_url(url: str, ctx: Optional[Context] = None) -> str:
        """
        Visit a webpage and extract its content as clean Markdown.
        Capable of rendering JavaScript (SPA/React sites) and bypassing anti-bot protections.
        """
        if ctx: await ctx.info(f"Reading URL: {url}")
            
        async with AsyncThordataClient(scraper_token=settings.THORDATA_SCRAPER_TOKEN) as client:
            html = await client.universal_scrape(
                url=url,
                js_render=True, 
                output_format="html",
                # 增加等待时间以确保动态内容加载
                wait=2000
            )
            # 确保 html 是字符串
            html_str = str(html) if not isinstance(html, str) else html
            markdown = html_to_markdown_clean(html_str)
            return truncate_content(markdown)
        
    @mcp.tool()
    @handle_mcp_errors
    async def google_search_batch(queries: List[str], num: int = 3, ctx: Optional[Context] = None) -> str:
        """
        Run multiple Google searches in parallel.
        Useful for comprehensive research on a topic.
        """
        if len(queries) > 5: return "Error: Max 5 queries allowed per batch."
        
        if ctx: await ctx.info(f"Batch searching: {queries}")

        async with AsyncThordataClient(scraper_token=settings.THORDATA_SCRAPER_TOKEN) as client:
            tasks = [client.serp_search(q, engine="google", num=num) for q in queries]
            results_list = await asyncio.gather(*tasks, return_exceptions=True)
            
            final_output = []
            for q, res in zip(queries, results_list):
                final_output.append(f"# Results for: {q}\n")
                if isinstance(res, Exception):
                    final_output.append(f"Error: {res}\n")
                    continue
                
                # Fix: res might be Exception, so we check type above.
                # If res is dict, we access it safely.
                if isinstance(res, dict):
                    organic = res.get("organic", [])
                    if not organic:
                        final_output.append("No results found.\n")
                        continue
                        
                    for i, item in enumerate(organic, 1):
                        title = item.get("title", "No Title")
                        link = item.get("link", "#")
                        snippet = item.get("snippet", "")
                        final_output.append(f"{i}. [{title}]({link})\n   {snippet}")
                else:
                    final_output.append(f"Unexpected response type: {type(res)}")

                final_output.append("\n---\n")
            
            return "\n".join(final_output)