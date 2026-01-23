import json, httpx, re
from urllib.parse import urlparse, parse_qs
from typing import Optional, Dict, Any, Tuple
from mcp.server.fastmcp import FastMCP, Context
from thordata import AsyncThordataClient, ScraperTaskConfig
from ..config import settings
from ..registry import SPIDER_REGISTRY, SpiderConfig
from ..utils import handle_mcp_errors, html_to_markdown_clean, truncate_content

def register(mcp: FastMCP):
    def _match_spider(url: str) -> Tuple[Optional[SpiderConfig], str, Dict[str, Any]]:
        parsed = urlparse(url)
        path, domain, query = parsed.path, parsed.netloc.lower(), parse_qs(parsed.query)
        
        # 1. Amazon 专项路由 (对标你提供的 5 个示例)
        if "amazon" in domain:
            # asin 详情
            asin_match = re.search(r'/(?:dp|gp/product)/([A-Z0-9]{10})', url)
            if asin_match: return SPIDER_REGISTRY["amazon_asin"], asin_match.group(1), {}
            # 评价
            if "/product-reviews/" in path: return SPIDER_REGISTRY["amazon_review"], url, {}
            # 卖家 (包含 /sp? 逻辑)
            if "seller" in path or "sp?" in parsed.query or "merchant" in parsed.query: 
                return SPIDER_REGISTRY["amazon_seller"], url, {}
            # 搜索
            if "/s" in path and "k" in query: 
                return SPIDER_REGISTRY["amazon_search"], query["k"][0], {"domain": f"https://{parsed.netloc}/"}
            return SPIDER_REGISTRY["amazon_product"], url, {}

        # 2. YouTube 专项路由 (对标你提供的 4 个示例)
        if "youtube.com" in domain or "youtu.be" in domain:
            v_id = query.get("v", [None])[0] or (path.split('/')[-1] if "youtu.be" in domain else None)
            if v_id:
                # 默认视频详情 (使用 video_builder)
                return SPIDER_REGISTRY["youtube_video"], url, {}
            # 频道视频列表 (使用 builder)
            if "/@" in path or "/channel/" in path:
                return SPIDER_REGISTRY["youtube_channel"], url, {}
            return None, "", {}

        # 3. Twitter/X 专项路由
        if "twitter.com" in domain or "x.com" in domain:
            if "/status/" in path: return SPIDER_REGISTRY["twitter_post"], url, {}
            return SPIDER_REGISTRY["twitter_profile"], url, {}

        # 4. 其他社交媒体 & Google
        if "instagram.com" in domain:
            if "/p/" in path or "/reels/" in path: return SPIDER_REGISTRY["ins_reel"], url, {}
            user_match = re.search(r'instagram\.com/([^/?#]+)', url)
            if user_match: return SPIDER_REGISTRY["ins_profile"], user_match.group(1), {}
            
        if "reddit.com" in domain:
            if "/comments/" in path: return SPIDER_REGISTRY["reddit_comment"], url, {}
            return SPIDER_REGISTRY["reddit_post"], url, {}

        if "linkedin.com" in domain:
            if "/jobs/" in path: return SPIDER_REGISTRY["linkedin_job"], url, {}
            return SPIDER_REGISTRY["linkedin_company"], url, {}

        if "github.com" in domain:
            return SPIDER_REGISTRY["github_repo"], url, {}

        if "google.com" in domain:
            if "/maps/" in path: return SPIDER_REGISTRY["gmaps_detail"], url, {}
            if "/shopping/" in path: return SPIDER_REGISTRY["google_shopping"], url, {}

        return None, "", {}

    async def _create_video_task_raw(client: AsyncThordataClient, cfg: SpiderConfig, final_params: dict) -> str:
        """对标你提供的 video_builder 示例参数"""
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
            "spider_universal": json.dumps(spider_universal)
        }
        from thordata._utils import build_builder_headers
        headers = build_builder_headers(client.scraper_token or "", client.public_token or "", client.public_key or "")
        async with client._http._session.post(client._video_builder_url, data=payload, headers=headers) as resp: # type: ignore
            data = await resp.json()
            if data.get("code") != 200: raise Exception(f"Video API Error: {data}")
            return data["data"]["task_id"]

    @mcp.tool()
    @handle_mcp_errors
    async def smart_scrape(url: str, ctx: Optional[Context] = None) -> str:
        if ctx: await ctx.info(f"Smart Scrape: 100% Inspecting {url}")
        cfg, input_val, dynamic_params = _match_spider(url)
        
        async with AsyncThordataClient(
            scraper_token=settings.THORDATA_SCRAPER_TOKEN,
            public_token=settings.THORDATA_PUBLIC_TOKEN,
            public_key=settings.THORDATA_PUBLIC_KEY
        ) as client:
            await client._http._ensure_session()
            
            if cfg:
                if ctx: await ctx.info(f"⚡ Routed to Specialized Scraper: {cfg.desc}")
                final_params = {cfg.input_key: input_val, **cfg.extra_params, **dynamic_params}
                
                # 路由选择：video_builder 还是标准 builder
                if cfg.is_video:
                    task_id = await _create_video_task_raw(client, cfg, final_params)
                else:
                    config = ScraperTaskConfig(f"mcp_{cfg.id}", cfg.id, cfg.name, final_params)
                    task_id = await client.create_scraper_task_advanced(config)
                
                if ctx: await ctx.info(f"Task {task_id} created. Polling for structured JSON...")
                status = await client.wait_for_task(task_id, max_wait=300)
                
                if status.lower() in ["ready", "success", "finished"]:
                    res_url = await client.get_task_result(task_id)
                    async with httpx.AsyncClient(timeout=60.0) as http:
                        resp = await http.get(res_url)
                        data = resp.json()
                        return json.dumps(data[0] if isinstance(data, list) and len(data) == 1 else data, indent=2)
                cfg = None # 失败则降级

            if not cfg:
                if ctx: await ctx.info("🌐 Falling back to Universal Scraper (Markdown)")
                html = await client.universal_scrape(url=url, js_render=True, wait=3000)
                return truncate_content(html_to_markdown_clean(str(html)))
        return "Error: Unknown logic state"