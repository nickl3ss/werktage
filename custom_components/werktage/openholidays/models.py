"""Data types of the OpenHolidays API and pure parsing functions.

Nothing here touches the network, so it can be tested with plain JSON.
"""
from __future__ import annotations

import datetime as dt
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from .errors import InvalidResponse

MIN_HOLIDAY_BLOCK_DAYS = 28   # a year of school holidays without a block this long is implausible


def _localized(items: Any, field: str) -> dict[str, str]:
    """``[{"language": "DE", "text": "…"}, …]`` → ``{"DE": "…"}``."""
    if not isinstance(items, list):
        raise InvalidResponse(f"{field}: expected a list of localized texts")
    result: dict[str, str] = {}
    for item in items:
        if not isinstance(item, dict) or "language" not in item or "text" not in item:
            raise InvalidResponse(f"{field}: localized text without language or text")
        result[str(item["language"]).upper()] = str(item["text"])
    return result


def _pick(names: Mapping[str, str], language: str | None) -> str:
    """The text in ``language``, else English, else the first one."""
    if language and (text := names.get(language.upper())):
        return text
    return names.get("EN") or next(iter(names.values()), "")


def _date(value: Any, field: str) -> dt.date:
    try:
        return dt.date.fromisoformat(str(value))
    except ValueError as err:
        raise InvalidResponse(f"{field}: not an ISO date: {value!r}") from err


@dataclass(frozen=True, slots=True)
class Holiday:
    id: str
    start: dt.date
    end: dt.date
    names: Mapping[str, str]          # language code → name
    type: str                         # "Public", "School", …
    nationwide: bool
    subdivisions: tuple[str, ...]     # subdivision codes, empty if nationwide

    def name(self, language: str | None = None) -> str:
        return _pick(self.names, language)

    @property
    def days(self) -> int:
        return (self.end - self.start).days + 1

    def covers(self, day: dt.date) -> bool:
        return self.start <= day <= self.end


@dataclass(frozen=True, slots=True)
class Subdivision:
    code: str                         # e.g. "DE-NW"
    names: Mapping[str, str]

    def name(self, language: str | None = None) -> str:
        return _pick(self.names, language)


@dataclass(frozen=True, slots=True)
class Country:
    code: str                         # ISO 3166-1 alpha-2, e.g. "DE"
    names: Mapping[str, str]

    def name(self, language: str | None = None) -> str:
        return _pick(self.names, language)


def parse_holidays(data: Any) -> list[Holiday]:
    """Parse the JSON of ``/SchoolHolidays`` or ``/PublicHolidays``."""
    if not isinstance(data, list):
        raise InvalidResponse("holidays: expected a list")
    holidays = []
    for item in data:
        if not isinstance(item, dict):
            raise InvalidResponse("holidays: expected objects")
        try:
            start = _date(item["startDate"], "startDate")
            end = _date(item["endDate"], "endDate")
            names = _localized(item["name"], "name")
        except KeyError as err:
            raise InvalidResponse(f"holidays: missing field {err}") from err
        if end < start:
            raise InvalidResponse(f"holidays: endDate before startDate ({item.get('id')})")
        subdivisions = tuple(str(s["code"]) for s in item.get("subdivisions") or []
                             if isinstance(s, dict) and "code" in s)
        holidays.append(Holiday(str(item.get("id", "")), start, end, names, str(item.get("type", "")),
                                bool(item.get("nationwide", False)), subdivisions))
    return sorted(holidays, key=lambda h: (h.start, h.end, h.id))


def parse_subdivisions(data: Any) -> list[Subdivision]:
    """Parse the JSON of ``/Subdivisions``."""
    if not isinstance(data, list):
        raise InvalidResponse("subdivisions: expected a list")
    result = []
    for item in data:
        if not isinstance(item, dict) or "code" not in item:
            raise InvalidResponse("subdivisions: object without code")
        result.append(Subdivision(str(item["code"]), _localized(item.get("name", []), "name")))
    return result


def parse_countries(data: Any) -> list[Country]:
    """Parse the JSON of ``/Countries``."""
    if not isinstance(data, list):
        raise InvalidResponse("countries: expected a list")
    result = []
    for item in data:
        if not isinstance(item, dict) or "isoCode" not in item:
            raise InvalidResponse("countries: object without isoCode")
        result.append(Country(str(item["isoCode"]), _localized(item.get("name", []), "name")))
    return result


def is_plausible(holidays: Iterable[Holiday], years: Iterable[int]) -> bool:
    """Whether a school holiday result is complete enough to replace a cached one.

    Every requested year must contain at least one block of
    ``MIN_HOLIDAY_BLOCK_DAYS`` consecutive days (the summer holidays). A partial
    or empty answer — an API in trouble — must never overwrite good data.
    """
    holidays = list(holidays)
    for year in years:
        if not any(h.days >= MIN_HOLIDAY_BLOCK_DAYS and (h.start.year == year or h.end.year == year) for h in holidays):
            return False
    return True
