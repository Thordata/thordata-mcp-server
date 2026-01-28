import argparse
import logging
import sys

from mcp.server.fastmcp import FastMCP

from thordata_mcp.registry import register_all
from thordata_mcp.debug_http import create_debug_routes

logging.basicConfig(
    level=logging.INFO,
    stream=sys.stderr,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="thordata-mcp")
    parser.add_argument(
        "--transport",
        default="stdio",
        choices=["stdio", "sse", "streamable-http"],
        help="Transport protocol (stdio, sse, streamable-http).",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Bind host (for SSE / HTTP transports). Default 127.0.0.1.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Bind port (for SSE / HTTP transports). Default 8000.",
    )
    parser.add_argument(
        "--mount-path",
        default=None,
        help="Optional mount path for SSE / streamable-http.",
    )
    parser.add_argument(
        "--log-level",
        default="info",
        choices=["debug", "info", "warning", "error", "critical"],
        help="Logging level (stderr).",
    )
    parser.add_argument(
        "--no-debug-api",
        action="store_true",
        help="Disable /debug/tools/* HTTP endpoints.",
    )
    parser.add_argument(
        "--list-tools",
        action="store_true",
        help="Print registered tool names to stderr and exit.",
    )
    parser.add_argument(
        "--expose-all-tools",
        action="store_true",
        default=False,
        help="Expose all tools (default: only expose 6 core tools: search, scrape, task_run, browser.navigate, browser.snapshot, tasks.list).",
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    """Thordata MCP Server entry point."""

    parser = _build_parser()
    args = parser.parse_args(argv)

    # Adjust log level early
    logging.getLogger().setLevel(args.log_level.upper())

    # Create MCP server instance
    mcp = FastMCP("Thordata")

    # Override host/port before run (only affects network transports)
    mcp.settings.host = args.host
    mcp.settings.port = args.port

    # Register all tools (synchronously wraps async registrations)
    register_all(mcp, expose_all=args.expose_all_tools)

    # Inject debug routes if using HTTP transport and not disabled
    if args.transport == "streamable-http" and not args.no_debug_api:
        routes = create_debug_routes(mcp)
        mcp._custom_starlette_routes.extend(routes)  # type: ignore[attr-defined]
        logger.info("Debug API enabled at /debug/tools/*")

    if args.list_tools:
        import anyio

        async def _list() -> list[object]:
            return await mcp.list_tools()

        try:
            tools = anyio.run(_list)
        except Exception as e:
            logger.error("Unable to list tools: %s", e, exc_info=True)
            sys.exit(2)

        for t in tools:
            name = t.get("name") if isinstance(t, dict) else getattr(t, "name", None)
            if name:
                print(name, file=sys.stderr)
        return

    if args.transport == "stdio":
        logger.info("Starting Thordata MCP Server (stdio mode). Waiting for JSON-RPC on stdin…")
    else:
        logger.info(
            "Starting Thordata MCP Server (transport=%s host=%s port=%s mount_path=%s)",
            args.transport,
            args.host,
            args.port,
            args.mount_path,
        )

    try:
        mcp.run(transport=args.transport, mount_path=args.mount_path)
    except KeyboardInterrupt:
        logger.info("Server stopped by user.")
    except Exception as e:
        logger.critical("Server crashed: %s", e, exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
