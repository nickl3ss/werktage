"""Base class and devices shared by the sensor and calendar platforms."""
from __future__ import annotations

from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity import Entity

from .const import DOMAIN, HOUSE_ID, NAME
from .coordinator import WerktagsCoordinator


def resident_device(coordinator: WerktagsCoordinator, person_id: str) -> DeviceInfo:
    return DeviceInfo(
        identifiers={(DOMAIN, f"{coordinator.entry.entry_id}_resident_{person_id}")},
        name=coordinator.person_name(person_id),
        manufacturer=NAME, model="Resident", entry_type=DeviceEntryType.SERVICE,
    )


def room_device(coordinator: WerktagsCoordinator, area_id: str) -> DeviceInfo:
    """Named after the area but deliberately *not* placed in it.

    Home Assistant builds entity ids from area, device and entity name by
    default; a device named like its area would yield ``sensor.bedroom_bedroom_morning``.
    Without the area the id is ``sensor.bedroom_morning``.
    """
    return DeviceInfo(
        identifiers={(DOMAIN, f"{coordinator.entry.entry_id}_room_{area_id}")},
        name=coordinator.area_name(area_id),
        manufacturer=NAME, model="Room", entry_type=DeviceEntryType.SERVICE,
    )


def house_device(coordinator: WerktagsCoordinator) -> DeviceInfo:
    return DeviceInfo(
        identifiers={(DOMAIN, f"{coordinator.entry.entry_id}_{HOUSE_ID}")},
        name="House", translation_key="house",
        manufacturer=NAME, model="House", entry_type=DeviceEntryType.SERVICE,
    )


class WerktagsEntity(Entity):
    """Pushes state on every coordinator change; no polling."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, coordinator: WerktagsCoordinator, unique_suffix: str) -> None:
        self.coordinator = coordinator
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{unique_suffix}"
        self._attr_attribution = coordinator.attribution

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self.coordinator.async_add_listener(self._handle_update))

    @callback
    def _handle_update(self) -> None:
        self._attr_attribution = self.coordinator.attribution
        self.async_write_ha_state()
