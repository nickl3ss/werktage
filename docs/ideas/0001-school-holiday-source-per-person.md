# 0001 — School holiday source per person

**Status:** idea, not planned · **Opened:** 2026-09-30 · **Area:** integration, cards

## Problem

School holidays are configured once per installation (P23): one source, one
country and subdivision, shared by every pupil. A pupil who attends school in
another subdivision (commuting across a state border, a boarding school) or a
school with its own calendar gets the wrong days off. Today the only way out
is to enter the differences as exceptions, day by day or via the period card.

## Proposal

Give each resident an optional **school holiday source** that overrides the
installation's default:

| Value | Meaning |
|---|---|
| *(unset)* | as the installation (default, today's behaviour) |
| `openholidays:<country>-<subdivision>` | another subdivision from the OpenHolidays API, e.g. `DE-HE` |
| `calendar:<entity_id>` | a calendar entity whose all-day events are school holidays |

Public holidays stay per installation: they follow the place of residence,
not the place of school.

## Changes

- **Store:** `residents[<id>].school_holiday_source` (string or null);
  `school_holidays` becomes a map `source key → cache` instead of one cache.
  Migration: the existing cache moves under the installation's key.
- **Rules:** `Calendar` gets `school_holidays_for(source_key)`; `default_day`
  takes the resident's source key. Unknown days per source (P5 unchanged).
- **Coordinator:** fetch and plausibility check per distinct source, still one
  request per source per month; repair issues name the source.
- **Services:** `set_role` gains an optional `school_holiday_source` field;
  `get_overview` returns it per person; `get_days` reports the school holiday
  name per person instead of per day (a day may be a holiday for one pupil
  only).
- **Cards:** residents card gets a column with a select (installation default,
  the subdivisions of the configured country, calendar entities); calendar
  card marks school holidays per toggle rather than per cell.
- **Options flow:** unchanged.

## Notes

- Data license: every additional OpenHolidays source carries the same ODbL
  attribution; nothing changes there.
- Estimated size: small — one field, one map, one column. Can be added later
  without losing data.
