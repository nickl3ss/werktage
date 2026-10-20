"""Export of days off into a shared calendar (#3, P37): what should be there, what is, what to do.

Pure: no Home Assistant imports. The coordinator reads the target calendar's
events, hands them to :func:`plan` and executes the result through the calendar
entity. Events the integration wrote carry a marker in their description, so it
never touches anything else; this is an export, not a synchronisation.
"""
from __future__ import annotations

import datetime as dt
import hashlib
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from .rules import ONE_DAY, Household, Reason

MARKER = "werktage:"      # description = "werktage:<person key>/<date>"


def person_key(person_id: str) -> str:
    """A stable stand-in for the person id in the shared calendar: the id itself never leaves Home Assistant."""
    return hashlib.sha256(person_id.encode()).hexdigest()[:12]

_LABELS = {
    "en": {Reason.WEEKEND: "Weekend", Reason.EXCEPTION_DAY_OFF: "Day off", Reason.CALENDAR_DAY_OFF: "Day off",
           Reason.SCHOOL_HOLIDAY: "School holidays", Reason.PUBLIC_HOLIDAY: "Public holiday"},
    "de": {Reason.WEEKEND: "Wochenende", Reason.EXCEPTION_DAY_OFF: "Frei", Reason.CALENDAR_DAY_OFF: "Frei",
           Reason.SCHOOL_HOLIDAY: "Schulferien", Reason.PUBLIC_HOLIDAY: "Feiertag"},
}


def reason_label(reason: Reason, language: str | None) -> str:
    """Title for a day off without a holiday name, in the installation's language."""
    table = _LABELS.get((language or "en").split("-")[0].lower(), _LABELS["en"])
    return table.get(reason, reason.value.replace("_", " "))


@dataclass(frozen=True, slots=True)
class WantedEvent:
    key: str                  # "<person_id>/<date>"
    day: dt.date
    summary: str

    @property
    def description(self) -> str:
        return f"{MARKER}{self.key}"


@dataclass(frozen=True, slots=True)
class OwnEvent:
    """An event in the target calendar that the integration wrote earlier."""

    uid: str
    key: str
    summary: str


def key_of(description: str | None) -> str | None:
    """The export key of an event we wrote, ``None`` for anything else."""
    if description and description.startswith(MARKER):
        return description[len(MARKER):].strip() or None
    return None


def wanted_events(household: Household, resident_ids: Iterable[str], names: Mapping[str, str], first: dt.date,
                  last: dt.date, include_weekends: bool, language: str | None) -> dict[str, WantedEvent]:
    """One event per resident and day off in ``first``..``last``; unknown days never (P5).

    Without ``include_weekends`` the days of the household weekend are left out
    (they would flood the calendar); a personal weekly pattern (P29) is a day
    off worth telling and is always exported.
    """
    wanted: dict[str, WantedEvent] = {}
    household_weekend = household.calendar.weekend
    for resident_id in resident_ids:
        day = first
        while day <= last:
            info = household.day_of(resident_id, day)
            weekend = info is not None and info.reason is Reason.WEEKEND and day.weekday() in household_weekend
            if info is not None and not info.is_workday and info.is_known and (include_weekends or not weekend):
                key = f"{person_key(resident_id)}/{day.isoformat()}"
                label = info.holiday_name or reason_label(info.reason, language)
                wanted[key] = WantedEvent(key, day, f"{names.get(resident_id, resident_id)}: {label}")
            day += ONE_DAY
    return wanted


def plan(wanted: Mapping[str, WantedEvent], existing: Iterable[OwnEvent]) -> tuple[list[WantedEvent], list[OwnEvent]]:
    """``(to create, to delete)``: missing or changed events are created, stale or changed ones deleted."""
    present: dict[str, OwnEvent] = {}
    to_delete: list[OwnEvent] = []
    for event in existing:
        target = wanted.get(event.key)
        if target is None or target.summary != event.summary or event.key in present:
            to_delete.append(event)                       # no longer true, renamed, or a duplicate
        else:
            present[event.key] = event
    to_create = [event for key, event in sorted(wanted.items()) if key not in present]
    return to_create, to_delete
