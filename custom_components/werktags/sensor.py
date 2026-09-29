"""Morning and evening mode sensors for residents, rooms and the house.

New residents and rooms get their sensors as soon as they appear in the
store — no restart needed. Residents without a role today and rooms without
residents today are ``unavailable`` (specification 5.3).
"""
from __future__ import annotations

import datetime as dt
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import HOUSE_ID
from .coordinator import WerktagsConfigEntry, WerktagsCoordinator
from .entity import WerktagsEntity, house_device, resident_device, room_device
from .rules import ONE_DAY, DayInfo, EveningMode, MorningMode, evening_mode, morning_mode

PARALLEL_UPDATES = 0


async def async_setup_entry(hass: HomeAssistant, entry: WerktagsConfigEntry,
                            async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    coordinator = entry.runtime_data
    known: set[str] = set()

    @callback
    def add_new() -> None:
        new: list[SensorEntity] = []
        for person_id in coordinator.data.residents:
            if f"resident_{person_id}" not in known:
                known.add(f"resident_{person_id}")
                new += [ResidentModeSensor(coordinator, person_id, evening=False),
                        ResidentModeSensor(coordinator, person_id, evening=True)]
        for area_id in coordinator.data.rooms:
            if f"room_{area_id}" not in known:
                known.add(f"room_{area_id}")
                new += [RoomModeSensor(coordinator, area_id, evening=False),
                        RoomModeSensor(coordinator, area_id, evening=True)]
        if HOUSE_ID not in known:
            known.add(HOUSE_ID)
            new += [HouseModeSensor(coordinator, evening=False), HouseModeSensor(coordinator, evening=True)]
        if new:
            async_add_entities(new)

    add_new()
    entry.async_on_unload(coordinator.async_add_listener(add_new))


class ModeSensor(WerktagsEntity, SensorEntity):
    """Common shape: enum sensor with the reason as attributes."""

    _attr_device_class = SensorDeviceClass.ENUM

    def __init__(self, coordinator: WerktagsCoordinator, unique_suffix: str, evening: bool) -> None:
        super().__init__(coordinator, f"{unique_suffix}_{'evening' if evening else 'morning'}")
        self.evening = evening
        self._attr_translation_key = "evening" if evening else "morning"
        self._attr_options = [m.value for m in (EveningMode if evening else MorningMode)]

    def _day(self) -> DayInfo | None:
        raise NotImplementedError

    def _target_date(self) -> dt.date:
        return self.coordinator.today() + (ONE_DAY if self.evening else dt.timedelta())

    @property
    def native_value(self) -> str | None:
        info = self._day()
        if info is None:
            return None
        return (evening_mode(info) if self.evening else morning_mode(info)).value

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        info = self._day()
        attributes: dict[str, Any] = {"date": self._target_date().isoformat()}
        if info is not None:
            attributes.update({"day_type": info.day_type.value, "reason": info.reason.value,
                               "holiday_name": info.holiday_name})
            if info.role is not None:
                attributes["role"] = info.role.value
        return attributes


class ResidentModeSensor(ModeSensor):
    def __init__(self, coordinator: WerktagsCoordinator, person_id: str, evening: bool) -> None:
        super().__init__(coordinator, f"resident_{person_id}", evening)
        self.person_id = person_id
        self._attr_device_info = resident_device(coordinator, person_id)

    def _day(self) -> DayInfo | None:
        return self.coordinator.household.day_of(self.person_id, self._target_date())

    @property
    def available(self) -> bool:
        return self.coordinator.household.day_of(self.person_id, self.coordinator.today()) is not None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        attributes = super().extra_state_attributes
        household, today = self.coordinator.household, self.coordinator.today()
        next_workday = household.next_day(self.person_id, today, workday=True)
        next_day_off = household.next_day(self.person_id, today, workday=False)
        attributes["next_workday"] = next_workday.isoformat() if next_workday else None
        attributes["next_day_off"] = next_day_off.isoformat() if next_day_off else None
        return attributes


class RoomModeSensor(ModeSensor):
    def __init__(self, coordinator: WerktagsCoordinator, area_id: str, evening: bool) -> None:
        super().__init__(coordinator, f"room_{area_id}", evening)
        self.area_id = area_id
        self._attr_device_info = room_device(coordinator, area_id)

    def _day(self) -> DayInfo | None:
        return self.coordinator.household.room_day(self.area_id, self._target_date(), evening=self.evening)

    @property
    def available(self) -> bool:
        """At least one assigned resident must have a role today."""
        room = self.coordinator.data.rooms.get(self.area_id)
        if room is None:
            return False
        today, household = self.coordinator.today(), self.coordinator.household
        return any(household.day_of(rid, today) is not None for rid in room.residents_on(today))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        attributes = super().extra_state_attributes
        room = self.coordinator.data.rooms.get(self.area_id)
        if room is not None:
            residents = sorted(room.residents_on(self._target_date()))
            attributes["residents"] = [self.coordinator.person_name(rid) for rid in residents]
            attributes["rule"] = (room.evening_rule if self.evening else room.morning_rule).value
        return attributes


class HouseModeSensor(ModeSensor):
    def __init__(self, coordinator: WerktagsCoordinator, evening: bool) -> None:
        super().__init__(coordinator, HOUSE_ID, evening)
        self._attr_device_info = house_device(coordinator)

    def _day(self) -> DayInfo | None:
        return self.coordinator.household.house_day(self._target_date(), evening=self.evening)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        attributes = super().extra_state_attributes
        house = self.coordinator.household
        residents = house.house_residents_on(self._target_date())
        attributes["residents"] = [self.coordinator.person_name(rid) for rid in residents]
        attributes["rule"] = (house.house.evening_rule if self.evening else house.house.morning_rule).value
        return attributes
