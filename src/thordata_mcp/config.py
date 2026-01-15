import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # API Credentials
    THORDATA_SCRAPER_TOKEN: str
    THORDATA_PUBLIC_TOKEN: str | None = None
    THORDATA_PUBLIC_KEY: str | None = None

    # Spider ID Mappings (Based on your Dashboard)
    # 你可以在 .env 中用 THORDATA_SPIDER_AMAZON=... 来覆盖这些默认值
    SPIDER_AMAZON: str = "amazon_product_page" # 假设值，请核对
    SPIDER_GOOGLE_MAPS: str = "google_map-details_by-url"
    SPIDER_YOUTUBE: str = "youtube_video-post_by-url"
    SPIDER_INSTAGRAM: str = "instagram_post_page"
    SPIDER_TIKTOK: str = "tiktok_post_page"

    class Config:
        env_file = ".env"
        extra = "ignore"

try:
    settings = Settings()
except Exception as e:
    # 允许在没有 .env 的情况下导入，但在运行时会报错
    settings = None