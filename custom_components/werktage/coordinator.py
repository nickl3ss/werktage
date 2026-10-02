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

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryError
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_time_change
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from . import sources, storage
from .const import (
    ATTRIBUTION_OPENHOLIDAYS,
    CONF_ADD_HOLIDAYS,
    CONF_ADMIN_ONLY,
    CONF_CALENDAR_ENTITY,
    CONF_COUNTRY,
    CONF_HOUSE_EVENING_RULE,
    CONF_HOUSE_MORNING_RULE,
    CONF_HOUSE_ROLES,
    CONF_REMOVE_HOLIDAYS,
    CONF_SCHOOL_HOLIDAY_SOURCE,
    CONF_SUBDIVISION,
    CONF_WEEKEND,
    DEFAULT_WEEKEND_DAYS,
    DOMAIN,
    FETCH_INTERVAL_DAYS,
    ISSUE_AREA_MISSING,
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
    Calendar,
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
from .storage import SchoolHolidayCache, StoredData

_LOGGER = logging.getLogger(__name__)
type WerktagsConfigEntry = ConfigEntry[WerktagsCoordinator]


class WerktagsError(ValueError):
    """A rejected change. ``key`` names the translated message (``exceptions`` in strings.json)."""

    def __init__(self, key: str, **placeholders: str) -> None:
        super().__init__(key)
        self.key = key
        self.placeholders = placeholders


class FetchFailed(Exception):
    """A school holiday fetch did not yield usable data."""


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
        self._store: Store[dict[str, Any]] = Store(hass, storage.DATA_VERSION, f"{DOMAIN}.data")
        self.data = StoredData()
        self.household = Household(calendar=Calendar())
        self._public_holidays: dict[dt.date, str] = {}
        self._public_holidays_span: tuple[dt.date, dt.date] | None = None
        self._listeners: list[Callable[[], None]] = []
        self._unsub: list[CALLBACK_TYPE] = []
        self._unsub_started: CALLBACK_TYPE | None = None     # the one-time start listener, until it fired
        self._fetching = False
        self._source_down = False      # for log-when-unavailable: one line on failure, one on recovery

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
        return ATTRIBUTION_OPENHOLIDAYS if self.source == SOURCE_OPENHOLIDAYS else None

    def today(self) -> dt.date:
        return dt_util.now().date()

    # -- lifecycle -------------------------------------------------------------------
    async def async_load(self) -> None:
        try:
            self.data = storage.from_dict(await self._store.async_load())
        except ValueError as err:
            raise ConfigEntryError(translation_domain=DOMAIN, translation_key="store_unreadable",
                                   translation_placeholders={"error": str(err)}) from err
        rooms = {area_id: room for area_id, room in self.data.rooms.items() if room.ever_assigned}
        if len(rooms) != len(self.data.rooms):   # written by versions that let a rule alone create a room
            self.data = replace(self.data, rooms=rooms)
            await self._store.async_save(storage.to_dict(self.data))
        await self._async_public_holidays()
        self._rebuild()
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
        if self._unsub_started is not None:
            self._unsub_started()
            self._unsub_started = None

    async def _at_midnight(self, _now: dt.datetime) -> None:
        await self._async_public_holidays()      # a new year may have entered the kept span
        self._rebuild()

    async def _daily_check(self, _now: dt.datetime) -> None:
        await self.async_refresh_school_holidays()

    async def _on_started(self, _event: Any) -> None:
        self._unsub_started = None          # a one-time listener removes itself; unsubscribing it again logs an error
        await self._startup_fetch()

    async def _startup_fetch(self, _event: Any = None) -> None:
        await self.async_refresh_school_holidays()

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

    def _school_holidays(self) -> SchoolHolidays:
        cache = self.data.school_holidays
        if self.source == SOURCE_NONE:
            return SchoolHolidays(attribution=None)
        if cache is None or cache.source != self.source or cache.known_from is None or cache.known_to is None:
            return SchoolHolidays(known_from=dt.date.max, known_to=dt.date.max, attribution=self.attribution)
        return sources.school_holidays_from_periods(cache.periods, cache.known_from, cache.known_to, self.attribution)

    @callback
    def _rebuild(self) -> None:
        extra, removed = self.holiday_corrections()
        calendar = Calendar(self._public_holidays, self._school_holidays(), self.weekend, extra, removed)
        self.household = Household(calendar, self.data.residents, self.data.rooms, self.house, self.data.exceptions)
        self._check_registry_issues()
        self._notify()

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
               severity: ir.IssueSeverity = ir.IssueSeverity.WARNING) -> None:
        if active:
            ir.async_create_issue(self.hass, DOMAIN, issue_id, is_fixable=False, severity=severity,
                                  translation_key=issue_id, translation_placeholders=placeholders)
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
                             short_name: str | None = None) -> None:
        residents = dict(self.data.residents)
        current = residents.get(person_id)
        if current is None:
            current = Resident(person_id, short_name or self.propose_short_name(person_id), History(),
                               order=len(residents))
        if short_name:
            self._check_short_name(person_id, short_name)
            current = replace(current, short_name=short_name)
        residents[person_id] = replace(current, roles=current.roles.with_step(valid_from, role))
        await self._async_commit(replace(self.data, residents=residents))

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
        """Personal days off every week from a date on; ``None`` returns the person to the household weekend."""
        resident = self.data.residents.get(person_id)
        if resident is None:
            raise WerktagsError("not_resident")
        if weekdays is not None and not all(0 <= d <= 6 for d in weekdays):
            raise WerktagsError("weekdays_range")
        history = History() if weekdays is None else resident.off_weekdays.with_step(valid_from, frozenset(weekdays))
        residents = {**self.data.residents, person_id: replace(resident, off_weekdays=history)}
        await self._async_commit(replace(self.data, residents=residents))

    async def async_set_house(self, person_ids: Iterable[str] | None, valid_from: dt.date) -> None:
        """Residents that count for the house from a date on; ``None`` returns to the role-based default."""
        history: History[frozenset[str]]
        if person_ids is None:
            history = History()
        else:
            ids = frozenset(person_ids)
            unknown = [pid for pid in ids if pid not in self.data.residents]
            if unknown:
                raise WerktagsError("not_residents", persons=", ".join(sorted(unknown)))
            history = self.data.house_residents.with_step(valid_from, ids)
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
    def cache_is_fresh(self) -> bool:
        cache = self.data.school_holidays
        if cache is None or cache.fetched_at is None or cache.source != self.source:
            return False
        return dt_util.utcnow() - cache.fetched_at < dt.timedelta(days=FETCH_INTERVAL_DAYS)

    async def async_refresh_school_holidays(self, force: bool = False) -> bool:
        """Fetch school holidays if due (or ``force``). Returns whether new data arrived."""
        if self.source == SOURCE_NONE or self._fetching or (not force and self.cache_is_fresh()):
            return False
        self._fetching = True
        try:
            periods = await self._fetch_periods()
        except FetchFailed as err:
            if not self._source_down:
                _LOGGER.warning("School holidays could not be fetched from %s: %s", self.source, err)
                self._source_down = True
            periods = None
        finally:
            self._fetching = False

        old = self.data.school_holidays or SchoolHolidayCache(self.source)
        if periods is None:
            cache = replace(old, source=self.source, failures=old.failures + 1)
        else:
            if self._source_down:
                _LOGGER.info("School holidays from %s are available again", self.source)
                self._source_down = False
            first, last = sources.fetch_span(self.today())
            known_to = min(last, max((p.end for p in periods), default=first))
            # earlier years are not fetched again: keep what the same source told us about them
            kept = tuple(p for p in old.periods if p.end < first) if old.source == self.source else ()
            contiguous = bool(kept) and old.known_from is not None and old.known_to is not None \
                and old.known_to >= first - dt.timedelta(days=1)
            known_from = old.known_from if contiguous else first
            cache = SchoolHolidayCache(self.source, kept + tuple(periods), known_from, known_to, dt_util.utcnow(), 0)
        await self._async_commit(replace(self.data, school_holidays=cache))
        self._issue(ISSUE_SCHOOL_HOLIDAYS_UNREACHABLE, cache.failures >= MAX_FETCH_FAILURES,
                    {"source": self.source, "failures": str(cache.failures)})
        self._check_completeness()
        return periods is not None

    def _check_completeness(self) -> None:
        """From October, next year's summer holidays must be known (specification 5.5)."""
        today = self.today()
        cache = self.data.school_holidays
        needed = dt.date(today.year + 1, 8, 31)
        incomplete = (self.source != SOURCE_NONE and today.month >= 10
                      and (cache is None or cache.known_to is None or cache.known_to < needed))
        known_to = cache.known_to.isoformat() if cache and cache.known_to else "-"
        self._issue(ISSUE_SCHOOL_HOLIDAYS_INCOMPLETE, incomplete, {"year": str(today.year + 1), "known_to": known_to})

    async def _fetch_periods(self) -> list[SchoolHolidayPeriod]:
        first, last = sources.fetch_span(self.today())
        if self.source == SOURCE_OPENHOLIDAYS:
            client = OpenHolidaysClient(async_get_clientsession(self.hass), user_agent=USER_AGENT)
            try:
                holidays = await client.school_holidays(self.country, self.subdivision, first, last)
            except OpenHolidaysError as err:
                raise FetchFailed(str(err)) from err
            # the year after next may not be published yet; this year and next must be complete
            if not is_plausible(holidays, [self.today().year, self.today().year + 1]):
                raise FetchFailed("answer not plausible (missing summer holidays)")
            language = (self.hass.config.language or "en").split("-")[0].upper()
            return [SchoolHolidayPeriod(h.start, h.end, h.name(language)) for h in holidays]
        if self.source == SOURCE_CALENDAR and self.calendar_entity:
            try:
                return await self._fetch_from_calendar(self.calendar_entity, first, last)
            except Exception as err:  # noqa: BLE001 — a calendar integration may raise anything
                raise FetchFailed(str(err)) from err
        raise FetchFailed(f"no school holiday source configured ({self.source})")

    async def _fetch_from_calendar(self, entity_id: str, first: dt.date, last: dt.date) -> list[SchoolHolidayPeriod]:
        tz = dt_util.get_default_time_zone()
        response: Any = await self.hass.services.async_call(
            "calendar", "get_events",
            {"entity_id": entity_id, "start_date_time": dt.datetime.combine(first, dt.time(), tz).isoformat(),
             "end_date_time": dt.datetime.combine(last + dt.timedelta(days=1), dt.time(), tz).isoformat()},
            blocking=True, return_response=True,
        )
        events = (response or {}).get(entity_id, {}).get("events", []) if isinstance(response, dict) else []
        periods = []
        for event in events:
            start, end = str(event.get("start", "")), str(event.get("end", ""))
            if len(start) != 10 or len(end) != 10:
                continue                       # only all-day events count as school holidays
            end_date = dt.date.fromisoformat(end) - dt.timedelta(days=1)    # calendar ends are exclusive
            periods.append(SchoolHolidayPeriod(dt.date.fromisoformat(start), end_date, str(event.get("summary", ""))))
        return sorted(periods, key=lambda p: p.start)

    # -- read-outs for services and cards ----------------------------------------------
    def status(self) -> dict[str, Any]:
        cache = self.data.school_holidays
        return {
            "country": self.country, "subdivision": self.subdivision, "weekend": sorted(self.weekend),
            "school_holiday_source": self.source, "attribution": self.attribution,
            "school_holidays": None if cache is None or cache.source != self.source else {
                "fetched_at": cache.fetched_at.isoformat() if cache.fetched_at else None,
                "known_from": cache.known_from.isoformat() if cache.known_from else None,
                "known_to": cache.known_to.isoformat() if cache.known_to else None,
                "periods": len(cache.periods), "failures": cache.failures,
            },
        }
