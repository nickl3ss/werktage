"""Data sources feeding the rules: public holidays (offline) and school holidays (cached).

Public holidays come from the ``holidays`` library that Home Assistant ships
for its ``workday`` and ``holiday`` integrations. School holidays arrive from
outside (OpenHolidays API or a calendar entity) and are kept here as plain
periods, so this module needs no network and no Home Assistant.
"""
from __future__ import annotations

import datetime as dt
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

import holidays as holidays_lib

from .rules import DEFAULT_WEEKEND, Calendar, SchoolHolidays

YEARS_BACK = 1      # public holidays are computed from January of last year …
YEARS_AHEAD = 2     # … to December of the year after next


def year_span(today: dt.date) -> tuple[dt.date, dt.date]:
    """The date range the integration keeps data for (specification section 4)."""
    return dt.date(today.year - YEARS_BACK, 1, 1), dt.date(today.year + YEARS_AHEAD, 12, 31)


def fetch_span(today: dt.date) -> tuple[dt.date, dt.date]:
    """The three calendar years fetched every month: this year and the two after.

    Earlier years stay in the cache from former fetches; they no longer change.
    """
    return dt.date(today.year, 1, 1), dt.date(today.year + YEARS_AHEAD, 12, 31)


def public_holidays(country: str, subdivision: str | None, years: Iterable[int],
                    language: str | None = None) -> dict[dt.date, str]:
    """Public holidays of a country/subdivision by date, named in ``language`` if available.

    ``subdivision`` is the bare code the ``holidays`` library uses (``"NW"``),
    not the ISO form (``"DE-NW"``); ``subdivision_code`` converts.
    """
    year_list = list(years)
    try:
        table = holidays_lib.country_holidays(country, subdiv=subdivision or None, years=year_list, language=language)
    except (NotImplementedError, TypeError):
        # unsupported language for this country → default names
        table = holidays_lib.country_holidays(country, subdiv=subdivision or None, years=year_list)
    return {day: str(name) for day, name in sorted(table.items())}


def subdivision_code(country: str, iso_subdivision: str | None) -> str | None:
    """``"DE-NW"`` → ``"NW"`` for the ``holidays`` library; ``None`` stays ``None``."""
    if not iso_subdivision:
        return None
    prefix = f"{country}-"
    return iso_subdivision[len(prefix):] if iso_subdivision.startswith(prefix) else iso_subdivision


def supported_subdivisions(country: str) -> list[str]:
    """Subdivision codes the ``holidays`` library knows for a country (bare form)."""
    try:
        return list(holidays_lib.country_holidays(country).subdivisions)
    except NotImplementedError:
        return []


def subdivision_names(country: str) -> dict[str, str]:
    """Bare code → display name, as the ``workday`` integration shows them; code if no name is known."""
    try:
        table = holidays_lib.country_holidays(country)
    except NotImplementedError:
        return {}
    aliases = table.get_subdivision_aliases() if table.subdivisions_aliases else {}
    return {code: ", ".join(aliases.get(code) or []) or code for code in table.subdivisions}


def supported_countries() -> list[str]:
    """ISO 3166-1 alpha-2 codes the ``holidays`` library supports (it also lists the alpha-3 aliases)."""
    return sorted(code for code in holidays_lib.list_supported_countries(include_aliases=False) if len(code) == 2)


def supports_country(country: str) -> bool:
    return country in holidays_lib.list_supported_countries()


@dataclass(frozen=True, slots=True)
class SchoolHolidayPeriod:
    start: dt.date
    end: dt.date
    name: str

    def as_dict(self) -> dict[str, str]:
        return {"start": self.start.isoformat(), "end": self.end.isoformat(), "name": self.name}

    @classmethod
    def from_dict(cls, data: dict[str, str]) -> SchoolHolidayPeriod:
        return cls(dt.date.fromisoformat(data["start"]), dt.date.fromisoformat(data["end"]), str(data["name"]))


def school_holidays_from_periods(periods: Sequence[SchoolHolidayPeriod], known_from: dt.date,
                                 known_to: dt.date, attribution: str | None) -> SchoolHolidays:
    return SchoolHolidays(tuple((p.start, p.end, p.name) for p in periods), known_from, known_to, attribution)


def build_calendar(country: str, subdivision: str | None, today: dt.date, *,
                   school_holidays: SchoolHolidays, weekend: frozenset[int] = DEFAULT_WEEKEND,
                   language: str | None = None) -> Calendar:
    """The calendar for the rules: public holidays for the kept year span plus school holidays."""
    first, last = year_span(today)
    return Calendar(
        public_holidays=public_holidays(country, subdivision_code(country, subdivision),
                                        range(first.year, last.year + 1), language),
        school_holidays=school_holidays,
        weekend=weekend,
    )
