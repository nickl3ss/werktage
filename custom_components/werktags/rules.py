"""Rules of Werktags: which day is a workday for whom, and what follows from it.

Pure functions and small immutable data types, no Home Assistant imports.
Section numbers refer to docs/specification.md.

    default_day  (3.1)  weekend / public holiday / school holiday by role
    effective_day (3.2) exception before default; unknown counts as workday
    morning/evening modes (3.3) for persons, rooms and the house
    History (3.4)       steps "valid from", one lookup per day
"""
from __future__ import annotations

import datetime as dt
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from enum import StrEnum

ONE_DAY = dt.timedelta(days=1)
SEARCH_LIMIT_DAYS = 400   # next_workday / next_day_off give up after this


class Role(StrEnum):
    PUPIL = "pupil"
    ADULT = "adult"
    NONE = "none"


class DayType(StrEnum):
    WORKDAY = "workday"
    DAY_OFF = "day_off"


class Reason(StrEnum):
    """Why a day is what it is; exposed as the ``reason`` attribute."""

    WORKDAY = "workday"
    WEEKEND = "weekend"
    PUBLIC_HOLIDAY = "public_holiday"
    SCHOOL_HOLIDAY = "school_holiday"
    EXCEPTION_DAY_OFF = "exception_day_off"
    EXCEPTION_WORKDAY = "exception_workday"
    UNKNOWN = "unknown"


class MorningMode(StrEnum):
    WORKDAY = "workday"
    DAY_OFF = "day_off"


class EveningMode(StrEnum):
    BEFORE_WORKDAY = "before_workday"
    BEFORE_DAY_OFF = "before_day_off"


class CombineRule(StrEnum):
    """How a room or the house combines its residents (3.3)."""

    DAY_OFF_WINS = "day_off_wins"
    WORKDAY_WINS = "workday_wins"


DEFAULT_MORNING_RULE = CombineRule.DAY_OFF_WINS
DEFAULT_EVENING_RULE = CombineRule.WORKDAY_WINS
DEFAULT_WEEKEND = frozenset({5, 6})          # Saturday, Sunday (date.weekday())
DEFAULT_HOUSE_ROLES = frozenset({Role.ADULT})


# --- History: values valid from a date (3.4) ----------------------------------

@dataclass(frozen=True, slots=True)
class Step[T]:
    valid_from: dt.date
    value: T


@dataclass(frozen=True, slots=True)
class History[T]:
    """Ordered steps ``(valid_from, value)``; the last step on or before a day applies.

    Before the first step there is no value (``None``). A change made today never
    rewrites the past: every day keeps the step that was valid on it.
    """

    steps: tuple[Step[T], ...] = ()

    def __post_init__(self) -> None:
        dates = [s.valid_from for s in self.steps]
        if dates != sorted(dates) or len(set(dates)) != len(dates):
            raise ValueError("history steps must be sorted by date and unique")

    def value_on(self, day: dt.date) -> T | None:
        value: T | None = None
        for step in self.steps:
            if step.valid_from > day:
                break
            value = step.value
        return value

    def with_step(self, valid_from: dt.date, value: T) -> History[T]:
        """Copy with a step added; a step on the same date is replaced."""
        kept = tuple(s for s in self.steps if s.valid_from != valid_from)
        return History(tuple(sorted((*kept, Step(valid_from, value)), key=lambda s: s.valid_from)))

    def without_step(self, valid_from: dt.date) -> History[T]:
        return History(tuple(s for s in self.steps if s.valid_from != valid_from))

    @property
    def first_date(self) -> dt.date | None:
        return self.steps[0].valid_from if self.steps else None


# --- Calendar: the data every rule needs -------------------------------------

@dataclass(frozen=True, slots=True)
class SchoolHolidays:
    """School holiday periods and the range of days they are known for.

    Days outside ``known_from``..``known_to`` are *unknown* (3.2). A source
    ``none`` is represented by no periods and an unlimited known range.
    """

    periods: tuple[tuple[dt.date, dt.date, str], ...] = ()
    known_from: dt.date = dt.date.min
    known_to: dt.date = dt.date.max
    attribution: str | None = None

    def name_on(self, day: dt.date) -> str | None:
        for start, end, name in self.periods:
            if start <= day <= end:
                return name
        return None

    def is_known(self, day: dt.date) -> bool:
        return self.known_from <= day <= self.known_to


@dataclass(frozen=True, slots=True)
class Calendar:
    """Everything that applies to all persons alike: weekend and holidays."""

    public_holidays: Mapping[dt.date, str] = field(default_factory=dict)
    school_holidays: SchoolHolidays = field(default_factory=SchoolHolidays)
    weekend: frozenset[int] = DEFAULT_WEEKEND


# --- Day of one person (3.1, 3.2) --------------------------------------------

@dataclass(frozen=True, slots=True)
class DayInfo:
    """The effective day of one person, with the reason."""

    day_type: DayType
    reason: Reason
    holiday_name: str | None = None
    role: Role | None = None

    @property
    def is_workday(self) -> bool:
        return self.day_type is DayType.WORKDAY

    @property
    def is_known(self) -> bool:
        return self.reason is not Reason.UNKNOWN


def default_day(role: Role, day: dt.date, calendar: Calendar) -> DayInfo:
    """Section 3.1: weekend and public holidays for everyone, school holidays for pupils.

    Order matters only for the reason: a public holiday on a weekend is reported
    as ``public_holiday``, a public holiday inside school holidays likewise.
    """
    if holiday := calendar.public_holidays.get(day):
        return DayInfo(DayType.DAY_OFF, Reason.PUBLIC_HOLIDAY, holiday, role)
    if day.weekday() in calendar.weekend:
        return DayInfo(DayType.DAY_OFF, Reason.WEEKEND, None, role)
    if role is Role.PUPIL:
        if not calendar.school_holidays.is_known(day):
            return DayInfo(DayType.WORKDAY, Reason.UNKNOWN, None, role)
        if name := calendar.school_holidays.name_on(day):
            return DayInfo(DayType.DAY_OFF, Reason.SCHOOL_HOLIDAY, name, role)
    return DayInfo(DayType.WORKDAY, Reason.WORKDAY, None, role)


def effective_day(role: Role, day: dt.date, calendar: Calendar,
                  exception: DayType | None = None) -> DayInfo:
    """Section 3.2: an exception replaces the default; unknown days count as workdays."""
    default = default_day(role, day, calendar)
    if exception is None:
        return default
    reason = Reason.EXCEPTION_DAY_OFF if exception is DayType.DAY_OFF else Reason.EXCEPTION_WORKDAY
    return DayInfo(exception, reason, default.holiday_name, role)


def normalize_exception(role: Role, day: dt.date, calendar: Calendar,
                        wanted: DayType | None) -> DayType | None:
    """The exception to *store* for a wanted day type: ``None`` if it equals the default.

    Section 3.2: an exception equal to the default is deleted instead of stored.
    An unknown default is treated as a workday here, so wanting a workday on an
    unknown day stores nothing and wanting a day off stores ``day_off``.
    """
    if wanted is None:
        return None
    default = default_day(role, day, calendar)
    return None if default.day_type is wanted else wanted


# --- Modes (3.3) ----------------------------------------------------------------

def morning_mode(today: DayInfo) -> MorningMode:
    return MorningMode.WORKDAY if today.is_workday else MorningMode.DAY_OFF


def evening_mode(tomorrow: DayInfo) -> EveningMode:
    return EveningMode.BEFORE_WORKDAY if tomorrow.is_workday else EveningMode.BEFORE_DAY_OFF


def combine(days: Sequence[DayInfo], rule: CombineRule) -> DayInfo:
    """Combine the days of several residents into one (3.3).

    ``day_off_wins``: a single day off makes the group's day a day off.
    ``workday_wins``: a single workday makes it a workday.
    No residents at all: unknown, which counts as a workday (P5).
    """
    if not days:
        return DayInfo(DayType.WORKDAY, Reason.UNKNOWN)
    wins = DayType.DAY_OFF if rule is CombineRule.DAY_OFF_WINS else DayType.WORKDAY
    for info in days:
        if info.day_type is wins:
            return info
    return days[0]


# --- Household: residents, rooms, exceptions ----------------------------------

@dataclass(frozen=True, slots=True)
class Resident:
    id: str                      # person id from Home Assistant
    short_name: str
    roles: History[Role] = field(default_factory=History)
    order: int = 0

    def role_on(self, day: dt.date) -> Role | None:
        role = self.roles.value_on(day)
        return None if role is None or role is Role.NONE else role


@dataclass(frozen=True, slots=True)
class Room:
    id: str                      # area id from Home Assistant
    residents: History[frozenset[str]] = field(default_factory=History)
    morning_rule: CombineRule = DEFAULT_MORNING_RULE
    evening_rule: CombineRule = DEFAULT_EVENING_RULE

    def residents_on(self, day: dt.date) -> frozenset[str]:
        return self.residents.value_on(day) or frozenset()


@dataclass(frozen=True, slots=True)
class House:
    roles: frozenset[Role] = DEFAULT_HOUSE_ROLES
    morning_rule: CombineRule = DEFAULT_MORNING_RULE
    evening_rule: CombineRule = DEFAULT_EVENING_RULE


Exceptions = Mapping[dt.date, Mapping[str, DayType]]


@dataclass(frozen=True, slots=True)
class Household:
    """All data the rules need, plus the lookups the integration asks for."""

    calendar: Calendar
    residents: Mapping[str, Resident] = field(default_factory=dict)
    rooms: Mapping[str, Room] = field(default_factory=dict)
    house: House = field(default_factory=House)
    exceptions: Exceptions = field(default_factory=dict)

    # -- one person -------------------------------------------------------
    def exception_for(self, resident_id: str, day: dt.date) -> DayType | None:
        return self.exceptions.get(day, {}).get(resident_id)

    def day_of(self, resident_id: str, day: dt.date) -> DayInfo | None:
        """The effective day of a resident, or ``None`` without a role on that day."""
        resident = self.residents.get(resident_id)
        if resident is None or (role := resident.role_on(day)) is None:
            return None
        return effective_day(role, day, self.calendar, self.exception_for(resident_id, day))

    def default_of(self, resident_id: str, day: dt.date) -> DayInfo | None:
        resident = self.residents.get(resident_id)
        if resident is None or (role := resident.role_on(day)) is None:
            return None
        return default_day(role, day, self.calendar)

    def next_day(self, resident_id: str, start: dt.date, workday: bool) -> dt.date | None:
        """First day after ``start`` that is a workday (or a day off); ``None`` if not found."""
        day = start
        for _ in range(SEARCH_LIMIT_DAYS):
            day += ONE_DAY
            info = self.day_of(resident_id, day)
            if info is not None and info.is_workday is workday:
                return day
        return None

    # -- groups -------------------------------------------------------------
    def _days_of(self, resident_ids: Iterable[str], day: dt.date) -> list[DayInfo]:
        infos = (self.day_of(rid, day) for rid in sorted(resident_ids))
        return [info for info in infos if info is not None]

    def room_day(self, room_id: str, day: dt.date, *, evening: bool = False) -> DayInfo:
        room = self.rooms[room_id]
        rule = room.evening_rule if evening else room.morning_rule
        return combine(self._days_of(room.residents_on(day), day), rule)

    def house_residents_on(self, day: dt.date) -> list[str]:
        return sorted(rid for rid, r in self.residents.items() if r.role_on(day) in self.house.roles)

    def house_day(self, day: dt.date, *, evening: bool = False) -> DayInfo:
        rule = self.house.evening_rule if evening else self.house.morning_rule
        return combine(self._days_of(self.house_residents_on(day), day), rule)

    # -- modes as the entities show them -------------------------------------
    def resident_modes(self, resident_id: str, today: dt.date) -> tuple[MorningMode, EveningMode] | None:
        now, tomorrow = self.day_of(resident_id, today), self.day_of(resident_id, today + ONE_DAY)
        if now is None:
            return None
        return morning_mode(now), evening_mode(tomorrow or DayInfo(DayType.WORKDAY, Reason.UNKNOWN))

    def room_modes(self, room_id: str, today: dt.date) -> tuple[MorningMode, EveningMode]:
        return (morning_mode(self.room_day(room_id, today)),
                evening_mode(self.room_day(room_id, today + ONE_DAY, evening=True)))

    def house_modes(self, today: dt.date) -> tuple[MorningMode, EveningMode]:
        return (morning_mode(self.house_day(today)),
                evening_mode(self.house_day(today + ONE_DAY, evening=True)))

    # -- changes: return a new household -------------------------------------
    def with_exceptions(self, resident_ids: Iterable[str], start: dt.date, end: dt.date,
                        wanted: DayType | None) -> Household:
        """Set (or with ``None`` clear) exceptions for every day in ``start``..``end``.

        Days whose default already equals ``wanted`` get no exception (3.2).
        Residents without a role on a day are skipped.
        """
        if end < start:
            raise ValueError("end before start")
        exceptions: dict[dt.date, dict[str, DayType]] = {d: dict(v) for d, v in self.exceptions.items()}
        day = start
        while day <= end:
            for rid in resident_ids:
                resident = self.residents.get(rid)
                role = resident.role_on(day) if resident else None
                if role is None:
                    continue
                stored = normalize_exception(role, day, self.calendar, wanted)
                per_day = exceptions.setdefault(day, {})
                if stored is None:
                    per_day.pop(rid, None)
                else:
                    per_day[rid] = stored
            if not exceptions.get(day):
                exceptions.pop(day, None)
            day += ONE_DAY
        return replace(self, exceptions=exceptions)

    def changes_for(self, resident_ids: Iterable[str], start: dt.date, end: dt.date,
                    wanted: DayType | None) -> dict[str, int]:
        """Preview: how many days per resident would change (card *Period*)."""
        after = self.with_exceptions(resident_ids, start, end, wanted)
        counts: dict[str, int] = {}
        for rid in resident_ids:
            changed = 0
            day = start
            while day <= end:
                before, later = self.day_of(rid, day), after.day_of(rid, day)
                if before is not None and later is not None and before.day_type is not later.day_type:
                    changed += 1
                day += ONE_DAY
            counts[rid] = changed
        return counts
