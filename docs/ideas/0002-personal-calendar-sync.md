# 0002 — Personal calendars as a source of days off

**Status:** idea, not planned · **Opened:** 2026-09-30 · **Area:** integration, cards

## Problem

Vacations, days off, business trips and school events already live in
personal calendars (Google, CalDAV, Nextcloud, Outlook via Home Assistant's
calendar integrations). Today they have to be typed a second time as
exceptions, either day by day or through the period card. The integration
only uses a calendar for the shared school holidays.

## Proposal

Let every resident have an optional **absence calendar**: a calendar entity
whose all-day events become `day_off` exceptions. Optionally, a second,
opposite calendar for **extra workdays** (Saturday shifts, school on a
Saturday). Events with a time (not all-day) are ignored, as with school
holidays.

| Per resident | Meaning |
|---|---|
| `days_off_calendar` | all-day events → day off |
| `workdays_calendar` | all-day events → workday (rarer; optional) |
| keyword filter (optional) | only events whose title matches, e.g. "Urlaub", "frei", "off" |

Calendar days are a third layer between default and manual exception:

    effective = manual exception ?? calendar ?? default

A manual exception still wins, so a day can be corrected without editing the
calendar.

## Changes

- **Store:** per resident the two entity ids and the keyword; a cache of
  calendar days per resident (like the school holiday cache) with the range it
  covers.
- **Coordinator:** read the calendars once a day and after the calendar
  entity changes state (`async_track_state_change_event`), for the kept year
  span; `calendar.get_events` as today. Unknown range → default (not unknown
  as for school holidays, because a missing calendar should not turn every
  day into a workday).
- **Rules:** `DayInfo.reason` gets `calendar_day_off` / `calendar_workday`.
- **Services:** `set_role` (or a new `set_calendar`) takes the entity ids and
  keyword; `get_days` reports the source of a day.
- **Cards:** calendar card marks calendar days differently from manual
  exceptions (dotted outline); residents card gets the two selectors.
- **Docs:** README section "Calendars" with the three most common setups
  (Google shared family calendar, Nextcloud, ICS via Remote Calendar).

## Notes

- The reverse direction exists already: `calendar.<name>_days_off` exposes
  every resident's days off to dashboards and automations.
- Combines well with idea 0001 (school holiday source per person): both add
  a per-resident calendar entity, so they should share the UI.
- Not in scope: writing back into personal calendars.
