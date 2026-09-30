"""The client against a local aiohttp test server — no real network."""
from __future__ import annotations

import asyncio
import datetime as dt

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer
from openholidays import InvalidResponse, OpenHolidaysClient, RequestFailed

d = dt.date.fromisoformat

# The Home Assistant test plugin blocks sockets; these tests talk to a local test server only.
# The fixture (not the enable_socket mark) is used because both plugins hook the setup phase and
# their order differs between machines; a fixture always runs after the hooks.
pytestmark = pytest.mark.usefixtures("socket_enabled")

SCHOOL = [{"id": "s1", "startDate": "2031-06-30", "endDate": "2031-08-08", "type": "School",
           "name": [{"language": "EN", "text": "Summer Holidays"}], "nationwide": False,
           "subdivisions": [{"code": "XX-AA", "shortName": "AA"}]}]


@pytest.fixture
async def api():
    """A fake API that records requests and can misbehave on demand."""
    calls: list[tuple[str, dict[str, str], str]] = []
    mode = {"value": "ok"}

    async def school(request: web.Request) -> web.StreamResponse:
        calls.append(("SchoolHolidays", dict(request.query), request.headers.get("User-Agent", "")))
        if mode["value"] == "500":
            return web.Response(status=500, text="boom")
        if mode["value"] == "html":
            return web.Response(text="<html>", content_type="text/html")
        if mode["value"] == "slow":
            await asyncio.sleep(2)
        return web.json_response(SCHOOL)

    async def subdivisions(request: web.Request) -> web.Response:
        return web.json_response([{"code": "XX-AA", "name": [{"language": "EN", "text": "Alpha"}]}])

    app = web.Application()
    app.router.add_get("/SchoolHolidays", school)
    app.router.add_get("/PublicHolidays", school)
    app.router.add_get("/Subdivisions", subdivisions)
    async with TestClient(TestServer(app)) as client:
        yield client, calls, mode


async def test_school_holidays_sends_the_right_query_and_user_agent(api):
    client, calls, _ = api
    oh = OpenHolidaysClient(client.session, user_agent="werktags-test/0.1", base_url=str(client.make_url("")))
    holidays = await oh.school_holidays("XX", "XX-AA", d("2031-01-01"), d("2031-12-31"))
    assert [h.name() for h in holidays] == ["Summer Holidays"]
    path, query, agent = calls[0]
    assert path == "SchoolHolidays"
    assert query == {"countryIsoCode": "XX", "subdivisionCode": "XX-AA",
                     "validFrom": "2031-01-01", "validTo": "2031-12-31"}
    assert agent == "werktags-test/0.1"


async def test_public_holidays_without_subdivision(api):
    client, calls, _ = api
    oh = OpenHolidaysClient(client.session, user_agent="t", base_url=str(client.make_url("")))
    await oh.public_holidays("XX", None, d("2031-01-01"), d("2031-12-31"))
    assert "subdivisionCode" not in calls[0][1]
    assert (await oh.subdivisions("XX"))[0].code == "XX-AA"


async def test_http_error_and_bad_body_raise(api):
    client, _, mode = api
    oh = OpenHolidaysClient(client.session, user_agent="t", base_url=str(client.make_url("")))
    mode["value"] = "500"
    with pytest.raises(RequestFailed) as err:
        await oh.school_holidays("XX", "XX-AA", d("2031-01-01"), d("2031-12-31"))
    assert err.value.status == 500
    mode["value"] = "html"
    with pytest.raises(InvalidResponse):
        await oh.school_holidays("XX", "XX-AA", d("2031-01-01"), d("2031-12-31"))


async def test_timeout_raises_request_failed(api):
    client, _, mode = api
    oh = OpenHolidaysClient(client.session, user_agent="t", base_url=str(client.make_url("")), timeout=0.2)
    mode["value"] = "slow"
    with pytest.raises(RequestFailed, match="timeout"):
        await oh.school_holidays("XX", "XX-AA", d("2031-01-01"), d("2031-12-31"))


async def test_reversed_range_is_rejected_before_any_request(api):
    client, calls, _ = api
    oh = OpenHolidaysClient(client.session, user_agent="t", base_url=str(client.make_url("")))
    with pytest.raises(ValueError):
        await oh.school_holidays("XX", "XX-AA", d("2031-12-31"), d("2031-01-01"))
    assert calls == []
