"""Setup, entities and services in a test Home Assistant (fictitious household, see conftest)."""
from __future__ import annotations

import datetime as dt
from unittest.mock import patch

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import issue_registry as ir
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.werktags.const import DOMAIN

from .conftest import TODAY, d

# --- setup -------------------------------------------------------------------------

async def test_setup_creates_house_sensors_and_fetches_school_holidays(hass: HomeAssistant, setup_integration, fake_api):
    fake_api.school_holidays.assert_awaited_once()
    morning = hass.states.get("sensor.house_morning")
    assert morning is not None and morning.state == "workday"         # Thursday, nobody has a role yet → unknown
    assert morning.attributes["reason"] == "unknown"
    assert morning.attributes["attribution"].startswith("School holidays: OpenHolidays API")
    evening = hass.states.get("sensor.house_evening")
    assert evening.state == "before_workday" and evening.attributes["date"] == "2026-10-02"


async def test_unload(hass: HomeAssistant, setup_integration: MockConfigEntry):
    assert await hass.config_entries.async_unload(setup_integration.entry_id)
    await hass.async_block_till_done()
    assert setup_integration.state.name == "NOT_LOADED"
    assert hass.states.get("sensor.house_morning").state == "unavailable"


# --- entities follow the household ---------------------------------------------------

async def test_set_role_creates_entities_without_restart(hass: HomeAssistant, household):
    anna = hass.states.get("sensor.anna_morning")
    assert anna is not None and anna.state == "workday" and anna.attributes["role"] == "adult"
    assert anna.attributes["next_day_off"] == "2026-10-03"                 # public holiday (Saturday)
    assert hass.states.get("sensor.anna_evening").state == "before_workday"   # Friday is a workday
    clara = hass.states.get("sensor.clara_morning")
    assert clara.attributes["next_day_off"] == "2026-10-03"
    assert hass.states.get("calendar.anna_days_off") is not None


async def test_devices_and_areas(hass: HomeAssistant, household, areas):
    registry = dr.async_get(hass)
    bedroom = registry.async_get_device_by_identifier((DOMAIN, "test_entry_room_bedroom"), "test_entry")
    assert bedroom is not None and bedroom.name == "Bedroom" and bedroom.area_id is None   # see entity.room_device
    house = registry.async_get_device_by_identifier((DOMAIN, "test_entry_house"), "test_entry")
    assert house is not None


async def test_room_and_house_rules(hass: HomeAssistant, household, call_service, persons):
    assert hass.states.get("sensor.bedroom_morning").state == "workday"
    # Anna takes Thursday off: the bedroom sleeps in (day_off_wins), the evening still before a workday
    await call_service("set_days", person=persons["p_anna"], start=TODAY.isoformat(), status="day_off")
    bedroom = hass.states.get("sensor.bedroom_morning")
    assert bedroom.state == "day_off" and bedroom.attributes["reason"] == "exception_day_off"
    assert hass.states.get("sensor.bedroom_evening").state == "before_workday"
    assert hass.states.get("sensor.house_morning").state == "day_off"          # default: day_off_wins
    assert hass.states.get("sensor.anna_morning").attributes["day_type"] == "day_off"
    assert hass.states.get("sensor.ben_morning").state == "workday"


async def test_school_holidays_apply_to_pupils_only(hass: HomeAssistant, household):
    with patch("custom_components.werktags.coordinator.WerktagsCoordinator.today", return_value=d("2026-10-06")):
        household.runtime_data._rebuild()
        await hass.async_block_till_done()
        clara = hass.states.get("sensor.clara_morning")
        assert clara.state == "day_off" and clara.attributes["holiday_name"] == "Autumn Holidays"
        assert hass.states.get("sensor.nursery_morning").state == "day_off"
        assert hass.states.get("sensor.anna_morning").state == "workday"
        assert hass.states.get("sensor.house_morning").state == "workday"


async def test_role_none_makes_entities_unavailable(hass: HomeAssistant, household, call_service, persons):
    await call_service("set_role", person=persons["p_clara"], role="none", valid_from="2026-09-01")
    assert hass.states.get("sensor.clara_morning").state == "unavailable"
    assert hass.states.get("calendar.clara_days_off").state == "unavailable"
    assert hass.states.get("sensor.nursery_morning").state == "unavailable"   # room without residents


async def test_calendar_lists_days_off_as_all_day_events(hass: HomeAssistant, household):
    response = await hass.services.async_call(
        "calendar", "get_events",
        {"entity_id": "calendar.clara_days_off", "start_date_time": "2026-10-01T00:00:00+02:00",
         "end_date_time": "2026-10-20T00:00:00+02:00"},
        blocking=True, return_response=True)
    events = response["calendar.clara_days_off"]["events"]
    summaries = [(e["start"], e["end"], e["summary"]) for e in events]
    assert summaries[0] == ("2026-10-03", "2026-10-04", "Tag der Deutschen Einheit")   # name from the library, end exclusive
    assert ("2026-10-05", "2026-10-17", "Autumn Holidays") in summaries                 # one block, weekend inside included


# --- services -----------------------------------------------------------------------

async def test_get_days_and_preview(hass: HomeAssistant, household, call_service, persons):
    days = await call_service("get_days", start=TODAY.isoformat(), weeks=2)
    assert days["start"] == "2026-09-28" and days["end"] == "2026-10-11"
    assert [r["short_name"] for r in days["residents"]] == ["A", "B", "C"]
    saturday = next(day for day in days["days"] if day["date"] == "2026-10-03")
    assert saturday["weekend"] and saturday["public_holiday"]
    assert saturday["persons"]["p_anna"]["reason"] == "public_holiday"
    monday = next(day for day in days["days"] if day["date"] == "2026-10-05")
    assert monday["school_holiday"] == "Autumn Holidays"
    assert monday["persons"]["p_clara"]["effective"] == "day_off" and monday["persons"]["p_anna"]["effective"] == "workday"

    preview = await call_service("preview_days", person=[persons["p_anna"], persons["p_clara"]],
                                 start="2026-10-05", end="2026-10-11", status="day_off")
    assert {c["name"]: c["days"] for c in preview["changes"]} == {"Anna": 5, "Clara": 0}


async def test_set_days_range_default_and_workday_on_weekend(hass: HomeAssistant, household, call_service, persons):
    await call_service("set_days", person=[persons["p_anna"]], start="2026-10-03", end="2026-10-04", status="workday")
    days = await call_service("get_days", start="2026-10-03", weeks=1)
    saturday = next(day for day in days["days"] if day["date"] == "2026-10-03")
    assert saturday["persons"]["p_anna"] == {
        "effective": "workday", "default": "day_off", "exception": "workday",
        "reason": "exception_workday", "holiday_name": saturday["public_holiday"], "role": "adult"}
    await call_service("set_days", person=[persons["p_anna"]], start="2026-10-03", end="2026-10-04", status="default")
    days = await call_service("get_days", start="2026-10-03", weeks=1)
    assert days["days"][5]["persons"]["p_anna"]["exception"] is None


async def test_get_overview_lists_every_person_and_area(hass: HomeAssistant, household, call_service, areas):
    overview = await call_service("get_overview")
    persons = {p["name"]: p for p in overview["persons"]}
    assert persons["Clara"]["role_today"] == "pupil" and persons["Clara"]["short_name"] == "C"
    assert persons["Anna"]["roles"] == [{"valid_from": "2010-01-01", "role": "adult"}]
    rooms = {r["name"]: r for r in overview["rooms"]}
    assert rooms["Kitchen"]["residents_today"] == [] and rooms["Kitchen"]["assignments"] == []
    assert rooms["Bedroom"]["residents_today"] == ["p_anna", "p_ben"]
    assert overview["house"]["residents_today"] == ["p_anna", "p_ben"]
    assert overview["status"]["school_holidays"]["periods"] == 6


async def test_remove_role_and_room_steps(hass: HomeAssistant, household, call_service, persons, areas):
    await call_service("set_role", person=persons["p_clara"], role="adult", valid_from="2027-08-01")
    overview = await call_service("get_overview")
    clara = next(p for p in overview["persons"] if p["name"] == "Clara")
    assert [r["role"] for r in clara["roles"]] == ["pupil", "adult"]
    await call_service("remove_role", person=persons["p_clara"], valid_from="2027-08-01")
    with pytest.raises(ServiceValidationError):
        await call_service("remove_role", person=persons["p_clara"], valid_from="2010-01-01")   # last step
    await call_service("set_room", area=areas["Bedroom"], morning_rule="workday_wins")
    await call_service("set_days", person=persons["p_anna"], start=TODAY.isoformat(), status="day_off")
    assert hass.states.get("sensor.bedroom_morning").state == "workday"
    with pytest.raises(ServiceValidationError):
        await call_service("remove_room_assignment", area=areas["Bedroom"], valid_from="1999-01-01")


async def test_validation_errors(hass: HomeAssistant, household, call_service, persons):
    with pytest.raises(ServiceValidationError):
        await call_service("set_days", person=persons["p_anna"], start="2026-10-05", end="2026-10-01", status="day_off")
    with pytest.raises(ServiceValidationError):
        await call_service("set_days", person=persons["p_anna"], start="2026-01-01", end="2027-12-31", status="day_off")
    with pytest.raises(ServiceValidationError):
        await call_service("set_role", person=persons["p_anna"], role="adult", short_name="B")   # taken by Ben
    hass.states.async_set("light.not_a_person", "on")
    with pytest.raises((ServiceValidationError, Exception)):
        await call_service("set_days", person="light.not_a_person", start="2026-10-05", status="day_off")


async def test_data_survives_a_reload(hass: HomeAssistant, household: MockConfigEntry, hass_storage):
    assert await hass.config_entries.async_unload(household.entry_id)
    await hass.async_block_till_done()
    assert await hass.config_entries.async_setup(household.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get("sensor.clara_morning").attributes["role"] == "pupil"
    assert f"{DOMAIN}.data" in hass_storage


# --- school holidays ---------------------------------------------------------------------

async def test_failed_fetch_keeps_old_data_and_raises_issue_after_three_failures(hass: HomeAssistant, household,
                                                                                 fake_api, call_service):
    fake_api.school_holidays.side_effect = RuntimeError("down")
    for _ in range(3):
        await call_service("refresh_school_holidays")
    status = (await call_service("get_overview"))["status"]["school_holidays"]
    assert status["periods"] == 6 and status["failures"] == 3
    assert ir.async_get(hass).async_get_issue(DOMAIN, "school_holidays_unreachable") is not None
    fake_api.school_holidays.side_effect = None
    await call_service("refresh_school_holidays")
    assert ir.async_get(hass).async_get_issue(DOMAIN, "school_holidays_unreachable") is None


async def test_implausible_answer_is_rejected(hass: HomeAssistant, household, fake_api, call_service, school_holidays):
    fake_api.school_holidays.return_value = school_holidays[:1]         # no summer holidays
    await call_service("refresh_school_holidays")
    status = (await call_service("get_overview"))["status"]["school_holidays"]
    assert status["periods"] == 6 and status["failures"] == 1


async def test_unknown_days_count_as_workday(hass: HomeAssistant, household):
    with patch("custom_components.werktags.coordinator.WerktagsCoordinator.today", return_value=d("2028-03-06")):
        household.runtime_data._rebuild()
        await hass.async_block_till_done()
        clara = hass.states.get("sensor.clara_morning")
        assert clara.state == "workday" and clara.attributes["reason"] == "unknown"


async def test_calendar_source(hass: HomeAssistant, config_entry: MockConfigEntry, persons, areas, fake_api, call_service):
    """School holidays from a calendar entity: all-day events, end exclusive."""
    from homeassistant.setup import async_setup_component

    async def fake_get_events(call):
        return {"calendar.school": {"events": [
            {"start": "2026-10-05", "end": "2026-10-17", "summary": "Autumn"},
            {"start": "2026-06-29", "end": "2026-08-08", "summary": "Summer"},
            {"start": "2026-11-02T08:00:00+01:00", "end": "2026-11-02T09:00:00+01:00", "summary": "timed, ignored"},
        ]}}

    hass.services.async_register("calendar", "get_events", fake_get_events, supports_response="only")
    hass.config_entries.async_update_entry(config_entry, data={**config_entry.data,
                                                                "school_holiday_source": "calendar",
                                                                "calendar_entity": "calendar.school"})
    assert await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()
    fake_api.school_holidays.assert_not_awaited()
    await call_service("set_role", person=persons["p_clara"], role="pupil", valid_from="2010-01-01")
    days = await call_service("get_days", start="2026-10-05", weeks=2)
    assert days["days"][0]["school_holiday"] == "Autumn" and days["days"][12]["school_holiday"] is None
    assert hass.states.get("sensor.clara_morning").attributes.get("attribution") is None


async def test_admin_only_blocks_non_admins(hass: HomeAssistant, household: MockConfigEntry, call_service, persons,
                                            hass_read_only_user):
    from homeassistant.core import Context
    hass.config_entries.async_update_entry(household, options={**household.data, "admin_only": True})
    await hass.async_block_till_done()
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(DOMAIN, "set_days", {"person": persons["p_anna"], "start": TODAY.isoformat(),
                                                             "status": "day_off"},
                                       blocking=True, context=Context(user_id=hass_read_only_user.id))
    # reading is always allowed
    await hass.services.async_call(DOMAIN, "get_overview", {}, blocking=True, return_response=True,
                                   context=Context(user_id=hass_read_only_user.id))


async def test_midnight_rebuild(hass: HomeAssistant, household):
    """At midnight the sensors move to the new day without any change in data."""
    from homeassistant.util import dt as dt_util
    from pytest_homeassistant_custom_component.common import async_fire_time_changed
    with patch("custom_components.werktags.coordinator.WerktagsCoordinator.today", return_value=d("2026-10-02")):
        next_midnight = (dt_util.now() + dt.timedelta(days=1)).replace(hour=0, minute=0, second=15, microsecond=0)
        async_fire_time_changed(hass, next_midnight)
        await hass.async_block_till_done()
        assert hass.states.get("sensor.anna_evening").state == "before_day_off"   # Friday → public holiday Saturday
        assert hass.states.get("sensor.anna_morning").attributes["date"] == "2026-10-02"
