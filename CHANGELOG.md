# Changelog

All changes in plain words, so that it is clear what an update does (Keep a Changelog 1.1.0). Releases are tags `X.Y.Z`; only tags are installed. Lines starting with *Decision:* record a direction taken (`docs/specification.md`, `docs/PROJECT.md § 7`).

## Unreleased

### Added
### Changed
### Fixed
### Removed
### Security

## 0.3.0 — 2026-10-21

The milestone "calendars per resident" (#1, #2, #3), the review of
2026-10-20 and the quality standard `nickl3ss/standards` (level gold).
Store version 3; 0.2.x files are migrated when loading, so a rollback
needs the store from the backup (see `docs/BETRIEB.md § 3`).

### Added
- A resident may have an own **school holiday source**: another region of
  the country or a calendar entity (`set_role` field `school_holiday_source`,
  the residents card, the options menu). Each source is fetched once a
  month on its own; repair hints name the source (#1).
- **Personal calendars as a source of days off**: a days-off calendar and
  a workdays calendar per resident with an optional keyword
  (`set_calendars`, the residents card, the options menu). All-day events
  become days off or extra workdays with the reasons `calendar_day_off`
  and `calendar_workday`; a manual exception still wins. Read at start,
  daily and half a minute after a calendar changes; an unreadable calendar
  keeps its last days (#2).
- **Export into a shared calendar**: *Configure → Export into a calendar*
  writes the days off of the coming weeks as all-day events into a
  CalDAV, Google or local calendar and keeps them current; only its own
  events (marker `werktage:` in the description) are created or removed;
  a refusing calendar raises a repair issue (#3).
- `calendar.<house>_school_holidays`: the school holidays of the source as
  all-day events on the house device (#14).
- The calendar card marks days from a personal calendar with a dotted
  outline and shows when the school holidays were last fetched; a pupil's
  own source is marked as well.
- Performance budgets for the three core flows as tests
  (`tests/test_perf.py`, `docs/PROJECT.md § 6`).
- Release assets: every release carries `werktage.zip`, HACS installs
  from it and GitHub counts the downloads (#7). Releases before 0.3.0 have
  no asset and can no longer be installed through HACS.
- The repository follows `nickl3ss/standards` (level gold): `standards.yaml`,
  `bin/check` as the one quality gate for `pre-push` and the CI,
  `CLAUDE.md` after the template, `docs/PROJECT.md` (architecture, ADRs,
  invariants with tests, deletion concept, threat model),
  `docs/TESTING.md`, `docs/BETRIEB.md`, `SECURITY.md`, `VERSIONS.md`,
  issue and pull request templates, labels and milestones, Conventional
  Commits with a `commit-msg` hook. The deep review is saved as
  `docs/REVIEW-2026-10-20.md`.
- Development on Windows: `tools/windows_dev.py` and a root `conftest.py`
  let the Home Assistant tests run there (18 s).

### Changed
- Decision: the display name is **Werktage** everywhere users see it
  (HACS, the integrations list, titles, texts, blueprints); the card
  element names `custom:werktags-*` and the bundle file keep their names
  so that dashboards keep working (P35, #6).
- Decision: returning to the household weekend (`set_weekly` with
  `household`) or to the house roles (`set_house` with `by_role`) is a step
  from `valid_from` on; earlier days keep their pattern or assignment
  instead of being rewritten (#11, specification 3.4).
- Decision: calendar days sit between the default and a manual exception,
  `effective = exception ?? calendar ?? default` (P36); the export is an
  export, not a synchronisation, and the integration never speaks CalDAV
  itself (P37).
- The repair hint about missing school holidays is checked when loading
  and every midnight, not only after a fetch; it names the source.
- Tap targets in the cards are at least 24 × 24 px (WCAG 2.5.8), day
  toggles 32 px high.
- The CI installs the pinned `requirements-dev.txt`, generic actions are
  pinned to commits, Dependabot proposes updates monthly; secret scanning
  and private vulnerability reporting are switched on.
- Documentation drift fixed: `get_days` takes 1–26 weeks, the five setup
  steps, `set_order` in the specification, the brand images.

### Fixed
- A store damaged by hand (missing keys) names `store_unreadable` instead
  of a traceback.
- The options dialog says "one or two characters" for a three-letter short
  name instead of "already used".
- `with_exceptions` no longer shares the `next_day` cache with the
  household it came from.

### Removed
- `logo.png` and `logo@2x.png` (440 KB): Home Assistant derives the logo
  from the icon.

## 0.2.3 — 2026-10-20

- Werktags is in the HACS default list (hacs/default#11521): install it from
  the HACS search; the custom repository step is gone from the README.
- The check whether the card bundle exists was a `stat` call on the event
  loop; it now runs in the executor job that hashes the bundle (review hint
  from the HACS submission).
- Repository notes: product decisions go up to P34.

## 0.2.2 — 2026-10-10

- `next_workday` and `next_day_off` are computed once per household and
  resident instead of on every state write (each scanned up to 400 days).
- Decision: the OpenHolidays library (`lib/openholidays`) keeps its own
  version, which only changes with the library.
- If computing the public holidays failed at midnight (for example after the
  `holidays` library dropped a subdivision), the error was only logged by the
  time listener and the sensors kept showing the previous day until the next
  midnight. The error is now logged by the integration and the day still
  changes with the holidays already known.
- Card tests pin the clock to the fixtures' date; they used the real date and
  failed from the week after the fixtures (CI of 0.2.1).

## 0.2.1 — 2026-10-06

- README: status line said 0.1.0; the upgrade note now tells Companion app
  users to clear the frontend cache once — an app page from before the rename
  still loads the card script from `/werktags_static/` and shows
  *Configuration error* on every card until then.
- The User-Agent sent to OpenHolidays reported version 0.1.0 after the 0.2.0
  release; `const.VERSION` now matches `manifest.json`, and a test keeps them
  in step.

## 0.2.0 — 2026-10-02

- **Breaking: domain renamed from `werktags` to `werktage`**, repository
  moved to `nickl3ss/werktage`. HACS removes the string `tags/` from every
  download URL (meant for the Git ref `tags/<version>`), so a repository or
  directory called `werktags/` was mangled to `werk` and neither the HACS
  validation nor an installation through HACS could work. The product name
  stays *Werktags*; the cards keep their names (`custom:werktags-calendar`
  …); entity ids do not change because they come from person and area
  names. Actions are now `werktage.*`, the card script is served at
  `/werktage_static/`, the store is `.storage/werktage.data`. Migrating an
  existing installation: remove the old entry, install the new version, set
  it up again and re-create residents, rooms and exceptions (see README).
  The HACS bug is reported upstream with a one-line fix. With the new names
  the HACS validation passes all nine checks.
- Unloading the entry after boot logged "Unable to remove unknown job
  listener": the one-time start listener had already removed itself.

## 0.1.0 — 2026-10-02

- Brand icon ships inside the integration (`brand/`), as Home Assistant
  2026.3 and later expects for custom integrations; no brands pull request.

- Release preparation: minimum Home Assistant 2026.1 (tested in CI next to
  the current release; `hacs.json` said 2025.2, which never worked),
  installation through HACS documented, the HACS check in CI is binding,
  extension ideas moved to GitHub issues.
- Gaps from the product audit: personal days off every week per resident
  (`set_weekly`, history), the house follows chosen residents instead of
  roles (`set_house`, history), extra and removed public holidays in the
  region step, `binary_sensor.<x>_workday` for residents, rooms and the
  house, two automation blueprints (cover in the morning, lights off in the
  evening), an options menu that adds residents, rooms and house residents
  without any dashboard card. Store version 2. Brand icon from the
  household's artwork (`brand/icon.png` in 256 px and a 2× variant in 512 px).
- Cards: weekday chips per resident with a reset to the household weekend;
  the house row on the rooms card is editable (empty = by role). 17 card
  tests, 84 Python tests.
- Library: ranges longer than 1095 days (the API's maximum, e.g. four
  calendar years with a leap year) are fetched in consecutive windows. Found
  on the first live run; before, every monthly fetch of the
  integration would have failed with HTTP 400.
- School holidays are fetched for three calendar years (this year and the two
  after) instead of four; earlier years stay in the cache. The setup dialog
  probes the API with the same range as the monthly fetch.
- Every rejected change has its own translated error message (English and
  German) instead of a generic one carrying English text.
- Silver: test coverage 99 % (CI fails below 95 %). Gold documentation: use
  cases, supported functions, data updates, known limitations,
  troubleshooting.
- A room is its residents: a rule alone no longer creates a room (and three
  unavailable entities), removing the last assignment removes the room, and
  rooms without residents written by earlier versions are dropped on load.
  The rooms card shows the rules once residents are assigned.
- Blueprints are validated with Home Assistant's blueprint schema in the
  tests; their later time now acts in any case, catching up a missed run.
- Cards: the reload-on-change watched `sensor.house_morning`, which only
  exists in English installations; the cards now find the Werktags sensors
  by platform. The script URL carries a hash of the bundle instead of the
  version, so a new build bypasses browser caches. README explains the
  one-time browser reload after setup (*Configuration error* on a card).
- Platinum rules: the setup dialog builds its country and region lists in the
  executor (the `holidays` library took about 0.2 s in the event loop on a
  Raspberry Pi); only two-letter country codes are offered. Every rule in
  `quality_scale.yaml` is now done or exempt except `brands`.
- Quality scale Bronze complete except the brands pull request (needs a
  public repository): `quality_scale.yaml`, manifest key order and
  `CONFIG_SCHEMA` as hassfest requires (hassfest passes locally), config flow
  tested to 100 %, README with installation parameters, options, removal
  and every action, CI workflow (hassfest, HACS, ruff, mypy, pytest with
  coverage, card tests). 100 Python tests.

- Integration: config flow with three steps and options, store with
  versioned JSON, coordinator (midnight rebuild, monthly school holiday
  fetch from the OpenHolidays API or a calendar entity, plausibility check,
  repair issues), morning/evening enum sensors per resident, room and house,
  a days-off calendar per resident, ten services (six writing, three with
  response, one refresh), diagnostics, English and German translations,
  optional card serving (`frontend.py`). Tested against Home Assistant
  2026.9.4 with `pytest-homeassistant-custom-component` (24 tests).
- Cards `werktags-calendar`, `werktags-period`, `werktags-residents`,
  `werktags-rooms` with a visual editor, in plain JavaScript without a
  framework; bundled by `tools/build_cards.py` into
  `custom_components/werktage/www/werktags-cards.js` and served by the
  integration. 15 browserless tests (`node --test`).
- `deploy.sh <config dir>` copies the integration into an installation;
  `tools/sync_vendor.py` keeps the vendored `openholidays` copy in sync.

- Rules engine `custom_components/werktage/rules.py`: default day by role,
  exceptions in both directions, unknown days count as workdays, morning and
  evening modes, room and house combination rules, histories for roles and
  room assignments, range changes with preview. 34 tests, no Home Assistant
  dependency.
- Library `lib/openholidays`: async client for the OpenHolidays API with
  offline parsers and a plausibility check. 15 tests against a local test
  server. Verified once against the live API.
- Tooling: `pyproject.toml` with pytest, mypy (strict) and ruff; all clean.

## 0.0.1 — 2026-09-29

- Repository created: layout, license (MIT), data source notice, HACS and
  manifest metadata, pre-publication check. No integration code yet.
