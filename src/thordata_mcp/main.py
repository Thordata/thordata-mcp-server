import httpx
from typing import Optional, Any
from mcp.server.fastmcp import FastMCP, Context

# FIX: Use absolute imports
from thordata import AsyncThordataClient
from thordata_mcp.config import settings
from thordata_mcp.utils import html_to_markdown_clean, truncate_content

# Initialize Server
mcp = FastMCP("Thordata")

# --- 1. Web Tools (General) ---
@mcp.tool()
async def google_search(query: str, num: int = 5, ctx: Optional[Context] = None) -> str:
    """
    Search Google for real-time information.
    """
    token = settings.THORDATA_SCRAPER_TOKEN
    if not token: return "Error: Scraper Token missing."

    async with AsyncThordataClient(scraper_token=token) as client:
        try:
            results = await client.serp_search(query=query, engine="google", num=num)
            organic = results.get("organic", [])
            if not organic: return "No results found."
            
            output = [f"### [{item.get('title')}]({item.get('link')})\n{item.get('snippet')}\n" for item in organic]
            return "\n".join(output)
        except Exception as e:
            return f"Error: {e}"

@mcp.tool()
async def read_url(url: str, ctx: Optional[Context] = None) -> str:
    """
    Read a webpage content as clean Markdown.
    """
    token = settings.THORDATA_SCRAPER_TOKEN
    if not token: return "Error: Scraper Token missing."

    if ctx: await ctx.info(f"Reading URL: {url}") # Fix: await ctx.info

    async with AsyncThordataClient(scraper_token=token) as client:
        try:
            html = await client.universal_scrape(url=url, js_render=True, output_format="html")
            return truncate_content(html_to_markdown_clean(str(html)))
        except Exception as e:
            return f"Error: {e}"

# --- 2. Commerce Tools (Amazon & Maps) ---
@mcp.tool()
async def get_google_maps_details(url: str, ctx: Optional[Context] = None) -> str:
    """
    Extract detailed business info from a Google Maps URL.
    """
    if not settings.THORDATA_PUBLIC_TOKEN: return "Error: Public Token missing."
    if ctx: await ctx.info(f"Starting Maps task for: {url}")

    async with AsyncThordataClient(
        scraper_token=settings.THORDATA_SCRAPER_TOKEN,
        public_token=settings.THORDATA_PUBLIC_TOKEN,
        public_key=settings.THORDATA_PUBLIC_KEY
    ) as client:
        try:
            # 使用 type: ignore 忽略 Pylance 对动态 run_task 的报错
            res_url = await client.run_task(  # type: ignore
                "mcp_maps", settings.SPIDER_GOOGLE_MAPS, "google.com", {"url": url}
            )
            async with httpx.AsyncClient() as http:
                data = (await http.get(res_url)).json()
                # 优化：只返回第一条以节省上下文
                if isinstance(data, list) and data: return str(data[0])
                return str(data)
        except Exception as e:
            return f"Error: {e}"

@mcp.tool()
async def get_amazon_product(url: str, ctx: Optional[Context] = None) -> str:
    """
    Extract product details (price, rating, ASIN) from an Amazon URL.
    """
    if not settings.THORDATA_PUBLIC_TOKEN: return "Error: Public Token missing."
    if ctx: await ctx.info(f"Starting Amazon task for: {url}")

    async with AsyncThordataClient(
        scraper_token=settings.THORDATA_SCRAPER_TOKEN,
        public_token=settings.THORDATA_PUBLIC_TOKEN,
        public_key=settings.THORDATA_PUBLIC_KEY
    ) as client:
        try:
            # 这里的 spider_id 对应你提供的 amazon_global-product_by-url
            # 因为它支持 .com, .co.jp 等多站点，通用性最强
            res_url = await client.run_task(  # type: ignore
                "mcp_amz", 
                "amazon_global-product_by-url", 
                "amazon.com", 
                {"url": url}
            )
            async with httpx.AsyncClient() as http:
                data = (await http.get(res_url)).json()
                if isinstance(data, list) and data: return str(data[0])
                return str(data)
        except Exception as e:
            return f"Error: {e}"

@mcp.tool()
async def search_amazon_products(keyword: str, domain: str = "https://www.amazon.com/", ctx: Optional[Context] = None) -> str:
    """
    Search for products on Amazon.
    Args:
        keyword: Search term (e.g. "iPhone 15").
        domain: Amazon domain (default: https://www.amazon.com/).
    """
    if not settings.THORDATA_PUBLIC_TOKEN: return "Error: Public Token missing."

    async with AsyncThordataClient(
        scraper_token=settings.THORDATA_SCRAPER_TOKEN,
        public_token=settings.THORDATA_PUBLIC_TOKEN,
        public_key=settings.THORDATA_PUBLIC_KEY
    ) as client:
        try:
            # 对应 spider_id: amazon_product-list_by-keywords-domain
            res_url = await client.run_task(  # type: ignore
                "mcp_amz_search", 
                "amazon_product-list_by-keywords-domain", 
                "amazon.com", 
                {"keyword": keyword, "domain": domain, "page_turning": "1"}
            )
            async with httpx.AsyncClient() as http:
                data = (await http.get(res_url)).json()
                # 截断结果，防止 Token 爆炸 (只返回前5个)
                if isinstance(data, list):
                    return str(data[:5])
                return str(data)
        except Exception as e:
            return f"Error: {e}"

# --- 3. Media Tools (YouTube) ---
@mcp.tool()
async def get_youtube_video_info(url: str, ctx: Optional[Context] = None) -> str:
    """Get metadata for a YouTube video."""
    if not settings.THORDATA_PUBLIC_TOKEN: return "Error: Public Token missing."
    
    async with AsyncThordataClient(
        scraper_token=settings.THORDATA_SCRAPER_TOKEN,
        public_token=settings.THORDATA_PUBLIC_TOKEN,
        public_key=settings.THORDATA_PUBLIC_KEY
    ) as client:
        try:
            res_url = await client.run_task(  # type: ignore
                "mcp_yt", settings.SPIDER_YOUTUBE, "youtube.com", {"url": url}
            )
            async with httpx.AsyncClient() as http:
                data = (await http.get(res_url)).json()
                if isinstance(data, list) and data: return str(data[0])
                return str(data)
        except Exception as e:
            return f"Error: {e}"

def main():
    mcp.run()

if __name__ == "__main__":
    main()