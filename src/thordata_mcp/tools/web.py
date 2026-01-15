from mcp.server.fastmcp import Context
from thordata import AsyncThordataClient
from ..utils import html_to_markdown_clean, truncate_content

async def register_web_tools(mcp):
    """Register general web browsing tools."""

    @mcp.tool()
    async def google_search(query: str, num: int = 5, ctx: Context = None) -> str:
        """
        Perform a real-time Google search.
        Returns a list of titles, links, and snippets.
        """
        async with AsyncThordataClient() as client:
            try:
                # 使用 SERP API
                results = await client.serp_search(query=query, engine="google", num=num)
                organic = results.get("organic", [])
                
                if not organic:
                    return "No results found."
                
                output = []
                for item in organic:
                    output.append(f"### [{item.get('title')}]({item.get('link')})\n{item.get('snippet')}\n")
                
                return "\n".join(output)
            except Exception as e:
                return f"Error: {str(e)}"

    @mcp.tool()
    async def read_url(url: str, ctx: Context = None) -> str:
        """
        Visit a webpage and extract its content as Markdown.
        Capable of rendering JavaScript (SPA/React sites).
        """
        ctx.info(f"Scraping URL: {url}")
        async with AsyncThordataClient() as client:
            try:
                # 使用 Universal API
                html = await client.universal_scrape(
                    url=url,
                    js_render=True, # 默认开启 JS 渲染以应对复杂网页
                    output_format="html"
                )
                
                markdown = html_to_markdown_clean(str(html))
                return truncate_content(markdown)
            except Exception as e:
                return f"Error reading page: {str(e)}"