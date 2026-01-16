from typing import Optional
from mcp.server.fastmcp import FastMCP
from thordata import AsyncThordataClient
import httpx
from ..config import settings

def register(mcp: FastMCP):
    """Register social media tools."""
    
    @mcp.tool()
    async def get_youtube_video_info(url: str) -> str:
        """Get metadata for a YouTube video."""
        if not settings.THORDATA_PUBLIC_TOKEN:
            return "Configuration Error: THORDATA_PUBLIC_TOKEN is missing."
            
        async with AsyncThordataClient(
            scraper_token=settings.THORDATA_SCRAPER_TOKEN,
            public_token=settings.THORDATA_PUBLIC_TOKEN,
            public_key=settings.THORDATA_PUBLIC_KEY
        ) as client:
            try:
                result_url = await client.run_task(  # type: ignore
                    file_name="mcp_yt_task",
                    spider_id=settings.SPIDER_YOUTUBE,
                    spider_name="youtube.com",
                    parameters={"url": url}
                )
                async with httpx.AsyncClient() as http:
                    data = (await http.get(result_url)).json()
                    if isinstance(data, list) and data: return str(data[0])
                    return str(data)
            except Exception as e:
                return f"Task Failed: {str(e)}"