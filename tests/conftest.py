"""Fixtures for the integration tests: a small fictitious household in a test Home Assistant."""
from __future__ import annotations

import datetime as dt
from collections.abc import AsyncGenerator, Callable
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import entity_registry as er
from homeassistant.setup import async_setup_component
from openholidays import Holiday
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.werktags.const import (
    CONF_ADMIN_ONLY,
    CONF_CALENDAR_ENTITY,
    CONF_COUNTRY,
    CONF_HOUSE_EVENING_RULE,
    CONF_HOUSE_MORNING_RULE,
    CONF_HOUSE_ROLES,
    CONF_SCHOOL_HOLIDAY_SOURCE,
    CONF_SUBDIVISION,
    CONF_WEEKEND,
    DOMAIN,
    SOURCE_OPENHOLIDAYS,
)

d = dt.date.fromisoformat
TODAY = d("2026-10-01")     # a Thursday; 3 Oct is a public holiday in DE, autumn break 5–16 Oct (fictitious dates)

PERSONS = {"p_anna": "Anna", "p_ben": "Ben", "p_clara": "Clara"}
AREAS = {"bedroom": "Bedroom", "nursery": "Nursery", "kitchen": "Kitchen"}

FAKE_SCHOOL_HOLIDAYS = [
    Holiday("h1", d("2025-12-22"), d("2026-01-07"), {"EN": "Christmas Holidays", "DE": "Weihnachtsferien"}, "School", False, ("DE-NW",)),
    Holiday("h2", d("2026-06-29"), d("2026-08-07"), {"EN": "Summer Holidays", "DE": "Sommerferien"}, "School", False, ("DE-NW",)),
    Holiday("h3", d("2026-10-05"), d("2026-10-16"), {"EN": "Autumn Holidays", "DE": "Herbstferien"}, "School", False, ("DE-NW",)),
    Holiday("h4", d("2026-12-23"), d("2027-01-08"), {"EN": "Christmas Holidays", "DE": "Weihnachtsferien"}, "School", False, ("DE-NW",)),
    Holiday("h5", d("2027-06-28"), d("2027-08-06"), {"EN": "Summer Holidays", "DE": "Sommerferien"}, "School", False, ("DE-NW",)),
    Holiday("h6", d("2027-10-04"), d("2027-10-15"), {"EN": "Autumn Holidays", "DE": "Herbstferien"}, "School", False, ("DE-NW",)),
]

CONFIG = {
    CONF_COUNTRY: "DE", CONF_SUBDIVISION: "DE-NW", CONF_WEEKEND: ["5", "6"],
    CONF_SCHOOL_HOLIDAY_SOURCE: SOURCE_OPENHOLIDAYS, CONF_CALENDAR_ENTITY: None,
    CONF_HOUSE_ROLES: ["adult"], CONF_HOUSE_MORNING_RULE: "day_off_wins", CONF_HOUSE_EVENING_RULE: "workday_wins",
    CONF_ADMIN_ONLY: False,
}


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Let the test Home Assistant load custom_components/werktags."""


@pytest.fixture(autouse=True)
def frozen_today() -> AsyncGenerator[None]:
    """Every test runs on TODAY, 09:00 in the configured time zone."""
    with patch("custom_components.werktags.coordinator.WerktagsCoordinator.today", return_value=TODAY):
        yield


@pytest.fixture
def school_holidays() -> list[Holiday]:
    return list(FAKE_SCHOOL_HOLIDAYS)


@pytest.fixture(autouse=True)
def fake_api(school_holidays: list[Holiday]) -> AsyncGenerator[Any]:
    """The OpenHolidays client answers with fictitious data; no network."""
    with patch("custom_components.werktags.coordinator.OpenHolidaysClient") as client_cls:
        client_cls.return_value.school_holidays = AsyncMock(return_value=school_holidays)
        yield client_cls.return_value


@pytest.fixture
async def persons(hass: HomeAssistant) -> dict[str, str]:
    """Persons as the ``person`` integration would create them: state with ``id`` + registry entry."""
    registry = er.async_get(hass)
    entity_ids = {}
    for person_id, name in PERSONS.items():
        entry = registry.async_get_or_create("person", "person", person_id, suggested_object_id=name.lower())
        hass.states.async_set(entry.entity_id, "home", {"id": person_id, "friendly_name": name})
        entity_ids[person_id] = entry.entity_id
    return entity_ids


@pytest.fixture
async def areas(hass: HomeAssistant) -> dict[str, str]:
    registry = ar.async_get(hass)
    for name in AREAS.values():
        registry.async_get_or_create(name)   # id is derived from the name: "bedroom", "clara_s_room", …
    return {a.name: a.id for a in registry.async_list_areas()}


@pytest.fixture
def config_entry(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(domain=DOMAIN, title="Werktags", data=CONFIG, unique_id=DOMAIN, entry_id="test_entry")
    entry.add_to_hass(hass)
    return entry


@pytest.fixture
async def setup_integration(hass: HomeAssistant, config_entry: MockConfigEntry, persons: dict[str, str],
                            areas: dict[str, str]) -> MockConfigEntry:
    assert await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()
    assert config_entry.state.name == "LOADED"
    await hass.async_block_till_done()
    return config_entry


@pytest.fixture
def call_service(hass: HomeAssistant) -> Callable[..., Any]:
    async def _call(service: str, **data: Any) -> Any:
        response = await hass.services.async_call(
            DOMAIN, service, data, blocking=True,
            return_response=service in {"get_days", "preview_days", "get_overview"})
        await hass.async_block_till_done()
        return response
    return _call


@pytest.fixture
async def household(setup_integration: MockConfigEntry, persons: dict[str, str], areas: dict[str, str],
                    call_service: Callable[..., Any]) -> MockConfigEntry:
    """Anna and Ben adults in the bedroom, Clara a pupil in her room — all since 2010."""
    for person_id, role in (("p_anna", "adult"), ("p_ben", "adult"), ("p_clara", "pupil")):
        await call_service("set_role", person=persons[person_id], role=role, valid_from="2010-01-01",
                           short_name=PERSONS[person_id][0])
    await call_service("set_room", area=areas["Bedroom"], person=[persons["p_anna"], persons["p_ben"]],
                       valid_from="2010-01-01")
    await call_service("set_room", area=areas["Nursery"], person=[persons["p_clara"]], valid_from="2010-01-01")
    return setup_integration
