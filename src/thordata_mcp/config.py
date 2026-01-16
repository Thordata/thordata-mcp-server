from typing import List, Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # --- Authentication ---
    # 允许为 None，由 .env 注入，运行时若缺失会抛错，但静态检查通过
    THORDATA_SCRAPER_TOKEN: Optional[str] = Field(default=None)
    THORDATA_PUBLIC_TOKEN: Optional[str] = Field(default=None)
    THORDATA_PUBLIC_KEY: Optional[str] = Field(default=None)

    # --- Tool Configuration ---
    ENABLED_TOOL_GROUPS: List[str] = ["web", "commerce", "media"]

    # --- Spider ID Mappings ---
    SPIDER_GOOGLE_MAPS: str = "google_map-details_by-url"
    SPIDER_AMAZON: str = "amazon_product_page"
    SPIDER_YOUTUBE: str = "youtube_video-post_by-url"
    SPIDER_INSTAGRAM: str = "instagram_post_page"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

# 实例化
settings = Settings()