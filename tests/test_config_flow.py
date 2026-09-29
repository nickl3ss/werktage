"""Setup dialog and options."""
from __future__ import annotations

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.werktags.const import DOMAIN

from .conftest import CONFIG


async def test_user_flow_three_steps(hass: HomeAssistant):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert result["type"] is FlowResultType.FORM and result["step_id"] == "user"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"country": "DE", "subdivision": "DE-NW", "weekend": ["5", "6"]})
    assert result["step_id"] == "school_holidays"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"school_holiday_source": "calendar"})
    assert result["type"] is FlowResultType.FORM and result["errors"] == {"calendar_entity": "calendar_required"}
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"school_holiday_source": "openholidays"})
    assert result["step_id"] == "house"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"house_roles": ["adult"], "house_morning_rule": "workday_wins",
                            "house_evening_rule": "workday_wins", "admin_only": False})
    assert result["type"] is FlowResultType.CREATE_ENTRY and result["title"] == "Werktags"
    assert result["data"]["subdivision"] == "DE-NW" and result["data"]["house_morning_rule"] == "workday_wins"
    await hass.async_block_till_done()


async def test_second_instance_is_refused(hass: HomeAssistant, config_entry: MockConfigEntry):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert result["type"] is FlowResultType.ABORT and result["reason"] == "single_instance_allowed"


async def test_options_flow_changes_house_rule(hass: HomeAssistant, setup_integration: MockConfigEntry):
    result = await hass.config_entries.options.async_init(setup_integration.entry_id)
    assert result["step_id"] == "init"
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"country": "DE", "subdivision": "DE-NW", "weekend": ["5", "6"]})
    assert result["step_id"] == "school_holidays"
    result = await hass.config_entries.options.async_configure(result["flow_id"], {"school_holiday_source": "none"})
    assert result["step_id"] == "house"
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {**{k: CONFIG[k] for k in ("house_roles", "house_evening_rule", "admin_only")},
                            "house_morning_rule": "workday_wins"})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    coordinator = setup_integration.runtime_data
    assert coordinator.house.morning_rule.value == "workday_wins" and coordinator.source == "none"
    assert coordinator.data.school_holidays is None        # source changed → cache dropped
