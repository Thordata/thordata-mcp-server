from typing import Optional
from mcp.server.fastmcp import FastMCP, Context
from thordata import AsyncThordataClient
import httpx
from ..config import settings

def register(mcp: FastMCP):
    """Register e-commerce and map related tools."""

    @mcp.tool()
    async def get_google_maps_details(url: str, ctx: Optional[Context] = None) -> str:
        """
        Extract details (phone, website, hours) from a Google Maps Place URL.
        Uses Thordata Task API for deep scraping.
        """
        if not settings.THORDATA_PUBLIC_TOKEN:
            return "Configuration Error: THORDATA_PUBLIC_TOKEN is missing."

        if ctx: await ctx.info(f"Starting Maps task for: {url}")

        async with AsyncThordataClient(
            scraper_token=settings.THORDATA_SCRAPER_TOKEN,
            public_token=settings.THORDATA_PUBLIC_TOKEN,
            public_key=settings.THORDATA_PUBLIC_KEY
        ) as client:
            try:
                # 自动轮询直到完成
                result_url = await client.run_task(  # type: ignore
                    file_name="mcp_maps_task",
                    spider_id=settings.SPIDER_GOOGLE_MAPS,
                    spider_name="google.com",
                    parameters={"url": url}
                )
                
                # 下载结果
                async with httpx.AsyncClient() as http:
                    resp = await http.get(result_url)
                    data = resp.json()
                    
                    # 优化：如果是列表，只返回第一个结果以减少噪音
                    if isinstance(data, list) and data:
                        return str(data[0])
                    return str(data)
            except Exception as e:
                return f"Task Failed: {str(e)}"
    
    # 预留位：Amazon 工具将在下一阶段完善，先不注册以免报错
    # @mcp.tool()
    # async def get_amazon_product...