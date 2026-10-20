# Security policy

Werktage is a Home Assistant custom integration. It runs inside your Home
Assistant, stores its data in your `.storage/` directory and talks to one
external service, the OpenHolidays API, read-only. There is no account, no
hosted service and no telemetry.

## Supported versions

Only the latest release on GitHub (what HACS offers) receives fixes.

## Reporting a vulnerability

Please do not open a public issue for a security problem. Use GitHub's
private vulnerability reporting instead: *Security → Report a vulnerability*
on <https://github.com/nickl3ss/werktage>. You will get an acknowledgement
within seven days and a fix or a decision within thirty.

What counts as a security problem here:

- a service that changes data although *Only administrators may change data*
  is on, or that a user without admin rights can call anyway;
- household data (names, person ids, area ids, days off) leaking into
  diagnostics, logs, repair issues or the card script;
- content from a calendar or from the OpenHolidays API (event titles, holiday
  names) that ends up unescaped in the dashboard cards;
- a request from the integration to any host other than
  `openholidaysapi.org`.

Please include the Werktage version (`manifest.json`), the Home Assistant
version and steps to reproduce. Anonymise any household data.

## Design notes for reviewers

- All writes go through Home Assistant service calls validated with
  `voluptuous` schemas; the `admin_only` option is enforced in `services.py`.
- The cards escape every interpolated string (`esc()` in `frontend/src/logic.js`)
  and use no `eval` or inline scripts beyond the bundled file.
- The only network call is the OpenHolidays client in `lib/openholidays`,
  using Home Assistant's shared `aiohttp` session with a 15 s timeout and a
  fixed `User-Agent`.
- Diagnostics (`diagnostics.py`) export counts and configuration, never names.
