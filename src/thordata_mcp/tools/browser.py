from typing import Optional
from mcp.server.fastmcp import FastMCP, Context
from thordata import AsyncThordataClient, ThordataConfigError
from ..config import settings

def register(mcp: FastMCP):
    """Register browser automation tools."""
    
    @mcp.tool()
    async def get_scraping_browser_url(ctx: Optional[Context] = None) -> str:
        """
        Get a WebSocket URL for connecting to Thordata's Scraping Browser.
        Use this URL with Playwright's `connect_over_cdp` or Puppeteer's `connect`.
        """
        token = settings.THORDATA_SCRAPER_TOKEN or "dummy"
        
        # 显式检查凭证，提供更友好的错误信息
        user = settings.THORDATA_BROWSER_USERNAME or settings.THORDATA_RESIDENTIAL_USERNAME
        pwd = settings.THORDATA_BROWSER_PASSWORD or settings.THORDATA_RESIDENTIAL_PASSWORD
        
        if not user or not pwd:
            return (
                "❌ Configuration Error: Missing Browser/Proxy Credentials.\n"
                "Please set `THORDATA_RESIDENTIAL_USERNAME` and `THORDATA_RESIDENTIAL_PASSWORD` in your .env file.\n"
                "These are required to generate the secure WebSocket connection string."
            )

        async with AsyncThordataClient(scraper_token=token) as client:
            try:
                # SDK 会优先使用传入参数
                url = client.get_browser_connection_url(username=user, password=pwd)
                
                if ctx:
                    safe_user = url.split('@')[0].split(':')[-2]
                    await ctx.info(f"Generated Browser URL for user: {safe_user}")
                
                return (
                    f"Browser WebSocket Endpoint:\n`{url}`\n\n"
                    f"**Usage (Playwright Python):**\n"
                    f"```python\n"
                    f"browser = await playwright.chromium.connect_over_cdp('{url}')\n"
                    f"```"
                )
            except ThordataConfigError as e:
                 return f"❌ Configuration Error: {str(e)}"
            except Exception as e:
                return f"❌ Error generating URL: {str(e)}"