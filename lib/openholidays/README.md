# openholidays

Small async Python client for the [OpenHolidays API](https://www.openholidaysapi.org):
public and school holidays for European countries and their subdivisions.
No API key needed. Built on `aiohttp`; you pass in your own session.

```python
import aiohttp
from datetime import date
from openholidays import OpenHolidaysClient, is_plausible

async with aiohttp.ClientSession() as session:
    client = OpenHolidaysClient(session, user_agent="my-app/1.0 (+https://example.org)")
    holidays = await client.school_holidays("DE", "DE-NW", date(2026, 1, 1), date(2027, 12, 31))
    for h in holidays:
        print(h.start, h.end, h.name("DE"))
    assert is_plausible(holidays, [2026, 2027])
```

Errors: `RequestFailed` (network, timeout, HTTP status) and `InvalidResponse`
(unexpected JSON); both derive from `OpenHolidaysError`. Parsing is separate
from the network (`parse_holidays`, `parse_subdivisions`, `parse_countries`),
so it can be tested offline.

## Data license

The holiday data is provided by the OpenHolidays project under the
**Open Database License (ODbL) 1.0**. Applications must credit
"OpenHolidays API (openholidaysapi.org)". Be a good citizen: send a meaningful
`User-Agent` and fetch rarely — the data changes a few times a year.

The code of this library is MIT licensed.
