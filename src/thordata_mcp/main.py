import sys
import logging
from mcp.server.fastmcp import FastMCP
from thordata_mcp.tools import web, smart_scraper, browser

# 配置日志输出到 stderr
# 这是 MCP Stdio 模式的铁律：stdout 必须留给 JSON-RPC 通信，日志只能走 stderr
logging.basicConfig(
    level=logging.INFO, 
    stream=sys.stderr, 
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 初始化 Server
mcp = FastMCP("Thordata")

# 注册工具模块
web.register(mcp)
smart_scraper.register(mcp)
browser.register(mcp)

def main():
    """
    Main Entry Point.
    Runs the MCP server in Stdio mode (Standard Input/Output).
    This is the standard mode for Claude Desktop, Cursor, and Docker deployments.
    """
    logger.info("🚀 Starting ThorData MCP Server (Stdio Mode)")
    
    try:
        # FastMCP 默认就是 stdio 模式
        mcp.run()
    except KeyboardInterrupt:
        logger.info("Server stopped by user.")
    except Exception as e:
        logger.critical(f"Server crashed: {e}", exc_info=True)
        sys.exit(1)
    
if __name__ == "__main__":
    main()