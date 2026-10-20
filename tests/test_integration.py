"""Setup, entities and services in a test Home Assistant (fictitious household, see conftest)."""
from __future__ import annotations

import datetime as dt
from unittest.mock import patch

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import issue_registry as ir
from homeassistant.setup import async_setup_component
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed

from custom_components.werktage.const import DOMAIN

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


def _device(registry: dr.DeviceRegistry, identifier: str) -> dr.DeviceEntry | None:
    """Device lookup that works on the minimum and the current Home Assistant release."""
    if hasattr(registry, "async_get_device_by_identifier"):          # 2026.8 and later
        return registry.async_get_device_by_identifier((DOMAIN, identifier), "test_entry")
    return registry.async_get_device(identifiers={(DOMAIN, identifier)})


async def test_devices_and_areas(hass: HomeAssistant, household, areas):
    registry = dr.async_get(hass)
    bedroom = _device(registry, "test_entry_room_bedroom")
    assert bedroom is not None and bedroom.name == "Bedroom" and bedroom.area_id is None   # see entity.room_device
    house = _device(registry, "test_entry_house")
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
    with patch("custom_components.werktage.coordinator.WerktagsCoordinator.today", return_value=d("2026-10-06")):
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
        "effective": "workday", "default": "day_off", "exception": "workday", "calendar": None,
        "reason": "exception_workday", "holiday_name": saturday["public_holiday"], "role": "adult"}
    await call_service("set_days", person=[persons["p_anna"]], start="2026-10-03", end="2026-10-04", status="default")
    days = await call_service("get_days", start="2026-10-03", weeks=1)
    assert days["days"][5]["persons"]["p_anna"]["exception"] is None


async def test_weekly_days_off_replace_the_household_weekend(hass: HomeAssistant, household, call_service, persons):
    # Anna works four days: Friday off every week from this Monday on
    await call_service("set_weekly", person=persons["p_anna"], weekdays=[4, 5, 6], valid_from="2026-09-28")
    assert hass.states.get("sensor.anna_evening").state == "before_day_off"        # tomorrow is Friday
    assert hass.states.get("sensor.ben_evening").state == "before_workday"
    assert hass.states.get("binary_sensor.anna_workday").state == "on"            # Thursday
    friday = hass.states.get("sensor.anna_morning").attributes["next_day_off"]
    assert friday == "2026-10-02"
    overview = await call_service("get_overview")
    anna = next(p for p in overview["persons"] if p["name"] == "Anna")
    assert anna["off_weekdays"] == [4, 5, 6] and anna["off_weekdays_history"][0]["valid_from"] == "2026-09-28"
    assert overview["weekend"] == [5, 6]
    days = await call_service("get_days", start="2026-10-05", weeks=1)
    assert days["days"][4]["persons"]["p_anna"]["reason"] == "weekend"             # her Friday
    assert days["days"][4]["persons"]["p_ben"]["reason"] == "workday"
    await call_service("set_weekly", person=persons["p_anna"], household=True)
    assert hass.states.get("sensor.anna_evening").state == "before_workday"
    with pytest.raises(Exception, match="at most 6"):                                 # schema
        await call_service("set_weekly", person=persons["p_anna"], weekdays=[7])
    hass.states.async_set("person.nobody", "home", {"id": "p_nobody", "friendly_name": "Nobody"})
    with pytest.raises(ServiceValidationError):
        await call_service("set_weekly", person="person.nobody", weekdays=[0])       # not a resident


async def test_house_follows_chosen_residents(hass: HomeAssistant, household, call_service, persons):
    # only Clara (a pupil, autumn break from Monday) counts for the house from Monday on
    await call_service("set_house", person=[persons["p_clara"]], valid_from="2026-10-05")
    assert hass.states.get("sensor.house_morning").state == "workday"              # today the adults still count
    overview = await call_service("get_overview")
    assert overview["house"]["by_role"] is True and overview["house"]["residents_today"] == ["p_anna", "p_ben"]
    assert overview["house"]["assignments"] == [{"valid_from": "2026-10-05", "residents": ["p_clara"]}]
    days = await call_service("get_days", start="2026-10-05", weeks=1)
    assert days["days"][0]["persons"]["p_clara"]["reason"] == "school_holiday"
    coordinator = household.runtime_data
    assert coordinator.household.house_day(d("2026-10-05")).is_workday is False   # Clara's holidays rule the house
    assert coordinator.household.house_day(d("2026-10-01")).is_workday is True
    await call_service("set_house", by_role=True, valid_from="2026-10-05")
    assert coordinator.household.house_day(d("2026-10-05")).is_workday is True
    with pytest.raises(ServiceValidationError):
        await call_service("set_house", person=["person.nobody"])


async def test_binary_sensors_follow_residents_rooms_and_house(hass: HomeAssistant, household, call_service, persons):
    assert hass.states.get("binary_sensor.house_workday").state == "on"
    assert hass.states.get("binary_sensor.bedroom_workday").state == "on"
    assert hass.states.get("binary_sensor.clara_workday").attributes["reason"] == "workday"
    await call_service("set_days", person=persons["p_anna"], start=TODAY.isoformat(), status="day_off")
    assert hass.states.get("binary_sensor.anna_workday").state == "off"
    assert hass.states.get("binary_sensor.bedroom_workday").state == "off"       # day_off_wins
    assert hass.states.get("binary_sensor.house_workday").state == "off"
    await call_service("set_role", person=persons["p_clara"], role="none", valid_from="2026-09-01")
    assert hass.states.get("binary_sensor.clara_workday").state == "unavailable"
    assert hass.states.get("binary_sensor.nursery_workday").state == "unavailable"


async def test_holiday_corrections_from_the_options(hass: HomeAssistant, config_entry: MockConfigEntry, persons, areas,
                                                    call_service):
    hass.config_entries.async_update_entry(config_entry, options={
        "add_holidays": ["2026-10-02 Bridge day", "2026-10-30"], "remove_holidays": ["2026-10-03", "Reformation"]})
    assert await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()
    await call_service("set_role", person=persons["p_anna"], role="adult", valid_from="2010-01-01")
    days = {x["date"]: x for x in (await call_service("get_days", start="2026-09-28", weeks=5))["days"]}
    assert days["2026-10-02"]["public_holiday"] == "Bridge day"
    assert days["2026-10-02"]["persons"]["p_anna"]["reason"] == "public_holiday"
    assert days["2026-10-30"]["public_holiday"] == "Holiday"                          # unnamed
    assert days["2026-10-03"]["public_holiday"] is None                              # German Unity Day removed
    assert hass.states.get("sensor.anna_evening").state == "before_day_off"          # Friday is the bridge day


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
    from custom_components.werktage.openholidays import RequestFailed
    fake_api.school_holidays.side_effect = RequestFailed("down")
    for _ in range(3):
        with pytest.raises(HomeAssistantError):
            await call_service("refresh_school_holidays")
    status = (await call_service("get_overview"))["status"]["school_holidays"]
    assert status["periods"] == 6 and status["failures"] == 3
    assert ir.async_get(hass).async_get_issue(DOMAIN, "school_holidays_unreachable") is not None
    fake_api.school_holidays.side_effect = None
    await call_service("refresh_school_holidays")
    assert ir.async_get(hass).async_get_issue(DOMAIN, "school_holidays_unreachable") is None


async def test_implausible_answer_is_rejected(hass: HomeAssistant, household, fake_api, call_service, school_holidays):
    fake_api.school_holidays.return_value = school_holidays[:1]         # no summer holidays
    with pytest.raises(HomeAssistantError):
        await call_service("refresh_school_holidays")
    status = (await call_service("get_overview"))["status"]["school_holidays"]
    assert status["periods"] == 6 and status["failures"] == 1


async def test_unknown_days_count_as_workday(hass: HomeAssistant, household):
    with patch("custom_components.werktage.coordinator.WerktagsCoordinator.today", return_value=d("2028-03-06")):
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
    with patch("custom_components.werktage.coordinator.WerktagsCoordinator.today", return_value=d("2026-10-02")):
        next_midnight = (dt_util.now() + dt.timedelta(days=1)).replace(hour=0, minute=0, second=15, microsecond=0)
        async_fire_time_changed(hass, next_midnight)
        await hass.async_block_till_done()
        assert hass.states.get("sensor.anna_evening").state == "before_day_off"   # Friday → public holiday Saturday
        assert hass.states.get("sensor.anna_morning").attributes["date"] == "2026-10-02"


async def test_midnight_survives_a_public_holiday_error(hass: HomeAssistant, household, caplog):
    """If the public holidays cannot be recomputed at midnight, the day still changes with the known ones."""
    from homeassistant.util import dt as dt_util
    from pytest_homeassistant_custom_component.common import async_fire_time_changed
    with (patch("custom_components.werktage.coordinator.WerktagsCoordinator.today", return_value=d("2027-01-01")),
          patch("custom_components.werktage.sources.public_holidays", side_effect=NotImplementedError("XX"))):
        next_midnight = (dt_util.now() + dt.timedelta(days=1)).replace(hour=0, minute=0, second=15, microsecond=0)
        async_fire_time_changed(hass, next_midnight)    # a new year enters the kept span: holidays are recomputed
        await hass.async_block_till_done()
    assert hass.states.get("sensor.anna_morning").attributes["date"] == "2027-01-01"
    assert hass.states.get("sensor.anna_morning").state == "day_off"          # New Year's Day from the kept holidays
    assert household.state.name == "LOADED"
    assert "Public holidays could not be updated at midnight" in caplog.text


async def test_returning_to_the_household_weekend_keeps_the_past(hass: HomeAssistant, household, call_service, persons):
    """Invariant 2 (#11): the return to the household weekend is a step from a date on, not a deletion."""
    await call_service("set_weekly", person=persons["p_anna"], weekdays=[4, 5, 6], valid_from="2026-09-28")
    await call_service("set_weekly", person=persons["p_anna"], household=True, valid_from="2026-10-05")
    days = await call_service("get_days", start="2026-09-28", weeks=2)
    assert days["days"][4]["persons"]["p_anna"]["reason"] == "weekend"             # Friday 2 Oct: still her day off
    assert days["days"][11]["persons"]["p_anna"]["reason"] == "workday"            # Friday 9 Oct: household weekend
    overview = await call_service("get_overview")
    anna = next(p for p in overview["persons"] if p["name"] == "Anna")
    assert anna["off_weekdays_history"] == [{"valid_from": "2026-09-28", "weekdays": [4, 5, 6]},
                                            {"valid_from": "2026-10-05", "weekdays": None}]
    # a history that only ever says "household" is no history
    await call_service("set_weekly", person=persons["p_ben"], household=True, valid_from="2026-10-05")
    ben = next(p for p in overview["persons"] if p["name"] == "Ben")
    assert ben["off_weekdays_history"] == []
    assert household.runtime_data.data.residents["p_ben"].off_weekdays.steps == ()


async def test_returning_to_the_house_roles_keeps_the_past(hass: HomeAssistant, household, call_service, persons):
    """Invariant 2 (#11): "by role" from a date on leaves the earlier assignment in place."""
    await call_service("set_house", person=[persons["p_clara"]], valid_from="2026-10-05")
    await call_service("set_house", by_role=True, valid_from="2026-10-12")
    coordinator = household.runtime_data
    assert coordinator.household.house_day(d("2026-10-05")).is_workday is False   # Clara's autumn break ruled
    assert coordinator.household.house_day(d("2026-10-12")).is_workday is True    # the adults again
    overview = await call_service("get_overview")
    assert overview["house"]["assignments"] == [{"valid_from": "2026-10-05", "residents": ["p_clara"]},
                                                {"valid_from": "2026-10-12", "residents": None}]


async def test_the_house_has_a_school_holidays_calendar(hass: HomeAssistant, household):
    """#14: the source's periods with their names, as all-day events on the house device."""
    state = hass.states.get("calendar.house_school_holidays")
    assert state is not None and state.attributes["attribution"]
    response = await hass.services.async_call(
        "calendar", "get_events",
        {"entity_id": "calendar.house_school_holidays", "start_date_time": "2026-10-01T00:00:00+02:00",
         "end_date_time": "2027-01-31T00:00:00+01:00"},
        blocking=True, return_response=True)
    events = [(e["start"], e["end"], e["summary"]) for e in response["calendar.house_school_holidays"]["events"]]
    assert events == [("2026-10-05", "2026-10-17", "Autumn Holidays"), ("2026-12-23", "2027-01-09", "Christmas Holidays")]


async def test_a_resident_may_have_another_school_holiday_source(hass: HomeAssistant, household, call_service, persons,
                                                                fake_api):
    """#1: Clara goes to school in another region; her holidays come from that source, everyone else is unchanged."""
    from custom_components.werktage.openholidays import Holiday
    hesse = [Holiday("x1", d("2026-10-12"), d("2026-10-23"), {"EN": "Autumn Holidays"}, "School", False, ("DE-HE",)),
             Holiday("x2", d("2026-06-29"), d("2026-08-07"), {"EN": "Summer Holidays"}, "School", False, ("DE-HE",)),
             Holiday("x3", d("2027-07-05"), d("2027-08-13"), {"EN": "Summer Holidays"}, "School", False, ("DE-HE",))]
    default = list(fake_api.school_holidays.return_value)

    async def by_region(country, subdivision, first, last):
        return hesse if subdivision == "DE-HE" else default

    fake_api.school_holidays.side_effect = by_region
    await call_service("set_role", person=persons["p_clara"], role="pupil", valid_from="2010-01-01",
                       school_holiday_source="openholidays:DE-HE")
    await hass.async_block_till_done()
    days = await call_service("get_days", start="2026-10-05", weeks=2)
    assert days["days"][0]["persons"]["p_clara"]["reason"] == "workday"              # 5 Oct: a break in NW, not in HE
    assert days["days"][7]["persons"]["p_clara"]["reason"] == "school_holiday"        # 12 Oct: her own source
    assert days["days"][0]["school_holiday"] == "Autumn Holidays"                      # the installation's source
    assert hass.states.get("sensor.clara_morning").state == "workday"
    overview = await call_service("get_overview")
    clara = next(p for p in overview["persons"] if p["name"] == "Clara")
    assert clara["school_holiday_source"] == "openholidays:DE-HE"
    assert {o["value"] for o in overview["school_holiday_sources"]} >= {"", "openholidays:DE-HE"}
    assert set(overview["status"]["sources"]) == {"openholidays:DE-NW", "openholidays:DE-HE"}
    assert fake_api.school_holidays.await_count == 2                                   # one fetch per source
    assert fake_api.school_holidays.await_args_list[1].args[:2] == ("DE", "DE-HE")

    await call_service("set_role", person=persons["p_clara"], role="pupil", valid_from="2010-01-01",
                       school_holiday_source="")                                       # back to the installation's
    days = await call_service("get_days", start="2026-10-05", weeks=1)
    assert days["days"][0]["persons"]["p_clara"]["reason"] == "school_holiday"
    await call_service("refresh_school_holidays")
    assert set((await call_service("get_overview"))["status"]["sources"]) == {"openholidays:DE-NW"}   # pruned
    with pytest.raises(ServiceValidationError):
        await call_service("set_role", person=persons["p_clara"], role="pupil", valid_from="2010-01-01",
                           school_holiday_source="moon:far")


async def test_personal_calendars_give_days_off_and_extra_workdays(hass: HomeAssistant, household, call_service, persons):
    """#2: all-day events of the resident's calendars become days off / workdays below a manual exception."""
    events = {
        "calendar.anna": [{"start": "2026-10-07", "end": "2026-10-10", "summary": "Urlaub Nordsee"},      # Wed–Fri
                          {"start": "2026-10-20", "end": "2026-10-21", "summary": "Zahnarzt"},            # no keyword
                          {"start": "2026-10-21T08:00:00+02:00", "end": "2026-10-21T09:00:00+02:00", "summary": "Urlaub?"}],
        "calendar.shifts": [{"start": "2026-10-10", "end": "2026-10-11", "summary": "Samstagsdienst"}],   # Saturday
    }
    calls = []

    async def fake_get_events(call):
        calls.append(call.data["entity_id"])
        if events.get("broken"):
            raise RuntimeError("calendar offline")
        return {call.data["entity_id"]: {"events": events.get(call.data["entity_id"], [])}}

    hass.services.async_register("calendar", "get_events", fake_get_events, supports_response="only")
    hass.states.async_set("calendar.anna", "off", {"friendly_name": "Anna privat"})
    hass.states.async_set("calendar.shifts", "off", {"friendly_name": "Schichten"})
    with pytest.raises(ServiceValidationError):
        await call_service("set_calendars", person=persons["p_anna"], days_off_calendar="calendar.nowhere")
    await call_service("set_calendars", person=persons["p_anna"], days_off_calendar="calendar.anna",
                       workdays_calendar="calendar.shifts", keyword="Urlaub")
    await hass.async_block_till_done()
    days = {day["date"]: day["persons"]["p_anna"] for day in (await call_service("get_days", start="2026-10-05", weeks=3))["days"]}
    assert days["2026-10-07"]["reason"] == "calendar_day_off" and days["2026-10-07"]["calendar"] == "day_off"
    assert days["2026-10-09"]["reason"] == "calendar_day_off"                              # end exclusive: 7, 8, 9
    assert days["2026-10-10"]["reason"] == "calendar_workday"                              # the shift (no keyword there)
    assert days["2026-10-20"]["reason"] == "workday" and days["2026-10-20"]["calendar"] is None   # no keyword, timed ignored
    assert hass.states.get("sensor.ben_morning").attributes["reason"] == "workday"          # others unchanged
    overview = await call_service("get_overview")
    anna = next(p for p in overview["persons"] if p["name"] == "Anna")
    assert (anna["days_off_calendar"], anna["workdays_calendar"], anna["calendar_keyword"]) == ("calendar.anna", "calendar.shifts", "Urlaub")
    assert [c["entity_id"] for c in overview["calendars"]] == ["calendar.anna", "calendar.shifts"]   # not our own calendars

    await call_service("set_days", person=persons["p_anna"], start="2026-10-08", status="workday")    # a manual exception wins
    days = {day["date"]: day["persons"]["p_anna"] for day in (await call_service("get_days", start="2026-10-05", weeks=1))["days"]}
    assert days["2026-10-08"]["reason"] == "exception_workday" and days["2026-10-08"]["calendar"] == "day_off"
    await call_service("set_days", person=persons["p_anna"], start="2026-10-08", status="day_off")    # equals the calendar
    days = {day["date"]: day["persons"]["p_anna"] for day in (await call_service("get_days", start="2026-10-05", weeks=1))["days"]}
    assert days["2026-10-08"]["reason"] == "calendar_day_off" and days["2026-10-08"]["exception"] is None

    # the calendar changes: re-read after the pause
    events["calendar.anna"] = [{"start": "2026-10-14", "end": "2026-10-15", "summary": "Urlaub"}]
    before = len(calls)
    hass.states.async_set("calendar.anna", "on", {"friendly_name": "Anna privat"})
    await hass.async_block_till_done()
    assert len(calls) == before                                                           # debounced: nothing yet
    async_fire_time_changed(hass, dt_util.utcnow() + dt.timedelta(seconds=31))
    await hass.async_block_till_done()
    days = {day["date"]: day["persons"]["p_anna"] for day in (await call_service("get_days", start="2026-10-05", weeks=2))["days"]}
    assert days["2026-10-14"]["reason"] == "calendar_day_off" and days["2026-10-07"]["reason"] == "workday"

    # an unreadable calendar keeps the last days and never makes them unknown
    events["broken"] = True
    async_fire_time_changed(hass, (dt_util.now() + dt.timedelta(days=1)).replace(hour=3, minute=30, second=5))
    await hass.async_block_till_done()
    days = {day["date"]: day["persons"]["p_anna"] for day in (await call_service("get_days", start="2026-10-12", weeks=1))["days"]}
    assert days["2026-10-14"]["reason"] == "calendar_day_off"
    events["broken"] = False

    await call_service("set_calendars", person=persons["p_anna"])                          # removes both
    await hass.async_block_till_done()
    days = {day["date"]: day["persons"]["p_anna"] for day in (await call_service("get_days", start="2026-10-12", weeks=1))["days"]}
    assert days["2026-10-14"]["reason"] == "workday"
    assert household.runtime_data.data.calendar_days == {}


class FakeCalendar:
    """A writable calendar entity as CalDAV, Google or Local Calendar provide it (#3)."""

    def __init__(self) -> None:
        from homeassistant.components.calendar import CalendarEntityFeature, CalendarEvent
        self.supported_features = CalendarEntityFeature.CREATE_EVENT | CalendarEntityFeature.DELETE_EVENT
        self.events = [CalendarEvent(d("2026-10-06"), d("2026-10-07"), "Dentist", description="foreign", uid="foreign-1")]
        self.fail = False
        self._next = 0

    async def async_get_events(self, hass, start, end):
        return [e for e in self.events if e.start < end.date() and e.end > start.date()]

    async def async_create_event(self, **kwargs):
        from homeassistant.components.calendar import CalendarEvent
        if self.fail:
            raise RuntimeError("read-only share")
        self._next += 1
        self.events.append(CalendarEvent(kwargs["dtstart"], kwargs["dtend"], kwargs["summary"],
                                         description=kwargs.get("description"), uid=f"u{self._next}"))

    async def async_delete_event(self, uid, recurrence_id=None, recurrence_range=None):
        self.events = [e for e in self.events if e.uid != uid]

    def own(self):
        return sorted((e.description, e.summary) for e in self.events if (e.description or "").startswith("werktage:"))


async def test_days_off_are_exported_into_a_shared_calendar(hass: HomeAssistant, household, call_service, persons):
    """#3: wanted events are created, stale ones deleted, foreign ones untouched; failures raise a repair issue."""
    from custom_components.werktage.coordinator import WerktagsCoordinator
    fake = FakeCalendar()
    hass.states.async_set("calendar.family", "off", {"friendly_name": "Family"})
    coordinator = household.runtime_data
    with patch.object(WerktagsCoordinator, "_calendar_entity", lambda self, entity_id: fake if entity_id == "calendar.family" else None):
        hass.config_entries.async_update_entry(household, options={**household.options, "export_calendar": "calendar.family",
                                                                   "export_weeks": 2, "export_weekends": False})
        await coordinator.async_export_days_off()
        own = fake.own()
        assert ("werktage:p_anna/2026-10-03", "Anna: Tag der Deutschen Einheit") in own      # Saturday, but a holiday
        assert ("werktage:p_clara/2026-10-05", "Clara: Autumn Holidays") in own
        assert not any(key.endswith("/2026-10-04") for key, _ in own)                       # Sunday: no weekends
        assert all(key >= "werktage:p" and not key.endswith("/2026-10-15") for key, _ in own)   # two weeks: 1–14 Oct
        assert len([e for e in fake.events if e.uid == "foreign-1"]) == 1                    # foreign event untouched
        count = len(own)

        await call_service("set_days", person=persons["p_anna"], start="2026-10-07", status="day_off")   # a change …
        async_fire_time_changed(hass, dt_util.utcnow() + dt.timedelta(seconds=6))                      # … exported after 5 s
        await hass.async_block_till_done()
        assert ("werktage:p_anna/2026-10-07", "Anna: Day off") in fake.own() and len(fake.own()) == count + 1
        await call_service("set_days", person=persons["p_anna"], start="2026-10-07", status="default")
        async_fire_time_changed(hass, dt_util.utcnow() + dt.timedelta(seconds=12))
        await hass.async_block_till_done()
        assert len(fake.own()) == count                                                       # stale event removed

        hass.config_entries.async_update_entry(household, options={**household.options, "export_persons": ["p_clara"],
                                                                   "export_weekends": True})
        await coordinator.async_export_days_off()
        assert all(key.startswith("werktage:p_clara/") for key, _ in fake.own())             # only Clara, with weekends
        assert ("werktage:p_clara/2026-10-04", "Clara: Weekend") in fake.own()

        fake.fail = True
        hass.config_entries.async_update_entry(household, options={**household.options, "export_persons": []})
        await coordinator.async_export_days_off()
        assert ir.async_get(hass).async_get_issue(DOMAIN, "export_failed") is not None
        fake.fail = False
        await coordinator.async_export_days_off()
        assert ir.async_get(hass).async_get_issue(DOMAIN, "export_failed") is None

        hass.config_entries.async_update_entry(household, options={**household.options, "export_calendar": ""})
        await coordinator.async_export_days_off()                                            # off: nothing happens
        assert coordinator.export_calendar is None
