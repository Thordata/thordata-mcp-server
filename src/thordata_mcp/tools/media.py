from mcp.server.fastmcp import Context
from thordata import AsyncThordataClient
from ..config import settings

async def register_media_tools(mcp):
    """Register social media scraping tools."""

    @mcp.tool()
    async def get_youtube_video_info(url: str, ctx: Context = None) -> str:
        """
        Get metadata for a YouTube video (Title, Views, Description).
        """
        if not settings.THORDATA_PUBLIC_TOKEN:
            return "Error: Public Token required."

        ctx.info(f"Scraping YouTube video: {url}")
        
        async with AsyncThordataClient(
            public_token=settings.THORDATA_PUBLIC_TOKEN,
            public_key=settings.THORDATA_PUBLIC_KEY,
            scraper_token=settings.THORDATA_SCRAPER_TOKEN # run_task needs scraper_token too for creation
        ) as client:
            try:
                result_url = await client.run_task(
                    file_name="mcp_yt_task",
                    spider_id=settings.SPIDER_YOUTUBE,
                    spider_name="youtube.com",
                    parameters={"url": url}
                )
                import httpx
                async with httpx.AsyncClient() as http:
                    resp = await http.get(result_url)
                    data = resp.json()
                    # Return first result if list
                    if isinstance(data, list) and data:
                        return str(data[0])
                    return str(data)
            except Exception as e:
                return f"Error: {str(e)}"

    @mcp.tool()
    async def get_instagram_post(url: str, ctx: Context = None) -> str:
        """
        Get details of an Instagram post.
        """
        if not settings.THORDATA_PUBLIC_TOKEN:
            return "Error: Public Token required."
            
        ctx.info(f"Scraping Instagram post: {url}")

        async with AsyncThordataClient(
            public_token=settings.THORDATA_PUBLIC_TOKEN,
            public_key=settings.THORDATA_PUBLIC_KEY,
            scraper_token=settings.THORDATA_SCRAPER_TOKEN
        ) as client:
            try:
                result_url = await client.run_task(
                    file_name="mcp_ig_task",
                    spider_id=settings.SPIDER_INSTAGRAM,
                    spider_name="instagram.com",
                    parameters={"url": url}
                )
                import httpx
                async with httpx.AsyncClient() as http:
                    resp = await http.get(result_url)
                    return str(resp.json())
            except Exception as e:
                return f"Error: {str(e)}"