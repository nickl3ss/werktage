"""What the integration persists, and how it is (de)serialized.

Pure functions between the rules' data types and JSON-ready dicts. The Home
Assistant ``Store`` only loads and saves the dict. Keys are the internal ids of
persons and areas (stable across renames). Versioned: ``migrate`` upgrades
older layouts.
"""
from __future__ import annotations

import datetime as dt
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from .rules import CombineRule, DayType, History, Resident, Role, Room, Step
from .sources import SchoolHolidayPeriod

DATA_VERSION = 1


@dataclass(frozen=True, slots=True)
class SchoolHolidayCache:
    source: str                                   # "openholidays" | "calendar" | "none"
    periods: tuple[SchoolHolidayPeriod, ...] = ()
    known_from: dt.date | None = None
    known_to: dt.date | None = None
    fetched_at: dt.datetime | None = None
    failures: int = 0                             # consecutive failed fetches


@dataclass(frozen=True, slots=True)
class StoredData:
    residents: dict[str, Resident] = field(default_factory=dict)
    rooms: dict[str, Room] = field(default_factory=dict)
    exceptions: dict[dt.date, dict[str, DayType]] = field(default_factory=dict)
    school_holidays: SchoolHolidayCache | None = None


# --- to JSON ------------------------------------------------------------------

def _history_to_list(history: History[Any], encode: Any) -> list[dict[str, Any]]:
    return [{"valid_from": s.valid_from.isoformat(), "value": encode(s.value)} for s in history.steps]


def _history_from_list(items: list[dict[str, Any]], decode: Any) -> History[Any]:
    return History(tuple(Step(dt.date.fromisoformat(i["valid_from"]), decode(i["value"])) for i in items))


def to_dict(data: StoredData) -> dict[str, Any]:
    cache = data.school_holidays
    return {
        "version": DATA_VERSION,
        "residents": {
            rid: {"short_name": r.short_name, "order": r.order,
                  "roles": _history_to_list(r.roles, lambda role: role.value)}
            for rid, r in sorted(data.residents.items())
        },
        "rooms": {
            aid: {"morning_rule": room.morning_rule.value, "evening_rule": room.evening_rule.value,
                  "residents": _history_to_list(room.residents, lambda ids: sorted(ids))}
            for aid, room in sorted(data.rooms.items())
        },
        "exceptions": {
            day.isoformat(): {rid: value.value for rid, value in sorted(per_day.items())}
            for day, per_day in sorted(data.exceptions.items()) if per_day
        },
        "school_holidays": None if cache is None else {
            "source": cache.source,
            "periods": [p.as_dict() for p in cache.periods],
            "known_from": cache.known_from.isoformat() if cache.known_from else None,
            "known_to": cache.known_to.isoformat() if cache.known_to else None,
            "fetched_at": cache.fetched_at.isoformat() if cache.fetched_at else None,
            "failures": cache.failures,
        },
    }


# --- from JSON -------------------------------------------------------------------

def _date_or_none(value: Any) -> dt.date | None:
    return dt.date.fromisoformat(value) if value else None


def from_dict(raw: Mapping[str, Any] | None) -> StoredData:
    """Build ``StoredData`` from a stored dict; ``None`` or ``{}`` gives empty data."""
    if not raw:
        return StoredData()
    raw = migrate(dict(raw))
    residents = {
        rid: Resident(rid, str(r.get("short_name", "")), _history_from_list(r.get("roles", []), Role),
                      int(r.get("order", 0)))
        for rid, r in raw.get("residents", {}).items()
    }
    rooms = {
        aid: Room(aid, _history_from_list(room.get("residents", []), frozenset),
                  CombineRule(room.get("morning_rule", CombineRule.DAY_OFF_WINS.value)),
                  CombineRule(room.get("evening_rule", CombineRule.WORKDAY_WINS.value)))
        for aid, room in raw.get("rooms", {}).items()
    }
    exceptions = {
        dt.date.fromisoformat(day): {rid: DayType(value) for rid, value in per_day.items()}
        for day, per_day in raw.get("exceptions", {}).items() if per_day
    }
    cache_raw = raw.get("school_holidays")
    cache = None if not cache_raw else SchoolHolidayCache(
        source=str(cache_raw.get("source", "none")),
        periods=tuple(SchoolHolidayPeriod.from_dict(p) for p in cache_raw.get("periods", [])),
        known_from=_date_or_none(cache_raw.get("known_from")),
        known_to=_date_or_none(cache_raw.get("known_to")),
        fetched_at=dt.datetime.fromisoformat(cache_raw["fetched_at"]) if cache_raw.get("fetched_at") else None,
        failures=int(cache_raw.get("failures", 0)),
    )
    return StoredData(residents, rooms, exceptions, cache)


def migrate(raw: dict[str, Any]) -> dict[str, Any]:
    """Upgrade older layouts in place. Version 1 is the first; nothing to do yet."""
    version = int(raw.get("version", DATA_VERSION))
    if version > DATA_VERSION:
        raise ValueError(f"stored data version {version} is newer than supported {DATA_VERSION}")
    raw["version"] = DATA_VERSION
    return raw
