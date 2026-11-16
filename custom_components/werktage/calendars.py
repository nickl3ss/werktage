"""Calendars of the installation (ARC-12, #16): every read and write of a calendar entity goes through here.

The adapter functions list the calendars a resident may choose, read all-day events
(personal calendars #2, a calendar as school holiday source #1) and execute an export
plan (#3) through the target calendar entity: read our own events with their uids,
delete, create. Two parts of the coordinator build on them: ``PersonalCalendars``
(read the residents' calendars into the store) and ``CalendarExport`` (write the days
off into a shared calendar). The titles of day-off events come from the integration's
translations (#15). What to write is planned in ``export.py`` (pure); the store and the
rebuild stay with the coordinator.
"""
from __future__ import annotations

import datetime as dt
import logging
from collections.abc import Mapping
from dataclasses import replace
from typing import TYPE_CHECKING, Any

from homeassistant.components.calendar import CalendarEntity
from homeassistant.components.calendar.const import DOMAIN as CALENDAR_DOMAIN
from homeassistant.components.calendar.const import CalendarEntityFeature
from homeassistant.core import CALLBACK_TYPE, Event, EventStateChangedData, HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import translation
from homeassistant.helpers.debounce import Debouncer
from homeassistant.helpers.entity_component import EntityComponent
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.util import dt as dt_util

from . import export
from .const import (
    CALENDAR_DEBOUNCE_SECONDS,
    CALENDAR_LOOKAHEAD_DAYS,
    CALENDAR_LOOKBACK_DAYS,
    DOMAIN,
    EXPORT_DEBOUNCE_SECONDS,
    ISSUE_EXPORT_FAILED,
)
from .rules import ONE_DAY, Reason
from .sources import SchoolHolidayPeriod
from .storage import CalendarDaysCache

if TYPE_CHECKING:
    from .coordinator import WerktagsCoordinator

_LOGGER = logging.getLogger(__name__)

type AllDayEvent = tuple[dt.date, dt.date, str]        # first day, last day (inclusive), title

# Titles of days off without a holiday name (#15): the morning sensor's reasons, and its plain
# "day off" for exceptions and calendar days ("Anna: Day off", not "Anna: Exception: day off").
_TITLE_KEYS = {
    Reason.WEEKEND: "sensor.morning.state_attributes.reason.state.weekend",
    Reason.PUBLIC_HOLIDAY: "sensor.morning.state_attributes.reason.state.public_holiday",
    Reason.SCHOOL_HOLIDAY: "sensor.morning.state_attributes.reason.state.school_holiday",
    Reason.EXCEPTION_DAY_OFF: "sensor.morning.state.day_off",
    Reason.CALENDAR_DAY_OFF: "sensor.morning.state.day_off",
}


class ExportUnavailable(Exception):
    """The target calendar is not loaded or cannot create and delete events."""


# -- titles ----------------------------------------------------------------------------
def _titles(translations: Mapping[str, str]) -> dict[Reason, str]:
    prefix = f"component.{DOMAIN}.entity."
    return {reason: text for reason, key in _TITLE_KEYS.items() if (text := translations.get(prefix + key))}


async def async_event_titles(hass: HomeAssistant) -> dict[Reason, str]:
    """Titles in the installation's language (English for keys a language lacks); loads them if needed."""
    return _titles(await translation.async_get_translations(hass, hass.config.language, "entity", {DOMAIN}))


@callback
def cached_event_titles(hass: HomeAssistant) -> dict[Reason, str]:
    """The same from the cache that the entity platforms fill, for a calendar's ``event`` property.

    Right after a change of language the new one may not be loaded yet; English stands in until it is.
    """
    cached = translation.async_get_cached_translations
    return (_titles(cached(hass, hass.config.language, "entity", DOMAIN))
            or _titles(cached(hass, "en", "entity", DOMAIN)))


# -- reading ---------------------------------------------------------------------------
def is_foreign(hass: HomeAssistant, entity_id: str) -> bool:
    """A calendar of another integration; our own calendars would feed back on themselves."""
    entry = er.async_get(hass).async_get(entity_id)
    return entry is None or entry.platform != DOMAIN


def foreign_calendars(hass: HomeAssistant) -> list[dict[str, str]]:
    """Every calendar entity of the installation except our own, sorted by name."""
    states = [state for state in hass.states.async_all(CALENDAR_DOMAIN) if is_foreign(hass, state.entity_id)]
    return [{"entity_id": state.entity_id, "name": state.name}
            for state in sorted(states, key=lambda state: state.name.lower())]


async def async_all_day_events(hass: HomeAssistant, entity_id: str, first: dt.date,
                               last: dt.date) -> list[AllDayEvent]:
    """Every all-day event in ``first``..``last``; timed events ignored, calendar ends exclusive.

    Events we exported ourselves (marker in the description) are skipped: a source
    must not feed back on itself (#3).
    """
    tz = dt_util.get_default_time_zone()
    response: Any = await hass.services.async_call(
        CALENDAR_DOMAIN, "get_events",
        {"entity_id": entity_id, "start_date_time": dt.datetime.combine(first, dt.time(), tz).isoformat(),
         "end_date_time": dt.datetime.combine(last + ONE_DAY, dt.time(), tz).isoformat()},
        blocking=True, return_response=True,
    )
    events = (response or {}).get(entity_id, {}).get("events", []) if isinstance(response, dict) else []
    result = []
    for event in events:
        start, end = str(event.get("start", "")), str(event.get("end", ""))
        if len(start) != 10 or len(end) != 10 or export.key_of(str(event.get("description") or "")):
            continue
        result.append((dt.date.fromisoformat(start), dt.date.fromisoformat(end) - ONE_DAY,
                       str(event.get("summary", ""))))
    return result


async def async_days(hass: HomeAssistant, entity_id: str, first: dt.date, last: dt.date,
                     keyword: str | None = None) -> frozenset[dt.date]:
    """The days in ``first``..``last`` covered by all-day events (whose title contains ``keyword``, if given)."""
    days: set[dt.date] = set()
    for start, end, title in await async_all_day_events(hass, entity_id, first, last):
        if keyword and keyword.lower() not in title.lower():
            continue
        day = max(start, first)
        while day <= min(end, last):
            days.add(day)
            day += ONE_DAY
    return frozenset(days)


async def async_school_holiday_periods(hass: HomeAssistant, entity_id: str, first: dt.date,
                                       last: dt.date) -> list[SchoolHolidayPeriod]:
    """A calendar as school holiday source (#1): one period per all-day event, by start."""
    events = await async_all_day_events(hass, entity_id, first, last)
    return sorted((SchoolHolidayPeriod(start, end, title) for start, end, title in events), key=lambda p: p.start)


# -- writing ---------------------------------------------------------------------------
def calendar_entity(hass: HomeAssistant, entity_id: str) -> CalendarEntity | None:
    """The calendar entity object (events with uids, writing), if its integration is loaded."""
    component: EntityComponent[CalendarEntity] | None = hass.data.get(CALENDAR_DOMAIN)
    return component.get_entity(entity_id) if component else None


def _writable(entity: CalendarEntity | None) -> bool:
    needed = CalendarEntityFeature.CREATE_EVENT | CalendarEntityFeature.DELETE_EVENT
    return entity is not None and (entity.supported_features or 0) & needed == needed


def export_supported(hass: HomeAssistant, entity_id: str) -> bool:
    """Whether the calendar can take our events: its integration must create and delete events."""
    return _writable(calendar_entity(hass, entity_id))


async def async_write_export(hass: HomeAssistant, entity_id: str, wanted: Mapping[str, export.WantedEvent],
                             first: dt.date, last: dt.date) -> None:
    """Bring our events in ``first``..``last`` in line with ``wanted``; everything else stays untouched.

    Raises ``ExportUnavailable`` for a missing or read-only calendar; whatever the
    calendar integration raises passes through.
    """
    entity = calendar_entity(hass, entity_id)
    if entity is None or not _writable(entity):
        raise ExportUnavailable("the calendar is not loaded or cannot create and delete events")
    tz = dt_util.get_default_time_zone()
    events = await entity.async_get_events(hass, dt.datetime.combine(first, dt.time(), tz),
                                           dt.datetime.combine(last + ONE_DAY, dt.time(), tz))
    existing = [export.OwnEvent(event.uid, key, event.summary) for event in events
                if event.uid and (key := export.key_of(event.description))]
    to_create, to_delete = export.plan(wanted, existing)
    for stale in to_delete:
        await entity.async_delete_event(stale.uid)
    for new in to_create:
        await entity.async_create_event(dtstart=new.day, dtend=new.day + ONE_DAY, summary=new.summary,
                                        description=new.description)


# -- the coordinator's parts -------------------------------------------------------------
class PersonalCalendars:
    """Reads the residents' personal calendars (#2): at start, daily and half a minute after one changes."""

    def __init__(self, coordinator: WerktagsCoordinator) -> None:
        self._c = coordinator
        self._down: set[str] = set()                     # residents whose calendars could not be read
        self._unsub: CALLBACK_TYPE | None = None         # state changes of the personal calendars
        self._debouncer = Debouncer(coordinator.hass, _LOGGER, cooldown=CALENDAR_DEBOUNCE_SECONDS, immediate=False,
                                    function=self.async_refresh)

    async def async_refresh(self) -> None:
        """Read every resident's calendars. An unreadable calendar keeps its last days, never turns the days
        unknown: a missing calendar must not make every day a workday."""
        c = self._c
        today = c.today()
        first = today - dt.timedelta(days=CALENDAR_LOOKBACK_DAYS)
        last = today + dt.timedelta(days=CALENDAR_LOOKAHEAD_DAYS)
        caches = dict(c.data.calendar_days)
        for person_id, resident in c.data.residents.items():
            if not resident.has_calendars:
                caches.pop(person_id, None)
                continue
            try:
                days_off = (await async_days(c.hass, resident.days_off_calendar, first, last, resident.calendar_keyword)
                            if resident.days_off_calendar else frozenset())     # the keyword filters days off only
                workdays = (await async_days(c.hass, resident.workdays_calendar, first, last)
                            if resident.workdays_calendar else frozenset())
            except Exception as err:  # noqa: BLE001 — a calendar integration may raise anything
                if person_id not in self._down:
                    _LOGGER.warning("Personal calendars %s could not be read, keeping the last days: %s",
                                    [x for x in (resident.days_off_calendar, resident.workdays_calendar) if x], err)
                    self._down.add(person_id)
                continue
            self._down.discard(person_id)
            old = caches.get(person_id)
            new = CalendarDaysCache(tuple(sorted(days_off)), tuple(sorted(workdays)), first, last, dt_util.utcnow())
            if old is None or (old.days_off, old.workdays, old.known_from, old.known_to) != (new.days_off, new.workdays,
                                                                                            first, last):
                caches[person_id] = new                # unchanged days: no store write, no rebuild, no export
        for person_id in [pid for pid in caches if pid not in c.data.residents]:
            caches.pop(person_id)
        if caches != c.data.calendar_days:
            await c.async_commit(replace(c.data, calendar_days=caches))

    @callback
    def track(self) -> None:
        """Re-read (debounced) whenever one of the personal calendars changes state."""
        self._untrack()
        entity_ids = sorted({entity_id for r in self._c.data.residents.values()
                             for entity_id in (r.days_off_calendar, r.workdays_calendar) if entity_id})
        if entity_ids:
            self._unsub = async_track_state_change_event(self._c.hass, entity_ids, self._changed)

    @callback
    def _changed(self, _event: Event[EventStateChangedData]) -> None:
        self._c.entry.async_create_background_task(self._c.hass, self._debouncer.async_call(), "werktage calendars")

    @callback
    def _untrack(self) -> None:
        if self._unsub is not None:
            self._unsub()
            self._unsub = None

    @callback
    def stop(self) -> None:
        self._untrack()
        self._debouncer.async_cancel()


class CalendarExport:
    """Writes the coming days off into the shared calendar and removes the ones no longer true (#3, P37).

    Only events with our marker in the description are ever created, compared or
    deleted; everything else in the calendar stays untouched. A failure raises a
    repair issue and is logged once until the export works again.
    """

    def __init__(self, coordinator: WerktagsCoordinator) -> None:
        self._c = coordinator
        self._down = False
        self._running = False
        self._debouncer = Debouncer(coordinator.hass, _LOGGER, cooldown=EXPORT_DEBOUNCE_SECONDS, immediate=False,
                                    function=self.async_run)               # after a burst of changes

    @callback
    def schedule(self) -> None:
        self._c.entry.async_create_background_task(self._c.hass, self._debouncer.async_call(), "werktage export")

    async def async_run(self) -> None:
        c = self._c
        entity_id = c.export_calendar
        if not entity_id:
            c.set_issue(ISSUE_EXPORT_FAILED, False)
            return
        if self._running:
            return
        self._running = True
        try:
            today = c.today()
            last = today + dt.timedelta(weeks=c.export_weeks) - ONE_DAY
            residents = [pid for pid in c.data.residents if not c.export_persons or pid in c.export_persons]
            wanted = export.wanted_events(c.household, residents, {pid: c.person_name(pid) for pid in residents},
                                          today, last, c.export_weekends, await async_event_titles(c.hass))
            try:
                await async_write_export(c.hass, entity_id, wanted, today, last)
            except Exception as err:  # noqa: BLE001 — a calendar integration may raise anything
                if not self._down:
                    _LOGGER.warning("Days off could not be exported into %s: %s", entity_id, err)
                    self._down = True
                c.set_issue(ISSUE_EXPORT_FAILED, True, {"calendar": entity_id, "error": str(err)})
                return
            if self._down:
                _LOGGER.info("Export into %s works again", entity_id)
                self._down = False
            c.set_issue(ISSUE_EXPORT_FAILED, False)
        finally:
            self._running = False

    @callback
    def stop(self) -> None:
        self._debouncer.async_cancel()
