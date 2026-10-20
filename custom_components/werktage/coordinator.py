"""The coordinator: holds the stored data, rebuilds the household, fetches school holidays.

Every change goes through here: services call the ``async_*`` methods, which
update the store, rebuild the rules' ``Household`` and notify the entities.
Dates are calendar days in the Home Assistant time zone (specification P6).
"""
from __future__ import annotations

import datetime as dt
import logging
from collections.abc import Callable, Iterable
from dataclasses import replace
from typing import Any

from homeassistant.components.calendar import CalendarEntity
from homeassistant.components.calendar.const import DOMAIN as CALENDAR_DOMAIN
from homeassistant.components.calendar.const import CalendarEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED
from homeassistant.core import CALLBACK_TYPE, Event, EventStateChangedData, HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryError
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.debounce import Debouncer
from homeassistant.helpers.entity_component import EntityComponent
from homeassistant.helpers.event import async_track_state_change_event, async_track_time_change
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from . import export, sources, storage
from .const import (
    ATTRIBUTION_OPENHOLIDAYS,
    CALENDAR_DEBOUNCE_SECONDS,
    CALENDAR_LOOKAHEAD_DAYS,
    CALENDAR_LOOKBACK_DAYS,
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
    EXPORT_DEBOUNCE_SECONDS,
    FETCH_INTERVAL_DAYS,
    ISSUE_AREA_MISSING,
    ISSUE_EXPORT_FAILED,
    ISSUE_PERSON_MISSING,
    ISSUE_SCHOOL_HOLIDAYS_INCOMPLETE,
    ISSUE_SCHOOL_HOLIDAYS_UNREACHABLE,
    MAX_FETCH_FAILURES,
    SOURCE_CALENDAR,
    SOURCE_NONE,
    SOURCE_OPENHOLIDAYS,
    USER_AGENT,
)
from .openholidays import OpenHolidaysClient, OpenHolidaysError, is_plausible
from .rules import (
    DEFAULT_EVENING_RULE,
    DEFAULT_HOUSE_ROLES,
    DEFAULT_MORNING_RULE,
    ONE_DAY,
    Calendar,
    CalendarDays,
    CombineRule,
    DayType,
    History,
    House,
    Household,
    Resident,
    Role,
    Room,
    SchoolHolidays,
)
from .sources import SchoolHolidayPeriod
from .storage import CalendarDaysCache, SchoolHolidayCache, StoredData

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


class FetchFailed(Exception):
    """A school holiday fetch did not yield usable data."""


def _with_default_step[T](history: History[T | None], valid_from: dt.date, value: T | None) -> History[T | None]:
    """Add a step; a history that only ever says "default" (``None``) collapses to no history at all."""
    history = history.with_step(valid_from, value)
    return History() if all(step.value is None for step in history.steps) else history


async def async_probe_openholidays(hass: HomeAssistant, country: str, subdivision: str | None) -> int:
    """How many school holiday periods the API has for this year (setup check). Raises ``OpenHolidaysError``."""
    client = OpenHolidaysClient(async_get_clientsession(hass), user_agent=USER_AGENT)
    first, last = sources.fetch_span(dt_util.now().date())      # the very range the integration fetches later
    return len(await client.school_holidays(country, subdivision, first, last))


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
        self._listeners: list[Callable[[], None]] = []
        self._unsub: list[CALLBACK_TYPE] = []
        self._unsub_started: CALLBACK_TYPE | None = None     # the one-time start listener, until it fired
        self._fetching = False
        self._source_down: set[str] = set()   # log-when-unavailable per source: one line down, one up
        self._calendars_down: set[str] = set()                 # residents whose calendars could not be read
        self._unsub_calendars: CALLBACK_TYPE | None = None     # state changes of the personal calendars (#2)
        self._calendar_debouncer = Debouncer(hass, _LOGGER, cooldown=CALENDAR_DEBOUNCE_SECONDS, immediate=False,
                                             function=self.async_refresh_calendars)
        self._export_debouncer = Debouncer(hass, _LOGGER, cooldown=EXPORT_DEBOUNCE_SECONDS, immediate=False,
                                           function=self.async_export_days_off)     # after a burst of changes (#3)
        self._export_down = False
        self._exporting = False

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

    # -- export into a shared calendar (#3) ------------------------------------
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
                added[dt.date.fromisoformat(day)] = name.strip() or "Holiday"
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
        return self.attribution_for(self.source_key)

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

    @staticmethod
    def attribution_for(key: str) -> str | None:
        return ATTRIBUTION_OPENHOLIDAYS if key.startswith(f"{SOURCE_OPENHOLIDAYS}:") else None

    def school_holiday_source_options(self) -> list[dict[str, str]]:
        """Choices for a resident's source: the installation's, every region of the country, every calendar."""
        german = (self.hass.config.language or "en").lower().startswith("de")
        options = [{"value": "", "label": "wie die Installation" if german else "as the installation"}]
        names = sources.subdivision_names(self.country)
        options += [{"value": f"{SOURCE_OPENHOLIDAYS}:{self.country}-{code}", "label": name}
                    for code, name in sorted(names.items(), key=lambda item: item[1])]
        options += [{"value": f"{SOURCE_CALENDAR}:{c['entity_id']}", "label": c["name"]}
                    for c in self.calendar_entities()]
        return options

    def calendar_entities(self) -> list[dict[str, str]]:
        """Every calendar entity of the installation except our own, sorted by name."""
        registry = er.async_get(self.hass)
        states = [state for state in self.hass.states.async_all("calendar")
                  if (entry := registry.async_get(state.entity_id)) is None or entry.platform != DOMAIN]
        return [{"entity_id": state.entity_id, "name": state.name}
                for state in sorted(states, key=lambda state: state.name.lower())]

    def _check_source_key(self, key: str) -> None:
        source, parameter = sources.parse_source_key(key)
        if source == SOURCE_OPENHOLIDAYS and parameter and sources.is_region_code(parameter):
            return
        if source == SOURCE_CALENDAR and parameter and self.hass.states.get(parameter) is not None:
            return
        raise WerktagsError("source_unknown", source=key)

    def cache_for(self, key: str) -> SchoolHolidayCache | None:
        return self.data.school_holidays.get(key)

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
        await self._async_public_holidays()
        self._rebuild()
        self._check_completeness()                # a fresh cache skips the fetch, the hint must not wait for it
        self._track_calendars()
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
        if self._unsub_calendars is not None:
            self._unsub_calendars()
            self._unsub_calendars = None
        self._calendar_debouncer.async_cancel()
        self._export_debouncer.async_cancel()
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
        self._check_completeness()                # October may have begun, or the source may have changed

    async def _daily_check(self, _now: dt.datetime) -> None:
        await self.async_refresh_school_holidays()
        await self.async_refresh_calendars()

    async def _on_started(self, _event: Any) -> None:
        self._unsub_started = None          # a one-time listener removes itself; unsubscribing it again logs an error
        await self._startup_fetch()

    async def _startup_fetch(self, _event: Any = None) -> None:
        await self.async_refresh_school_holidays()
        await self.async_refresh_calendars()
        await self.async_export_days_off()

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

    def _school_holidays(self, key: str) -> SchoolHolidays:
        if key == SOURCE_NONE:
            return SchoolHolidays(attribution=None)
        cache = self.cache_for(key)
        if cache is None or cache.known_from is None or cache.known_to is None:
            return SchoolHolidays(known_from=dt.date.max, known_to=dt.date.max, attribution=self.attribution_for(key))
        return sources.school_holidays_from_periods(cache.periods, cache.known_from, cache.known_to,
                                                    self.attribution_for(key))

    @callback
    def _rebuild(self) -> None:
        extra, removed = self.holiday_corrections()
        calendar = Calendar(self._public_holidays, self._school_holidays(self.source_key), self.weekend, extra, removed,
                            school_holidays_by_source={key: self._school_holidays(key) for key in self.source_keys()})
        calendar_days = {rid: CalendarDays(frozenset(c.days_off), frozenset(c.workdays))
                         for rid, c in self.data.calendar_days.items()}
        self.household = Household(calendar, self.data.residents, self.data.rooms, self.house, self.data.exceptions,
                                   calendar_days)
        self._check_registry_issues()
        self._notify()
        if self.export_calendar and self.hass.is_running:        # at boot the target calendar may not be up yet
            self.entry.async_create_background_task(self.hass, self._export_debouncer.async_call(), "werktage export")

    async def _async_save(self) -> None:
        await self._store.async_save(storage.to_dict(self.data))

    async def _async_commit(self, data: StoredData) -> None:
        self.data = data
        await self._async_save()
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
        self._issue(ISSUE_PERSON_MISSING, bool(missing_persons), {"ids": ", ".join(missing_persons)})
        self._issue(ISSUE_AREA_MISSING, bool(missing_areas), {"ids": ", ".join(missing_areas)})

    def _issue(self, issue_id: str, active: bool, placeholders: dict[str, str] | None = None,
               severity: ir.IssueSeverity = ir.IssueSeverity.WARNING, translation_key: str | None = None) -> None:
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
        await self._async_commit(replace(self.data, exceptions=exceptions))

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
                self._check_source_key(key)
            else:
                key = None
            current = replace(current, school_holiday_source=key)
        residents[person_id] = replace(current, roles=current.roles.with_step(valid_from, role))
        await self._async_commit(replace(self.data, residents=residents))
        if any(not self.cache_is_fresh(key) for key in self.source_keys()):
            self.entry.async_create_background_task(self.hass, self.async_refresh_school_holidays(),
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
        await self._async_commit(replace(self.data, residents=residents))

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
        await self._async_commit(replace(self.data, residents=residents))

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
        await self._async_commit(replace(self.data, residents={**self.data.residents, person_id: updated}))
        self._track_calendars()
        self.entry.async_create_background_task(self.hass, self.async_refresh_calendars(), "werktage calendars")

    async def async_refresh_calendars(self) -> None:
        """Read every resident's personal calendars (#2). An unreadable calendar keeps its last days, never
        turns the days unknown: a missing calendar must not make every day a workday."""
        today = self.today()
        first = today - dt.timedelta(days=CALENDAR_LOOKBACK_DAYS)
        last = today + dt.timedelta(days=CALENDAR_LOOKAHEAD_DAYS)
        caches = dict(self.data.calendar_days)
        for person_id, resident in self.data.residents.items():
            if not resident.has_calendars:
                caches.pop(person_id, None)
                continue
            try:
                keyword = resident.calendar_keyword                      # filters the days-off calendar only
                days_off = (await self._calendar_days(resident.days_off_calendar, first, last, keyword)
                            if resident.days_off_calendar else frozenset())
                workdays = (await self._calendar_days(resident.workdays_calendar, first, last, None)   # dedicated
                            if resident.workdays_calendar else frozenset())
            except Exception as err:  # noqa: BLE001 — a calendar integration may raise anything
                if person_id not in self._calendars_down:
                    _LOGGER.warning("Personal calendars %s could not be read, keeping the last days: %s",
                                    [c for c in (resident.days_off_calendar, resident.workdays_calendar) if c], err)
                    self._calendars_down.add(person_id)
                continue
            self._calendars_down.discard(person_id)
            caches[person_id] = CalendarDaysCache(tuple(sorted(days_off)), tuple(sorted(workdays)), first, last,
                                                  dt_util.utcnow())
        for person_id in [pid for pid in caches if pid not in self.data.residents]:
            caches.pop(person_id)
        if caches != self.data.calendar_days:
            await self._async_commit(replace(self.data, calendar_days=caches))

    # -- export into a shared calendar (#3) ------------------------------------------------
    def _calendar_entity(self, entity_id: str) -> CalendarEntity | None:
        """The calendar entity object (for events with uids and for writing), if its integration is loaded."""
        component: EntityComponent[CalendarEntity] | None = self.hass.data.get(CALENDAR_DOMAIN)
        return component.get_entity(entity_id) if component else None

    def export_supported(self, entity_id: str) -> bool:
        """Whether the calendar can take our events: its integration must create and delete events."""
        entity = self._calendar_entity(entity_id)
        needed = CalendarEntityFeature.CREATE_EVENT | CalendarEntityFeature.DELETE_EVENT
        return entity is not None and (entity.supported_features or 0) & needed == needed

    async def async_export_days_off(self) -> None:
        """Write the coming days off into the shared calendar and remove the ones that are no longer true.

        Only events with our marker in the description are ever created, compared or
        deleted (export.py); everything else in the calendar stays untouched. Failures
        raise a repair issue and are logged once until the export works again.
        """
        entity_id = self.export_calendar
        if not entity_id:
            self._issue(ISSUE_EXPORT_FAILED, False)
            return
        if self._exporting:
            return
        self._exporting = True
        try:
            entity = self._calendar_entity(entity_id)
            if entity is None or not self.export_supported(entity_id):
                self._export_problem(entity_id, "the calendar is not loaded or cannot create and delete events")
                return
            today = self.today()
            last = today + dt.timedelta(weeks=self.export_weeks) - ONE_DAY
            residents = [pid for pid in self.data.residents if not self.export_persons or pid in self.export_persons]
            names = {pid: self.person_name(pid) for pid in residents}
            wanted = export.wanted_events(self.household, residents, names, today, last, self.export_weekends,
                                          self.hass.config.language)
            tz = dt_util.get_default_time_zone()
            try:
                events = await entity.async_get_events(self.hass, dt.datetime.combine(today, dt.time(), tz),
                                                       dt.datetime.combine(last + ONE_DAY, dt.time(), tz))
                existing = [export.OwnEvent(event.uid, key, event.summary) for event in events
                            if event.uid and (key := export.key_of(event.description))]
                to_create, to_delete = export.plan(wanted, existing)
                for stale in to_delete:
                    await entity.async_delete_event(stale.uid)
                for new in to_create:
                    await entity.async_create_event(dtstart=new.day, dtend=new.day + ONE_DAY, summary=new.summary,
                                                    description=new.description)
            except Exception as err:  # noqa: BLE001 — a calendar integration may raise anything
                self._export_problem(entity_id, str(err))
                return
            if self._export_down:
                _LOGGER.info("Export into %s works again", entity_id)
                self._export_down = False
            self._issue(ISSUE_EXPORT_FAILED, False)
        finally:
            self._exporting = False

    def _export_problem(self, entity_id: str, error: str) -> None:
        if not self._export_down:
            _LOGGER.warning("Days off could not be exported into %s: %s", entity_id, error)
            self._export_down = True
        self._issue(ISSUE_EXPORT_FAILED, True, {"calendar": entity_id, "error": error})

    @callback
    def _track_calendars(self) -> None:
        """Re-read the personal calendars (debounced) whenever one of them changes state."""
        if self._unsub_calendars is not None:
            self._unsub_calendars()
            self._unsub_calendars = None
        entity_ids = sorted({entity_id for r in self.data.residents.values()
                             for entity_id in (r.days_off_calendar, r.workdays_calendar) if entity_id})
        if entity_ids:
            self._unsub_calendars = async_track_state_change_event(self.hass, entity_ids, self._calendar_changed)

    @callback
    def _calendar_changed(self, _event: Event[EventStateChangedData]) -> None:
        self.entry.async_create_background_task(self.hass, self._calendar_debouncer.async_call(), "werktage calendars")

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
        await self._async_commit(replace(self.data, house_residents=history))

    async def async_set_order(self, person_ids: list[str]) -> None:
        residents = dict(self.data.residents)
        for index, rid in enumerate(person_ids):
            if rid in residents:
                residents[rid] = replace(residents[rid], order=index)
        await self._async_commit(replace(self.data, residents=residents))

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
        await self._async_commit(replace(self.data, rooms=rooms))

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
        await self._async_commit(replace(self.data, rooms=rooms))

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

    # -- school holidays -----------------------------------------------------------------
    def cache_is_fresh(self, key: str | None = None) -> bool:
        cache = self.cache_for(key or self.source_key)
        if cache is None or cache.fetched_at is None:
            return False
        return dt_util.utcnow() - cache.fetched_at < dt.timedelta(days=FETCH_INTERVAL_DAYS)

    async def async_refresh_school_holidays(self, force: bool = False) -> bool:
        """Fetch every source in use that is due (or all with ``force``). Returns whether new data arrived."""
        if self._fetching:
            return False
        self._fetching = True
        try:
            arrived = False
            for key in self.source_keys():
                if force or not self.cache_is_fresh(key):
                    arrived = await self._refresh_source(key) or arrived
            await self._prune_caches()
        finally:
            self._fetching = False
        return arrived

    async def _refresh_source(self, key: str) -> bool:
        try:
            periods = await self._fetch_periods(key)
        except FetchFailed as err:
            if key not in self._source_down:
                _LOGGER.warning("School holidays could not be fetched from %s: %s", key, err)
                self._source_down.add(key)
            periods = None

        old = self.cache_for(key) or SchoolHolidayCache(key)
        if periods is None:
            cache = replace(old, source=key, failures=old.failures + 1)
        else:
            if key in self._source_down:
                _LOGGER.info("School holidays from %s are available again", key)
                self._source_down.discard(key)
            first, last = sources.fetch_span(self.today())
            known_to = min(last, max((p.end for p in periods), default=first))
            # earlier years are not fetched again: keep what the same source told us about them
            kept = tuple(p for p in old.periods if p.end < first)
            contiguous = bool(kept) and old.known_from is not None and old.known_to is not None \
                and old.known_to >= first - dt.timedelta(days=1)
            known_from = old.known_from if contiguous else first
            cache = SchoolHolidayCache(key, kept + tuple(periods), known_from, known_to, dt_util.utcnow(), 0)
        await self._async_commit(replace(self.data, school_holidays={**self.data.school_holidays, key: cache}))
        self._issue(self._issue_id(ISSUE_SCHOOL_HOLIDAYS_UNREACHABLE, key), cache.failures >= MAX_FETCH_FAILURES,
                    {"source": key, "failures": str(cache.failures)}, translation_key=ISSUE_SCHOOL_HOLIDAYS_UNREACHABLE)
        self._check_completeness()
        return periods is not None

    async def _prune_caches(self) -> None:
        """Drop the caches (and hints) of sources nobody uses any more."""
        unused = set(self.data.school_holidays) - set(self.source_keys())
        if not unused:
            return
        for key in unused:
            for base in (ISSUE_SCHOOL_HOLIDAYS_UNREACHABLE, ISSUE_SCHOOL_HOLIDAYS_INCOMPLETE):
                self._issue(self._issue_id(base, key), False)
        await self._async_commit(replace(self.data, school_holidays={
            key: cache for key, cache in self.data.school_holidays.items() if key not in unused}))

    def _issue_id(self, base: str, key: str) -> str:
        """The installation's source keeps the plain id; a resident's source gets its own."""
        return base if key == self.source_key else f"{base}_{key}"

    def _check_completeness(self) -> None:
        """From October, next year's summer holidays must be known for every source in use (specification 5.5)."""
        today = self.today()
        needed = dt.date(today.year + 1, 8, 31)
        for key in self.source_keys():
            cache = self.cache_for(key)
            incomplete = today.month >= 10 and (cache is None or cache.known_to is None or cache.known_to < needed)
            known_to = cache.known_to.isoformat() if cache and cache.known_to else "-"
            self._issue(self._issue_id(ISSUE_SCHOOL_HOLIDAYS_INCOMPLETE, key), incomplete,
                        {"year": str(today.year + 1), "known_to": known_to, "source": key},
                        translation_key=ISSUE_SCHOOL_HOLIDAYS_INCOMPLETE)
        if self.source == SOURCE_NONE:
            self._issue(ISSUE_SCHOOL_HOLIDAYS_INCOMPLETE, False)

    async def _fetch_periods(self, key: str) -> list[SchoolHolidayPeriod]:
        first, last = sources.fetch_span(self.today())
        source, parameter = sources.parse_source_key(key)
        if source == SOURCE_OPENHOLIDAYS and parameter:
            country, _, subdivision = parameter.partition("-")
            client = OpenHolidaysClient(async_get_clientsession(self.hass), user_agent=USER_AGENT)
            try:
                holidays = await client.school_holidays(country, parameter if subdivision else None, first, last)
            except OpenHolidaysError as err:
                raise FetchFailed(str(err)) from err
            # the year after next may not be published yet; this year and next must be complete
            if not is_plausible(holidays, [self.today().year, self.today().year + 1]):
                raise FetchFailed("answer not plausible (missing summer holidays)")
            language = (self.hass.config.language or "en").split("-")[0].upper()
            return [SchoolHolidayPeriod(h.start, h.end, h.name(language)) for h in holidays]
        if source == SOURCE_CALENDAR and parameter:
            try:
                return await self._fetch_from_calendar(parameter, first, last)
            except Exception as err:  # noqa: BLE001 — a calendar integration may raise anything
                raise FetchFailed(str(err)) from err
        raise FetchFailed(f"no school holiday source configured ({key})")

    async def _fetch_from_calendar(self, entity_id: str, first: dt.date, last: dt.date) -> list[SchoolHolidayPeriod]:
        periods = [SchoolHolidayPeriod(start, end, summary) for start, end, summary in
                   await self._all_day_events(entity_id, first, last)]
        return sorted(periods, key=lambda p: p.start)

    async def _calendar_days(self, entity_id: str, first: dt.date, last: dt.date,
                             keyword: str | None) -> frozenset[dt.date]:
        """The days covered by all-day events (whose title contains ``keyword``, if given) in ``first``..``last``."""
        days: set[dt.date] = set()
        for start, end, summary in await self._all_day_events(entity_id, first, last):
            if keyword and keyword.lower() not in summary.lower():
                continue
            day = max(start, first)
            while day <= min(end, last):
                days.add(day)
                day += dt.timedelta(days=1)
        return frozenset(days)

    async def _all_day_events(self, entity_id: str, first: dt.date,
                              last: dt.date) -> list[tuple[dt.date, dt.date, str]]:
        """``(first day, last day, title)`` of every all-day event; timed events ignored, calendar ends exclusive."""
        tz = dt_util.get_default_time_zone()
        response: Any = await self.hass.services.async_call(
            "calendar", "get_events",
            {"entity_id": entity_id, "start_date_time": dt.datetime.combine(first, dt.time(), tz).isoformat(),
             "end_date_time": dt.datetime.combine(last + dt.timedelta(days=1), dt.time(), tz).isoformat()},
            blocking=True, return_response=True,
        )
        events = (response or {}).get(entity_id, {}).get("events", []) if isinstance(response, dict) else []
        result = []
        for event in events:
            start, end = str(event.get("start", "")), str(event.get("end", ""))
            if len(start) != 10 or len(end) != 10:
                continue
            end_date = dt.date.fromisoformat(end) - dt.timedelta(days=1)
            result.append((dt.date.fromisoformat(start), end_date, str(event.get("summary", ""))))
        return result

    # -- read-outs for services and cards ----------------------------------------------
    def status(self) -> dict[str, Any]:
        def describe(key: str) -> dict[str, Any] | None:
            cache = self.cache_for(key)
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
