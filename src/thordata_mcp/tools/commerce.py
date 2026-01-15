from mcp.server.fastmcp import Context
from thordata import AsyncThordataClient
from ..config import settings

async def register_commerce_tools(mcp):
    
    @mcp.tool()
    async def get_google_maps_details(url: str, ctx: Context = None) -> str:
        """
        Extract detailed business information from a Google Maps URL.
        Returns: Phone, Website, Opening Hours, Rating, etc.
        """
        if not settings.THORDATA_PUBLIC_TOKEN:
            return "Error: Public Token required for Task API."

        ctx.info(f"Starting Google Maps task for: {url}")
        
        async with AsyncThordataClient(
            public_token=settings.THORDATA_PUBLIC_TOKEN,
            public_key=settings.THORDATA_PUBLIC_KEY
        ) as client:
            try:
                # 使用 run_task 自动轮询
                result_url = await client.run_task(
                    file_name="mcp_maps_task",
                    spider_id=settings.SPIDER_GOOGLE_MAPS,
                    spider_name="google.com",
                    parameters={"url": url}
                )
                # MCP 需要返回文本内容，所以我们需要把结果下载下来
                # 这里简单复用 requests (或者用 httpx 更好，但为了简单先这样)
                import httpx
                async with httpx.AsyncClient() as http:
                    resp = await http.get(result_url)
                    data = resp.json()
                    # 只返回第一条结果以节省 Token
                    if isinstance(data, list) and data:
                        return str(data[0])
                    return str(data)
            except Exception as e:
                return f"Error: {str(e)}"

    @mcp.tool()
    async def get_amazon_product(url: str, ctx: Context = None) -> str:
        """
        Extract product details from an Amazon URL.
        Returns: Price, Title, Description, Images.
        """
        if not settings.THORDATA_PUBLIC_TOKEN:
            return "Error: Public Token required."

        async with AsyncThordataClient(
            public_token=settings.THORDATA_PUBLIC_TOKEN,
            public_key=settings.THORDATA_PUBLIC_KEY
        ) as client:
            try:
                result_url = await client.run_task(
                    file_name="mcp_amazon_task",
                    spider_id=settings.SPIDER_AMAZON,
                    spider_name="amazon.com",
                    parameters={"url": url}
                )
                import httpx
                async with httpx.AsyncClient() as http:
                    resp = await http.get(result_url)
                    return str(resp.json())
            except Exception as e:
                return f"Error: {str(e)}"