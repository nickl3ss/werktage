"""Werktags — workdays per person for Home Assistant.

Weekends, public and school holidays by default, exceptions per person and
day, and a morning/evening mode for every person, room and the whole house.
"""
from __future__ import annotations

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.device_registry import DeviceEntry
from homeassistant.helpers.storage import Store
from homeassistant.helpers.typing import ConfigType

from . import frontend, storage
from .const import DOMAIN
from .coordinator import WerktagsConfigEntry, WerktagsCoordinator
from .services import async_setup_services

PLATFORMS = [Platform.SENSOR, Platform.BINARY_SENSOR, Platform.CALENDAR]
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)     # nothing in configuration.yaml

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
    await frontend.async_register(hass)      # HACS version only; the core version drops frontend.py
    return True


async def async_unload_entry(hass: HomeAssistant, entry: WerktagsConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await entry.runtime_data.async_unload()
    return unloaded


async def async_remove_entry(hass: HomeAssistant, entry: WerktagsConfigEntry) -> None:
    """The integration was removed: delete the stored residents, rooms and exceptions."""
    store: Store[dict[str, object]] = Store(hass, storage.DATA_VERSION, f"{DOMAIN}.data")
    await store.async_remove()


async def async_remove_config_entry_device(hass: HomeAssistant, entry: WerktagsConfigEntry,
                                           device: DeviceEntry) -> bool:
    """Devices of residents and rooms that no longer exist may be deleted in the UI."""
    return any(domain == DOMAIN and entry.runtime_data.is_stale_device_id(identifier)
               for domain, identifier in device.identifiers)
