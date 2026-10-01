"""Setup dialog (five steps) and options."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.werktags.const import DOMAIN
from custom_components.werktags.openholidays import RequestFailed

from .conftest import CONFIG, d

HOUSE = {"house_roles": ["adult"], "house_morning_rule": "workday_wins", "house_evening_rule": "workday_wins"}


async def _to_school_holidays(hass: HomeAssistant, country: str = "DE", subdivision: str = "DE-NW"):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert result["type"] is FlowResultType.FORM and result["step_id"] == "user"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"country": country})
    assert result["step_id"] == "region"
    region = {"weekend": ["5", "6"]}
    if subdivision:
        region["subdivision"] = subdivision
    result = await hass.config_entries.flow.async_configure(result["flow_id"], region)
    return result


async def test_user_flow_five_steps(hass: HomeAssistant, fake_api):
    result = await _to_school_holidays(hass)
    assert result["step_id"] == "school_holidays"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"school_holiday_source": "openholidays"})
    fake_api.school_holidays.assert_awaited_once()          # test-before-configure
    assert result["step_id"] == "house"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], HOUSE)
    assert result["step_id"] == "access"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"admin_only": True})
    assert result["type"] is FlowResultType.CREATE_ENTRY and result["title"] == "Werktags"
    data = result["data"]
    assert data["subdivision"] == "DE-NW" and data["house_morning_rule"] == "workday_wins" and data["admin_only"] is True
    assert data["calendar_entity"] is None
    await hass.async_block_till_done()


async def test_region_form_lists_subdivision_names(hass: HomeAssistant):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"country": "DE"})
    schema = result["data_schema"].schema
    field = next(k for k in schema if k == "subdivision")
    options = schema[field].config["options"]
    assert {"value": "DE-NW", "label": "Nordrhein-Westfalen"} in options
    assert all(o["label"] != o["value"] for o in options)   # names, not codes


async def test_country_without_subdivisions_skips_the_field(hass: HomeAssistant):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"country": "LU"})
    assert result["step_id"] == "region"
    assert "subdivision" not in {str(k) for k in result["data_schema"].schema}


async def test_wrong_subdivision_is_rejected(hass: HomeAssistant):
    """The selector only offers the country's regions; anything else fails schema validation."""
    from homeassistant.data_entry_flow import InvalidData
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"country": "DE"})
    with pytest.raises(InvalidData):
        await hass.config_entries.flow.async_configure(result["flow_id"], {"subdivision": "FR-75", "weekend": ["5", "6"]})


async def test_calendar_source_needs_an_existing_calendar(hass: HomeAssistant):
    result = await _to_school_holidays(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"school_holiday_source": "calendar"})
    assert result["errors"] == {"calendar_entity": "calendar_required"}
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"school_holiday_source": "calendar", "calendar_entity": "calendar.nope"})
    assert result["errors"] == {"calendar_entity": "calendar_missing"}
    hass.states.async_set("calendar.school", "off")
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"school_holiday_source": "calendar", "calendar_entity": "calendar.school"})
    assert result["step_id"] == "house"


@pytest.mark.parametrize("problem, error", [(RequestFailed("down"), "cannot_connect"), ([], "not_covered")])
async def test_openholidays_is_tested_before_configure(hass: HomeAssistant, fake_api, problem, error):
    if isinstance(problem, Exception):
        fake_api.school_holidays = AsyncMock(side_effect=problem)
    else:
        fake_api.school_holidays = AsyncMock(return_value=problem)
    result = await _to_school_holidays(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"school_holiday_source": "openholidays"})
    assert result["type"] is FlowResultType.FORM and result["errors"] == {"base": error}


async def test_second_instance_is_refused(hass: HomeAssistant, config_entry: MockConfigEntry):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert result["type"] is FlowResultType.ABORT and result["reason"] == "single_instance_allowed"


async def _options(hass: HomeAssistant, entry: MockConfigEntry, menu: str):
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.MENU and result["step_id"] == "init"
    return await hass.config_entries.options.async_configure(result["flow_id"], {"next_step_id": menu})


async def test_options_flow_reloads_with_new_settings(hass: HomeAssistant, setup_integration: MockConfigEntry):
    result = await _options(hass, setup_integration, "settings")
    assert result["step_id"] == "settings"
    result = await hass.config_entries.options.async_configure(result["flow_id"], {"country": "DE"})
    assert result["step_id"] == "region"
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"subdivision": "DE-NW", "weekend": ["5", "6"], "add_holidays": ["2026-10-02 Bridge day"],
                            "remove_holidays": ["2026-10-03"]})
    assert result["step_id"] == "school_holidays"
    result = await hass.config_entries.options.async_configure(result["flow_id"], {"school_holiday_source": "none"})
    assert result["step_id"] == "house_rules"
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {**{k: CONFIG[k] for k in ("house_roles", "house_evening_rule")}, "house_morning_rule": "workday_wins"})
    assert result["step_id"] == "access"
    result = await hass.config_entries.options.async_configure(result["flow_id"], {"admin_only": False})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    coordinator = setup_integration.runtime_data                 # the entry reloaded → new coordinator
    assert coordinator.house.morning_rule.value == "workday_wins" and coordinator.source == "none"
    assert coordinator.status()["school_holidays"] is None      # the old cache belongs to the old source
    calendar = coordinator.household.calendar
    assert calendar.public_holiday_on(d("2026-10-02")) == "Bridge day"       # added
    assert calendar.public_holiday_on(d("2026-10-03")) is None               # removed (German Unity Day)


async def test_region_step_rejects_malformed_extra_holidays(hass: HomeAssistant):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"country": "DE"})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"weekend": ["5", "6"], "add_holidays": ["24.12.2026 Christmas Eve"]})
    assert result["step_id"] == "region" and result["errors"] == {"add_holidays": "holiday_format"}


async def test_options_menu_adds_a_resident_a_room_and_the_house(hass: HomeAssistant, setup_integration: MockConfigEntry,
                                                                  persons, areas):
    result = await _options(hass, setup_integration, "resident")
    assert result["type"] is FlowResultType.FORM and result["step_id"] == "resident"
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"person": persons["p_anna"], "role": "adult", "short_name": "A", "off_weekdays": ["4", "5", "6"],
                            "valid_from": "2026-09-01"})
    assert result["type"] is FlowResultType.ABORT and result["reason"] == "resident_saved"
    await hass.async_block_till_done()
    coordinator = setup_integration.runtime_data
    anna = coordinator.data.residents["p_anna"]
    assert anna.short_name == "A" and anna.weekend_on(d("2026-10-01")) == frozenset({4, 5, 6})
    assert hass.states.get("binary_sensor.anna_workday").state == "on"      # Thursday
    assert hass.states.get("sensor.anna_evening").state == "before_day_off"  # Friday is her day off now

    # a second person with the same short name → error, form again
    result = await _options(hass, setup_integration, "resident")
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"person": persons["p_ben"], "role": "adult", "short_name": "a"})
    assert result["type"] is FlowResultType.FORM and result["errors"] == {"short_name": "short_name_taken"}

    # rooms need residents
    result = await _options(hass, setup_integration, "room")
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"area": areas["Bedroom"], "person": [persons["p_clara"]],
                            "morning_rule": "day_off_wins", "evening_rule": "workday_wins"})
    assert result["type"] is FlowResultType.FORM and result["errors"] == {"person": "not_resident"}
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"area": areas["Bedroom"], "person": [persons["p_anna"]],
                            "morning_rule": "day_off_wins", "evening_rule": "workday_wins"})
    assert result["type"] is FlowResultType.ABORT and result["reason"] == "room_saved"
    await hass.async_block_till_done()
    assert coordinator.data.rooms[areas["Bedroom"]].residents_on(d("2026-10-01")) == frozenset({"p_anna"})
    assert hass.states.get("binary_sensor.bedroom_workday").state == "on"

    result = await _options(hass, setup_integration, "house")
    result = await hass.config_entries.options.async_configure(result["flow_id"], {"person": [persons["p_anna"]]})
    assert result["type"] is FlowResultType.ABORT and result["reason"] == "house_saved"
    await hass.async_block_till_done()
    assert coordinator.household.house_residents_on(d("2026-10-01")) == ["p_anna"]


async def test_options_menu_rejects_bad_input_and_resets_the_weekly_pattern(hass: HomeAssistant,
                                                                            setup_integration: MockConfigEntry, persons,
                                                                            areas):
    result = await _options(hass, setup_integration, "resident")
    await hass.config_entries.options.async_configure(
        result["flow_id"], {"person": persons["p_anna"], "role": "adult", "off_weekdays": ["0"]})
    coordinator = setup_integration.runtime_data
    assert coordinator.data.residents["p_anna"].weekend_on(d("2026-10-01")) == frozenset({0})
    result = await _options(hass, setup_integration, "resident")                 # saved again without weekdays
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"person": persons["p_anna"], "role": "adult"})
    assert result["reason"] == "resident_saved"
    assert coordinator.data.residents["p_anna"].weekend_on(d("2026-10-01")) is None   # household weekend again

    result = await _options(hass, setup_integration, "room")
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"area": "nowhere", "person": [persons["p_anna"]],
                            "morning_rule": "day_off_wins", "evening_rule": "workday_wins"})
    assert result["type"] is FlowResultType.FORM and result["errors"] == {"area": "unknown_area"}
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"area": areas["Kitchen"], "morning_rule": "day_off_wins", "evening_rule": "workday_wins"})
    assert result["errors"] == {"person": "room_without_residents"}                 # no residents: no room

    result = await _options(hass, setup_integration, "house")
    result = await hass.config_entries.options.async_configure(result["flow_id"], {"person": [persons["p_clara"]]})
    assert result["type"] is FlowResultType.FORM and result["errors"] == {"person": "not_resident"}


async def test_options_flow_drops_the_region_when_the_country_changes(hass: HomeAssistant, setup_integration: MockConfigEntry):
    result = await _options(hass, setup_integration, "settings")
    result = await hass.config_entries.options.async_configure(result["flow_id"], {"country": "AT"})
    assert result["step_id"] == "region"
    import voluptuous as vol
    key = next(k for k in result["data_schema"].schema if str(k) == "subdivision")
    assert key.default is vol.UNDEFINED                            # no region preselected for the new country


async def test_the_holidays_library_never_runs_in_the_event_loop(hass: HomeAssistant):
    """It is synchronous and walks its country modules; the dialog builds its lists in the executor."""
    import threading

    from custom_components.werktags import sources
    loop_thread, seen = threading.get_ident(), []
    real_countries, real_names = sources.supported_countries, sources.subdivision_names

    def countries():
        seen.append(threading.get_ident())
        return real_countries()

    def names(country):
        seen.append(threading.get_ident())
        return real_names(country)

    with patch.object(sources, "supported_countries", countries), patch.object(sources, "subdivision_names", names):
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {"country": "DE"})
    assert result["step_id"] == "region" and len(seen) >= 2 and loop_thread not in seen

