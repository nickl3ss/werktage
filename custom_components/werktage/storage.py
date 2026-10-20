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

DATA_VERSION = 3
INSTALLATION_KEY = "_installation"      # placeholder key of a migrated single cache (see migrate)


@dataclass(frozen=True, slots=True)
class SchoolHolidayCache:
    source: str                                   # the source key, e.g. "openholidays:DE-NW" (sources.make_source_key)
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
    school_holidays: dict[str, SchoolHolidayCache] = field(default_factory=dict)   # per source key (version 3, #1)
    house_residents: History[frozenset[str] | None] = field(default_factory=History)   # version 2; None steps: 3


# --- to JSON ------------------------------------------------------------------

def _history_to_list(history: History[Any], encode: Any) -> list[dict[str, Any]]:
    return [{"valid_from": s.valid_from.isoformat(), "value": encode(s.value)} for s in history.steps]


def _history_from_list(items: list[dict[str, Any]], decode: Any) -> History[Any]:
    return History(tuple(Step(dt.date.fromisoformat(i["valid_from"]), decode(i["value"])) for i in items))


def _cache_to_dict(cache: SchoolHolidayCache) -> dict[str, Any]:
    return {
        "source": cache.source,
        "periods": [p.as_dict() for p in cache.periods],
        "known_from": cache.known_from.isoformat() if cache.known_from else None,
        "known_to": cache.known_to.isoformat() if cache.known_to else None,
        "fetched_at": cache.fetched_at.isoformat() if cache.fetched_at else None,
        "failures": cache.failures,
    }


def _cache_from_dict(cache_raw: Mapping[str, Any]) -> SchoolHolidayCache:
    return SchoolHolidayCache(
        source=str(cache_raw.get("source", "none")),
        periods=tuple(SchoolHolidayPeriod.from_dict(p) for p in cache_raw.get("periods", [])),
        known_from=_date_or_none(cache_raw.get("known_from")),
        known_to=_date_or_none(cache_raw.get("known_to")),
        fetched_at=dt.datetime.fromisoformat(cache_raw["fetched_at"]) if cache_raw.get("fetched_at") else None,
        failures=int(cache_raw.get("failures", 0)),
    )


def to_dict(data: StoredData) -> dict[str, Any]:
    return {
        "version": DATA_VERSION,
        "residents": {
            rid: {"short_name": r.short_name, "order": r.order, "school_holiday_source": r.school_holiday_source,
                  "roles": _history_to_list(r.roles, lambda role: role.value),
                  "off_weekdays": _history_to_list(r.off_weekdays, lambda days: None if days is None else sorted(days))}
            for rid, r in sorted(data.residents.items())
        },
        "house": {"residents": _history_to_list(data.house_residents,
                                                lambda ids: None if ids is None else sorted(ids))},
        "rooms": {
            aid: {"morning_rule": room.morning_rule.value, "evening_rule": room.evening_rule.value,
                  "residents": _history_to_list(room.residents, lambda ids: sorted(ids))}
            for aid, room in sorted(data.rooms.items())
        },
        "exceptions": {
            day.isoformat(): {rid: value.value for rid, value in sorted(per_day.items())}
            for day, per_day in sorted(data.exceptions.items()) if per_day
        },
        "school_holidays": {key: _cache_to_dict(cache) for key, cache in sorted(data.school_holidays.items())},
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
                      int(r.get("order", 0)),
                      _history_from_list(r.get("off_weekdays", []),
                                         lambda days: None if days is None else frozenset(int(d) for d in days)),
                      school_holiday_source=r.get("school_holiday_source") or None)
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
    caches = {str(key): _cache_from_dict(cache_raw) for key, cache_raw in (raw.get("school_holidays") or {}).items()}
    house_residents = _history_from_list(raw.get("house", {}).get("residents", []),
                                         lambda ids: None if ids is None else frozenset(ids))
    return StoredData(residents, rooms, exceptions, caches, house_residents)


def migrate(raw: dict[str, Any]) -> dict[str, Any]:
    """Upgrade older layouts in place.

    1 → 2: residents gain ``off_weekdays`` (empty = household weekend), the
    house gains an explicit resident assignment (empty = by role). Both are
    optional keys, so version 1 data reads unchanged.
    2 → 3: a step of ``off_weekdays`` or ``house.residents`` may hold ``null``
    (back to the household default from that date on); older data never
    contains ``null``. ``school_holidays`` becomes a map source key → cache
    (#1); the single cache of older data moves under the key ``_installation``,
    which the coordinator renames to the installation's source once it knows
    the configuration. Residents may carry ``school_holiday_source``.
    """
    version = int(raw.get("version", DATA_VERSION))
    if version > DATA_VERSION:
        raise ValueError(f"stored data version {version} is newer than supported {DATA_VERSION}")
    cache = raw.get("school_holidays")
    if isinstance(cache, dict) and "periods" in cache:                 # version ≤ 2: one cache, no key
        raw["school_holidays"] = {INSTALLATION_KEY: cache}
    elif cache is None:
        raw["school_holidays"] = {}
    raw["version"] = DATA_VERSION
    return raw
