import sys
import logging
from mcp.server.fastmcp import FastMCP
from thordata_mcp.tools import web, smart_scraper, browser

# Configure logging to stderr
logging.basicConfig(level=logging.INFO, stream=sys.stderr, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Initialize Server
mcp = FastMCP("Thordata")

# Register Tools
web.register(mcp)           # Google Search, Read URL
smart_scraper.register(mcp) # Smart Scrape (Amazon, YouTube, Maps, etc.)
browser.register(mcp)       # Browser Automation Helper

def main():
    """
    Main entry point.
    Forces stdio transport mode to ensure compatibility with MCP clients.
    """
    try:
        mcp.run(transport="stdio")
    except TypeError:
        # Fallback for older/newer versions compatibility
        mcp.run()
    except Exception as e:
        logger.critical(f"Server crashed: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()