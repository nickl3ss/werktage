"""Read-only calendars: the days off of every resident, and the school holidays of the house."""
from __future__ import annotations

import datetime as dt

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import SOURCE_NONE
from .coordinator import WerktagsConfigEntry, WerktagsCoordinator
from .entity import WerktagsEntity, house_device, resident_device
from .export import reason_label
from .rules import ONE_DAY, DayInfo, Reason, Role

PARALLEL_UPDATES = 0
LOOKAHEAD_DAYS = 400


async def async_setup_entry(hass: HomeAssistant, entry: WerktagsConfigEntry,
                            async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    coordinator = entry.runtime_data
    known: set[str] = set()

    @callback
    def add_new() -> None:
        new = [DaysOffCalendar(coordinator, pid) for pid in coordinator.data.residents if pid not in known]
        known.update(e.person_id for e in new)
        if new:
            async_add_entities(new)

    if coordinator.source != SOURCE_NONE:          # a changed source reloads the entry, so this is decided once
        async_add_entities([SchoolHolidaysCalendar(coordinator)])
    add_new()
    entry.async_on_unload(coordinator.async_add_listener(add_new))


class DaysOffCalendar(WerktagsEntity, CalendarEntity):
    _attr_translation_key = "days_off"

    def __init__(self, coordinator: WerktagsCoordinator, person_id: str) -> None:
        super().__init__(coordinator, f"resident_{person_id}_days_off")
        self.person_id = person_id
        self._attr_device_info = resident_device(coordinator, person_id)

    @property
    def available(self) -> bool:
        return self.coordinator.household.day_of(self.person_id, self.coordinator.today()) is not None

    def _events(self, start: dt.date, end: dt.date) -> list[CalendarEvent]:
        """Consecutive days off with the same reason become one all-day event."""
        events: list[CalendarEvent] = []
        current: tuple[dt.date, dt.date, str] | None = None
        day = start
        while day <= end:
            info = self.coordinator.household.day_of(self.person_id, day)
            if info is not None and not info.is_workday:
                summary = self._summary(info, day)
                if current and current[1] == day - ONE_DAY and current[2] == summary:
                    current = (current[0], day, summary)
                else:
                    if current:
                        events.append(_event(*current))
                    current = (day, day, summary)
            day += ONE_DAY
        if current:
            events.append(_event(*current))
        return events

    def _summary(self, info: DayInfo, day: dt.date) -> str:
        """Public holidays by name; a pupil's school holidays as one block, weekends inside included."""
        if info.reason is Reason.PUBLIC_HOLIDAY and info.holiday_name:
            return info.holiday_name
        if info.role is Role.PUPIL and (name := self.coordinator.household.calendar.school_holidays.name_on(day)):
            return name
        return info.holiday_name or reason_label(info.reason, self.coordinator.hass.config.language)

    @property
    def event(self) -> CalendarEvent | None:
        today = self.coordinator.today()
        events = self._events(today, today + dt.timedelta(days=LOOKAHEAD_DAYS))
        return events[0] if events else None

    async def async_get_events(self, hass: HomeAssistant, start_date: dt.datetime,
                               end_date: dt.datetime) -> list[CalendarEvent]:
        return self._events(start_date.date(), end_date.date())


class SchoolHolidaysCalendar(WerktagsEntity, CalendarEntity):
    """The school holidays of the configured source, one all-day event per period, with its name (#14)."""

    _attr_translation_key = "school_holidays"

    def __init__(self, coordinator: WerktagsCoordinator) -> None:
        super().__init__(coordinator, "house_school_holidays")
        self._attr_device_info = house_device(coordinator)

    def _events(self, start: dt.date, end: dt.date) -> list[CalendarEvent]:
        periods = self.coordinator.household.calendar.school_holidays.periods
        return [_event(first, last, name) for first, last, name in sorted(periods) if last >= start and first <= end]

    @property
    def event(self) -> CalendarEvent | None:
        today = self.coordinator.today()
        events = self._events(today, today + dt.timedelta(days=LOOKAHEAD_DAYS))
        return events[0] if events else None

    async def async_get_events(self, hass: HomeAssistant, start_date: dt.datetime,
                               end_date: dt.datetime) -> list[CalendarEvent]:
        return self._events(start_date.date(), end_date.date())


def _event(start: dt.date, end: dt.date, summary: str) -> CalendarEvent:
    return CalendarEvent(start=start, end=end + ONE_DAY, summary=summary)   # calendar ends are exclusive
