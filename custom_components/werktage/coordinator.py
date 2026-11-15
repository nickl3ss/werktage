"""The coordinator: holds the stored data, rebuilds the household, takes every change.

Every change goes through here: services and the options flow call the ``async_*``
methods, which update the store, rebuild the rules' ``Household`` and notify the
entities. Three parts do the work that reaches outside the store (#16): the school
holiday fetch (``school_holidays.py``), the personal calendars and the export
(``calendars.py``, the adapter to the calendar entities). They read the data from
here and commit through :meth:`WerktagsCoordinator.async_commit`. Dates are calendar
days in the Home Assistant time zone (specification P6).
"""
from __future__ import annotations

import datetime as dt
import logging
from collections.abc import Callable, Iterable
from dataclasses import replace
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryError
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.event import async_track_time_change
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from . import calendars, export, sources, storage
from .calendars import CalendarExport, PersonalCalendars
from .const import (
    CONF_ADD_HOLIDAYS,
    CONF_ADMIN_ONLY,
    CONF_CALENDAR_ENTITY,
    CONF_COUNTRY,
    CONF_EXPORT_CALENDAR,
    CONF_EXPORT_PERSONS,
    CONF_EXPORT_WEEKENDS,
    CONF_EXPORT_WEEKS,
    CONF_HOUSE_EVENING_RULE,
    CONF_HOUSE_MORNING_RULE,
    CONF_HOUSE_ROLES,
    CONF_REMOVE_HOLIDAYS,
    CONF_SCHOOL_HOLIDAY_SOURCE,
    CONF_SUBDIVISION,
    CONF_WEEKEND,
    DEFAULT_EXPORT_WEEKS,
    DEFAULT_WEEKEND_DAYS,
    DOMAIN,
    ISSUE_AREA_MISSING,
    ISSUE_PERSON_MISSING,
    SOURCE_CALENDAR,
    SOURCE_NONE,
    SOURCE_OPENHOLIDAYS,
)
from .rules import (
    DEFAULT_EVENING_RULE,
    DEFAULT_HOUSE_ROLES,
    DEFAULT_MORNING_RULE,
    Calendar,
    CalendarDays,
    CombineRule,
    DayType,
    History,
    House,
    Household,
    Reason,
    Resident,
    Role,
    Room,
)
from .school_holidays import SchoolHolidayFetcher, attribution_for
from .storage import StoredData

_LOGGER = logging.getLogger(__name__)
type WerktagsConfigEntry = ConfigEntry[WerktagsCoordinator]


class _DataStore(Store[dict[str, Any]]):
    """The store file carries ``DATA_VERSION``; older files are upgraded by ``storage.migrate``."""

    async def _async_migrate_func(self, old_major_version: int, old_minor_version: int,
                                  old_data: dict[str, Any]) -> dict[str, Any]:
        return storage.migrate(old_data)


UNCHANGED = "\0unchanged"       # "leave this field as it is" for optional service fields


class WerktagsError(ValueError):
    """A rejected change. ``key`` names the translated message (``exceptions`` in strings.json)."""

    def __init__(self, key: str, **placeholders: str) -> None:
        super().__init__(key)
        self.key = key
        self.placeholders = placeholders


def _with_default_step[T](history: History[T | None], valid_from: dt.date, value: T | None) -> History[T | None]:
    """Add a step; a history that only ever says "default" (``None``) collapses to no history at all."""
    history = history.with_step(valid_from, value)
    return History() if all(step.value is None for step in history.steps) else history


class WerktagsCoordinator:
    """One instance per config entry (and there is only one entry)."""

    def __init__(self, hass: HomeAssistant, entry: WerktagsConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self._store: Store[dict[str, Any]] = _DataStore(hass, storage.DATA_VERSION, f"{DOMAIN}.data")
        self.data = StoredData()
        self.household = Household(calendar=Calendar())
        self._public_holidays: dict[dt.date, str] = {}
        self._public_holidays_span: tuple[dt.date, dt.date] | None = None
        self._titles: dict[Reason, str] = {}                  # translated day-off titles, loaded with the data (#15)
        self._listeners: list[Callable[[], None]] = []
        self._unsub: list[CALLBACK_TYPE] = []
        self._unsub_started: CALLBACK_TYPE | None = None     # the one-time start listener, until it fired
        self.fetcher = SchoolHolidayFetcher(self)              # school holidays per source (#1)
        self.personal_calendars = PersonalCalendars(self)      # days off and workdays from calendars (#2)
        self.exporter = CalendarExport(self)                   # days off into a shared calendar (#3)

    # -- configuration (options win over data) ---------------------------------
    def _conf(self, key: str, default: Any = None) -> Any:
        return self.entry.options.get(key, self.entry.data.get(key, default))

    @property
    def country(self) -> str:
        return str(self._conf(CONF_COUNTRY, self.hass.config.country or "DE"))

    @property
    def subdivision(self) -> str | None:
        return self._conf(CONF_SUBDIVISION) or None

    @property
    def weekend(self) -> frozenset[int]:
        return frozenset(int(d) for d in self._conf(CONF_WEEKEND, DEFAULT_WEEKEND_DAYS))

    @property
    def source(self) -> str:
        return str(self._conf(CONF_SCHOOL_HOLIDAY_SOURCE, SOURCE_NONE))

    @property
    def calendar_entity(self) -> str | None:
        return self._conf(CONF_CALENDAR_ENTITY) or None

    @property
    def admin_only(self) -> bool:
        return bool(self._conf(CONF_ADMIN_ONLY, False))

    @property
    def export_calendar(self) -> str | None:
        return self._conf(CONF_EXPORT_CALENDAR) or None

    @property
    def export_weeks(self) -> int:
        return int(self._conf(CONF_EXPORT_WEEKS, DEFAULT_EXPORT_WEEKS))

    @property
    def export_persons(self) -> frozenset[str]:
        """Residents to export; empty means everyone."""
        return frozenset(str(pid) for pid in self._conf(CONF_EXPORT_PERSONS, []) or [])

    @property
    def export_weekends(self) -> bool:
        return bool(self._conf(CONF_EXPORT_WEEKENDS, False))

    @property
    def house(self) -> House:
        return House(
            roles=frozenset(Role(r) for r in self._conf(CONF_HOUSE_ROLES, [r.value for r in DEFAULT_HOUSE_ROLES])),
            morning_rule=CombineRule(self._conf(CONF_HOUSE_MORNING_RULE, DEFAULT_MORNING_RULE.value)),
            evening_rule=CombineRule(self._conf(CONF_HOUSE_EVENING_RULE, DEFAULT_EVENING_RULE.value)),
            residents=self.data.house_residents,
        )

    def holiday_corrections(self) -> tuple[dict[dt.date, str], frozenset[dt.date]]:
        """Options → (added holidays by date, removed dates). Removal by date or by part of the name."""
        added: dict[dt.date, str] = {}
        for item in self._conf(CONF_ADD_HOLIDAYS, []) or []:
            day, _, name = str(item).strip().partition(" ")
            try:
                added[dt.date.fromisoformat(day)] = name.strip() or export.title(Reason.PUBLIC_HOLIDAY, self._titles)
            except ValueError:
                _LOGGER.warning("Ignoring added holiday %r: expected YYYY-MM-DD [name]", item)
        removed: set[dt.date] = set()
        for item in self._conf(CONF_REMOVE_HOLIDAYS, []) or []:
            text = str(item).strip()
            try:
                removed.add(dt.date.fromisoformat(text))
            except ValueError:
                removed.update(day for day, name in self._public_holidays.items() if text.lower() in name.lower())
        return added, frozenset(removed)

    @property
    def attribution(self) -> str | None:
        return attribution_for(self.source_key)

    # -- school holiday sources: the installation's and the residents' (#1) -----------
    @property
    def source_key(self) -> str:
        """The installation's source as a key: ``openholidays:DE-NW`` · ``calendar:calendar.x`` · ``none``."""
        parameter = (self.subdivision or self.country) if self.source == SOURCE_OPENHOLIDAYS else self.calendar_entity
        return sources.make_source_key(self.source, parameter)

    def source_keys(self) -> list[str]:
        """Every distinct source in use: the installation's and the residents' overrides; ``none`` excluded."""
        keys = {self.source_key} | {r.school_holiday_source for r in self.data.residents.values()
                                    if r.school_holiday_source}
        return sorted(key for key in keys if key != SOURCE_NONE)

    async def _check_source_key(self, key: str) -> None:
        """Only a region of a supported country or a foreign calendar entity may be a source."""
        source, parameter = sources.parse_source_key(key)
        if source == SOURCE_OPENHOLIDAYS and parameter:
            # the holidays library walks its country modules on first use: never in the event loop (invariant 10)
            if await self.hass.async_add_executor_job(sources.is_region_code, parameter):
                return
        elif (source == SOURCE_CALENDAR and parameter and self.hass.states.get(parameter) is not None
              and calendars.is_foreign(self.hass, parameter)):           # our own calendars would feed back
            return
        raise WerktagsError("source_unknown", source=key)

    def today(self) -> dt.date:
        return dt_util.now().date()

    # -- lifecycle -------------------------------------------------------------------
    async def async_load(self) -> None:
        try:
            self.data = storage.from_dict(await self._store.async_load())
        except (ValueError, KeyError, TypeError) as err:   # damaged by hand or by a newer version
            raise ConfigEntryError(translation_domain=DOMAIN, translation_key="store_unreadable",
                                   translation_placeholders={"error": str(err)}) from err
        rooms = {area_id: room for area_id, room in self.data.rooms.items() if room.ever_assigned}
        if len(rooms) != len(self.data.rooms):   # written by versions that let a rule alone create a room
            self.data = replace(self.data, rooms=rooms)
            await self._store.async_save(storage.to_dict(self.data))
        if (old := self.data.school_holidays.get(storage.INSTALLATION_KEY)) is not None:   # written before 0.3.0
            caches = {key: cache for key, cache in self.data.school_holidays.items() if key != storage.INSTALLATION_KEY}
            if old.source == self.source and self.source_key != SOURCE_NONE:
                caches[self.source_key] = replace(old, source=self.source_key)
            self.data = replace(self.data, school_holidays=caches)
            await self._store.async_save(storage.to_dict(self.data))
        self._titles = await calendars.async_event_titles(self.hass)
        await self._async_public_holidays()
        self._rebuild()
        self.fetcher.check_completeness()          # a fresh cache skips the fetch, the hint must not wait for it
        self.personal_calendars.track()
        self._unsub.append(async_track_time_change(self.hass, self._at_midnight, hour=0, minute=0, second=10))
        self._unsub.append(async_track_time_change(self.hass, self._daily_check, hour=3, minute=30, second=0))
        if self.hass.is_running:
            # added at run time: fetch now, in the background so setup does not wait for the network
            self.entry.async_create_background_task(self.hass, self._startup_fetch(), "werktage school holidays")
        else:
            # at boot: wait until Home Assistant has started, the network may not be up yet
            self._unsub_started = self.hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, self._on_started)

    async def async_unload(self) -> None:
        for unsub in self._unsub:
            unsub()
        self._unsub.clear()
        self.personal_calendars.stop()
        self.exporter.stop()
        if self._unsub_started is not None:
            self._unsub_started()
            self._unsub_started = None

    async def _at_midnight(self, _now: dt.datetime) -> None:
        try:
            await self._async_public_holidays()      # a new year may have entered the kept span
        except ConfigEntryError as err:
            # keep the holidays already known: the sensors must still move to the new day
            _LOGGER.error("Public holidays could not be updated at midnight, keeping the known ones: %s", err)
        self._rebuild()
        self.fetcher.check_completeness()            # October may have begun, or the source may have changed

    async def _daily_check(self, _now: dt.datetime) -> None:
        await self.fetcher.async_refresh()
        await self.personal_calendars.async_refresh()

    async def _on_started(self, _event: Any) -> None:
        self._unsub_started = None          # a one-time listener removes itself; unsubscribing it again logs an error
        await self._startup_fetch()

    async def _startup_fetch(self) -> None:
        await self.fetcher.async_refresh()
        await self.personal_calendars.async_refresh()
        await self.exporter.async_run()

    # -- listeners ---------------------------------------------------------------------
    @callback
    def async_add_listener(self, update: Callable[[], None]) -> CALLBACK_TYPE:
        self._listeners.append(update)

        @callback
        def remove() -> None:
            self._listeners.remove(update)
        return remove

    @callback
    def _notify(self) -> None:
        for update in list(self._listeners):
            update()

    # -- building ----------------------------------------------------------------------
    async def _async_public_holidays(self) -> None:
        """Public holidays for the kept year span, computed off the event loop.

        The ``holidays`` library reads a locale file on first use; that must not
        happen in the event loop. Recomputed only when the span changes.
        """
        span = sources.year_span(self.today())
        if span == self._public_holidays_span:
            return
        country, subdivision, language = self.country, self.subdivision, self.hass.config.language
        try:
            self._public_holidays = await self.hass.async_add_executor_job(
                sources.public_holidays, country, sources.subdivision_code(country, subdivision),
                range(span[0].year, span[1].year + 1), language)
        except NotImplementedError as err:
            raise ConfigEntryError(translation_domain=DOMAIN, translation_key="country_unsupported",
                                   translation_placeholders={"error": str(err)}) from err
        self._public_holidays_span = span

    @callback
    def _rebuild(self) -> None:
        extra, removed = self.holiday_corrections()
        school_holidays = self.fetcher.school_holidays
        calendar = Calendar(self._public_holidays, school_holidays(self.source_key), self.weekend, extra, removed,
                            school_holidays_by_source={key: school_holidays(key) for key in self.source_keys()})
        calendar_days = {rid: CalendarDays(frozenset(c.days_off), frozenset(c.workdays))
                         for rid, c in self.data.calendar_days.items()}
        self.household = Household(calendar, self.data.residents, self.data.rooms, self.house, self.data.exceptions,
                                   calendar_days)
        self._check_registry_issues()
        self._notify()
        if self.export_calendar and self.hass.is_running:        # at boot the target calendar may not be up yet
            self.exporter.schedule()

    async def async_commit(self, data: StoredData) -> None:
        """Store ``data``, rebuild the household and notify the entities; the coordinator's parts commit here too."""
        self.data = data
        await self._store.async_save(storage.to_dict(self.data))
        self._rebuild()

    # -- persons and areas of the installation ---------------------------------------
    def person_entity_id(self, person_id: str) -> str | None:
        return er.async_get(self.hass).async_get_entity_id("person", "person", person_id)

    def person_name(self, person_id: str) -> str:
        entity_id = self.person_entity_id(person_id)
        state = self.hass.states.get(entity_id) if entity_id else None
        return state.name if state else person_id

    def person_id_of(self, entity_id: str) -> str:
        """The stable id of a ``person.*`` entity; raises ``WerktagsError`` if unknown."""
        state = self.hass.states.get(entity_id)
        person_id = state.attributes.get("id") if state else None
        if not person_id:
            entry = er.async_get(self.hass).async_get(entity_id)
            person_id = entry.unique_id if entry and entry.domain == "person" else None
        if not person_id:
            raise WerktagsError("unknown_person", entity_id=entity_id)
        return str(person_id)

    def all_persons(self) -> list[tuple[str, str, str]]:
        """``(person_id, entity_id, name)`` of every person in Home Assistant."""
        result = []
        for state in self.hass.states.async_all("person"):
            if person_id := state.attributes.get("id"):
                result.append((str(person_id), state.entity_id, state.name))
        return sorted(result, key=lambda p: p[2].lower())

    def area_name(self, area_id: str) -> str:
        area = ar.async_get(self.hass).async_get_area(area_id)
        return area.name if area else area_id

    def area_exists(self, area_id: str) -> bool:
        return ar.async_get(self.hass).async_get_area(area_id) is not None

    def all_areas(self) -> list[tuple[str, str]]:
        return sorted(((a.id, a.name) for a in ar.async_get(self.hass).async_list_areas()), key=lambda a: a[1].lower())

    def _check_registry_issues(self) -> None:
        registry = er.async_get(self.hass)
        missing_persons = [self.person_name(rid) for rid in self.data.residents
                           if registry.async_get_entity_id("person", "person", rid) is None]
        missing_areas = [aid for aid in self.data.rooms if not self.area_exists(aid)]
        self.set_issue(ISSUE_PERSON_MISSING, bool(missing_persons), {"ids": ", ".join(missing_persons)})
        self.set_issue(ISSUE_AREA_MISSING, bool(missing_areas), {"ids": ", ".join(missing_areas)})

    def set_issue(self, issue_id: str, active: bool, placeholders: dict[str, str] | None = None,
                  severity: ir.IssueSeverity = ir.IssueSeverity.WARNING, translation_key: str | None = None) -> None:
        """Raise or clear a repair hint of the integration."""
        if active:
            ir.async_create_issue(self.hass, DOMAIN, issue_id, is_fixable=False, severity=severity,
                                  translation_key=translation_key or issue_id, translation_placeholders=placeholders)
        else:
            ir.async_delete_issue(self.hass, DOMAIN, issue_id)

    # -- changes (called by services) --------------------------------------------------
    async def async_set_days(self, person_ids: Iterable[str], start: dt.date, end: dt.date,
                             status: DayType | None) -> None:
        household = self.household.with_exceptions(list(person_ids), start, end, status)
        exceptions = {day: dict(per_day) for day, per_day in household.exceptions.items()}
        await self.async_commit(replace(self.data, exceptions=exceptions))

    def propose_short_name(self, person_id: str) -> str:
        """First letter of the name, made unique among the other residents (A, AN, A2, …)."""
        name = self.person_name(person_id).strip() or "?"
        taken = {r.short_name.upper() for rid, r in self.data.residents.items() if rid != person_id}
        candidates = [name[:1].upper(), name[:2].upper()] + [f"{name[:1].upper()}{i}" for i in range(2, 10)]
        return next((c for c in candidates if c and c not in taken), name[:1].upper())

    async def async_set_role(self, person_id: str, role: Role, valid_from: dt.date,
                             short_name: str | None = None, school_holiday_source: str | None = UNCHANGED) -> None:
        """Add a role step; ``school_holiday_source`` sets (or with ``""``/``None`` clears) the resident's own
        source (#1); left out, it stays as it is."""
        residents = dict(self.data.residents)
        current = residents.get(person_id)
        if current is None:
            current = Resident(person_id, short_name or self.propose_short_name(person_id), History(),
                               order=len(residents))
        if short_name:
            self._check_short_name(person_id, short_name)
            current = replace(current, short_name=short_name)
        if school_holiday_source != UNCHANGED:
            key = (school_holiday_source or "").strip() or None
            if key is not None and key != self.source_key:
                await self._check_source_key(key)
            else:
                key = None
            current = replace(current, school_holiday_source=key)
        residents[person_id] = replace(current, roles=current.roles.with_step(valid_from, role))
        await self.async_commit(replace(self.data, residents=residents))
        if any(not self.fetcher.is_fresh(key) for key in self.source_keys()):
            self.entry.async_create_background_task(self.hass, self.fetcher.async_refresh(),
                                                    "werktage school holidays")

    def _check_short_name(self, person_id: str, short_name: str) -> None:
        if not 1 <= len(short_name) <= 2:
            raise WerktagsError("short_name_length")
        for rid, resident in self.data.residents.items():
            if rid != person_id and resident.short_name.lower() == short_name.lower():
                raise WerktagsError("short_name_taken", short_name=short_name)

    async def async_remove_role(self, person_id: str, valid_from: dt.date) -> None:
        resident = self.data.residents.get(person_id)
        if resident is None or not any(s.valid_from == valid_from for s in resident.roles.steps):
            raise WerktagsError("no_role_entry")
        if len(resident.roles.steps) == 1:
            raise WerktagsError("last_role_entry")
        residents = dict(self.data.residents)
        residents[person_id] = replace(resident, roles=resident.roles.without_step(valid_from))
        await self.async_commit(replace(self.data, residents=residents))

    async def async_set_weekly(self, person_id: str, weekdays: frozenset[int] | None, valid_from: dt.date) -> None:
        """Personal days off every week from a date on; ``None`` returns the person to the
        household weekend from that date on. Earlier days keep their pattern (3.4)."""
        resident = self.data.residents.get(person_id)
        if resident is None:
            raise WerktagsError("not_resident")
        if weekdays is not None and not all(0 <= d <= 6 for d in weekdays):
            raise WerktagsError("weekdays_range")
        value = None if weekdays is None else frozenset(weekdays)
        history = _with_default_step(resident.off_weekdays, valid_from, value)
        residents = {**self.data.residents, person_id: replace(resident, off_weekdays=history)}
        await self.async_commit(replace(self.data, residents=residents))

    async def async_set_calendars(self, person_id: str, days_off_calendar: str | None, workdays_calendar: str | None,
                                  keyword: str | None) -> None:
        """The resident's personal calendars (#2); ``None`` or ``""`` clears a calendar. Reads them right away."""
        resident = self.data.residents.get(person_id)
        if resident is None:
            raise WerktagsError("not_resident")
        for entity_id in (days_off_calendar, workdays_calendar):
            if entity_id and self.hass.states.get(entity_id) is None:
                raise WerktagsError("calendar_unknown", entity_id=entity_id)
        updated = replace(resident, days_off_calendar=days_off_calendar or None,
                          workdays_calendar=workdays_calendar or None, calendar_keyword=(keyword or "").strip() or None)
        await self.async_commit(replace(self.data, residents={**self.data.residents, person_id: updated}))
        self.personal_calendars.track()
        self.entry.async_create_background_task(self.hass, self.personal_calendars.async_refresh(),
                                                "werktage calendars")

    async def async_set_house(self, person_ids: Iterable[str] | None, valid_from: dt.date) -> None:
        """Residents that count for the house from a date on; ``None`` returns to the role-based
        default from that date on. Earlier days keep their assignment (3.4)."""
        history: History[frozenset[str] | None]
        if person_ids is None:
            history = _with_default_step(self.data.house_residents, valid_from, None)
        else:
            ids = frozenset(person_ids)
            unknown = [pid for pid in ids if pid not in self.data.residents]
            if unknown:
                raise WerktagsError("not_residents", persons=", ".join(sorted(unknown)))
            history = _with_default_step(self.data.house_residents, valid_from, ids)
        await self.async_commit(replace(self.data, house_residents=history))

    async def async_set_order(self, person_ids: list[str]) -> None:
        residents = dict(self.data.residents)
        for index, rid in enumerate(person_ids):
            if rid in residents:
                residents[rid] = replace(residents[rid], order=index)
        await self.async_commit(replace(self.data, residents=residents))

    async def async_set_room(self, area_id: str, person_ids: Iterable[str] | None, valid_from: dt.date | None,
                             morning_rule: CombineRule | None = None,
                             evening_rule: CombineRule | None = None) -> None:
        if not self.area_exists(area_id):
            raise WerktagsError("unknown_area", area=area_id)
        rooms = dict(self.data.rooms)
        room = rooms.get(area_id) or Room(area_id)
        if person_ids is not None and valid_from is not None:
            room = replace(room, residents=room.residents.with_step(valid_from, frozenset(person_ids)))
        if morning_rule is not None:
            room = replace(room, morning_rule=morning_rule)
        if evening_rule is not None:
            room = replace(room, evening_rule=evening_rule)
        if not room.ever_assigned:
            raise WerktagsError("room_without_residents")        # rules belong to a room that has residents
        rooms[area_id] = room
        await self.async_commit(replace(self.data, rooms=rooms))

    async def async_remove_room_assignment(self, area_id: str, valid_from: dt.date) -> None:
        room = self.data.rooms.get(area_id)
        if room is None or not any(s.valid_from == valid_from for s in room.residents.steps):
            raise WerktagsError("no_room_assignment")
        rooms = dict(self.data.rooms)
        room = replace(room, residents=room.residents.without_step(valid_from))
        if room.ever_assigned:
            rooms[area_id] = room
        else:
            del rooms[area_id]                  # a room is its residents; without any it is gone
        await self.async_commit(replace(self.data, rooms=rooms))

    async def async_refresh_school_holidays(self, force: bool = False) -> bool:
        """Fetch the school holidays of every source in use that is due (all with ``force``); see the fetcher."""
        return await self.fetcher.async_refresh(force)

    def is_stale_device_id(self, identifier: str) -> bool:
        """Whether a device identifier belongs to a resident or room that no longer exists."""
        prefix = f"{self.entry.entry_id}_"
        if not identifier.startswith(prefix):
            return False
        rest = identifier[len(prefix):]
        if rest.startswith("resident_"):
            return rest[len("resident_"):] not in self.data.residents
        if rest.startswith("room_"):
            return rest[len("room_"):] not in self.data.rooms
        return False

    # -- read-outs for services and cards ----------------------------------------------
    def status(self) -> dict[str, Any]:
        def describe(key: str) -> dict[str, Any] | None:
            cache = self.data.school_holidays.get(key)
            return None if cache is None else {
                "fetched_at": cache.fetched_at.isoformat() if cache.fetched_at else None,
                "known_from": cache.known_from.isoformat() if cache.known_from else None,
                "known_to": cache.known_to.isoformat() if cache.known_to else None,
                "periods": len(cache.periods), "failures": cache.failures,
            }
        return {
            "country": self.country, "subdivision": self.subdivision, "weekend": sorted(self.weekend),
            "school_holiday_source": self.source, "attribution": self.attribution,
            "school_holidays": describe(self.source_key),                       # the installation's source
            "sources": {key: describe(key) for key in self.source_keys()},     # every source in use (#1)
        }
