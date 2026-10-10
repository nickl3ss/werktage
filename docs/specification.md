# Werktags — Specification

**Status:** implemented (released as 0.2.x, quality scale Platinum) ·
**Version:** 3 (2026-10-10) — all open questions decided (P21–P34)

Werktags tells Home Assistant, **per person**, whether a day is a workday or a
day off. From that it derives a **morning mode** (*workday* / *day off*) and an
**evening mode** (*before a workday* / *before a day off*) for every person,
every room and the whole house. Automations use these modes, for example to
open a bedroom shutter at 07:00 on workdays and at 10:00 otherwise.

This document is the product specification. It contains no data of any
particular household; examples use fictitious people (Anna, Ben, Clara).

---

## 1. Scope

Werktags consists of three parts that live in this repository and can later be
split without changes:

| Part | Content | Later |
|---|---|---|
| **Library** `openholidays` (`lib/`) | client for the OpenHolidays API, no Home Assistant dependency | own package on PyPI |
| **Integration** `werktage` (`custom_components/werktage/`) | rules, entities, services, setup | candidate for Home Assistant core |
| **Cards** (`frontend/`) | calendar, date range, residents, rooms | own HACS repository (category *Dashboard*) |

It is an **integration**, not an *app* (formerly *add-on*): it runs inside Home
Assistant, provides entities and services and works on every installation
type.

## 2. Product decisions

| No. | Topic | Decision |
|---|---|---|
| P1 | Who is a resident? | A Home Assistant **person** with a role |
| P2 | Roles | `pupil` or `adult`, each **valid from** a date; `none` removes the person from that date |
| P3 | Default days off | Weekend (configurable, default Sat + Sun) and public holidays for everyone; **school holidays for pupils only** |
| P4 | Exceptions | Per person and day, **both directions**: `day_off` and `workday` (e.g. an early start on a Saturday) |
| P5 | Unknown days | A day without data (e.g. school holidays not yet available) counts **as a workday**, with `reason: unknown` — better on time than late |
| P6 | Day boundary | **Midnight**, in the Home Assistant time zone |
| P7 | Rooms | Home Assistant **areas** with residents assigned, **valid from** a date; a person may belong to several rooms |
| P8 | Room rules | Configurable per room: in the **morning the resident with a day off wins** (anyone off → *day off*), in the **evening the resident who works tomorrow wins** (anyone working tomorrow → *before a workday*) |
| P9 | House | All residents with one of the **house roles** (default `adult`) on that day, with the same kind of rules |
| P10 | Granularity | Whole days only |
| P11 | Past days | May be changed |
| P12 | Editing rights | All users by default; option *administrators only* |
| P13 | Notifications | Repair issues in the UI only, no push notifications |
| P14 | Setup | Config flow and options, **no YAML** |
| P15 | UI | Dashboard cards only — **no custom panel, no custom WebSocket API**; cards use entities and services with response |
| P16 | Code language | English identifiers, keys, comments and logs; German and English UI through translations |
| P17 | School holiday sources | OpenHolidays API, a calendar entity, or none |
| P18 | Checkbox meaning | In the calendar card **checked = day off**; tapping *All* when everybody is off sets **everybody to workday** |
| P19 | Calendar range | Five weeks starting with the current week, paged week by week |
| P20 | Date ranges | Own card: `day_off` · `workday` · `default`, people, from–to; applies to **every day** in the range, including weekends and public holidays |
| P21 | Entities | **Two sensors** per resident, room and house (`morning`, `evening`) plus a read-only calendar per resident; no separate workday binary sensors |
| P22 | Role key for pupils | `pupil` (displayed *Pupil* / *Schüler*) |
| P23 | School holidays | **One school holiday calendar per installation**, shared by all pupils; individual school days off are exceptions |
| P24 | School on Saturdays | Not supported; the weekend is the same for everyone; single school Saturdays are exceptions |
| P25 | Christmas Eve, New Year's Eve | Workdays unless they are public holidays in the subdivision |
| P26 | Exceptions on role or room change | **Kept** — exceptions belong to person and day |
| P27 | Change log | **None** — only the current state is stored |
| P28 | Editing the past | Single days without confirmation; past role and room steps ask for confirmation |
| P29 | Weekly pattern per person | A resident may have personal days off every week (history, `valid_from`); they **replace** the household weekend for that person. Exceptions still win. |
| P30 | Residents of the house | Explicitly chosen residents (history); empty means everyone with a house role as before |
| P31 | Holiday corrections | Settings: added holidays (`YYYY-MM-DD [name]`) and removed ones (date or part of the name); an added holiday counts as a public holiday, a removed one as an ordinary day |
| P32 | Binary sensors and blueprints | `binary_sensor.<x>_workday` next to the enum sensors; two blueprints for the common morning/evening automations |
| P33 | Public holidays fail at midnight | The error is logged and the day still changes with the holidays already known; sensors never keep yesterday's date (see P5: missing data is never silently a day off) |
| P34 | Library version | `lib/openholidays` carries its own version, which only changes with the library; the integration's `manifest.json` version is what the User-Agent reports |

## 3. Rules

### 3.1 Default day type

| | role `adult` | role `pupil` |
|---|---|---|
| weekend (household, or the person's weekly pattern, P29) | day off | day off |
| public holiday of the configured subdivision, corrected per P31 | day off | day off |
| school holiday | workday | **day off** |
| otherwise | workday | workday |

The role that applies is the role **on that day** (3.4).

### 3.2 Effective day of a person

    effective(person, day) = exception(person, day)  if present
                           = default(person, day)    otherwise

- Only exceptions are stored. An exception equal to the default is deleted
  instead of stored.
- Unknown days count as workdays (P5), centrally in the integration, so
  automations never see `unknown`.

### 3.3 Modes

    morning(day) = workday         if effective(day) is a workday, else day_off
    evening(day) = before_workday  if effective(day + 1) is a workday, else before_day_off

Rooms and the house combine their residents on that day:

| Setting | Values | Default |
|---|---|---|
| `morning_rule` | `day_off_wins` · `workday_wins` | `day_off_wins` |
| `evening_rule` | `workday_wins` · `day_off_wins` | `workday_wins` |

Example with defaults — room of Anna and Ben:

| Anna today | Ben today | morning | | Anna tomorrow | Ben tomorrow | evening |
|---|---|---|---|---|---|---|
| workday | workday | workday | | off | off | before_day_off |
| off | workday | **day_off** | | off | workday | **before_workday** |
| off | off | day_off | | workday | workday | before_workday |

A room without residents on a day counts as workday (P5).

### 3.4 History of roles and rooms

Roles and room assignments are sequences of steps `(valid_from, value)`. Each
day uses the step valid on it, so a change today never rewrites the past. A
step may lie in the past (P11); the UI asks for confirmation. Exceptions are
independent of roles and rooms.

## 4. Data sources

| What | Source | Behaviour |
|---|---|---|
| Public holidays | `holidays` library (shipped with Home Assistant), country and subdivision from setup | offline |
| School holidays | OpenHolidays API · calendar entity · none | see below |

**OpenHolidays API:** fetched at startup if the cache is older than 30 days,
otherwise monthly; 15 s timeout, own `User-Agent`; range: **this year and the
two following years** (`sources.fetch_span`). The API accepts at most 1095
days per request, so the client splits longer ranges into consecutive windows
(three calendar years with a leap year are 1096 days). Earlier years are not
fetched again; their periods stay in the cache as long as the source is the
same. The setup dialog probes the API with the very same range. A result
replaces the cache only if it is plausible. The data is licensed under
**ODbL 1.0**: attribution in the UI, the documentation and the entities'
`attribution`; no holiday data is stored in this repository (see NOTICE).

**Calendar entity:** every all-day event of the selected calendar is a school
holiday.

## 5. Integration

### 5.1 Setup (config flow, options)

| Step | Field | Default |
|---|---|---|
| 1 | country, subdivision | from `hass.config.country` |
| 1 | weekend days | Sat, Sun |
| 1 | added holidays, removed holidays | none |
| 2 | school holiday source, calendar entity | OpenHolidays if the country is covered, otherwise none |
| 3 | house roles, house rules | `adult`, `day_off_wins`, `workday_wins` |
| 3 | who may edit | all users |

One config entry per installation (`single_config_entry`). The options flow
opens a menu: the settings steps above (the entry reloads afterwards) or a
form for a resident (role, short name, weekly days off, valid from), a room
(area, residents, rules) or the residents of the house — written straight
into the store so no dashboard card is needed.

### 5.2 Store

Residents with roles, rooms with assignments and rules, exceptions and the
school holiday cache. No change log (P27). Keys are the internal ids of
persons and areas, stable across renames. Versioned with migrations.

### 5.3 Devices and entities

One service device per resident, per room and for the house. Room devices are
named after their area but **not placed in it**: Home Assistant builds entity
ids from area, device and entity name by default, and a device named like its
area would yield `sensor.bedroom_bedroom_morning` instead of
`sensor.bedroom_morning`. Names via `translation_key`; entity ids follow the
installation language.

| Entity (English installation) | States | Attributes |
|---|---|---|
| `sensor.anna_morning` | `workday` · `day_off` | `reason` (`weekend`, `public_holiday`, `school_holiday`, `exception_day_off`, `exception_workday`, `workday`, `unknown`), `holiday_name`, `role`, `next_workday`, `next_day_off` |
| `sensor.anna_evening` | `before_workday` · `before_day_off` | as above, for tomorrow |
| `calendar.anna_days_off` | on when today is a day off | read-only, days off as all-day events |
| `binary_sensor.anna_workday` | `on` on a workday | `reason`, `holiday_name`; also per room and for the house |
| `sensor.<room>_morning`, `sensor.<room>_evening` | as above | `residents`, `rule` |
| `sensor.house_morning`, `sensor.house_evening` | as above | `residents`, `rule` |

- `device_class: enum`, translated states. Every entity carries the
  `attribution` of the school holiday source.
- `unique_id` = `<entry_id>_<person_id|area_id|house>_<key>`.
- New residents and rooms get their entities immediately, without restart.
  Removed ones become `unavailable`; the device can be deleted.
- Updated at midnight, after every change and after every fetch.

### 5.4 Services

| Service | Fields | Effect |
|---|---|---|
| `werktage.set_days` | `person` (one or more), `start`, `end`, `status` (`day_off`/`workday`/`default`) | exceptions for a day or range |
| `werktage.set_role` | `person`, `role` (`pupil`/`adult`/`none`), `valid_from`, `short_name` | adds a role step |
| `werktage.remove_role` | `person`, `valid_from` | removes a role step |
| `werktage.set_room` | `area`, `person` (several), `valid_from`, `morning_rule`, `evening_rule` | adds an assignment step or sets rules |
| `werktage.remove_room_assignment` | `area`, `valid_from` | removes an assignment step |
| `werktage.set_weekly` | `person`, `weekdays` (0 = Monday), `valid_from`, `household` | personal days off every week; `household` returns to the household weekend |
| `werktage.set_house` | `person` (several), `valid_from`, `by_role` | residents that count for the house; `by_role` or no persons returns to the roles |
| `werktage.get_days` | `start`, `weeks` | **returns** per day and resident: effective, default, exception, reason, holiday names, role |
| `werktage.preview_days` | as `set_days` | **returns** the days that would change |
| `werktage.get_overview` | — | **returns** all persons, areas, roles, assignments and source status |
| `werktage.refresh_school_holidays` | — | fetches now |

Read services use `SupportsResponse.ONLY`. Writing checks the permission
option (P12). Every rejected change raises a `ServiceValidationError` with its
own translation key (`exceptions` in `strings.json`); the coordinator raises
`WerktagsError(key, **placeholders)`, the service layer translates it. A test
checks that every key used in the code is translated in English and German.

### 5.5 Repairs and diagnostics

Repair issues for: school holidays not reachable three times, holidays
missing for the current or next year (from 1 October), deleted person or area
still in use, country not covered by OpenHolidays. Diagnostics without names.

## 6. Cards

`custom:werktags-calendar`, `-period`, `-residents`, `-rooms`, each with a
visual editor. They read through entities and services only. Source in
`frontend/src` (pure logic separated from the elements), bundled without a
build system into one classic script. In the HACS
version the integration serves them itself (`frontend.py`, `add_extra_js_url`,
versioned URL); later they move to their own repository.

- **Calendar:** five week rows Mon–Sun from the current week; each day shows
  the date, *All* and one toggle per resident (short name); weekends and
  public holidays shaded with the holiday name, school holidays outlined,
  exceptions highlighted. Below 600 px one row per day.
- **Period:** status, people, from–to, preview, apply; at most 366 days.
- **Residents:** all persons, short name, role today, new role from date,
  weekday chips for personal days off (with a reset to the household
  weekend), history, order. Changes are applied with one button and ask
  before touching the past.
- **Rooms:** all areas, residents as chips, rules, change from date, history;
  the house row is edited the same way (empty = by role).

The README provides a ready-made dashboard with the four cards.

## 7. Quality

- Tests with `pytest-homeassistant-custom-component`; the rules as pure
  functions with one test per rule; browserless tests for the cards.
- `hassfest`, HACS validation and tests in `.github/workflows/ci.yml`;
  `mypy --strict`. hassfest runs locally from a sparse checkout of
  `home-assistant/core` (`script/hassfest`, `script/translations`,
  `script/util`) with the venv's Python and ruff on the path.
- `custom_components/werktage/quality_scale.yaml` records every rule.
  Bronze is complete; `brands` is met by the local brand images (`brand/`),
  which Home Assistant 2026.3 and later load for custom integrations (the
  brands repository no longer takes them). The scale is **Platinum**: Silver
  and Gold are complete (coverage 99 %, documentation,
  translated errors), and so are the Platinum rules — the only network
  dependency is asyncio and gets Home Assistant's session, the synchronous
  `holidays` library runs in the executor everywhere (a test checks the
  config flow), `mypy --strict` in CI.
- `tools/check_publication.py` before every commit: no private household data.

## 8. Path to Home Assistant core

- API code lives in the library (required by core).
- No custom frontend served by the core version; cards stay community cards.
- First submission small (`sensor` only), documentation PR alongside.
- Discuss the concept first in an architecture discussion: how it differs from
  `workday` (per person, school holidays, room rules).
- A smaller early contribution: school holidays as a source for the core
  `holiday` integration.

## 9. Open questions

None. The former questions Q1–Q8 are decided as P21–P28.
