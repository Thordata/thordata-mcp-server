from mcp.server.fastmcp import FastMCP
import httpx

# FIX: Use absolute imports to support both 'mcp dev' and package execution
from thordata import AsyncThordataClient
from thordata_mcp.config import settings
from thordata_mcp.utils import html_to_markdown_clean, truncate_content

# Initialize Server
mcp = FastMCP("Thordata")

# --- 1. Web Tools ---
@mcp.tool()
async def google_search(query: str, num: int = 5) -> str:
    """Search Google for real-time information."""
    async with AsyncThordataClient(scraper_token=settings.THORDATA_SCRAPER_TOKEN) as client:
        try:
            results = await client.serp_search(query=query, engine="google", num=num)
            organic = results.get("organic", [])
            output = [f"### [{item.get('title')}]({item.get('link')})\n{item.get('snippet')}\n" for item in organic]
            return "\n".join(output) if output else "No results."
        except Exception as e:
            return f"Error: {e}"

@mcp.tool()
async def read_url(url: str) -> str:
    """Read a webpage content as Markdown."""
    async with AsyncThordataClient(scraper_token=settings.THORDATA_SCRAPER_TOKEN) as client:
        try:
            html = await client.universal_scrape(url=url, js_render=True, output_format="html")
            return truncate_content(html_to_markdown_clean(str(html)))
        except Exception as e:
            return f"Error: {e}"

# --- 2. Commerce Tools ---
@mcp.tool()
async def get_google_maps_details(url: str) -> str:
    """Get details from a Google Maps Place URL."""
    if not settings.THORDATA_PUBLIC_TOKEN: return "Config Error: Public Token missing."
    async with AsyncThordataClient(
        scraper_token=settings.THORDATA_SCRAPER_TOKEN,
        public_token=settings.THORDATA_PUBLIC_TOKEN,
        public_key=settings.THORDATA_PUBLIC_KEY
    ) as client:
        try:
            res_url = await client.run_task(
                "mcp_maps", settings.SPIDER_GOOGLE_MAPS, "google.com", {"url": url}
            )
            async with httpx.AsyncClient() as http:
                return str((await http.get(res_url)).json())
        except Exception as e:
            return f"Error: {e}"

# --- 3. Media Tools ---
@mcp.tool()
async def get_youtube_video_info(url: str) -> str:
    """Get metadata for a YouTube video."""
    if not settings.THORDATA_PUBLIC_TOKEN: return "Config Error: Public Token missing."
    async with AsyncThordataClient(
        scraper_token=settings.THORDATA_SCRAPER_TOKEN,
        public_token=settings.THORDATA_PUBLIC_TOKEN,
        public_key=settings.THORDATA_PUBLIC_KEY
    ) as client:
        try:
            res_url = await client.run_task(
                "mcp_yt", settings.SPIDER_YOUTUBE, "youtube.com", {"url": url}
            )
            async with httpx.AsyncClient() as http:
                # Return first item if list
                data = (await http.get(res_url)).json()
                if isinstance(data, list) and data: return str(data[0])
                return str(data)
        except Exception as e:
            return f"Error: {e}"

def main():
    mcp.run()

if __name__ == "__main__":
    main()