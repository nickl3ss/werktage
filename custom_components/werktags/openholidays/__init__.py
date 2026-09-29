"""Async client for the OpenHolidays API (https://www.openholidaysapi.org).

Public and school holidays for European countries and their subdivisions.
The data is licensed under the Open Database License (ODbL) 1.0; users of this
library must credit "OpenHolidays API (openholidaysapi.org)".

    async with aiohttp.ClientSession() as session:
        client = OpenHolidaysClient(session, user_agent="my-app/1.0")
        holidays = await client.school_holidays("DE", "DE-NW", date(2026, 1, 1), date(2027, 12, 31))
"""
from .client import DEFAULT_BASE_URL, OpenHolidaysClient
from .errors import InvalidResponse, OpenHolidaysError, RequestFailed
from .models import Country, Holiday, Subdivision, is_plausible, parse_countries, parse_holidays, parse_subdivisions

__all__ = [
    "DEFAULT_BASE_URL",
    "Country",
    "Holiday",
    "InvalidResponse",
    "OpenHolidaysClient",
    "OpenHolidaysError",
    "RequestFailed",
    "Subdivision",
    "is_plausible",
    "parse_countries",
    "parse_holidays",
    "parse_subdivisions",
]
__version__ = "0.1.0"
