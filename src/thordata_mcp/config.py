from typing import List, Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # --- Authentication ---
    THORDATA_SCRAPER_TOKEN: Optional[str] = Field(default=None)
    THORDATA_PUBLIC_TOKEN: Optional[str] = Field(default=None)
    THORDATA_PUBLIC_KEY: Optional[str] = Field(default=None)

    # --- Proxy / Browser Credentials ---
    THORDATA_BROWSER_USERNAME: Optional[str] = Field(default=None)
    THORDATA_BROWSER_PASSWORD: Optional[str] = Field(default=None)
    THORDATA_RESIDENTIAL_USERNAME: Optional[str] = Field(default=None)
    THORDATA_RESIDENTIAL_PASSWORD: Optional[str] = Field(default=None)

    # --- Tool Configuration ---
    ENABLED_TOOL_GROUPS: List[str] = ["web", "commerce", "media", "browser"]

    # --- Spider ID Mappings (Reference) ---
    # These match the keys in SPIDER_REGISTRY (see thordata_mcp/registry.py)
    SPIDER_GOOGLE_MAPS: str = "google_map-details_by-url"
    SPIDER_AMAZON: str = "amazon_global-product_by-url" 
    SPIDER_YOUTUBE: str = "youtube_video_by-url"
    SPIDER_TIKTOK: str = "tiktok_posts_by-url"
    SPIDER_LINKEDIN: str = "linkedin_job_listings_information_by-job-listing-url"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

settings = Settings()