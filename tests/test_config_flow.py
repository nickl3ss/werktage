"""Setup dialog (five steps) and options."""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.werktags.const import DOMAIN
from custom_components.werktags.openholidays import RequestFailed

from .conftest import CONFIG

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


async def test_options_flow_reloads_with_new_settings(hass: HomeAssistant, setup_integration: MockConfigEntry):
    result = await hass.config_entries.options.async_init(setup_integration.entry_id)
    assert result["step_id"] == "init"
    result = await hass.config_entries.options.async_configure(result["flow_id"], {"country": "DE"})
    assert result["step_id"] == "region"
    result = await hass.config_entries.options.async_configure(result["flow_id"], {"subdivision": "DE-NW", "weekend": ["5", "6"]})
    assert result["step_id"] == "school_holidays"
    result = await hass.config_entries.options.async_configure(result["flow_id"], {"school_holiday_source": "none"})
    assert result["step_id"] == "house"
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {**{k: CONFIG[k] for k in ("house_roles", "house_evening_rule")}, "house_morning_rule": "workday_wins"})
    assert result["step_id"] == "access"
    result = await hass.config_entries.options.async_configure(result["flow_id"], {"admin_only": False})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    coordinator = setup_integration.runtime_data                 # the entry reloaded → new coordinator
    assert coordinator.house.morning_rule.value == "workday_wins" and coordinator.source == "none"
    assert coordinator.status()["school_holidays"] is None      # the old cache belongs to the old source


async def test_options_flow_drops_the_region_when_the_country_changes(hass: HomeAssistant, setup_integration: MockConfigEntry):
    result = await hass.config_entries.options.async_init(setup_integration.entry_id)
    result = await hass.config_entries.options.async_configure(result["flow_id"], {"country": "AT"})
    assert result["step_id"] == "region"
    import voluptuous as vol
    key = next(k for k in result["data_schema"].schema if str(k) == "subdivision")
    assert key.default is vol.UNDEFINED                            # no region preselected for the new country
