"""
Quick local test for MCP tools without an MCP client.
"""

from __future__ import annotations

import os
import sys
from pprint import pprint


def main() -> int:
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)

    # Import after sys.path adjustment (inside function to satisfy Ruff E402)
    from scripts.mcp_server import read_page, search_web

    # 1. Test web search
    print("\n=== search_web (google) ===")
    # Note: Function call might fail if no credentials in .env, but we want to see it run
    result = search_web("Thordata proxy network", engine="google", num=3)
    pprint(result)

    # 2. Test read_page (Universal)
    print("\n=== read_page ===")
    # Using a simple URL to avoid heavy billing or long wait
    text = read_page("https://example.com", js_render=False)
    print(text[:500])

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
