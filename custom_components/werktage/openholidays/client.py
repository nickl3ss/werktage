"""HTTP client for the OpenHolidays API, built on an aiohttp session you provide."""
from __future__ import annotations

import datetime as dt
from typing import Any

import aiohttp

from .errors import InvalidResponse, RequestFailed
from .models import Country, Holiday, Subdivision, parse_countries, parse_holidays, parse_subdivisions

DEFAULT_BASE_URL = "https://openholidaysapi.org"
DEFAULT_TIMEOUT_SECONDS = 15.0
MAX_RANGE_DAYS = 1095      # the API answers HTTP 400 to longer ranges ("The maximum date range is 1095 days")


class OpenHolidaysClient:
    """One instance per application; the session is shared and never closed here.

    ``user_agent`` should name the application and its version, so the operators
    of the API can see who is calling. Please keep the number of requests low —
    the data changes rarely, once a month is plenty.
    """

    def __init__(self, session: aiohttp.ClientSession, *, user_agent: str,
                 base_url: str = DEFAULT_BASE_URL, timeout: float = DEFAULT_TIMEOUT_SECONDS) -> None:
        self._session = session
        self._base_url = base_url.rstrip("/")
        self._headers = {"Accept": "application/json", "User-Agent": user_agent}
        self._timeout = aiohttp.ClientTimeout(total=timeout)

    async def _get(self, path: str, params: dict[str, str]) -> Any:
        url = f"{self._base_url}/{path}"
        try:
            async with self._session.get(url, params=params, headers=self._headers, timeout=self._timeout) as response:
                if response.status != 200:
                    raise RequestFailed(f"{path}: HTTP {response.status}", response.status)
                try:
                    return await response.json(content_type=None)
                except ValueError as err:
                    raise InvalidResponse(f"{path}: body is not JSON") from err
        except TimeoutError as err:
            raise RequestFailed(f"{path}: timeout after {self._timeout.total} s") from err
        except aiohttp.ClientError as err:
            raise RequestFailed(f"{path}: {err}") from err

    async def _holidays(self, path: str, country: str, subdivision: str | None,
                        valid_from: dt.date, valid_to: dt.date) -> list[Holiday]:
        """Longer ranges than the API accepts are fetched in consecutive windows;
        a holiday that spans a window boundary is returned once."""
        if valid_to < valid_from:
            raise ValueError("valid_to before valid_from")
        holidays: list[Holiday] = []
        seen: set[str] = set()
        start = valid_from
        while start <= valid_to:
            end = min(valid_to, start + dt.timedelta(days=MAX_RANGE_DAYS - 1))
            params = {"countryIsoCode": country, "validFrom": start.isoformat(), "validTo": end.isoformat()}
            if subdivision:
                params["subdivisionCode"] = subdivision
            for holiday in parse_holidays(await self._get(path, params)):
                if holiday.id not in seen:
                    seen.add(holiday.id)
                    holidays.append(holiday)
            start = end + dt.timedelta(days=1)
        return holidays

    async def school_holidays(self, country: str, subdivision: str | None,
                              valid_from: dt.date, valid_to: dt.date) -> list[Holiday]:
        """School holidays of a subdivision (e.g. ``"DE"``, ``"DE-NW"``) in a date range."""
        return await self._holidays("SchoolHolidays", country, subdivision, valid_from, valid_to)

    async def public_holidays(self, country: str, subdivision: str | None,
                              valid_from: dt.date, valid_to: dt.date) -> list[Holiday]:
        """Public holidays; with a subdivision only those that apply there."""
        return await self._holidays("PublicHolidays", country, subdivision, valid_from, valid_to)

    async def subdivisions(self, country: str) -> list[Subdivision]:
        return parse_subdivisions(await self._get("Subdivisions", {"countryIsoCode": country}))

    async def countries(self) -> list[Country]:
        return parse_countries(await self._get("Countries", {}))
