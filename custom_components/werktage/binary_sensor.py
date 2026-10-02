"""``binary_sensor.<x>_workday`` — on when today is a workday for a resident, room or the house.

The enum sensors carry the full picture; these binary sensors exist for
blueprints and conditions that expect an on/off entity.
"""
from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import HOUSE_ID
from .coordinator import WerktagsConfigEntry, WerktagsCoordinator
from .entity import WerktagsEntity, house_device, resident_device, room_device
from .rules import DayInfo

PARALLEL_UPDATES = 0


async def async_setup_entry(hass: HomeAssistant, entry: WerktagsConfigEntry,
                            async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    coordinator = entry.runtime_data
    known: set[str] = set()

    @callback
    def add_new() -> None:
        new: list[BinarySensorEntity] = []
        for person_id in coordinator.data.residents:
            if f"resident_{person_id}" not in known:
                known.add(f"resident_{person_id}")
                new.append(ResidentWorkdaySensor(coordinator, person_id))
        for area_id in coordinator.data.rooms:
            if f"room_{area_id}" not in known:
                known.add(f"room_{area_id}")
                new.append(RoomWorkdaySensor(coordinator, area_id))
        if HOUSE_ID not in known:
            known.add(HOUSE_ID)
            new.append(HouseWorkdaySensor(coordinator))
        if new:
            async_add_entities(new)

    add_new()
    entry.async_on_unload(coordinator.async_add_listener(add_new))


class WorkdaySensor(WerktagsEntity, BinarySensorEntity):
    _attr_translation_key = "workday"

    def _day(self) -> DayInfo | None:
        raise NotImplementedError

    @property
    def is_on(self) -> bool | None:
        info = self._day()
        return None if info is None else info.is_workday

    @property
    def extra_state_attributes(self) -> dict[str, str | None]:
        info = self._day()
        return {"reason": info.reason.value if info else None, "holiday_name": info.holiday_name if info else None}


class ResidentWorkdaySensor(WorkdaySensor):
    def __init__(self, coordinator: WerktagsCoordinator, person_id: str) -> None:
        super().__init__(coordinator, f"resident_{person_id}_workday")
        self.person_id = person_id
        self._attr_device_info = resident_device(coordinator, person_id)

    def _day(self) -> DayInfo | None:
        return self.coordinator.household.day_of(self.person_id, self.coordinator.today())

    @property
    def available(self) -> bool:
        return self._day() is not None


class RoomWorkdaySensor(WorkdaySensor):
    def __init__(self, coordinator: WerktagsCoordinator, area_id: str) -> None:
        super().__init__(coordinator, f"room_{area_id}_workday")
        self.area_id = area_id
        self._attr_device_info = room_device(coordinator, area_id)

    def _day(self) -> DayInfo | None:
        return self.coordinator.household.room_day(self.area_id, self.coordinator.today())

    @property
    def available(self) -> bool:
        room = self.coordinator.data.rooms.get(self.area_id)
        if room is None:
            return False
        today, household = self.coordinator.today(), self.coordinator.household
        return any(household.day_of(rid, today) is not None for rid in room.residents_on(today))


class HouseWorkdaySensor(WorkdaySensor):
    def __init__(self, coordinator: WerktagsCoordinator) -> None:
        super().__init__(coordinator, f"{HOUSE_ID}_workday")
        self._attr_device_info = house_device(coordinator)

    def _day(self) -> DayInfo | None:
        return self.coordinator.household.house_day(self.coordinator.today())
