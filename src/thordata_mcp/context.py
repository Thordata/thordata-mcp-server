from typing import Optional
from thordata.async_client import AsyncThordataClient
from .browser_session import BrowserSession
from .config import get_settings

class ServerContext:
    _client: Optional[AsyncThordataClient] = None
    _browser_session: Optional[BrowserSession] = None

    @classmethod
    async def get_client(cls) -> AsyncThordataClient:
        if cls._client is None:
            settings = get_settings()
            cls._client = AsyncThordataClient(
                scraper_token=settings.THORDATA_SCRAPER_TOKEN,
                public_token=settings.THORDATA_PUBLIC_TOKEN,
                public_key=settings.THORDATA_PUBLIC_KEY
            )
            # Ensure session is started
            await cls._client.__aenter__()
        return cls._client

    @classmethod
    async def get_browser_session(cls) -> BrowserSession:
        if cls._browser_session is None:
            client = await cls.get_client()
            cls._browser_session = BrowserSession(client)
        return cls._browser_session

    @classmethod
    async def cleanup(cls):
        if cls._browser_session:
            await cls._browser_session.close()
            cls._browser_session = None
            
        if cls._client:
            await cls._client.close()
            cls._client = None
