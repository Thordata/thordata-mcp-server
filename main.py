"""
Thordata MCP Server

This script exposes Thordata-powered tools via the Model Context Protocol (MCP).
It allows LLMs (like Claude) to:
1. Search the web (Google/Bing/...)
2. Scrape any page (Universal Unlocker)
3. Extract structured data from platforms (Amazon, YouTube, TikTok, etc.) via Web Scraper API

Usage:
    python -m scripts.mcp_server
"""

from __future__ import annotations

import json
import logging
import os
import time
from functools import lru_cache
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP
from thordata import (
    Engine,
    ThordataClient,
    ThordataConfigError,
)

# ---------------------------------------------------------------------------
# Configuration & Logging
# ---------------------------------------------------------------------------

ROOT_DIR = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT_DIR / ".env"
load_dotenv(ENV_PATH)

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("thordata.mcp")


@lru_cache
def get_client() -> ThordataClient:
    token = os.getenv("THORDATA_SCRAPER_TOKEN")
    pub_token = os.getenv("THORDATA_PUBLIC_TOKEN")
    pub_key = os.getenv("THORDATA_PUBLIC_KEY")

    if not token or not pub_token or not pub_key:
        raise ThordataConfigError(
            "Missing credentials. Please set THORDATA_SCRAPER_TOKEN, "
            "THORDATA_PUBLIC_TOKEN, and THORDATA_PUBLIC_KEY in .env"
        )

    return ThordataClient(
        scraper_token=token,
        public_token=pub_token,
        public_key=pub_key,
    )


mcp = FastMCP("Thordata Tools")

# ---------------------------------------------------------------------------
# Core Tools: Search & Universal Scrape
# ---------------------------------------------------------------------------


@mcp.tool()
def search_web(
    query: str,
    engine: str = "google",
    num: int = 5,
    location: str | None = None,
) -> str:
    """
    Search the web for real-time information using Google, Bing, etc.
    """
    try:
        client = get_client()
        # Map string engine to Enum, default to Google
        eng_enum = getattr(Engine, engine.upper(), Engine.GOOGLE)

        logger.info(f"Searching {eng_enum}: {query}")

        params = {}
        if location:
            params["location"] = location

        res = client.serp_search(query, engine=eng_enum, num=num, **params)
        organic = res.get("organic", [])

        # Simplify output for LLM
        summary = []
        for item in organic[:num]:
            summary.append(
                {
                    "title": item.get("title"),
                    "link": item.get("link"),
                    "snippet": item.get("snippet"),
                    "rank": item.get("rank"),
                }
            )

        return json.dumps(summary, ensure_ascii=False, indent=2)

    except Exception as e:
        logger.error(f"Search failed: {e}")
        return f"Error: {e}"


@mcp.tool()
def read_page(url: str, js_render: bool = True, country: str = "us") -> str:
    """
    Read and extract text from any webpage, automatically handling antibot protection.
    """
    try:
        client = get_client()
        logger.info(f"Reading page: {url}")

        html = client.universal_scrape(
            url=url, js_render=js_render, country=country, output_format="html"
        )

        # Simple HTML cleaning
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "svg"]):
            tag.decompose()

        text = soup.get_text(separator="\n")
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        clean_text = "\n".join(lines)

        return f"Source: {url}\n\n{clean_text[:15000]}"  # Limit context window

    except Exception as e:
        logger.error(f"Read page failed: {e}")
        return f"Error: {e}"


# ---------------------------------------------------------------------------
# Specialized Spider Tools (Web Scraper API)
# ---------------------------------------------------------------------------


def _run_spider_task(spider_id: str, spider_name: str, params: dict[str, Any]) -> str:
    """Helper to run a task and wait for result."""
    client = get_client()
    task_id = client.create_scraper_task(
        file_name=f"mcp_{spider_name}_{int(time.time())}",
        spider_id=spider_id,
        spider_name=spider_name,
        parameters=params,
    )
    logger.info(f"Task created: {task_id} ({spider_name})")

    # Wait for completion (simple polling)
    # Note: In production MCP, async/streaming is better, but this is simple.
    max_retries = 60  # 5 mins
    for _ in range(max_retries):
        status = client.get_task_status(task_id)
        if status.lower() in ("ready", "success", "finished"):
            return client.get_task_result(task_id, "json")
        if status.lower() in ("failed", "error"):
            return f"Error: Task {task_id} failed."
        time.sleep(5)

    return f"Error: Task {task_id} timed out."


# --- E-Commerce ---


@mcp.tool()
def get_amazon_product(url: str) -> str:
    """Extract structured data from an Amazon product page."""
    return _run_spider_task(
        spider_id="amazon_product_detail",  # Replace with actual ID from Store
        spider_name="amazon.com",
        params={"url": url},
    )


@mcp.tool()
def get_amazon_search(keyword: str, domain: str = "amazon.com") -> str:
    """Search for products on Amazon."""
    return _run_spider_task(
        spider_id="amazon_search",
        spider_name="amazon.com",
        params={"keyword": keyword, "domain": domain},
    )


# --- Social Media ---


@mcp.tool()
def get_youtube_video_info(url: str) -> str:
    """Extract metadata from a YouTube video."""
    return _run_spider_task(
        spider_id="youtube_video_detail", spider_name="youtube.com", params={"url": url}
    )


@mcp.tool()
def get_tiktok_profile(username: str) -> str:
    """Extract TikTok profile information."""
    return _run_spider_task(
        spider_id="tiktok_user_profile",
        spider_name="tiktok.com",
        params={"username": username},
    )


# --- Business ---


@mcp.tool()
def get_linkedin_company(url: str) -> str:
    """Extract LinkedIn company profile data."""
    return _run_spider_task(
        spider_id="linkedin_company_profile",
        spider_name="linkedin.com",
        params={"url": url},
    )


# ---------------------------------------------------------------------------
# Server Entry
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("🚀 Thordata MCP Server running...")
    # FastMCP uses stdio by default for Claude Desktop integration
    mcp.run()
