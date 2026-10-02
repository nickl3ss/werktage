"""The shipped blueprints load with Home Assistant's blueprint schema and yield valid automations."""
from __future__ import annotations

from pathlib import Path

import pytest
from homeassistant.components.automation.config import async_validate_config_item
from homeassistant.components.blueprint.models import Blueprint, BlueprintInputs
from homeassistant.components.blueprint.schemas import BLUEPRINT_SCHEMA
from homeassistant.core import HomeAssistant
from homeassistant.util.yaml import load_yaml_dict

BLUEPRINTS = sorted((Path(__file__).parent.parent / "blueprints" / "automation" / "werktage").glob("*.yaml"))
INPUTS = {
    "open_cover_in_the_morning": {"morning_sensor": "sensor.anna_morning", "cover": {"entity_id": "cover.shutter"},
                                  "workday_time": "07:00:00", "day_off_time": "10:00:00"},
    "lights_off_in_the_evening": {"evening_sensor": "sensor.house_evening", "targets": {"entity_id": ["light.hall"]},
                                  "before_workday_time": "22:00:00", "before_day_off_time": "23:00:00"},
}


@pytest.mark.parametrize("path", BLUEPRINTS, ids=lambda p: p.stem)
async def test_blueprint_is_valid_and_produces_a_valid_automation(hass: HomeAssistant, path: Path):
    blueprint = Blueprint(load_yaml_dict(str(path)), path=path.name, expected_domain="automation", schema=BLUEPRINT_SCHEMA)
    assert blueprint.validate() is None
    assert set(blueprint.inputs) == set(INPUTS[path.stem]), "every input must be exercised here"
    inputs = BlueprintInputs(blueprint, {"use_blueprint": {"path": path.name, "input": INPUTS[path.stem]}})
    inputs.validate()
    config = inputs.async_substitute()
    validated = await async_validate_config_item(hass, "test", config)
    assert validated is not None and len(validated["triggers"]) >= 2 and validated["actions"]


def test_blueprints_exist():
    assert [p.stem for p in BLUEPRINTS] == ["lights_off_in_the_evening", "open_cover_in_the_morning"]
