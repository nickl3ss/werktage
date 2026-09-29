"""Werktags — workdays per person for Home Assistant.

Weekends, public and school holidays by default, exceptions per person and
day, and a morning/evening mode for every person, room and the whole house.
"""
from __future__ import annotations

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType

from . import frontend
from .const import DOMAIN
from .coordinator import WerktagsConfigEntry, WerktagsCoordinator
from .services import async_setup_services

PLATFORMS = [Platform.SENSOR, Platform.CALENDAR]

__all__ = ["DOMAIN"]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the services once; they work as soon as the entry is loaded."""
    async_setup_services(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: WerktagsConfigEntry) -> bool:
    coordinator = WerktagsCoordinator(hass, entry)
    await coordinator.async_load()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    await frontend.async_register(hass)      # HACS version only; the core version drops frontend.py
    return True


async def async_unload_entry(hass: HomeAssistant, entry: WerktagsConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await entry.runtime_data.async_unload()
    return unloaded


async def _async_options_updated(hass: HomeAssistant, entry: WerktagsConfigEntry) -> None:
    await entry.runtime_data.async_options_updated()
