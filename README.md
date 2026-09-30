# Werktags

**Workdays per person for Home Assistant** — weekends, public holidays and
school holidays by default, exceptions per person and day, and morning/evening
modes for people, rooms and the whole house.

> **Status: in development.** Integration and cards work and are tested
> (Home Assistant 2026.9). A first release follows.

## What it will do

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

## Installation

1. Copy `custom_components/werktags/` into the `custom_components/` folder of
   your Home Assistant configuration (or run `./deploy.sh <config dir>`), and
   restart Home Assistant. HACS: add this repository as a custom repository
   of type *Integration*.
2. *Settings → Devices & services → Add integration → Werktags*. Five short
   steps: country, region and weekend, school holiday source (tested before
   the entry is created), house rules, who may edit.
3. Add residents: either with the dashboard cards below or via
   *Werktags → Configure*, which offers a menu — settings, add or change a
   resident, assign a room, residents of the house.

Removing the integration deletes its store; the persons and areas stay.

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

Two blueprints in `blueprints/automation/werktags/` cover the common cases
without any template — import them under *Settings → Automations → Blueprints*:

| Blueprint | Inputs |
|---|---|
| *Werktags: open a cover in the morning* | a morning sensor, a cover, the time on workdays and on days off (never before sunrise) |
| *Werktags: switch off in the evening* | an evening sensor, lights or switches, the time before a workday and before a day off |

### Services

Everything the cards do is a service (`werktags.set_days`, `set_role`,
`set_weekly`, `set_room`, `set_house`, `set_order`, `remove_role`,
`remove_room_assignment`, `refresh_school_holidays`), and three services
answer with data (`get_days`, `preview_days`, `get_overview`). The
*Developer tools → Actions* page documents every field.

## Repository layout

| Path | Content |
|---|---|
| `custom_components/werktags/` | the integration |
| `lib/openholidays/` | client library for the OpenHolidays API, no Home Assistant dependency |
| `frontend/` | source of the dashboard cards (`src/`) and their browserless tests (`test/`, run with `node --test frontend/test/*.test.mjs`); `tools/build_cards.py` bundles them into `custom_components/werktags/www/` |
| `blueprints/` | automation blueprints |
| `custom_components/werktags/brand/` | the icon (a house between night and day, with an early cyclist) for the brands repository; the artwork is in `docs/brand/` |
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

> **Stand: in Entwicklung.** Integration und Karten funktionieren und sind
> getestet (Home Assistant 2026.9). Eine erste Version folgt.
