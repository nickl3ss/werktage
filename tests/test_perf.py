"""Performance budgets of the three core flows (docs/PROJECT.md § 6, standard PERF-01, TST-18).

Measured on 2026-10-21 (Windows, Python 3.14, 10 + 3 residents, 4 rooms, test harness): set_days +
rebuild ≈ 105 ms, get_days for 26 weeks ≈ 15 ms, midnight rebuild with next_workday/next_day_off
≈ 105 ms. The budgets are 200 / 300 / 500 ms; the thresholds below are five times the budget so that
a slow CI runner never makes the suite flaky (TST-14) while a real regression (an order of
magnitude) still fails. Run with ``pytest -s tests/test_perf.py`` to see the numbers.
"""
from __future__ import annotations

import datetime as dt
import time

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed

from custom_components.werktage.const import DOMAIN

from .conftest import TODAY

RESIDENTS = 10
ROOMS = 4


@pytest.fixture
async def big_household(hass: HomeAssistant, household: MockConfigEntry, call_service, persons, areas):
    """Ten residents (adults and pupils, one with a weekly pattern) in four rooms."""
    ids = []
    for i in range(RESIDENTS):
        pid, entity = f"p_perf{i}", f"person.perf{i}"
        hass.states.async_set(entity, "home", {"id": pid, "friendly_name": f"Perf {i}"})
        await call_service("set_role", person=entity, role="pupil" if i % 3 == 0 else "adult", valid_from="2010-01-01",
                           short_name=f"P{i}")
        ids.append(entity)
    await call_service("set_weekly", person=ids[1], weekdays=[4, 5, 6], valid_from="2026-01-01")
    for i, area in enumerate(list(areas.values())[:ROOMS]):
        await call_service("set_room", area=area, person=ids[i * 2:i * 2 + 3], valid_from="2010-01-01")
    await hass.async_block_till_done()
    return ids


def _seconds(start: float) -> float:
    return time.perf_counter() - start


def _morning_sensor(hass: HomeAssistant, entry: MockConfigEntry, person_id: str) -> str:
    entity_id = er.async_get(hass).async_get_entity_id("sensor", DOMAIN, f"{entry.entry_id}_resident_{person_id}_morning")
    assert entity_id
    return entity_id


async def test_set_days_rebuild_budget(hass: HomeAssistant, household: MockConfigEntry, big_household, call_service):
    """Core flow 1: a tap on a day in the calendar card (set_days → store → rebuild → sensors)."""
    start = time.perf_counter()
    await call_service("set_days", person=big_household[0], start=TODAY.isoformat(), status="day_off")
    await hass.async_block_till_done()
    elapsed = _seconds(start)
    print(f"set_days + rebuild: {elapsed * 1000:.0f} ms")
    assert elapsed < 1.0          # budget 200 ms
    assert hass.states.get(_morning_sensor(hass, household, "p_perf0")).state == "day_off"


async def test_get_days_budget(hass: HomeAssistant, big_household, call_service):
    """Core flow 2: the calendar card asks for 26 weeks."""
    start = time.perf_counter()
    days = await call_service("get_days", start=TODAY.isoformat(), weeks=26)
    elapsed = _seconds(start)
    print(f"get_days 26 weeks: {elapsed * 1000:.0f} ms")
    assert elapsed < 1.5          # budget 300 ms
    assert len(days["days"]) == 26 * 7 and len(days["days"][0]["persons"]) >= RESIDENTS


async def test_midnight_rebuild_budget(hass: HomeAssistant, household: MockConfigEntry, big_household):
    """Core flow 3: the midnight rebuild, every resident sensor asking for its next workday and day off."""
    next_midnight = (dt_util.now() + dt.timedelta(days=1)).replace(hour=0, minute=0, second=15, microsecond=0)
    start = time.perf_counter()
    async_fire_time_changed(hass, next_midnight)
    await hass.async_block_till_done()
    elapsed = _seconds(start)
    print(f"midnight rebuild: {elapsed * 1000:.0f} ms")
    assert elapsed < 2.5          # budget 500 ms
    assert hass.states.get(_morning_sensor(hass, household, "p_perf0")).attributes["next_workday"] is not None
