from __future__ import annotations

from typing import Any, Optional

from mcp.server.fastmcp import Context, FastMCP
from thordata import AsyncThordataClient

from ...config import settings
from ...utils import handle_mcp_errors, ok_response


def register(mcp: FastMCP) -> None:
    """Register locations tools."""

    @mcp.tool(name="locations.countries")
    @handle_mcp_errors
    async def locations_countries(
        *,
        proxy_type: int = 2,
        ctx: Optional[Context] = None,
    ) -> dict[str, Any]:
        if ctx:
            await ctx.info(f"Listing countries proxy_type={proxy_type}")

        async with AsyncThordataClient(
            scraper_token=settings.THORDATA_SCRAPER_TOKEN,
            public_token=settings.THORDATA_PUBLIC_TOKEN,
            public_key=settings.THORDATA_PUBLIC_KEY,
        ) as client:
            data = await client.list_countries(proxy_type=proxy_type)
            return ok_response(
                tool="locations.countries",
                input={"proxy_type": proxy_type},
                output={"countries": data},
            )

    @mcp.tool(name="locations.states")
    @handle_mcp_errors
    async def locations_states(
        country_code: str,
        *,
        proxy_type: int = 2,
        ctx: Optional[Context] = None,
    ) -> dict[str, Any]:
        if ctx:
            await ctx.info(f"Listing states country={country_code} proxy_type={proxy_type}")

        async with AsyncThordataClient(
            scraper_token=settings.THORDATA_SCRAPER_TOKEN,
            public_token=settings.THORDATA_PUBLIC_TOKEN,
            public_key=settings.THORDATA_PUBLIC_KEY,
        ) as client:
            data = await client.list_states(country_code=country_code, proxy_type=proxy_type)
            return ok_response(
                tool="locations.states",
                input={"country_code": country_code, "proxy_type": proxy_type},
                output={"states": data},
            )

    @mcp.tool(name="locations.cities")
    @handle_mcp_errors
    async def locations_cities(
        country_code: str,
        *,
        state_code: str | None = None,
        proxy_type: int = 2,
        ctx: Optional[Context] = None,
    ) -> dict[str, Any]:
        if ctx:
            await ctx.info(
                f"Listing cities country={country_code} state={state_code} proxy_type={proxy_type}"
            )

        async with AsyncThordataClient(
            scraper_token=settings.THORDATA_SCRAPER_TOKEN,
            public_token=settings.THORDATA_PUBLIC_TOKEN,
            public_key=settings.THORDATA_PUBLIC_KEY,
        ) as client:
            data = await client.list_cities(
                country_code=country_code, state_code=state_code, proxy_type=proxy_type
            )
            return ok_response(
                tool="locations.cities",
                input={
                    "country_code": country_code,
                    "state_code": state_code,
                    "proxy_type": proxy_type,
                },
                output={"cities": data},
            )

    @mcp.tool(name="locations.asn")
    @handle_mcp_errors
    async def locations_asn(
        country_code: str,
        *,
        proxy_type: int = 2,
        ctx: Optional[Context] = None,
    ) -> dict[str, Any]:
        if ctx:
            await ctx.info(f"Listing ASN country={country_code} proxy_type={proxy_type}")

        async with AsyncThordataClient(
            scraper_token=settings.THORDATA_SCRAPER_TOKEN,
            public_token=settings.THORDATA_PUBLIC_TOKEN,
            public_key=settings.THORDATA_PUBLIC_KEY,
        ) as client:
            data = await client.list_asn(country_code=country_code, proxy_type=proxy_type)
            return ok_response(
                tool="locations.asn",
                input={"country_code": country_code, "proxy_type": proxy_type},
                output={"asn": data},
            )
