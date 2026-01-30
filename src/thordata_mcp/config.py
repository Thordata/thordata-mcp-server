import os
from functools import lru_cache
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Environment-driven configuration for the MCP server."""

    # Thordata credentials
    THORDATA_SCRAPER_TOKEN: str | None = None
    THORDATA_PUBLIC_TOKEN: str | None = None
    THORDATA_PUBLIC_KEY: str | None = None
    
    # Download URL enrichment (some SDK methods return a download URL missing required query params)
    # Typical working format:
    #   https://scraperapi.thordata.com/download?api_key=...&plat=1&task_id=...&type=json
    THORDATA_DOWNLOAD_BASE_URL: str = "https://scraperapi.thordata.com/download"
    THORDATA_DOWNLOAD_PLAT: str = "1"

    # Tasks discovery UX (to avoid dumping hundreds of tools to the client by default)
    # - mode=curated: only return tools from THORDATA_TASKS_GROUPS, with pagination
    # - mode=all: return all discovered tools
    # Default to listing ALL Web Scraper tasks, but paginated (no env changes required for “100+ tools” use-case).
    THORDATA_TASKS_LIST_MODE: str = "all"
    THORDATA_TASKS_LIST_DEFAULT_LIMIT: int = 100
    THORDATA_TASKS_GROUPS: str = "ecommerce,social,video,search,travel,code,professional"

    # Optional: restrict which SDK tool_keys are allowed to execute (safety/UX)
    # If set, only tool keys that match one of these comma-separated prefixes or exact keys are allowed.
    # Example: "thordata.tools.video.,thordata.tools.ecommerce.Amazon.ProductByAsin"
    THORDATA_TASKS_ALLOWLIST: str | None = None
    
    # Optional browser-specific credentials (scraping browser)
    THORDATA_BROWSER_USERNAME: str | None = None
    THORDATA_BROWSER_PASSWORD: str | None = None

    # Performance and timeout configuration
    UNLOCKER_DEFAULT_TIMEOUT: int = 30  # Default timeout for unlocker requests (seconds)
    UNLOCKER_MAX_RETRIES: int = 2  # Maximum number of retries
    UNLOCKER_RETRY_BACKOFF: float = 2.0  # Exponential backoff factor for retries

    SERP_DEFAULT_TIMEOUT: int = 15  # Default timeout for SERP requests (seconds)
    TASKS_DEFAULT_TIMEOUT: int = 60  # Default timeout for task-based scraping (seconds)

    # Performance monitoring
    ENABLE_PERFORMANCE_MONITORING: bool = True
    SLOW_REQUEST_THRESHOLD: float = 10.0  # Log warning if request takes longer than this (seconds)

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

