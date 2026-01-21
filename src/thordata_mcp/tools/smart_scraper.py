import json
import asyncio
from urllib.parse import urlparse, parse_qs
from typing import Optional
from mcp.server.fastmcp import FastMCP, Context
from thordata import AsyncThordataClient, CommonSettings, ScraperTaskConfig
import httpx

from ..config import settings
from ..registry import SPIDER_REGISTRY, SpiderConfig
from ..utils import handle_mcp_errors, html_to_markdown_clean, truncate_content

def register(mcp: FastMCP):
    
    def _match_spider(url: str) -> tuple[Optional[SpiderConfig], str, dict]:
        """Match URL to spider config."""
        parsed = urlparse(url)
        path = parsed.path
        query = parse_qs(parsed.query)
        domain = parsed.netloc.lower()
        
        if "amazon" in domain:
            if "/dp/" in url: return SPIDER_REGISTRY["amazon_product"], url, {}
            if "/s" in url and "k" in query: return SPIDER_REGISTRY["amazon_search"], query["k"][0], {"domain": f"https://{parsed.netloc}/"}
        
        if "google.com/maps" in url:
            return SPIDER_REGISTRY["gmaps_detail"], url, {}
            
        if "youtube.com" in domain or "youtu.be" in domain:
            if "v=" in url or "youtu.be" in domain:
                return SPIDER_REGISTRY["youtube_video"], url, {}
                
        if "tiktok.com" in domain and "/video/" in path:
            return SPIDER_REGISTRY["tiktok_post"], url, {}
            
        return None, "", {}

    async def _create_video_task_raw(client: AsyncThordataClient, cfg: SpiderConfig, final_params: dict) -> str:
        """
        Manually create video task to bypass SDK limitations.
        Uses the PROVEN payload structure from RAG pipeline testing.
        """
        # 1. The "Golden" Payload
        spider_universal = {
            "resolution": "<=360p",
            "video_codec": "vp9",
            "audio_format": "opus",
            "bitrate": "<=320",
            "selected_only": "false"
        }
        
        payload = {
            "file_name": f"mcp_vid_{cfg.id}",
            "spider_id": cfg.id,
            "spider_name": cfg.name,
            "spider_parameters": json.dumps([final_params]),
            "spider_errors": "true",
            # CRITICAL: API requires 'spider_universal' key
            "spider_universal": json.dumps(spider_universal)
        }

        # 2. Get Headers via SDK Helper
        from thordata._utils import build_builder_headers
        headers = build_builder_headers(
            client.scraper_token or "",
            client.public_token or "",
            client.public_key or ""
        )

        # 3. Send Request (Using client session)
        # Note: We access the protected _video_builder_url
        async with client._get_session().post(
            client._video_builder_url, 
            data=payload, 
            headers=headers
        ) as response:
            response.raise_for_status()
            data = await response.json()
            
            if data.get("code") != 200:
                raise Exception(f"Video Builder API Error: {data}")
                
            return data["data"]["task_id"]

    @mcp.tool()
    @handle_mcp_errors
    async def smart_scrape(url: str, ctx: Optional[Context] = None) -> str:
        """
        Intelligently scrape ANY URL. 
        Auto-detects Amazon/YouTube/Maps/TikTok and returns structured JSON.
        Falls back to universal browser scraper for other sites.
        """
        if ctx: await ctx.info(f"Smart Scrape analyzing: {url}")
        
        cfg, input_val, dynamic_params = _match_spider(url)
        
        async with AsyncThordataClient(
            scraper_token=settings.THORDATA_SCRAPER_TOKEN,
            public_token=settings.THORDATA_PUBLIC_TOKEN,
            public_key=settings.THORDATA_PUBLIC_KEY
        ) as client:
            
            # --- Specialized Route ---
            if cfg:
                if ctx: await ctx.info(f"⚡ Routed to Specialized Spider: {cfg.desc}")
                
                if not settings.THORDATA_PUBLIC_TOKEN:
                    return "Error: Specialized scraping requires THORDATA_PUBLIC_TOKEN."

                final_params = {cfg.input_key: input_val}
                final_params.update(cfg.extra_params)
                final_params.update(dynamic_params)
                
                task_id = ""

                # Special handling for Video to ensure success
                if cfg.is_video:
                    task_id = await _create_video_task_raw(client, cfg, final_params)
                else:
                    # Standard Web Task (SDK method works fine here)
                    config = ScraperTaskConfig(
                        file_name=f"mcp_{cfg.id}",
                        spider_id=cfg.id,
                        spider_name=cfg.name,
                        parameters=final_params
                    )
                    task_id = await client.create_scraper_task_advanced(config)
                
                if ctx: await ctx.info(f"Task {task_id} created. Waiting...")

                # Wait for completion (SDK Helper)
                status = await client.wait_for_task(task_id, max_wait=300)
                
                if status.lower() not in ["ready", "success", "finished"]:
                    return f"Task failed with status: {status}"

                # Get Download URL
                result_url = await client.get_task_result(task_id)

                # Download & Parse
                async with httpx.AsyncClient(timeout=60.0) as http:
                    resp = await http.get(result_url)
                    try:
                        data = resp.json()
                        # Simplify list
                        if isinstance(data, list) and len(data) == 1:
                            return json.dumps(data[0], indent=2)
                        return json.dumps(data, indent=2)
                    except json.JSONDecodeError:
                        return resp.text
            
            # --- Universal Fallback ---
            else:
                if ctx: await ctx.info("🌐 Routing to Universal Scraper (Markdown)")
                html = await client.universal_scrape(
                    url=url, 
                    js_render=True, 
                    wait=3000
                )
                markdown = html_to_markdown_clean(str(html))
                return truncate_content(markdown)