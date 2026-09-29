# Werktags

**Workdays per person for Home Assistant** — weekends, public holidays and
school holidays by default, exceptions per person and day, and morning/evening
modes for people, rooms and the whole house.

> **Status: in development.** The integration works (setup dialog,
> sensors, calendars, services) and is tested against Home Assistant 2026.9.
> Dashboard cards and a release follow.

## What it will do

- One Home Assistant **person** = one resident with a **role**
  (*pupil* or *adult*), valid from a date.
- **Default days off:** weekends and public holidays for everyone, school
  holidays for pupils. Country and subdivision are chosen during setup.
- **Exceptions** per person and day in both directions: an extra day off, or
  a workday on a day that would otherwise be free.
- **Rooms** are Home Assistant areas with residents assigned, valid from a
  date.
- Per resident, room and house two sensors:
  - **morning** — `workday` / `day_off` (today);
  - **evening** — `before_workday` / `before_day_off` (tomorrow).
- Dashboard cards: calendar, date range, residents, rooms.

See the [specification](docs/specification.md) for rules, entities and
services.

## Repository layout

| Path | Content |
|---|---|
| `custom_components/werktags/` | the integration |
| `lib/openholidays/` | client library for the OpenHolidays API, no Home Assistant dependency |
| `frontend/` | source of the dashboard cards |
| `blueprints/` | automation blueprints |
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
je Person und Tag setzen. Für Personen, Räume und das Haus gibt es einen
Morgen- und einen Abendmodus.

> **Stand: in Entwicklung.** Die Integration funktioniert (Einrichtungsdialog,
> Sensoren, Kalender, Dienste) und ist gegen Home Assistant 2026.9 getestet.
> Dashboard-Karten und eine erste Version folgen.
