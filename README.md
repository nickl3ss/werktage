# Werktags

**Workdays per person for Home Assistant** — weekends, public holidays and
school holidays by default, exceptions per person and day, and morning/evening
modes for people, rooms and the whole house.

> **Status: 0.2.0.** Integration and cards are tested against Home Assistant
> 2026.1 (minimum) and 2026.9 and run in a household. Ideas and bugs:
> [issues](https://github.com/nickl3ss/werktage/issues).

## What it does

- One Home Assistant **person** = one resident with a **role**
  (*pupil* or *adult*), valid from a date.
- **Default days off:** weekends and public holidays for everyone, school
  holidays for pupils. Country and subdivision are chosen during setup.
- **Exceptions** per person and day in both directions: an extra day off, or
  a workday on a day that would otherwise be free.
- **Personal weekly pattern** per person (part-time, four-day week): days off
  every week that replace the household weekend, valid from a date.
- **Holiday corrections** in the settings: extra holidays (bridge days,
  company holidays) and public holidays that do not apply.
- **Rooms** are Home Assistant areas with residents assigned, valid from a
  date. The **house** follows chosen residents or, by default, everyone with
  a house role.
- Per resident, room and house three entities:
  - **morning** — `workday` / `day_off` (today);
  - **evening** — `before_workday` / `before_day_off` (tomorrow);
  - **workday** — a binary sensor for conditions and blueprints.
- Dashboard cards: calendar, date range, residents, rooms — or the same
  without cards through the integration's options menu.

## Use cases

- **Shutters and curtains that respect who sleeps in.** A child's room opens
  at 09:00 on school days and at noon on weekends and during school holidays.
- **Lights for the early riser.** The stairs light comes on at 05:30 as soon
  as one adult has to work — and stays off when everybody is off.
- **A later evening before a day off.** Switch things off at 22:00 before a
  workday and at 23:00 before a day off; the evening sensors look at tomorrow.
- **Part-time and shift patterns.** A four-day week is a weekly pattern;
  a day of leave, a sick child or a Saturday shift is one tap in the calendar
  card.
- **Heating, wake-up alarms, presence simulation** — anything that today
  asks "is it a workday?" and gets the same answer for the whole household.

How it differs from the built-in *Workday* integration: Workday answers once
for the whole installation and knows weekends and public holidays. Werktags
answers **per person**, adds school holidays, personal exceptions and weekly
patterns, and combines people into rooms and the house by a rule you choose.

## Installation

> **Upgrading from 0.1.0:** the domain changed from `werktags` to
> `werktage` (a HACS bug mangles any download path containing `tags/`).
> Remove the old *Werktags* entry under *Devices & services*, install
> 0.2.0, set it up again and re-create residents, rooms and exceptions —
> or call `werktage.set_role`, `set_room`, `set_days` from a copy of the old
> `.storage/werktags.data`. Entity ids and the dashboard cards stay the same.
> The card script moved from `/werktags_static/` to `/werktage_static/`: a
> Companion app that still holds the old page shows *Configuration error* on
> every card, even after pulling to refresh — clear its frontend cache once
> (*Settings → Companion app → Troubleshooting*).

Requires Home Assistant 2026.1 or newer.

1. **With HACS** (recommended):

   [![Open your Home Assistant instance and open this repository in HACS.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=nickl3ss&repository=werktage&category=integration)

   Or in HACS: *⋮ → Custom repositories*, add
   `https://github.com/nickl3ss/werktage` with type *Integration*. Then
   download *Werktags* and restart Home Assistant.

   **Manually:** copy `custom_components/werktage/` into the
   `custom_components/` folder of your Home Assistant configuration (or run
   `./deploy.sh <config dir>`), and restart Home Assistant.
2. *Settings → Devices & services → Add integration → Werktags*. Five short
   steps; every field can be changed later under *Configure → Settings*.

   | Step | Field | Meaning | Default |
   |---|---|---|---|
   | Country | Country | Public holidays and, with OpenHolidays, school holidays of this country | the Home Assistant country |
   | Region | Subdivision | Regional public holidays and school holidays; empty = nationwide holidays only | — |
   | Region | Weekend days | Days off for everyone, every week | Saturday, Sunday |
   | Region | Additional holidays | One per line: `YYYY-MM-DD` optionally followed by a name (bridge days, company holidays) | — |
   | Region | Holidays that do not apply | One per line: a date or part of a holiday name | — |
   | School holidays | Source | *OpenHolidays API* (tested before the entry is created), a *calendar* entity, or *none* | OpenHolidays if the country is covered |
   | School holidays | Calendar | The calendar whose events are school holidays (source *calendar*) | — |
   | House | Roles that count for the house | Whose days make the house modes unless residents are chosen explicitly | adult |
   | House | Morning rule, evening rule | *Day off wins* or *workday wins* when residents disagree | day off wins, workday wins |
   | Access | Only administrators may change data | Cards and services refuse writes from other users | off |

3. Add residents: either with the dashboard cards below or via
   *Werktags → Configure*, which offers a menu:

   | Menu item | Fields |
   |---|---|
   | Settings | the five steps above, prefilled; the integration reloads afterwards |
   | Add or change a resident | person, role (*pupil*, *adult*, *none* ends residency), short name, personal days off every week, valid from |
   | Assign a room | area, residents, morning rule, evening rule, valid from |
   | Residents of the house | residents whose days count for the house (empty = everyone with a house role), valid from |

### Removal

*Settings → Devices & services → Werktags → ⋮ → Delete*. This removes the
entities and devices and deletes the integration's store
(`.storage/werktage.data`: residents, rooms, exceptions, cached school
holidays). Persons, areas, automations and dashboards stay; automations that
use Werktags entities then need a new condition. To remove the files as well,
delete `custom_components/werktage/` and restart Home Assistant.

See the [specification](docs/specification.md) for rules, entities and
services.

## Dashboard

The integration serves four cards; no Lovelace resource has to be added by
hand. A dashboard with one card per view:

```yaml
title: Werktags
views:
  - title: Kalender
    path: kalender
    cards:
      - type: custom:werktags-calendar
        weeks: 5
  - title: Zeitraum
    path: zeitraum
    cards:
      - type: custom:werktags-period
  - title: Bewohner
    path: bewohner
    cards:
      - type: custom:werktags-residents
  - title: Räume
    path: raeume
    cards:
      - type: custom:werktags-rooms
```

| Card | What it does |
|---|---|
| `custom:werktags-calendar` | five week rows from the current week (`weeks` configurable); every day shows *All* and one toggle per resident — **checked = day off**; weekends and public holidays shaded, school holidays outlined, exceptions marked; tap a date for the reasons; one row per day on narrow screens |
| `custom:werktags-period` | day off · workday · default for chosen residents over a date range, with a preview of what changes |
| `custom:werktags-residents` | every Home Assistant person with short name, role today, new role from a date (asks before changing the past), personal days off every week, history, order |
| `custom:werktags-rooms` | every area with its residents from a date, morning/evening rules, history; the house row chooses whose days count for the house (empty = everyone with a house role) |

## Automations

The sensors are enums; compare against the keys, not the displayed text:

```yaml
# Open the bedroom shutter at 07:00 on workdays, at 10:00 otherwise
triggers:
  - trigger: time
    at: "07:00:00"
    id: early
  - trigger: time
    at: "10:00:00"
    id: late
conditions:
  - condition: template
    value_template: >-
      {{ (trigger.id == 'early') == (states('sensor.bedroom_morning') == 'workday') }}
actions:
  - action: cover.open_cover
    target:
      entity_id: cover.bedroom_shutter
```

`sensor.<x>_evening` is `before_workday` or `before_day_off` and refers to
**tomorrow**; note that after midnight it already refers to the day after.
`binary_sensor.<x>_workday` is `on` on a workday, for plain state conditions.

### Blueprints

Two blueprints in `blueprints/automation/werktage/` cover the common cases
without any template — import them under *Settings → Automations → Blueprints*:

| Blueprint | Inputs |
|---|---|
| *Werktags: open a cover in the morning* | a morning sensor, a cover, the time on workdays and on days off (never before sunrise) |
| *Werktags: switch off in the evening* | an evening sensor, lights or switches, the time before a workday and before a day off |

The later time of each blueprint acts in any case, so a run that Home
Assistant missed (restart, power cut) is caught up. Both are validated
against Home Assistant's blueprint schema in the tests.

### Actions

Everything the cards do is an action of the `werktage` domain; the
*Developer tools → Actions* page offers a form for each. Dates are
`YYYY-MM-DD`; persons are `person.*` entities, areas are area ids.

| Action | Fields | Effect |
|---|---|---|
| `set_days` | `person` (one or more), `start`, `end` (default: `start`), `status` (`day_off`, `workday`, `default`) | exceptions for a day or range, weekends included; `default` removes exceptions |
| `set_role` | `person`, `role` (`pupil`, `adult`, `none`), `valid_from` (default: today), `short_name` | makes a person a resident or changes the role from a date on |
| `remove_role` | `person`, `valid_from` | removes one role entry (not the last) |
| `set_weekly` | `person`, `weekdays` (0 = Monday … 6 = Sunday), `valid_from`, `household` | personal days off every week; `household: true` returns to the household weekend |
| `set_room` | `area`, `person` (several), `valid_from`, `morning_rule`, `evening_rule` | residents of a room from a date on and/or its rules |
| `remove_room_assignment` | `area`, `valid_from` | removes one assignment entry |
| `set_house` | `person` (several), `valid_from`, `by_role` | residents whose days count for the house; `by_role: true` or no persons returns to the roles |
| `set_order` | `person` (in the wanted order) | order of residents in the calendar card |
| `refresh_school_holidays` | — | fetches the school holidays now |
| `get_days` | `start` (any day of the first week), `weeks` (1–8) | **returns** every day with weekend, holidays and, per resident, the effective and default day, exception, reason, role |
| `preview_days` | as `set_days` | **returns** how many days per person would change; writes nothing |
| `get_overview` | — | **returns** all persons and areas with roles, weekly patterns, assignments, the house and the source status |

Writes raise an error when a person is not a resident, a range is longer
than 366 days or ends before it starts, a short name is taken, or the user
may not edit (see *Access*); the fetch raises when the source is down.

## Supported functions

| Per resident, room and house | Entity (English installation) | States |
|---|---|---|
| Morning mode | `sensor.<name>_morning` | `workday`, `day_off` — today |
| Evening mode | `sensor.<name>_evening` | `before_workday`, `before_day_off` — tomorrow |
| Workday | `binary_sensor.<name>_workday` | `on` on a workday |
| Days off (residents only) | `calendar.<name>_days_off` | all-day events, read-only |

Sensor attributes: `reason` (`workday`, `weekend`, `public_holiday`,
`school_holiday`, `exception_day_off`, `exception_workday`, `unknown`),
`holiday_name`, `date`; residents also `role`, `next_workday`,
`next_day_off`; rooms and the house `residents` and `rule`. Resident entities
are named after the person, room entities after the area. Entity ids follow
the language of the installation (`sensor.anna_morgen` in German).

A person without a role, or a room without residents, makes its entities
unavailable; their devices can then be deleted.

## Data updates

- **Day change:** everything is recomputed at midnight and after every change
  made through a card, an action or the options. Nothing is polled.
- **Public holidays** are computed locally by the `holidays` library shipped
  with Home Assistant — no network.
- **School holidays (OpenHolidays API)** are fetched after the start of Home
  Assistant if the cache is older than 30 days, and then once a month: this
  year and the two following years. Earlier years stay in the cache. An
  answer replaces the cache only if it is plausible (summer holidays of this
  and next year present); otherwise the last known dates remain in use.
- **School holidays (calendar entity)** are read on the same schedule;
  every all-day event counts.
- `werktage.refresh_school_holidays` fetches immediately.

## Known limitations

- One school holiday region for the whole household; children at schools in
  different regions are not supported yet
  ([#1](https://github.com/nickl3ss/werktage/issues/1)).
- A day is either a workday or a day off — no half days, no shift times.
- Days whose school holidays are not published yet count as **workdays** for
  pupils (reason `unknown`). The API usually publishes about two years ahead.
- Moveable school days off that are not school holidays (teacher training,
  local bridge days) must be entered as exceptions or as additional holidays.
- The evening sensors refer to **tomorrow**; after midnight they already look
  at the day after.
- One instance per Home Assistant.
- After updating the files of the integration Home Assistant must be
  **restarted**; reloading the entry does not reload the code.

## Troubleshooting

| Symptom | What to check |
|---|---|
| Repair *School holidays could not be fetched* | Shown after three failed fetches. Check the internet connection; run `werktage.refresh_school_holidays` and read the error. The last known dates stay in use. |
| Repair *School holidays are missing for next year* | From October on, next year's summer holidays must be known. The API may not have published them yet — add them as exceptions with the *Period* card, or switch the source to a calendar. |
| Setup says *The OpenHolidays API has no school holidays for this country or region* | The country is not covered. Choose a calendar entity or *none*. |
| A pupil works during the holidays | The reason attribute tells why. `unknown` means the dates are not published; `exception_workday` means someone set an exception. |
| Entities are *unavailable* | The person has no role on that day, or the room has no residents. |
| A card shows *Configuration error* / *Custom element doesn't exist* | The page was loaded before the integration was set up or restarted: the list of scripts is part of the page. Reload the browser once. The Companion app keeps an older page in its cache: *Settings → Companion app → Troubleshooting → Clear cache*, then open the dashboard again. The script is served at `/werktage_static/werktags-cards.js`; it needs the `frontend` integration, which `default_config` includes. |
| An entity is called `sensor.bedroom_morning_2` | An entity with that id existed before. Rename it under *Settings → Entities*. |

Diagnostics (*Devices & services → Werktags → ⋮ → Download diagnostics*)
contain the configuration and counts, never names of persons.

## Repository layout

| Path | Content |
|---|---|
| `custom_components/werktage/` | the integration |
| `lib/openholidays/` | client library for the OpenHolidays API, no Home Assistant dependency |
| `frontend/` | source of the dashboard cards (`src/`) and their browserless tests (`test/`, run with `node --test frontend/test/*.test.mjs`); `tools/build_cards.py` bundles them into `custom_components/werktage/www/` |
| `blueprints/` | automation blueprints |
| `custom_components/werktage/brand/` | the icon (a house between night and day, with an early cyclist) for the brands repository; the artwork is in `docs/brand/` |
| `tests/` | tests |
| `tools/check_publication.py` | checks that no private household data is in the repository |

## Data sources and licenses

The code is licensed under the [MIT License](LICENSE). School holidays come
from the [OpenHolidays API](https://www.openholidaysapi.org) under the
**ODbL 1.0**, public holidays from
[python-holidays](https://github.com/vacanza/holidays). See [NOTICE](NOTICE).

---

## Deutsch

**Werktage je Person für Home Assistant.** Standardmäßig sind Wochenende und
Feiertage frei, für Schüler zusätzlich die Schulferien. Ausnahmen lassen sich
je Person und Tag setzen, dazu persönliche freie Wochentage (Teilzeit) und
Feiertagskorrekturen. Für Personen, Räume und das Haus gibt es einen
Morgen- und einen Abendmodus sowie einen Werktag-Binärsensor; zwei Blueprints
decken Rollladen morgens und Licht abends ab. Bewohner, Räume und Haus lassen
sich über die Karten oder das Optionen-Menü der Integration pflegen.

> **Stand: 0.2.0.** Integration und Karten sind gegen Home Assistant 2026.1
> (Mindestversion) und 2026.9 getestet. Installation über HACS wie oben
> beschrieben; Ideen und Fehler als
> [Issue](https://github.com/nickl3ss/werktage/issues).
