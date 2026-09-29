"""Diagnostics: configuration and counts, never names or ids of people."""
from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant

from .coordinator import WerktagsConfigEntry


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: WerktagsConfigEntry) -> dict[str, Any]:
    c = entry.runtime_data
    data = c.data
    return {
        "status": c.status(),
        "house": {"roles": sorted(r.value for r in c.house.roles), "morning_rule": c.house.morning_rule.value,
                  "evening_rule": c.house.evening_rule.value, "admin_only": c.admin_only},
        "counts": {
            "residents": len(data.residents),
            "role_steps": sum(len(r.roles.steps) for r in data.residents.values()),
            "rooms": len(data.rooms),
            "assignment_steps": sum(len(r.residents.steps) for r in data.rooms.values()),
            "exception_days": len(data.exceptions),
            "exceptions": sum(len(v) for v in data.exceptions.values()),
        },
    }
