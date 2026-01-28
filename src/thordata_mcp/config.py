import os
from functools import lru_cache
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Environment-driven configuration for the MCP server."""

    # Thordata credentials
    THORDATA_SCRAPER_TOKEN: str | None = None
    THORDATA_PUBLIC_TOKEN: str | None = None
    THORDATA_PUBLIC_KEY: str | None = None
    
    # Optional browser-specific credentials (scraping browser)
    THORDATA_BROWSER_USERNAME: str | None = None
    THORDATA_BROWSER_PASSWORD: str | None = None
    
    # Optional residential proxy credentials (for proxy network tools)
    THORDATA_RESIDENTIAL_USERNAME: str | None = None
    THORDATA_RESIDENTIAL_PASSWORD: str | None = None
    
    # Logging
    LOG_LEVEL: str = "INFO"
    
    class Config:
        env_file = ".env"
        extra = "ignore"


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance."""
    return Settings()


# Convenience instance for modules that import `settings` directly.
settings: Settings = get_settings()

