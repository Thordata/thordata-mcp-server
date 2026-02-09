from __future__ import annotations

import asyncio
import json
import re
from urllib.parse import parse_qs, urlparse
from typing import Any, Optional

import aiohttp
from mcp.server.fastmcp import Context, FastMCP
from thordata import ThordataAPIError, ThordataNetworkError
from thordata.types import Engine, SerpRequest
from thordata.tools import ToolRequest

from thordata_mcp.context import ServerContext
from thordata_mcp.utils import (
    handle_mcp_errors,
    ok_response,
    error_response,
    safe_ctx_info,
    enrich_download_url,
    html_to_markdown_clean,
    truncate_content,
)
from thordata_mcp.tools.utils import iter_tool_request_types, tool_key, tool_schema, tool_group_from_key


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_TOOLS_CACHE: list[type[ToolRequest]] | None = None
_TOOLS_MAP: dict[str, type[ToolRequest]] | None = None


def _ensure_tools() -> tuple[list[type[ToolRequest]], dict[str, type[ToolRequest]]]:
    global _TOOLS_CACHE, _TOOLS_MAP
    if _TOOLS_CACHE is None or _TOOLS_MAP is None:
        _TOOLS_CACHE = iter_tool_request_types()
        _TOOLS_MAP = {tool_key(t): t for t in _TOOLS_CACHE}
    return _TOOLS_CACHE, _TOOLS_MAP


def _catalog(
    *,
    group: str | None,
    keyword: str | None,
    limit: int,
    offset: int,
) -> tuple[list[type[ToolRequest]], dict[str, Any]]:
    tools, _ = _ensure_tools()
    kw = (keyword or "").strip().lower()
    g_filter = (group or "").strip().lower() or None
    out: list[type[ToolRequest]] = []
    for t in tools:
        k = tool_key(t)
        g = tool_group_from_key(k).lower()
        if g_filter and g != g_filter:
            continue
        if kw:
            if kw not in k.lower() and kw not in (getattr(t, "SPIDER_ID", "") or "").lower() and kw not in (getattr(t, "SPIDER_NAME", "") or "").lower():
                continue
        out.append(t)

    total = len(out)
    page = out[offset : offset + limit]
    group_counts: dict[str, int] = {}
    for t in out:
        gg = tool_group_from_key(tool_key(t))
        group_counts[gg] = group_counts.get(gg, 0) + 1
    meta = {"total": total, "returned": len(page), "offset": offset, "limit": limit, "groups": group_counts}
    return page, meta


def _extract_youtube_video_id(url: str) -> str | None:
    # support youtu.be/<id> and youtube.com/watch?v=<id>
    m = re.search(r"(?:youtu\.be/|v=)([A-Za-z0-9_-]{6,})", url)
    return m.group(1) if m else None


def _extract_amazon_asin(url: str) -> str | None:
    # /dp/<ASIN> or /gp/product/<ASIN>
    m = re.search(r"/dp/([A-Z0-9]{10})", url)
    if m:
        return m.group(1)
    m = re.search(r"/gp/product/([A-Z0-9]{10})", url)
    return m.group(1) if m else None


def _hostname(url: str) -> str:
    try:
        host = (urlparse(url).hostname or "").lower()
        # Normalize common subdomains to improve routing/heuristics.
        # This makes checks like host == "google.com" work for "www.google.com".
        for prefix in ("www.", "m."):
            if host.startswith(prefix):
                host = host[len(prefix) :]
                break
        return host
    except Exception:
        return ""


def _is_google_search_url(url: str) -> bool:
    """Return True if URL is a Google search results page we should route to SERP."""
    host = _hostname(url)
    if host != "google.com":
        return False
    try:
        p = urlparse(url)
    except Exception:
        return False
    if p.path != "/search":
        return False
    qs = parse_qs(p.query or "")
    q = (qs.get("q") or [""])[0].strip()
    return bool(q)


def _extract_google_search_query(url: str) -> str | None:
    try:
        p = urlparse(url)
        qs = parse_qs(p.query or "")
        q = (qs.get("q") or [""])[0].strip()
        return q or None
    except Exception:
        return None


def _classify_error(e: Exception) -> tuple[str, str]:
    """Map SDK errors to productized error_type/code."""
    s = str(e).lower()
    if "authentication" in s or "api key" in s or "public_token" in s or "public_key" in s:
        return "config_error", "E1001"
    if "permission" in s or "denied" in s or "not allowed" in s:
        return "permission_denied", "E1004"
    if "missing" in s and "parameter" in s:
        return "validation_error", "E4001"
    if "captcha" in s or "blocked" in s or "robot" in s:
        return "blocked", "E3002"
    return "task_failed", "E3001"


def _extract_structured_from_html(html: str) -> dict[str, Any]:
    """Lightweight HTML -> structured metadata (no LLM)."""
    out: dict[str, Any] = {}
    low = html.lower()

    # title
    m = re.search(r"<title[^>]*>(.*?)</title>", html, flags=re.IGNORECASE | re.DOTALL)
    if m:
        title = re.sub(r"\s+", " ", m.group(1)).strip()
        out["title"] = title

    # meta description
    m = re.search(r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']+)["\']', html, flags=re.IGNORECASE)
    if m:
        out["description"] = m.group(1).strip()

    # og:title / og:description
    m = re.search(r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)["\']', html, flags=re.IGNORECASE)
    if m:
        out["og_title"] = m.group(1).strip()
    m = re.search(r'<meta[^>]+property=["\']og:description["\'][^>]+content=["\']([^"\']+)["\']', html, flags=re.IGNORECASE)
    if m:
        out["og_description"] = m.group(1).strip()

    # json-ld blocks (first 3, best-effort json parse)
    jsonlds: list[Any] = []
    for m in re.finditer(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', html, flags=re.IGNORECASE | re.DOTALL):
        raw = m.group(1).strip()
        if not raw:
            continue
        try:
            jsonlds.append(json.loads(raw))
        except Exception:
            # try to fix trailing commas or invalid chars is too risky; keep raw snippet
            jsonlds.append({"_raw": raw[:4000]})
        if len(jsonlds) >= 3:
            break
    if jsonlds:
        out["jsonld"] = jsonlds

    # crude anti-bot hints
    if "captcha" in low or "are you a robot" in low or "/captcha/" in low:
        out["likely_blocked"] = True

    # Crude error/404/500 page hints (help smart_scrape mark error pages instead of normal content)
    error_phrases = [
        "404",
        "page not found",
        "page you requested is unavailable",
        "internal server error",
        "500",
        "temporarily unavailable",
        "sorry, this page",
        "dogs of amazon",  # Amazon anti-bot error page
        "sorry! we couldn't find that page",
        "access denied",
        "forbidden",
    ]
    title_lower = out.get("title", "").lower() if isinstance(out.get("title"), str) else ""
    is_error = any(ph in title_lower for ph in error_phrases) or any(ph in low for ph in error_phrases)
    # Check if it's an Amazon anti-bot page (common pattern)
    if "amazon" in low and ("dogs of amazon" in low or "page not found" in title_lower):
        is_error = True
    if is_error:
        out["is_error_page"] = True
        # Provide a rough HTTP status hint for upper-level logic branching
        if any(p in title_lower for p in ["404", "page not found", "dogs of amazon"]):
            out["http_status_hint"] = 404
        elif any(p in title_lower for p in ["500", "internal server error"]):
            out["http_status_hint"] = 500
        elif "access denied" in low or "forbidden" in low:
            out["http_status_hint"] = 403

    return out


def _normalize_extracted(extracted: dict[str, Any], *, url: str | None = None) -> dict[str, Any]:
    """Normalize extracted metadata (JSON-LD/OG/title) into a stable schema."""
    out: dict[str, Any] = {"url": url}
    if not isinstance(extracted, dict):
        return out

    # Start with best-effort names/descriptions
    title = extracted.get("og_title") or extracted.get("title")
    desc = extracted.get("og_description") or extracted.get("description")
    if isinstance(title, str) and title.strip():
        out["name"] = title.strip()
    if isinstance(desc, str) and desc.strip():
        out["description"] = desc.strip()

    # Parse JSON-LD for Product/Offer/AggregateRating
    jsonld = extracted.get("jsonld")
    blocks: list[Any] = jsonld if isinstance(jsonld, list) else []

    def _walk(obj: Any) -> list[dict[str, Any]]:
        found: list[dict[str, Any]] = []
        if isinstance(obj, dict):
            found.append(obj)
            for v in obj.values():
                found.extend(_walk(v))
        elif isinstance(obj, list):
            for it in obj:
                found.extend(_walk(it))
        return found

    flat: list[dict[str, Any]] = []
    for b in blocks:
        flat.extend(_walk(b))

    # Pick best candidates
    product: dict[str, Any] | None = None
    offer: dict[str, Any] | None = None
    rating: dict[str, Any] | None = None

    def _type_is(d: dict[str, Any], t: str) -> bool:
        v = d.get("@type")
        if isinstance(v, str):
            return v.lower() == t.lower()
        if isinstance(v, list):
            return any(isinstance(x, str) and x.lower() == t.lower() for x in v)
        return False

    for d in flat:
        if product is None and (_type_is(d, "Product") or _type_is(d, "Hotel") or _type_is(d, "LodgingBusiness")):
            product = d
        if offer is None and (_type_is(d, "Offer") or _type_is(d, "AggregateOffer")):
            offer = d
        if rating is None and (_type_is(d, "AggregateRating")):
            rating = d

    # Product fields
    if product:
        n = product.get("name")
        if isinstance(n, str) and n.strip():
            out.setdefault("name", n.strip())
        img = product.get("image")
        if isinstance(img, str):
            out["image"] = img
        elif isinstance(img, list) and img and isinstance(img[0], str):
            out["image"] = img[0]
        brand = product.get("brand")
        if isinstance(brand, dict):
            bn = brand.get("name")
            if isinstance(bn, str):
                out["brand"] = bn
        elif isinstance(brand, str):
            out["brand"] = brand

        # Sometimes offers/ratings nested
        nested_offer = product.get("offers")
        if offer is None and isinstance(nested_offer, dict):
            offer = nested_offer
        nested_rating = product.get("aggregateRating")
        if rating is None and isinstance(nested_rating, dict):
            rating = nested_rating

    # Offer fields
    if offer:
        price = offer.get("price") or offer.get("lowPrice")
        if isinstance(price, (int, float, str)):
            out["price"] = price
        currency = offer.get("priceCurrency")
        if isinstance(currency, str):
            out["currency"] = currency
        availability = offer.get("availability")
        if isinstance(availability, str):
            out["availability"] = availability.split("/")[-1]

    # Rating fields
    if rating:
        rv = rating.get("ratingValue")
        if isinstance(rv, (int, float, str)):
            out["rating"] = rv
        rc = rating.get("reviewCount") or rating.get("ratingCount")
        if isinstance(rc, (int, float, str)):
            out["reviews"] = rc

    # Blocked / error hints passthrough
    if extracted.get("likely_blocked") is True:
        out["likely_blocked"] = True
    if extracted.get("is_error_page") is True:
        out["is_error_page"] = True
        if "http_status_hint" in extracted:
            out["http_status_hint"] = extracted.get("http_status_hint")

    return out


def _normalize_record(record: Any, *, url: str | None = None) -> dict[str, Any]:
    """Normalize a structured task record into the same schema as _normalize_extracted."""
    out: dict[str, Any] = {"url": url}
    if not isinstance(record, dict):
        return out

    # common naming conventions across tasks
    name = record.get("name") or record.get("title")
    if isinstance(name, str) and name.strip():
        out["name"] = name.strip()

    desc = record.get("description") or record.get("text")
    if isinstance(desc, str) and desc.strip():
        out["description"] = desc.strip()[:2000]

    # urls
    u = record.get("url") or record.get("link")
    if isinstance(u, str) and u.strip():
        out["url"] = u.strip()

    # images
    img = record.get("image") or record.get("imageUrl") or record.get("thumbnailUrl") or record.get("thumbnail")
    if isinstance(img, str) and img.strip():
        out["image"] = img.strip()

    # pricing
    price = record.get("price") or record.get("total_price")
    if price is not None:
        out["price"] = price
    currency = record.get("currency")
    if isinstance(currency, str) and currency.strip():
        out["currency"] = currency.strip()

    # availability
    avail = record.get("availability") or record.get("inStock") or record.get("is_available")
    if isinstance(avail, (bool, str, int)):
        out["availability"] = avail

    # rating / reviews
    rating = record.get("rating") or record.get("ratings") or record.get("stars")
    if rating is not None:
        out["rating"] = rating
    reviews = record.get("reviews") or record.get("reviewCount") or record.get("commentsCount") or record.get("property_number_of_reviews")
    if reviews is not None:
        out["reviews"] = reviews

    return out


async def _fetch_json_preview(download_url: str, *, max_chars: int = 20_000) -> dict[str, Any]:
    """Fetch a small JSON preview from a download URL (best-effort, token-safe)."""
    if not download_url:
        return {"ok": False, "error": "missing_download_url"}
    def _first_object_from_array_prefix(s: str) -> dict[str, Any] | None:
        """Best-effort parse of the first JSON object in a JSON array prefix.

        Works even if the overall array is truncated, as long as the first object is complete.
        This avoids json.JSONDecoder.raw_decode failing when the prefix is cut mid-string.
        """
        s = s.lstrip()
        if not s.startswith("["):
            return None
        start = s.find("{")
        if start == -1:
            return None

        in_string = False
        escape = False
        depth = 0
        begun = False
        for i in range(start, len(s)):
            ch = s[i]
            if in_string:
                if escape:
                    escape = False
                elif ch == "\\":
                    escape = True
                elif ch == "\"":
                    in_string = False
                continue
            else:
                if ch == "\"":
                    in_string = True
                    continue
                if ch == "{":
                    depth += 1
                    begun = True
                elif ch == "}":
                    depth -= 1
                    if begun and depth == 0:
                        snippet = s[start : i + 1]
                        try:
                            obj = json.loads(snippet)
                            return obj if isinstance(obj, dict) else None
                        except Exception:
                            return None
        return None

    try:
        timeout = aiohttp.ClientTimeout(total=30)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(download_url) as resp:
                # Stream small preview to avoid truncating mid-string (which breaks JSON parsing).
                # We'll try to extract the first object from an array response, reading up to a hard cap.
                hard_cap = max(max_chars, 200_000)
                buf_parts: list[str] = []
                total = 0
                first_obj: dict[str, Any] | None = None

                async for chunk in resp.content.iter_chunked(16_384):
                    try:
                        part = chunk.decode("utf-8", errors="ignore")
                    except Exception:
                        part = str(chunk)
                    buf_parts.append(part)
                    total += len(part)
                    if total >= max_chars:
                        # As soon as we reach the soft cap, try to parse first object.
                        joined = "".join(buf_parts)
                        first_obj = _first_object_from_array_prefix(joined)
                        if first_obj is not None:
                            break
                    if total >= hard_cap:
                        break

                txt = "".join(buf_parts)
                truncated = total >= hard_cap or len(txt) > max_chars
                try:
                    data = json.loads(txt)
                except Exception:
                    if first_obj is None:
                        first_obj = _first_object_from_array_prefix(txt)
                    if first_obj is not None:
                        return {
                            "ok": True,
                            "status": resp.status,
                            "data": [first_obj],
                            "partial": True,
                            "truncated": truncated,
                            "note": "Decoded first array element from streamed prefix (best-effort preview).",
                        }
                    return {"ok": False, "status": resp.status, "raw": txt, "truncated": truncated}
                return {"ok": True, "status": resp.status, "data": data, "truncated": truncated}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _to_light_json(serp_json: Any) -> dict[str, Any]:
    """Convert full SERP JSON to a lightweight schema (token-friendly)."""
    data = serp_json if isinstance(serp_json, dict) else {}
    organic = data.get("organic")
    if not isinstance(organic, list):
        organic = []
    items: list[dict[str, Any]] = []
    for it in organic:
        if not isinstance(it, dict):
            continue
        link = it.get("link") or it.get("url") or it.get("href")
        title = it.get("title") or it.get("name")
        desc = it.get("description") or it.get("snippet")
        if isinstance(link, str) and isinstance(title, str):
            items.append({"link": link, "title": title, "description": desc if isinstance(desc, str) else None})
        if len(items) >= 50:
            break
    return {"organic": items}

def _candidate_tools_for_url(url: str, *, limit: int = 3) -> list[str]:
    """Pick likely Web Scraper tools for a URL based on spider_name + url field.
    
    Returns empty list if no good matches found (to avoid false positives).
    """
    host = _hostname(url)
    if not host:
        return []

    # Skip generic/example domains that shouldn't use Web Scraper tools
    generic_domains = {"example.com", "example.org", "example.net", "test.com", "localhost"}
    if host in generic_domains or host.endswith(".example.com"):
        return []

    tools, _ = _ensure_tools()
    scored: list[tuple[int, str]] = []

    for t in tools:
        k = tool_key(t)
        spider = (getattr(t, "SPIDER_NAME", "") or "").lower()
        # Must accept url-like input for generic routing
        fields = getattr(t, "__dataclass_fields__", {})  # type: ignore[attr-defined]
        has_url_field = "url" in fields
        if not has_url_field:
            continue

        # Early filtering: skip tools that clearly don't match the current site, avoid mis-selecting eBay/Crunchbase etc. for content sites like BBC/MDN
        kl = k.lower()
        # E-commerce platform tools: strict domain matching
        if "amazon" in kl and "amazon" not in host:
            continue
        if "walmart" in kl and "walmart" not in host:
            continue
        if "ebay" in kl and "ebay" not in host:
            continue
        if "etsy" in kl and "etsy" not in host:
            continue
        if "shopify" in kl and "shopify" not in host and "myshopify" not in host:
            continue
        # Business/recruitment platform tools: strict domain matching
        if "crunchbase" in kl and "crunchbase" not in host:
            continue
        if "glassdoor" in kl and "glassdoor" not in host:
            continue
        if "linkedin" in kl and "linkedin" not in host:
            continue
        if "indeed" in kl and "indeed" not in host:
            continue
        # Code/development platform tools: strict domain matching
        if "github" in kl and "github" not in host:
            continue
        if "gitlab" in kl and "gitlab" not in host:
            continue
        if "bitbucket" in kl and "bitbucket" not in host:
            continue
        # Repository tools only work on GitHub/GitLab domains
        if "repository" in kl and "github" not in host and "gitlab" not in host:
            continue
        # Google service tools: strict matching
        if ("googlemaps" in kl or "google.maps" in kl) and "maps" not in host and "maps.google" not in host:
            continue
        # Google Shopping tools - skip pure google.com (especially search), only use on shopping-related hosts
        if ("googleshopping" in kl or "google.shopping" in kl) and "shopping" not in host and host == "google.com":
            continue  # Skip entirely instead of penalizing
        # Social media tools: strict domain matching
        if "twitter" in kl and "twitter" not in host and "x.com" not in host:
            continue
        if "facebook" in kl and "facebook" not in host:
            continue
        if "instagram" in kl and "instagram" not in host:
            continue
        if "tiktok" in kl and "tiktok" not in host:
            continue
        # Video platform tools: strict domain matching
        if "youtube" in kl and "youtube" not in host and "youtu.be" not in host:
            continue
        if "vimeo" in kl and "vimeo" not in host:
            continue

        # GitHub tools: only match if URL looks like a repository (has /username/repo pattern)
        if "github" in k.lower() and "github" in host:
            import re
            # Check if URL has repository pattern (github.com/username/repo)
            repo_pattern = r'github\.(com|io)/[^/]+/[^/\s?#]+'
            if not re.search(repo_pattern, url.lower()):
                # Not a repository URL (e.g., github.com homepage), skip GitHub tools
                continue
        
        score = 0
        # Strong match: spider name matches hostname (exact or substring match)
        if spider and (spider in host or host.endswith(spider) or spider.endswith(host)):
            score += 20  # Increased from 10 to require stronger matches
        # Prefer ByUrl tools (tend to be most robust)
        if "byurl" in k.lower() or k.lower().endswith(".productbyurl"):
            score += 5
        # Prefer tools in same coarse group, if inferable by host keywords
        if "amazon" in host and ".ecommerce." in k:
            score += 3
        if ("youtube" in host or "youtu" in host) and ".video." in k:
            score += 3
        
        # Only include tools with positive score (strong matches)
        # Require minimum score of 5 to avoid weak matches
        if score >= 5:
            scored.append((score, k))

    scored.sort(key=lambda x: (-x[0], x[1]))
    # Ensure uniqueness by tool key
    uniq: list[str] = []
    seen: set[str] = set()
    for _s, k in scored:
        if k in seen:
            continue
        seen.add(k)
        uniq.append(k)
        if len(uniq) >= max(0, limit):
            break
    return uniq


def _guess_tool_for_url(url: str) -> tuple[str | None, dict[str, Any]]:
    """Best-effort selection of a structured Web Scraper tool from a URL."""
    u = url.lower()
    host = _hostname(url)

    # YouTube
    if "youtube.com" in u or "youtu.be" in u:
        vid = _extract_youtube_video_id(url)
        if vid:
            return "thordata.tools.video.YouTube.VideoInfo", {"video_id": vid}
        return "thordata.tools.video.YouTube.VideoDownload", {"url": url}
    
    # GitHub - only use RepositoryByUrl for actual repository URLs, not homepage
    if "github.com" in u or "github.io" in u:
        # Check if it's a repository URL (has /username/repo format, not just github.com)
        import re
        # Pattern: github.com/username/repo (with at least one path segment after github.com)
        repo_pattern = r'github\.(com|io)/[^/]+/[^/\s?#]+'
        if re.search(repo_pattern, u):
            # Make sure it's not just github.com or github.com/
            path_match = re.search(r'github\.(com|io)/([^/\s?#]+)', u)
            if path_match:
                path_after_domain = path_match.group(2)
                # If there's a path segment after github.com, check if it looks like a repo path
                if '/' in u.split('github.com/', 1)[-1].split('?')[0].split('#')[0]:
                    return "thordata.tools.code.GitHub.RepositoryByUrl", {"url": url}
        # For GitHub homepage (github.com, github.com/, etc.), return None to use Unlocker
        return None, {}

    # Amazon
    if "amazon." in u:
        asin = _extract_amazon_asin(url)
        if asin:
            return "thordata.tools.ecommerce.Amazon.ProductByAsin", {"asin": asin, "domain": "amazon.com"}
        return "thordata.tools.ecommerce.Amazon.ProductByUrl", {"url": url}

    # Airbnb (travel)
    if "airbnb." in u:
        # Try a safe-by-url scraper if present in SDK; otherwise let unlocker handle it.
        return "thordata.tools.travel.Airbnb.ProductByUrl", {"url": url}

    # TikTok / Instagram / LinkedIn / Google Maps: default to url-based scrapers if available
    if "tiktok.com" in u:
        return "thordata.tools.social.TikTok.Post", {"url": url}
    if "instagram.com" in u:
        # Prefer post-url if it looks like a post; otherwise profile-by-url
        if "/p/" in u or "/reel/" in u or "/tv/" in u:
            return "thordata.tools.social.Instagram.PostByUrl", {"posturl": url}
        return "thordata.tools.social.Instagram.ProfileByUrl", {"profileurl": url}
    if "linkedin.com" in u:
        return "thordata.tools.social.LinkedIn.Company", {"url": url}
    if "google.com/maps" in u or "maps.app.goo.gl" in u:
        return "thordata.tools.search.GoogleMaps.DetailsByUrl", {"url": url}

    return None, {}


async def _run_web_scraper_tool(
    *,
    tool: str,
    params: dict[str, Any],
    wait: bool,
    max_wait_seconds: int,
    file_type: str,
    ctx: Optional[Context],
) -> dict[str, Any]:
    _, tools_map = _ensure_tools()
    t = tools_map.get(tool)
    if not t:
        return error_response(
            tool="web_scraper.run",
            input={"tool": tool, "params": params},
            error_type="invalid_tool",
            code="E4003",
            message="Unknown tool key. Use web_scraper.catalog to discover valid keys.",
        )

    # VideoToolRequest common_settings dict -> CommonSettings (DX improvement)
    from thordata.tools.base import VideoToolRequest
    from thordata.types.common import CommonSettings

    # IMPORTANT: keep a JSON-serializable copy for response "input"
    params_for_input: dict[str, Any] = dict(params or {})

    if issubclass(t, VideoToolRequest) and "common_settings" in params:
        cs_dict = params.pop("common_settings", {})
        if isinstance(cs_dict, dict):
            params["common_settings"] = CommonSettings(**cs_dict)

    tool_request = t(**params)  # type: ignore[misc]
    client = await ServerContext.get_client()
    try:
        task_id = await client.run_tool(tool_request)
        result: dict[str, Any] = {
            "task_id": task_id,
            "spider_id": tool_request.get_spider_id(),
            "spider_name": tool_request.get_spider_name(),
        }

        if wait:
            try:
                status = await client.wait_for_task(task_id, max_wait=max_wait_seconds)
                # ensure JSON-safe
                status_s = str(status)
                result["status"] = status_s
                if status_s.strip().lower() in {"ready", "success", "finished", "succeeded", "task succeeded", "task_succeeded"}:
                    download_url = await client.get_task_result(task_id, file_type=file_type)
                    result["download_url"] = enrich_download_url(download_url, task_id=task_id, file_type=file_type)
            except TimeoutError:
                # Product behavior: timeout is not a hard error; task may still complete later.
                result["status"] = "Timeout"
                result["note"] = "Task did not finish within max_wait_seconds. Use web_scraper.wait or web_scraper.status later."

        return ok_response(
            tool="web_scraper.run",
            input={"tool": tool, "params": params_for_input, "wait": wait, "file_type": file_type, "max_wait_seconds": max_wait_seconds},
            output=result,
        )
    except (ThordataNetworkError, ThordataAPIError) as e:
        err_type, err_code = _classify_error(e)
        # Productized fallback hint: if tool params include url, suggest unlocker.fetch / smart_scrape
        maybe_url = None
        if isinstance(params, dict):
            u = params.get("url")
            if isinstance(u, str) and u:
                maybe_url = u

        details = {"tool": tool, "error": str(e), "fallback": {}}
        if maybe_url:
            details["fallback"] = {
                "suggest_tool": "unlocker.fetch",
                "hint_params": {"url": maybe_url, "js_render": True, "output_format": "html"},
                "note": "WEB_SCRAPER task failed; try WEB_UNLOCKER for a resilient HTML capture.",
            }
        else:
            details["fallback"] = {
                "suggest_tool": "smart_scrape",
                "hint_params": {"url": "(provide url)"},
                "note": "WEB_SCRAPER task failed; smart_scrape can auto-pick another structured task or fallback to WEB_UNLOCKER.",
            }

        return error_response(
            tool="web_scraper.run",
            input={"tool": tool, "params": params_for_input, "wait": wait, "file_type": file_type, "max_wait_seconds": max_wait_seconds},
            error_type=err_type,
            code=err_code,
            message="WEB_SCRAPER task failed.",
            details=details,
        )


# ---------------------------------------------------------------------------
# Public MCP tool registrations (productized)
# ---------------------------------------------------------------------------


def register(mcp: FastMCP) -> None:
    """Register product-line tools:
    - SERP SCRAPER: serp.search / serp.batch_search
    - WEB UNLOCKER: unlocker.fetch / unlocker.batch_fetch
    - WEB SCRAPER: web_scraper.run / web_scraper.batch_run / web_scraper.catalog / web_scraper.groups
    - SMART: smart_scrape (auto-select tool + fallback)
    """

    # -------------------------
    # SERP SCRAPER
    # -------------------------
    @mcp.tool(name="serp.search")
    @handle_mcp_errors
    async def serp_search(
        q: str,
        *,
        num: int = 10,
        start: int = 0,
        engine: str = "google",
        device: str | None = None,
        format: str = "json",
        render_js: bool | None = None,
        no_cache: bool | None = None,
        ai_overview: bool | None = None,
        google_domain: str | None = None,
        gl: str | None = None,
        hl: str | None = None,
        cr: str | None = None,
        lr: str | None = None,
        location: str | None = None,
        uule: str | None = None,
        tbm: str | None = None,
        ludocid: str | None = None,
        kgmid: str | None = None,
        extra_params: dict[str, Any] | None = None,
        ctx: Optional[Context] = None,
    ) -> dict[str, Any]:
        await safe_ctx_info(ctx, f"SERP search q={q!r} num={num} start={start} engine={engine} format={format}")
        client = await ServerContext.get_client()
        fmt = (format or "json").strip().lower()
        # SDK supports json/html/both; we implement light_json as a post-process of json.
        sdk_fmt = "json" if fmt in {"json", "light_json", "light"} else ("both" if fmt in {"both", "json+html", "2"} else "html")
        extras = dict(extra_params or {})
        if ai_overview is not None:
            extras["ai_overview"] = ai_overview
        req = SerpRequest(
            query=q,
            engine=getattr(Engine, engine.upper(), Engine.GOOGLE),
            num=num,
            start=start,
            device=device,
            output_format=sdk_fmt,
            render_js=render_js,
            no_cache=no_cache,
            google_domain=google_domain,
            country=gl,
            language=hl,
            countries_filter=cr,
            languages_filter=lr,
            location=location,
            uule=uule,
            search_type=tbm,
            ludocid=ludocid,
            kgmid=kgmid,
            extra_params=extras,
        )
        # Use client's serp_search_advanced method
        data = await client.serp_search_advanced(req)
        output: Any = data
        if fmt in {"light_json", "light"}:
            output = _to_light_json(data)
        return ok_response(
            tool="serp.search",
            input={
                "q": q,
                "engine": engine,
                "num": num,
                "start": start,
                "device": device,
                "format": format,
                "render_js": render_js,
                "no_cache": no_cache,
                "ai_overview": ai_overview,
                "google_domain": google_domain,
                "gl": gl,
                "hl": hl,
                "cr": cr,
                "lr": lr,
                "location": location,
                "uule": uule,
                "tbm": tbm,
                "ludocid": ludocid,
                "kgmid": kgmid,
                "extra_params": extra_params,
            },
            output=output,
        )

    @mcp.tool(name="serp.batch_search")
    @handle_mcp_errors
    async def serp_batch_search(
        requests: list[dict[str, Any]],
        *,
        concurrency: int = 5,
        format: str = "json",
        ctx: Optional[Context] = None,
    ) -> dict[str, Any]:
        concurrency = max(1, min(int(concurrency), 20))
        client = await ServerContext.get_client()
        sem = asyncio.Semaphore(concurrency)
        fmt = (format or "json").strip().lower()
        sdk_fmt = "json" if fmt in {"json", "light_json", "light"} else ("both" if fmt in {"both", "json+html", "2"} else "html")

        async def _one(i: int, r: dict[str, Any]) -> dict[str, Any]:
            q = str(r.get("q", r.get("query", "")))
            if not q:
                return {"index": i, "ok": False, "error": {"type": "validation_error", "message": "Missing query"}}
            num = int(r.get("num", 10))
            start = int(r.get("start", 0))
            eng = r.get("engine", "google")
            device = r.get("device")
            render_js = r.get("render_js")
            no_cache = r.get("no_cache")
            google_domain = r.get("google_domain")
            gl = r.get("gl")
            hl = r.get("hl")
            cr = r.get("cr")
            lr = r.get("lr")
            location = r.get("location")
            uule = r.get("uule")
            tbm = r.get("tbm")
            ludocid = r.get("ludocid")
            kgmid = r.get("kgmid")
            extra_params = r.get("extra_params") if isinstance(r.get("extra_params"), dict) else {}
            ai_overview = r.get("ai_overview")
            if ai_overview is not None:
                extra_params = dict(extra_params)
                extra_params["ai_overview"] = ai_overview
            async with sem:
                req = SerpRequest(
                    query=q,
                    engine=getattr(Engine, str(eng).upper(), Engine.GOOGLE),
                    num=num,
                    start=start,
                    device=device,
                    output_format=sdk_fmt,
                    render_js=render_js if isinstance(render_js, bool) or render_js is None else None,
                    no_cache=no_cache if isinstance(no_cache, bool) or no_cache is None else None,
                    google_domain=google_domain,
                    country=gl,
                    language=hl,
                    countries_filter=cr,
                    languages_filter=lr,
                    location=location,
                    uule=uule,
                    search_type=tbm,
                    ludocid=ludocid,
                    kgmid=kgmid,
                    extra_params=extra_params,
                )
                # Use new namespace API
                data = await client.serp.search_advanced(req)
                out: Any = data
                if fmt in {"light_json", "light"}:
                    out = _to_light_json(data)
                return {"index": i, "ok": True, "q": q, "output": out}

        await safe_ctx_info(ctx, f"SERP batch_search count={len(requests)} concurrency={concurrency} format={format}")
        results = await asyncio.gather(*[_one(i, r) for i, r in enumerate(requests)])
        return ok_response(tool="serp.batch_search", input={"count": len(requests), "concurrency": concurrency, "format": format}, output={"results": results})

    # -------------------------
    # WEB UNLOCKER (Universal)
    # -------------------------
    @mcp.tool(name="unlocker.fetch")
    @handle_mcp_errors
    async def unlocker_fetch(
        url: str,
        *,
        output_format: str = "html",
        js_render: bool = True,
        country: str | None = None,
        block_resources: str | None = None,
        wait_ms: int | None = None,
        wait_for: str | None = None,
        max_chars: int = 20_000,
        extra_params: dict[str, Any] | None = None,
        ctx: Optional[Context] = None,
    ) -> dict[str, Any]:
        await safe_ctx_info(
            ctx,
            f"UNLOCKER fetch url={url!r} format={output_format} js_render={js_render} country={country} wait_for={wait_for!r}",
        )
        client = await ServerContext.get_client()
        wait = int(wait_ms) if wait_ms is not None else None
        kwargs = extra_params or {}
        fmt = (output_format or "html").strip().lower()
        # markdown is a presentation format; fetch html then convert
        fetch_format = "html" if fmt in {"markdown", "md"} else fmt

        # Use new namespace API
        data = await client.universal.scrape_async(
            url=url,
            js_render=js_render,
            country=country,
            wait_for=wait_for,
            wait_time=wait,
            output_format=fetch_format,
            block_resources=block_resources,
            **kwargs,
        )

        if fetch_format == "png":
            import base64
            if isinstance(data, (bytes, bytearray)):
                png_base64 = base64.b64encode(data).decode("utf-8")
                size = len(data)
            else:
                png_base64 = str(data)
                size = None
            return ok_response(
                tool="unlocker.fetch",
                input={
                    "url": url,
                    "output_format": output_format,
                    "js_render": js_render,
                    "country": country,
                    "block_resources": block_resources,
                    "wait_ms": wait_ms,
                    "wait_for": wait_for,
                    "max_chars": max_chars,
                    "extra_params": extra_params,
                },
                output={"png_base64": png_base64, "size": size, "format": "png"},
            )

        html = str(data) if not isinstance(data, str) else data
        if fmt in {"markdown", "md"}:
            md = html_to_markdown_clean(html)
            md = truncate_content(md, max_length=int(max_chars))
            return ok_response(
                tool="unlocker.fetch",
                input={
                    "url": url,
                    "output_format": output_format,
                    "js_render": js_render,
                    "country": country,
                    "block_resources": block_resources,
                    "wait_ms": wait_ms,
                    "wait_for": wait_for,
                    "max_chars": max_chars,
                    "extra_params": extra_params,
                },
                output={"markdown": md},
            )

        return ok_response(
            tool="unlocker.fetch",
            input={
                "url": url,
                "output_format": output_format,
                "js_render": js_render,
                "country": country,
                "block_resources": block_resources,
                "wait_ms": wait_ms,
                "wait_for": wait_for,
                "max_chars": max_chars,
                "extra_params": extra_params,
            },
            output={"html": html},
        )

    @mcp.tool(name="unlocker.batch_fetch")
    @handle_mcp_errors
    async def unlocker_batch_fetch(
        requests: list[dict[str, Any]],
        *,
        concurrency: int = 5,
        ctx: Optional[Context] = None,
    ) -> dict[str, Any]:
        concurrency = max(1, min(int(concurrency), 20))
        client = await ServerContext.get_client()
        sem = asyncio.Semaphore(concurrency)

        async def _one(i: int, r: dict[str, Any]) -> dict[str, Any]:
            url = str(r.get("url", ""))
            if not url:
                return {"index": i, "ok": False, "error": {"type": "validation_error", "message": "Missing url"}}
            output_format = str(r.get("output_format", "html"))
            js_render = bool(r.get("js_render", True))
            country = r.get("country")
            block_resources = r.get("block_resources")
            wait_ms = r.get("wait_ms")
            wait_for = r.get("wait_for")
            max_chars = int(r.get("max_chars", 20_000))
            wait = int(wait_ms) if isinstance(wait_ms, (int, float)) else None
            extra_params = r.get("extra_params") or {}
            if not isinstance(extra_params, dict):
                extra_params = {}
            fmt = (output_format or "html").strip().lower()
            fetch_format = "html" if fmt in {"markdown", "md"} else fmt

            async with sem:
                try:
                    # Use new namespace API
                    data = await client.universal.scrape_async(
                        url=url,
                        js_render=js_render,
                        country=country,
                        wait_for=wait_for,
                        wait_time=wait,
                        output_format=fetch_format,
                        block_resources=block_resources,
                        **extra_params,
                    )
                except (ThordataNetworkError, ThordataAPIError) as e:
                    et, ec = _classify_error(e)
                    return {"index": i, "ok": False, "url": url, "error": {"type": et, "code": ec, "message": str(e)}}

            if fetch_format == "png":
                import base64
                if isinstance(data, (bytes, bytearray)):
                    png_base64 = base64.b64encode(data).decode("utf-8")
                    size = len(data)
                else:
                    png_base64 = str(data)
                    size = None
                return {"index": i, "ok": True, "url": url, "output": {"png_base64": png_base64, "size": size, "format": "png"}}

            html = str(data) if not isinstance(data, str) else data
            if fmt in {"markdown", "md"}:
                md = html_to_markdown_clean(html)
                md = truncate_content(md, max_length=max_chars)
                return {"index": i, "ok": True, "url": url, "output": {"markdown": md}}

            return {"index": i, "ok": True, "url": url, "output": {"html": html}}

        await safe_ctx_info(ctx, f"UNLOCKER batch_fetch count={len(requests)} concurrency={concurrency}")
        results = await asyncio.gather(*[_one(i, r) for i, r in enumerate(requests)])
        return ok_response(tool="unlocker.batch_fetch", input={"count": len(requests), "concurrency": concurrency}, output={"results": results})

    # -------------------------
    # WEB SCRAPER (100+ tasks)
    # -------------------------
    @mcp.tool(name="web_scraper.groups")
    @handle_mcp_errors
    async def web_scraper_groups(ctx: Optional[Context] = None) -> dict[str, Any]:
        tools, _ = _ensure_tools()
        counts: dict[str, int] = {}
        for t in tools:
            g = tool_group_from_key(tool_key(t))
            counts[g] = counts.get(g, 0) + 1
        await safe_ctx_info(ctx, f"web_scraper.groups groups={len(counts)} tools={len(tools)}")
        return ok_response(tool="web_scraper.groups", input={}, output={"groups": [{"id": k, "count": v} for k, v in sorted(counts.items())], "total": len(tools)})

    @mcp.tool(name="web_scraper.list_tasks")
    @handle_mcp_errors
    async def web_scraper_list_tasks(
        *,
        page: int = 1,
        size: int = 20,
        ctx: Optional[Context] = None,
    ) -> dict[str, Any]:
        """List task history (web UI parity)."""
        page = max(1, int(page))
        size = max(1, min(int(size), 200))
        client = await ServerContext.get_client()
        await safe_ctx_info(ctx, f"web_scraper.list_tasks page={page} size={size}")
        data = await client.list_tasks(page=page, size=size)
        return ok_response(tool="web_scraper.list_tasks", input={"page": page, "size": size}, output=data)

    @mcp.tool(name="web_scraper.catalog")
    @handle_mcp_errors
    async def web_scraper_catalog(
        *,
        group: str | None = None,
        keyword: str | None = None,
        limit: int = 100,
        offset: int = 0,
        ctx: Optional[Context] = None,
    ) -> dict[str, Any]:
        limit = max(1, min(int(limit), 500))
        offset = max(0, int(offset))
        page, meta = _catalog(group=group, keyword=keyword, limit=limit, offset=offset)
        await safe_ctx_info(ctx, f"web_scraper.catalog total={meta['total']} offset={offset} limit={limit}")
        return ok_response(tool="web_scraper.catalog", input={"group": group, "keyword": keyword, "limit": limit, "offset": offset}, output={"tools": [tool_schema(t) for t in page], "meta": meta})

    @mcp.tool(name="web_scraper.status")
    @handle_mcp_errors
    async def web_scraper_status(task_id: str, *, ctx: Optional[Context] = None) -> dict[str, Any]:
        """Get task status (web UI parity)."""
        client = await ServerContext.get_client()
        await safe_ctx_info(ctx, f"web_scraper.status task_id={task_id}")
        status = await client.get_task_status(task_id)
        return ok_response(tool="web_scraper.status", input={"task_id": task_id}, output={"task_id": task_id, "status": str(status)})

    @mcp.tool(name="web_scraper.status_batch")
    @handle_mcp_errors
    async def web_scraper_status_batch(
        task_ids: list[str],
        *,
        ctx: Optional[Context] = None,
    ) -> dict[str, Any]:
        """Batch status helper (web UI parity / convenience)."""
        if not task_ids:
            return error_response(
                tool="web_scraper.status_batch",
                input={"task_ids": task_ids},
                error_type="validation_error",
                code="E4001",
                message="Provide task_ids",
            )
        client = await ServerContext.get_client()
        await safe_ctx_info(ctx, f"web_scraper.status_batch count={len(task_ids)}")
        results: list[dict[str, Any]] = []
        for tid in task_ids[:200]:
            try:
                s = await client.get_task_status(tid)
                results.append({"task_id": tid, "ok": True, "status": str(s)})
            except Exception as e:
                et, ec = _classify_error(e)
                results.append({"task_id": tid, "ok": False, "error": {"type": et, "code": ec, "message": str(e)}})
        return ok_response(tool="web_scraper.status_batch", input={"count": len(task_ids)}, output={"results": results})

    @mcp.tool(name="web_scraper.wait")
    @handle_mcp_errors
    async def web_scraper_wait(
        task_id: str,
        *,
        poll_interval_seconds: float = 5.0,
        max_wait_seconds: float = 600.0,
        ctx: Optional[Context] = None,
    ) -> dict[str, Any]:
        """Wait for a task to finish (web UI parity)."""
        client = await ServerContext.get_client()
        await safe_ctx_info(ctx, f"web_scraper.wait task_id={task_id} max_wait={max_wait_seconds}")
        status = await client.wait_for_task(task_id, poll_interval=poll_interval_seconds, max_wait=max_wait_seconds)
        return ok_response(
            tool="web_scraper.wait",
            input={"task_id": task_id, "poll_interval_seconds": poll_interval_seconds, "max_wait_seconds": max_wait_seconds},
            output={"task_id": task_id, "status": str(status)},
        )

    @mcp.tool(name="web_scraper.result")
    @handle_mcp_errors
    async def web_scraper_result(
        task_id: str,
        *,
        file_type: str = "json",
        preview: bool = True,
        preview_max_chars: int = 20_000,
        ctx: Optional[Context] = None,
    ) -> dict[str, Any]:
        """Get task download_url and optional preview (web UI parity)."""
        client = await ServerContext.get_client()
        await safe_ctx_info(ctx, f"web_scraper.result task_id={task_id} file_type={file_type} preview={preview}")
        download_url = await client.get_task_result(task_id, file_type=file_type)
        download_url = enrich_download_url(download_url, task_id=task_id, file_type=file_type)
        preview_obj: dict[str, Any] | None = None
        structured: dict[str, Any] | None = None
        if preview and file_type.lower() == "json":
            preview_obj = await _fetch_json_preview(download_url, max_chars=int(preview_max_chars))
            if preview_obj.get("ok") is True:
                data = preview_obj.get("data")
                if isinstance(data, list) and data:
                    structured = _normalize_record(data[0])
                elif isinstance(data, dict):
                    structured = _normalize_record(data)
        return ok_response(
            tool="web_scraper.result",
            input={"task_id": task_id, "file_type": file_type, "preview": preview, "preview_max_chars": preview_max_chars},
            output={"task_id": task_id, "download_url": download_url, "preview": preview_obj, "structured": structured},
        )

    @mcp.tool(name="web_scraper.result_batch")
    @handle_mcp_errors
    async def web_scraper_result_batch(
        task_ids: list[str],
        *,
        file_type: str = "json",
        preview: bool = False,
        preview_max_chars: int = 20_000,
        ctx: Optional[Context] = None,
    ) -> dict[str, Any]:
        """Batch result helper (download_url per task, optional preview for json)."""
        if not task_ids:
            return error_response(
                tool="web_scraper.result_batch",
                input={"task_ids": task_ids},
                error_type="validation_error",
                code="E4001",
                message="Provide task_ids",
            )
        client = await ServerContext.get_client()
        await safe_ctx_info(ctx, f"web_scraper.result_batch count={len(task_ids)} file_type={file_type} preview={preview}")
        results: list[dict[str, Any]] = []
        for tid in task_ids[:100]:
            try:
                dl = await client.get_task_result(tid, file_type=file_type)
                dl = enrich_download_url(dl, task_id=tid, file_type=file_type)
                prev: dict[str, Any] | None = None
                structured: dict[str, Any] | None = None
                if preview and file_type.lower() == "json":
                    prev = await _fetch_json_preview(dl, max_chars=int(preview_max_chars))
                    if prev.get("ok") is True:
                        data = prev.get("data")
                        if isinstance(data, list) and data:
                            structured = _normalize_record(data[0])
                        elif isinstance(data, dict):
                            structured = _normalize_record(data)
                results.append({"task_id": tid, "ok": True, "download_url": dl, "preview": prev, "structured": structured})
            except Exception as e:
                et, ec = _classify_error(e)
                results.append({"task_id": tid, "ok": False, "error": {"type": et, "code": ec, "message": str(e)}})
        return ok_response(tool="web_scraper.result_batch", input={"count": len(task_ids), "file_type": file_type, "preview": preview}, output={"results": results})

    @mcp.tool(name="web_scraper.cancel")
    @handle_mcp_errors
    async def web_scraper_cancel(task_id: str, *, ctx: Optional[Context] = None) -> dict[str, Any]:
        """Cancel a running task.

        Note: The public Web Scraper Tasks API spec currently does not define a cancel endpoint.
        We keep this tool for UI parity; it returns a clear not_supported error.
        """
        await safe_ctx_info(ctx, f"web_scraper.cancel task_id={task_id}")
        return error_response(
            tool="web_scraper.cancel",
            input={"task_id": task_id},
            error_type="not_supported",
            code="E4005",
            message="Cancel endpoint is not available in the current public Tasks API.",
            details={"task_id": task_id},
        )

    @mcp.tool(name="web_scraper.run")
    @handle_mcp_errors
    async def web_scraper_run(
        tool: str,
        *,
        params: dict[str, Any] | None = None,
        param_json: str | None = None,
        wait: bool = True,
        max_wait_seconds: int = 300,
        file_type: str = "json",
        ctx: Optional[Context] = None,
    ) -> dict[str, Any]:
        if params is None:
            if param_json:
                try:
                    params = json.loads(param_json)
                except json.JSONDecodeError as e:
                    return error_response(tool="web_scraper.run", input={"tool": tool, "param_json": param_json}, error_type="json_error", code="E4002", message=str(e))
            else:
                params = {}
        return await _run_web_scraper_tool(tool=tool, params=params, wait=wait, max_wait_seconds=max_wait_seconds, file_type=file_type, ctx=ctx)

    @mcp.tool(name="web_scraper.batch_run")
    @handle_mcp_errors
    async def web_scraper_batch_run(
        requests: list[dict[str, Any]],
        *,
        concurrency: int = 5,
        wait: bool = True,
        max_wait_seconds: int = 300,
        file_type: str = "json",
        ctx: Optional[Context] = None,
    ) -> dict[str, Any]:
        concurrency = max(1, min(int(concurrency), 20))
        sem = asyncio.Semaphore(concurrency)

        def _compact(out: dict[str, Any]) -> dict[str, Any]:
            # Avoid huge payloads in batch responses; keep only key fields
            if out.get("ok") is True and isinstance(out.get("output"), dict):
                o = out["output"]
                keep = {k: o.get(k) for k in ("task_id", "spider_id", "spider_name", "status", "download_url") if k in o}
                return {**out, "output": keep}
            if out.get("ok") is False and isinstance(out.get("error"), dict):
                e = out["error"]
                keep_e = {k: e.get(k) for k in ("type", "code", "message") if k in e}
                return {**out, "error": keep_e}
            return out

        async def _one(i: int, r: dict[str, Any]) -> dict[str, Any]:
            tool = str(r.get("tool", ""))
            if not tool:
                return {"index": i, "ok": False, "error": {"type": "validation_error", "message": "Missing tool"}}
            params = r.get("params")
            param_json = r.get("param_json")
            if params is None:
                if isinstance(param_json, str) and param_json:
                    try:
                        params = json.loads(param_json)
                    except json.JSONDecodeError as e:
                        return {"index": i, "ok": False, "error": {"type": "json_error", "message": str(e)}}
                else:
                    params = {}
            if not isinstance(params, dict):
                params = {}
            async with sem:
                out = await _run_web_scraper_tool(tool=tool, params=params, wait=wait, max_wait_seconds=max_wait_seconds, file_type=file_type, ctx=ctx)
                if isinstance(out, dict):
                    out = _compact(out)
                return {"index": i, **out}

        await safe_ctx_info(ctx, f"web_scraper.batch_run count={len(requests)} concurrency={concurrency}")
        results = await asyncio.gather(*[_one(i, r) for i, r in enumerate(requests)])
        return ok_response(tool="web_scraper.batch_run", input={"count": len(requests), "concurrency": concurrency, "wait": wait, "file_type": file_type}, output={"results": results})

    # -------------------------
    # SMART SCRAPE (auto tool + fallback)
    # -------------------------
    @mcp.tool(name="smart_scrape")
    @handle_mcp_errors
    async def smart_scrape(
        url: str,
        *,
        goal: str | None = None,
        prefer_structured: bool = True,
        preview: bool = True,
        preview_max_chars: int = 20_000,
        max_wait_seconds: int = 300,
        ctx: Optional[Context] = None,
    ) -> dict[str, Any]:
        """Auto-select a Web Scraper task for the URL; fallback to Unlocker if needed."""
        await safe_ctx_info(ctx, f"smart_scrape url={url!r} prefer_structured={prefer_structured} goal={goal!r}")

        # 0) Skip Web Scraper for certain URL patterns that are better handled by Unlocker
        host = _hostname(url)
        url_lower = url.lower()
        selected_tool: str | None = None
        selected_params: dict[str, Any] = {}
        candidates: list[tuple[str, dict[str, Any]]] = []  # Initialize candidates list

        # Special-case: Google search pages are best handled by SERP (more reliable than Unlocker).
        if prefer_structured and _is_google_search_url(url):
            q = _extract_google_search_query(url)
            await safe_ctx_info(ctx, f"smart_scrape: Google search detected, routing to SERP q={q!r}")
            try:
                client = await ServerContext.get_client()
                req = SerpRequest(
                    query=str(q or ""),
                    engine=Engine.GOOGLE,
                    num=10,
                    start=0,
                    country=None,
                    language=None,
                    google_domain="google.com",
                    gl=None,
                    hl=None,
                    location=None,
                    uule=None,
                    ludocid=None,
                    kgmid=None,
                    extra_params={},
                )
                # Use new namespace API
                data = await client.serp.search_advanced(req)
                return ok_response(
                    tool="smart_scrape",
                    input={"url": url, "prefer_structured": prefer_structured, "preview": preview},
                    output={
                        "path": "SERP",
                        "serp": {"engine": "google", "q": q, "num": 10, "start": 0},
                        "result": data,
                        "structured": {"url": url, "query": q, "engine": "google"},
                        "candidates": [],
                        "tried": [],
                    },
                )
            except Exception as e:
                # If SERP fails, continue with existing flow (Unlocker fallback below).
                await safe_ctx_info(ctx, f"smart_scrape: SERP routing failed, falling back. err={e}")
        # Skip Web Scraper for Google search URLs (better handled by SERP or Unlocker)
        skip_web_scraper = False
        generic_domains = {"example.com", "example.org", "example.net", "test.com", "localhost"}
        if host == "google.com" and "/search" in url_lower:
            await safe_ctx_info(ctx, f"smart_scrape: Google search URL detected, skipping Web Scraper and using Unlocker")
            skip_web_scraper = True
        elif host in generic_domains or (host and host.endswith(".example.com")):
            await safe_ctx_info(ctx, f"smart_scrape: Generic domain {host} detected, skipping Web Scraper and using Unlocker")
            skip_web_scraper = True
        
        if not skip_web_scraper:
                # 1) Try to select a Web Scraper tool automatically (extensible)
                guessed_tool, guessed_params = _guess_tool_for_url(url)
                selected_tool = guessed_tool
                selected_params = guessed_params
                # Only keep guessed tool if it truly exists in the catalog
                _, tools_map = _ensure_tools()
                if selected_tool and selected_tool in tools_map:
                    candidates.append((selected_tool, selected_params))

                # 1b) If no strong guess, pick a few candidates by hostname + "has url field"
                # Only do this if we have a strong match (score > 0)
                if not candidates:
                    candidate_keys = _candidate_tools_for_url(url, limit=3)
                    # Only use candidates if we have good matches (avoid false positives)
                    # Filter out obviously wrong tools (like GitHub for non-GitHub URLs)
                    if not host:
                        host = _hostname(url)
                    filtered_candidates = []
                    for k in candidate_keys:
                        # Additional GitHub filtering: only use RepositoryByUrl for actual repository URLs
                        if "github" in k.lower() and "repository" in k.lower() and "github" in host:
                            import re
                            repo_pattern = r'github\.(com|io)/[^/]+/[^/\s?#]+'
                            if not re.search(repo_pattern, url.lower()):
                                # Not a repository URL (e.g., github.com homepage), skip
                                continue
                        # Skip GitHub tools for non-GitHub URLs
                        if "github" in k.lower() and host and "github" not in host.lower():
                            continue
                        # Skip repository tools for non-repo URLs
                        if "repository" in k.lower() and host and "github" not in host.lower() and "gitlab" not in host.lower():
                            continue
                        # Skip Amazon tools for non-Amazon URLs
                        if "amazon" in k.lower() and host and "amazon" not in host.lower():
                            continue
                        # Skip Walmart tools for non-Walmart URLs
                        if "walmart" in k.lower() and host and "walmart" not in host.lower():
                            continue
                        # Skip Google Shopping tools for generic Google URLs (especially search URLs)
                        if ("googleshopping" in k.lower() or "google.shopping" in k.lower()):
                            if host == "google.com" or "/search" in url_lower:
                                continue
                        filtered_candidates.append(k)
                    
                    if filtered_candidates:
                        for k in filtered_candidates:
                            candidates.append((k, {"url": url}))
                    else:
                        # No good candidates found, skip Web Scraper and go straight to Unlocker
                        await safe_ctx_info(ctx, f"smart_scrape: No suitable Web Scraper tool found for {url}, using Unlocker")

        # 2) Execute Web Scraper candidates (try a couple) before falling back
        # Only try Web Scraper if we have good candidates and prefer_structured is True
        if prefer_structured and candidates:
            tried: list[dict[str, Any]] = []
            for tool, params in candidates[:3]:
                r = await _run_web_scraper_tool(
                    tool=tool,
                    params=params,
                    wait=True,
                    max_wait_seconds=max_wait_seconds,
                    file_type="json",
                    ctx=ctx,
                )
                # Check if task succeeded (status should be Ready/Success, not Failed)
                result_obj = r.get("output") if isinstance(r.get("output"), dict) else {}
                status = result_obj.get("status", "").lower() if isinstance(result_obj, dict) else ""
                
                # If status is Failed, don't try more Web Scraper tools - go to Unlocker
                # Also check if r.get("ok") is False, which indicates the tool call itself failed
                if status == "failed" or (isinstance(r, dict) and r.get("ok") is False):
                    await safe_ctx_info(ctx, f"smart_scrape: Web Scraper tool {tool} failed (status={status}, ok={r.get('ok')}), falling back to Unlocker")
                    tried.append({
                        "tool": tool,
                        "ok": r.get("ok"),
                        "status": status,
                        "error": (r.get("error") or {}) if isinstance(r, dict) else {},
                    })
                    break  # Exit loop and go to Unlocker fallback
                
                # Only return success if both ok is True AND status is not failed
                if isinstance(r, dict) and r.get("ok") is True and status not in {"failed", "error", "failure"}:
                    # Optional: fetch a tiny preview so smart_scrape returns immediate structured fields
                    download_url = result_obj.get("download_url") if isinstance(result_obj, dict) else None
                    preview_obj: dict[str, Any] | None = None
                    structured: dict[str, Any] = {"url": url}
                    if preview and isinstance(download_url, str) and download_url:
                        preview_obj = await _fetch_json_preview(download_url, max_chars=int(preview_max_chars))
                        # Try to use preview data even if JSON parsing failed but we have raw data
                        if preview_obj.get("ok") is True:
                            data = preview_obj.get("data")
                            # many tasks return a list of records
                            if isinstance(data, list) and data:
                                structured = _normalize_record(data[0], url=url)
                            elif isinstance(data, dict):
                                structured = _normalize_record(data, url=url)
                        elif preview_obj.get("status") == 200 and preview_obj.get("raw"):
                            # JSON parsing failed but we have raw data - try to extract basic info
                            raw = preview_obj.get("raw", "")
                            if raw:
                                # Try to extract basic fields from raw text if possible
                                structured = {"url": url, "raw_preview": raw[:500]}  # Limit raw preview size
                    return ok_response(
                        tool="smart_scrape",
                        input={"url": url, "goal": goal, "prefer_structured": prefer_structured, "preview": preview},
                        output={
                            "path": "WEB_SCRAPER",
                            "selected_tool": tool,
                            "selected_params": params,
                            "result": r.get("output"),
                            "structured": structured,
                            "preview": preview_obj,
                            "tried": tried,
                        },
                    )
                # Task failed or returned error - log and try next candidate
                # (This code should not be reached if status == "failed" due to break above)
                error_info = (r.get("error") or {}) if isinstance(r, dict) else {}
                tried.append({
                    "tool": tool,
                    "ok": r.get("ok"),
                    "status": status,
                    "error": error_info,
                })
                await safe_ctx_info(ctx, f"smart_scrape: Tool {tool} failed (status={status}), trying next candidate or Unlocker")

        # 3) Fallback to Unlocker
        client = await ServerContext.get_client()
        try:
            # Use a longer timeout for Unlocker (up to max_wait_seconds)
            unlocker_timeout = min(max_wait_seconds, 120)  # Cap at 120 seconds for Unlocker
            # Use new namespace API
            data = await client.universal.scrape_async(url=url, js_render=True, output_format="html")
            html = str(data) if not isinstance(data, str) else data
            # Empty HTML: likely blocked by strong JS/anti-bot/login wall, mark as error page for caller decision
            if not html or not html.strip() or len(html.strip()) < 100:
                # Empty or very short HTML usually indicates blocking
                extracted: dict[str, Any] = {
                    "is_error_page": True,
                    "http_status_hint": 0,
                    "empty_html": True,
                    "likely_blocked": True,
                }
                structured = _normalize_extracted(extracted, url=url)
                warning = "empty_html: page returned empty or very short content; likely blocked by anti-bot or requires login. Consider using Browser Scraper."
            else:
                extracted = _extract_structured_from_html(html)
                structured = _normalize_extracted(extracted, url=url)
                warning = None
                if structured.get("likely_blocked") is True:
                    warning = "likely_blocked: page appears to contain anti-bot/captcha content; consider changing proxy/cookies or using Browser Scraper."
                if structured.get("is_error_page") is True and structured.get("http_status_hint") in (404, 500, 0, 403):
                    error_msg = "smart_scrape: page looks like an error/empty page based on HTML"
                    if structured.get("http_status_hint") == 404:
                        error_msg += " (404 Not Found)"
                    elif structured.get("http_status_hint") == 403:
                        error_msg += " (403 Forbidden/Access Denied)"
                    elif structured.get("http_status_hint") == 500:
                        error_msg += " (500 Internal Server Error)"
                    error_msg += "; consider verifying the URL or using SERP first."
                    warning = (warning or "") + " " + error_msg if warning else error_msg
            return ok_response(
                tool="smart_scrape",
                input={"url": url, "goal": goal, "prefer_structured": prefer_structured, "preview": preview},
                output={
                    "path": "WEB_UNLOCKER",
                    "unlocker": {"html": html},
                    "extracted": extracted,
                    "structured": structured,
                    "warning": warning,
                    "selected_tool": selected_tool,
                    "selected_params": selected_params,
                    "candidates": [c[0] for c in candidates],
                    "tried": tried if "tried" in locals() else [],
                },
            )
        except asyncio.TimeoutError as e:
            # Handle timeout specifically
            await safe_ctx_info(ctx, f"smart_scrape: Unlocker timed out after {unlocker_timeout}s: {e}")
            return error_response(
                tool="smart_scrape",
                input={"url": url, "goal": goal, "prefer_structured": prefer_structured, "preview": preview},
                error_type="timeout_error",
                code="E2003",
                message=f"Unlocker request timed out after {unlocker_timeout} seconds. The page may be slow to load or blocked.",
                details={
                    "selected_tool": selected_tool,
                    "candidates": [c[0] for c in candidates],
                    "tried": tried if "tried" in locals() else [],
                    "timeout_seconds": unlocker_timeout,
                },
            )
        except Exception as e:
            # If Unlocker also fails, return error with context
            await safe_ctx_info(ctx, f"smart_scrape: Unlocker also failed: {e}")
            error_msg = str(e)
            # Extract more useful error information
            if "504" in error_msg or "Gateway Timeout" in error_msg:
                error_type = "timeout_error"
                error_code = "E2003"
                error_message = f"Unlocker request timed out (504 Gateway Timeout). The page may be slow to load or blocked."
            elif "timeout" in error_msg.lower():
                error_type = "timeout_error"
                error_code = "E2003"
                error_message = f"Unlocker request timed out: {error_msg}"
            else:
                error_type = "network_error"
                error_code = "E2002"
                error_message = f"Both Web Scraper and Unlocker failed. Last error: {error_msg}"
            return error_response(
                tool="smart_scrape",
                input={"url": url, "goal": goal, "prefer_structured": prefer_structured, "preview": preview},
                error_type=error_type,
                code=error_code,
                message=error_message,
                details={
                    "selected_tool": selected_tool,
                    "candidates": [c[0] for c in candidates],
                    "tried": tried if "tried" in locals() else [],
                },
            )

