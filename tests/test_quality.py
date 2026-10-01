"""The less travelled paths: diagnostics, card serving, removal, error messages, fetch span."""
from __future__ import annotations

import datetime as dt
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED
from homeassistant.core import CoreState, HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import device_registry as dr
from homeassistant.setup import async_setup_component
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed

from custom_components.werktags import async_remove_config_entry_device, frontend, rules, sources
from custom_components.werktags.const import DOMAIN
from custom_components.werktags.coordinator import WerktagsError, async_probe_openholidays
from custom_components.werktags.diagnostics import async_get_config_entry_diagnostics
from custom_components.werktags.openholidays import Holiday
from custom_components.werktags.storage import SchoolHolidayCache, SchoolHolidayPeriod

from .conftest import TODAY, d

# --- diagnostics, cards, removal -------------------------------------------------------------

async def test_diagnostics_hold_counts_but_no_names(hass: HomeAssistant, household: MockConfigEntry):
    result = await async_get_config_entry_diagnostics(hass, household)
    assert result["counts"]["residents"] == 3 and result["counts"]["rooms"] == 2
    assert result["house"]["morning_rule"] == "day_off_wins"
    text = str(result)
    assert "Anna" not in text and "p_anna" not in text


async def test_cards_are_registered_once_when_the_frontend_is_loaded(hass: HomeAssistant):
    hass.config.components.update({"frontend", "http"})
    hass.http = MagicMock(async_register_static_paths=AsyncMock())
    with patch.object(frontend, "add_extra_js_url") as add_url:
        with patch.object(Path, "is_file", return_value=False):          # bundle missing: nothing is served
            await frontend.async_register(hass)
        add_url.assert_not_called()
        await frontend.async_register(hass)
        await frontend.async_register(hass)                               # second call is a no-op
    hass.http.async_register_static_paths.assert_awaited_once()
    url = add_url.call_args[0][1]
    assert url.startswith("/werktags_static/werktags-cards.js?v=") and len(url.rsplit("=", 1)[1]) == 8   # content hash


async def test_removing_the_integration_deletes_the_store(hass: HomeAssistant, household: MockConfigEntry, hass_storage):
    assert f"{DOMAIN}.data" in hass_storage
    await hass.config_entries.async_remove(household.entry_id)
    await hass.async_block_till_done()
    assert f"{DOMAIN}.data" not in hass_storage


async def test_only_devices_of_vanished_residents_and_rooms_may_be_deleted(hass: HomeAssistant, household: MockConfigEntry):
    registry = dr.async_get(hass)

    def device(identifier: str) -> dr.DeviceEntry:
        return registry.async_get_or_create(config_entry_id=household.entry_id, identifiers={(DOMAIN, identifier)})

    entry_id = household.entry_id
    assert await async_remove_config_entry_device(hass, household, device(f"{entry_id}_resident_gone"))
    assert await async_remove_config_entry_device(hass, household, device(f"{entry_id}_room_gone"))
    assert not await async_remove_config_entry_device(hass, household, device(f"{entry_id}_resident_p_anna"))
    assert not await async_remove_config_entry_device(hass, household, device(f"{entry_id}_house"))
    assert not await async_remove_config_entry_device(hass, household, device("other_resident_gone"))


# --- setup failures ----------------------------------------------------------------------------

async def test_unreadable_store_and_unsupported_country_fail_the_setup(hass: HomeAssistant, config_entry: MockConfigEntry,
                                                                       persons, areas):
    with patch("custom_components.werktags.storage.from_dict", side_effect=ValueError("version 99")):
        assert await async_setup_component(hass, DOMAIN, {})
        await hass.async_block_till_done()
    assert config_entry.state.name == "SETUP_ERROR" and config_entry.error_reason_translation_key == "store_unreadable"
    with patch("custom_components.werktags.sources.public_holidays", side_effect=NotImplementedError("XX")):
        await hass.config_entries.async_reload(config_entry.entry_id)
        await hass.async_block_till_done()
    assert config_entry.state.name == "SETUP_ERROR" and config_entry.error_reason_translation_key == "country_unsupported"


async def test_school_holidays_are_fetched_after_boot_and_checked_daily(hass: HomeAssistant, config_entry: MockConfigEntry,
                                                                        persons, areas, fake_api):
    hass.set_state(CoreState.not_running)               # as during bootstrap
    assert await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()
    fake_api.school_holidays.assert_not_awaited()                      # the network may not be up during boot
    hass.set_state(CoreState.running)
    hass.bus.async_fire(EVENT_HOMEASSISTANT_STARTED)
    await hass.async_block_till_done()
    fake_api.school_holidays.assert_awaited_once()
    coordinator = config_entry.runtime_data
    coordinator.data = coordinator.data.__class__(school_holidays=None)   # as if nothing was cached
    async_fire_time_changed(hass, (dt_util.now() + dt.timedelta(days=2)).replace(hour=3, minute=30, second=0, microsecond=0))
    await hass.async_block_till_done()
    assert fake_api.school_holidays.await_count == 2


# --- fetch span ----------------------------------------------------------------------------------

def test_fetch_span_is_three_calendar_years():
    assert sources.fetch_span(d("2026-09-30")) == (d("2026-01-01"), d("2028-12-31"))
    assert sources.year_span(d("2026-09-30"))[0] == d("2025-01-01")       # public holidays: one year back too


async def test_setup_probe_asks_for_the_same_range_as_the_monthly_fetch(hass: HomeAssistant, fake_api):
    assert await async_probe_openholidays(hass, "DE", "DE-NW") == 6
    first, last = fake_api.school_holidays.await_args[0][2:4]
    assert (first.month, first.day, last.month, last.day) == (1, 1, 12, 31) and last.year - first.year == 2


async def test_refresh_keeps_earlier_years_from_the_cache(hass: HomeAssistant, household: MockConfigEntry, fake_api,
                                                          call_service, school_holidays):
    coordinator = household.runtime_data
    fake_api.school_holidays.assert_awaited_once()
    assert fake_api.school_holidays.await_args[0][2:4] == (d("2026-01-01"), d("2028-12-31"))
    old = SchoolHolidayPeriod(d("2025-07-07"), d("2025-08-15"), "Summer 2025")
    cache = coordinator.data.school_holidays
    coordinator.data = coordinator.data.__class__(
        residents=coordinator.data.residents, rooms=coordinator.data.rooms,
        school_holidays=SchoolHolidayCache(cache.source, (old, *cache.periods), d("2025-01-01"), cache.known_to,
                                           cache.fetched_at, 0))
    fake_api.school_holidays.return_value = [h for h in school_holidays if h.start.year >= 2026]
    await call_service("refresh_school_holidays")
    cache = coordinator.data.school_holidays
    assert cache.periods[0] == old and cache.known_from == d("2025-01-01")       # last year survives
    assert len(cache.periods) == 1 + 5
    days = await call_service("get_days", start="2025-07-14", weeks=1)
    assert days["days"][0]["school_holiday"] == "Summer 2025"


# --- error messages have their own translation keys ------------------------------------------

async def test_rejected_changes_name_their_reason(hass: HomeAssistant, household: MockConfigEntry, call_service, persons,
                                                  areas):
    coordinator = household.runtime_data

    async def key_of(coro) -> str:
        with pytest.raises(ServiceValidationError) as err:
            await coro
        return err.value.translation_key

    assert await key_of(call_service("remove_role", person=persons["p_anna"], valid_from="1999-01-01")) == "no_role_entry"
    assert await key_of(call_service("remove_role", person=persons["p_anna"], valid_from="2010-01-01")) == "last_role_entry"
    assert await key_of(call_service("set_role", person=persons["p_anna"], role="adult", short_name="B")) == "short_name_taken"
    assert await key_of(call_service("remove_room_assignment", area=areas["Bedroom"], valid_from="1999-01-01")) \
        == "no_room_assignment"
    assert await key_of(call_service("set_room", area="nowhere", morning_rule="workday_wins")) == "unknown_area"
    hass.states.async_set("person.nobody", "home", {"id": "p_nobody", "friendly_name": "Nobody"})
    assert await key_of(call_service("set_weekly", person="person.nobody", weekdays=[0])) == "not_resident"
    assert await key_of(call_service("set_house", person=["person.nobody"])) == "not_residents"
    hass.states.async_set("person.ghost", "home", {})
    assert await key_of(call_service("set_days", person="person.ghost", start="2026-10-05", status="day_off")) \
        == "unknown_person"
    # reached only past the service schema
    for call, key in ((coordinator.async_set_weekly("p_anna", frozenset({9}), TODAY), "weekdays_range"),
                      (coordinator.async_set_role("p_anna", rules.Role.ADULT, TODAY, "ABC"), "short_name_length")):
        with pytest.raises(WerktagsError) as err:
            await call
        assert err.value.key == key
    # anything else the rules reject still becomes a validation error
    with patch.object(type(coordinator), "async_set_order", side_effect=ValueError("odd")):
        assert await key_of(call_service("set_order", person=[persons["p_anna"]])) == "invalid"


async def test_every_error_key_is_translated():
    import json
    base = Path(frontend.__file__).parent
    source = (base / "coordinator.py").read_text() + (base / "services.py").read_text()
    import re
    keys = set(re.findall(r'WerktagsError\("(\w+)"', source)) | set(re.findall(r'translation_key="(\w+)"', source))
    for name in ("strings.json", "translations/en.json", "translations/de.json"):
        translated = json.loads((base / name).read_text())
        missing = keys - set(translated["exceptions"]) - set(translated.get("issues", {}))
        assert not missing, f"{name}: {missing}"
        assert all(isinstance(v, dict) and v.get("message") for v in translated["exceptions"].values()), name


# --- services: the remaining branches ----------------------------------------------------------

async def test_order_room_steps_and_services_without_an_entry(hass: HomeAssistant, household: MockConfigEntry, call_service,
                                                              persons, areas):
    await call_service("set_order", person=[persons["p_clara"], persons["p_anna"]])
    overview = await call_service("get_overview")
    assert {p["name"]: p["order"] for p in overview["persons"] if p["order"] is not None}["Clara"] == 0
    await call_service("set_room", area=areas["Bedroom"], person=[persons["p_anna"]], valid_from="2027-01-01")
    await call_service("remove_room_assignment", area=areas["Bedroom"], valid_from="2027-01-01")
    assert len(household.runtime_data.data.rooms[areas["Bedroom"]].residents.steps) == 1
    # a resident whose role starts later is left out of earlier days
    await call_service("set_role", person=persons["p_ben"], role="none", valid_from="2010-01-01")
    await call_service("set_role", person=persons["p_ben"], role="adult", valid_from="2026-10-07")
    days = await call_service("get_days", start="2026-10-05", weeks=1)
    assert "p_ben" not in days["days"][0]["persons"] and "p_ben" in days["days"][2]["persons"]
    assert await hass.config_entries.async_unload(household.entry_id)
    with pytest.raises(ServiceValidationError) as err:
        await call_service("get_overview")
    assert err.value.translation_key == "not_loaded"


async def test_refresh_without_a_source_and_with_a_failing_calendar(hass: HomeAssistant, config_entry: MockConfigEntry,
                                                                    persons, areas, call_service):
    hass.config_entries.async_update_entry(config_entry, data={**config_entry.data, "school_holiday_source": "none"},
                                           options={"add_holidays": ["not a date"]})     # ignored with a warning
    assert await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()
    with pytest.raises(ServiceValidationError) as err:
        await call_service("refresh_school_holidays")
    assert err.value.translation_key == "no_source"

    async def broken(call):
        raise RuntimeError("calendar offline")

    hass.services.async_register("calendar", "get_events", broken, supports_response="only")
    hass.config_entries.async_update_entry(config_entry, data={**config_entry.data, "school_holiday_source": "calendar",
                                                                "calendar_entity": "calendar.school"}, options={})
    await hass.config_entries.async_reload(config_entry.entry_id)
    await hass.async_block_till_done()
    with pytest.raises(HomeAssistantError) as failed:
        await call_service("refresh_school_holidays")
    assert failed.value.translation_key == "fetch_failed"


# --- small pure helpers -----------------------------------------------------------------------------

def test_sources_fall_back_gracefully():
    names = sources.public_holidays("DE", "NW", [2026], language="xx_unknown")      # unknown language → default names
    assert d("2026-10-03") in names
    assert sources.subdivision_names("XX") == {}                                      # unknown country


def test_empty_history_and_unknown_resident():
    assert rules.History().first_date is None
    household = rules.Household(rules.Calendar({}, rules.SchoolHolidays(), rules.DEFAULT_WEEKEND), {}, {},
                                rules.House(), {})
    assert household.default_of("nobody", d("2026-10-01")) is None


def test_holiday_model_is_the_vendored_one():
    assert Holiday.__module__.startswith("custom_components.werktags.openholidays")


# --- a room is its residents -----------------------------------------------------------------

async def test_a_rule_alone_does_not_create_a_room(hass: HomeAssistant, household: MockConfigEntry, call_service, areas):
    with pytest.raises(ServiceValidationError) as err:
        await call_service("set_room", area=areas["Kitchen"], morning_rule="workday_wins")
    assert err.value.translation_key == "room_without_residents"
    assert areas["Kitchen"] not in household.runtime_data.data.rooms
    assert hass.states.get("sensor.kitchen_morning") is None


async def test_removing_the_last_assignment_removes_the_room(hass: HomeAssistant, household: MockConfigEntry, call_service,
                                                            areas):
    await call_service("remove_room_assignment", area=areas["Nursery"], valid_from="2010-01-01")
    coordinator = household.runtime_data
    assert areas["Nursery"] not in coordinator.data.rooms
    assert hass.states.get("sensor.nursery_morning").state == "unavailable"
    assert coordinator.is_stale_device_id(f"{household.entry_id}_room_{areas['Nursery']}")


async def test_rooms_without_residents_are_dropped_when_loading(hass: HomeAssistant, config_entry: MockConfigEntry, persons,
                                                               areas, hass_storage):
    """Earlier versions let a rule alone create a room; such rooms made unavailable entities."""
    hass_storage[f"{DOMAIN}.data"] = {"version": 2, "minor_version": 1, "key": f"{DOMAIN}.data", "data": {
        "version": 2, "residents": {}, "exceptions": {}, "school_holidays": None, "house": {"residents": []},
        "rooms": {"kitchen": {"residents": [], "morning_rule": "day_off_wins", "evening_rule": "workday_wins"}}}}
    assert await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()
    assert config_entry.runtime_data.data.rooms == {}
    assert hass.states.get("sensor.kitchen_morning") is None
    assert hass_storage[f"{DOMAIN}.data"]["data"]["rooms"] == {}

