"""School holidays per source (#1, #16): fetch, keep each source's cache fresh, raise and clear the hints.

A source is a key (``openholidays:DE-NW``, ``calendar:<entity>``; ``sources.make_source_key``).
OpenHolidays is reached only through the bundled library (P34), a calendar only through
``calendars.py``. At most one fetch per source in ``FETCH_INTERVAL_DAYS``; a failed fetch
keeps the old periods, and ``MAX_FETCH_FAILURES`` in a row raise a repair hint. The
coordinator owns the store: ``SchoolHolidayFetcher`` reads the caches from it and
commits new ones through it.
"""
from __future__ import annotations

import datetime as dt
import logging
from dataclasses import replace
from typing import TYPE_CHECKING

from homeassistant.core import HomeAssistant
from homeassistant.helpers import translation
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.util import dt as dt_util

from . import calendars, sources
from .const import (
    ATTRIBUTION_OPENHOLIDAYS,
    DOMAIN,
    FETCH_INTERVAL_DAYS,
    ISSUE_SCHOOL_HOLIDAYS_INCOMPLETE,
    ISSUE_SCHOOL_HOLIDAYS_UNREACHABLE,
    MAX_FETCH_FAILURES,
    SOURCE_CALENDAR,
    SOURCE_NONE,
    SOURCE_OPENHOLIDAYS,
    USER_AGENT,
)
from .openholidays import OpenHolidaysClient, OpenHolidaysError, is_plausible
from .rules import SchoolHolidays
from .sources import SchoolHolidayPeriod
from .storage import SchoolHolidayCache

if TYPE_CHECKING:
    from .coordinator import WerktagsCoordinator

_LOGGER = logging.getLogger(__name__)


class FetchFailed(Exception):
    """A school holiday fetch did not yield usable data."""


def attribution_for(key: str) -> str | None:
    """The licence note a source requires: OpenHolidays (ODbL 1.0); a calendar needs none."""
    return ATTRIBUTION_OPENHOLIDAYS if key.startswith(f"{SOURCE_OPENHOLIDAYS}:") else None


async def async_probe_openholidays(hass: HomeAssistant, country: str, subdivision: str | None) -> int:
    """How many school holiday periods the API has for this year (setup check). Raises ``OpenHolidaysError``."""
    client = OpenHolidaysClient(async_get_clientsession(hass), user_agent=USER_AGENT)
    first, last = sources.fetch_span(dt_util.now().date())      # the very range the integration fetches later
    return len(await client.school_holidays(country, subdivision, first, last))


async def async_source_options(hass: HomeAssistant, country: str) -> list[dict[str, str]]:
    """Choices for a resident's source: the installation's, every region of the country, every calendar."""
    texts = await translation.async_get_translations(hass, hass.config.language, "selector", {DOMAIN})
    options = [{"value": "", "label": texts.get(
        f"component.{DOMAIN}.selector.school_holiday_source.options.installation", "")}]          # #15
    names = await hass.async_add_executor_job(sources.subdivision_names, country)   # invariant 10
    options += [{"value": f"{SOURCE_OPENHOLIDAYS}:{country}-{code}", "label": name}
                for code, name in sorted(names.items(), key=lambda item: item[1])]
    options += [{"value": f"{SOURCE_CALENDAR}:{c['entity_id']}", "label": c["name"]}
                for c in calendars.foreign_calendars(hass)]
    return options


class SchoolHolidayFetcher:
    """The coordinator's part for school holidays: one cache and one pair of repair hints per source in use."""

    def __init__(self, coordinator: WerktagsCoordinator) -> None:
        self._c = coordinator
        self._fetching = False
        self._down: set[str] = set()          # log-when-unavailable per source: one line down, one up

    def school_holidays(self, key: str) -> SchoolHolidays:
        """The rules' view of a source; unknown everywhere until its first fetch (P5)."""
        if key == SOURCE_NONE:
            return SchoolHolidays(attribution=None)
        cache = self._c.data.school_holidays.get(key)
        if cache is None or cache.known_from is None or cache.known_to is None:
            return SchoolHolidays(known_from=dt.date.max, known_to=dt.date.max, attribution=attribution_for(key))
        return sources.school_holidays_from_periods(cache.periods, cache.known_from, cache.known_to,
                                                    attribution_for(key))

    def is_fresh(self, key: str) -> bool:
        cache = self._c.data.school_holidays.get(key)
        if cache is None or cache.fetched_at is None:
            return False
        return dt_util.utcnow() - cache.fetched_at < dt.timedelta(days=FETCH_INTERVAL_DAYS)

    async def async_refresh(self, force: bool = False) -> bool:
        """Fetch every source in use that is due (or all with ``force``). Returns whether new data arrived."""
        if self._fetching:
            return False
        self._fetching = True
        try:
            arrived = False
            for key in self._c.source_keys():
                if force or not self.is_fresh(key):
                    arrived = await self._refresh_source(key) or arrived
            await self._prune()
        finally:
            self._fetching = False
        return arrived

    async def _refresh_source(self, key: str) -> bool:
        c = self._c
        try:
            periods = await self._fetch_periods(key)
        except FetchFailed as err:
            if key not in self._down:
                _LOGGER.warning("School holidays could not be fetched from %s: %s", key, err)
                self._down.add(key)
            periods = None

        old = c.data.school_holidays.get(key) or SchoolHolidayCache(key)
        if periods is None:
            cache = replace(old, source=key, failures=old.failures + 1)
        else:
            if key in self._down:
                _LOGGER.info("School holidays from %s are available again", key)
                self._down.discard(key)
            first, last = sources.fetch_span(c.today())
            known_to = min(last, max((p.end for p in periods), default=first))
            # earlier years are not fetched again: keep what the same source told us about them
            kept = tuple(p for p in old.periods if p.end < first)
            contiguous = bool(kept) and old.known_from is not None and old.known_to is not None \
                and old.known_to >= first - dt.timedelta(days=1)
            known_from = old.known_from if contiguous else first
            cache = SchoolHolidayCache(key, kept + tuple(periods), known_from, known_to, dt_util.utcnow(), 0)
        await c.async_commit(replace(c.data, school_holidays={**c.data.school_holidays, key: cache}))
        c.set_issue(self._issue_id(ISSUE_SCHOOL_HOLIDAYS_UNREACHABLE, key), cache.failures >= MAX_FETCH_FAILURES,
                    {"source": key, "failures": str(cache.failures)}, translation_key=ISSUE_SCHOOL_HOLIDAYS_UNREACHABLE)
        self.check_completeness()
        return periods is not None

    async def _prune(self) -> None:
        """Drop the caches (and hints) of sources nobody uses any more."""
        c = self._c
        unused = set(c.data.school_holidays) - set(c.source_keys())
        if not unused:
            return
        for key in unused:
            for base in (ISSUE_SCHOOL_HOLIDAYS_UNREACHABLE, ISSUE_SCHOOL_HOLIDAYS_INCOMPLETE):
                c.set_issue(self._issue_id(base, key), False)
        await c.async_commit(replace(c.data, school_holidays={
            key: cache for key, cache in c.data.school_holidays.items() if key not in unused}))

    def _issue_id(self, base: str, key: str) -> str:
        """The installation's source keeps the plain id; a resident's source gets its own."""
        return base if key == self._c.source_key else f"{base}_{key}"

    def check_completeness(self) -> None:
        """From October, next year's summer holidays must be known for every source in use (specification 5.5)."""
        c = self._c
        today = c.today()
        needed = dt.date(today.year + 1, 8, 31)
        for key in c.source_keys():
            cache = c.data.school_holidays.get(key)
            incomplete = today.month >= 10 and (cache is None or cache.known_to is None or cache.known_to < needed)
            known_to = cache.known_to.isoformat() if cache and cache.known_to else "-"
            c.set_issue(self._issue_id(ISSUE_SCHOOL_HOLIDAYS_INCOMPLETE, key), incomplete,
                        {"year": str(today.year + 1), "known_to": known_to, "source": key},
                        translation_key=ISSUE_SCHOOL_HOLIDAYS_INCOMPLETE)
        if c.source == SOURCE_NONE:
            c.set_issue(ISSUE_SCHOOL_HOLIDAYS_INCOMPLETE, False)

    async def _fetch_periods(self, key: str) -> list[SchoolHolidayPeriod]:
        c = self._c
        first, last = sources.fetch_span(c.today())
        source, parameter = sources.parse_source_key(key)
        if source == SOURCE_OPENHOLIDAYS and parameter:
            country, _, subdivision = parameter.partition("-")
            client = OpenHolidaysClient(async_get_clientsession(c.hass), user_agent=USER_AGENT)
            try:
                holidays = await client.school_holidays(country, parameter if subdivision else None, first, last)
            except OpenHolidaysError as err:
                raise FetchFailed(str(err)) from err
            # the year after next may not be published yet; this year and next must be complete
            if not is_plausible(holidays, [c.today().year, c.today().year + 1]):
                raise FetchFailed("answer not plausible (missing summer holidays)")
            language = (c.hass.config.language or "en").split("-")[0].upper()
            return [SchoolHolidayPeriod(h.start, h.end, h.name(language)) for h in holidays]
        if source == SOURCE_CALENDAR and parameter:
            try:
                return await calendars.async_school_holiday_periods(c.hass, parameter, first, last)
            except Exception as err:  # noqa: BLE001 — a calendar integration may raise anything
                raise FetchFailed(str(err)) from err
        raise FetchFailed(f"no school holiday source configured ({key})")
