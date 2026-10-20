# CLAUDE.md — Werktage

Custom Integration für Home Assistant: Werktage je Person (Wochenende, Feiertage, Schulferien, Ausnahmen) mit Morgen- und Abendmodus für Personen, Räume und Haus. Soll-Verhalten: `docs/specification.md` (Entscheidungen `P1`–`P37`). Architektur, ADRs und Invarianten: `docs/PROJECT.md`. Das Repo ist **öffentlich** (MIT, HACS-Standardliste); alles darin kann jederzeit von jedem gelesen werden.

Es gilt der zentrale Qualitätsstandard `nickl3ss/standards` (Stufe und Ausnahmen in `standards.yaml`). Regeln nachschlagen: `/standards:standard <kapitel|regel-id>`; Review: `/standards:review`.

## Kommunikation

- Deutsch, knapp, Stichpunkte vor Fließtext, keine Füllwörter.
- Annahmen vor der Umsetzung als nummerierte Fragen — **eine Runde, dann warten**.
- Erst planen, dann bauen: Aufträge, die mehr als eine Datei ändern, bekommen zuerst einen Plan mit Markern `[NEU]` `[GEÄNDERT]` `[ENTFERNT]` `[RISIKO]` `[OFFEN]` und warten auf „Go“.
- **Nutzerbild (für das UX-Review):** Hausbewohner ohne Home-Assistant-Kenntnisse, bedient die Kalenderkarte am Handy; ein Administrator richtet Bewohner und Räume einmal ein.

## Grundprinzipien (nie verletzen)

1. **Fail-safe:** Fehlende Daten gelten als Werktag mit `reason: unknown`, nie stillschweigend frei (P5).
2. **Code und private Daten strikt getrennt.** Keine echten Namen, Personen-IDs, Bereichsnamen, IP-Adressen oder freien Tage — nicht im Code, in Tests, Beispielen, Commit-Nachrichten oder der Historie. Tests und Beispiele benutzen Anna, Ben, Clara, David, Emil. `tools/check_publication.py` prüft Dateien **und** Historie; private Suchbegriffe stehen zeilenweise in der ignorierten `.publication-terms`.
3. **Eine Quelle der Wahrheit.** Version nur in `manifest.json` (Test gegen `const.VERSION`); Anzeigetexte nur in `strings.json` + `translations/`; generierte Dateien (`custom_components/werktage/www/`, `custom_components/werktage/openholidays/`) werden nie von Hand geändert, sondern mit `tools/build_cards.py` und `tools/sync_vendor.py` erzeugt.
4. **Drei Teile, sauber getrennt** (ARC-01, ARC-12): `lib/openholidays/` importiert nichts aus Home Assistant und hat eine eigene Version (P34); die Integration spricht die API nur über diese Bibliothek; die Karten lesen nur Entitäten und Dienste mit Antwort, `frontend.py` ist die einzige Auslieferung — keine eigene WebSocket-API, kein Panel.
5. **Die Vergangenheit wird nie umgeschrieben:** Rollen, Räume, Wochenmuster und Hausbewohner gelten ab `valid_from` (Spezifikation 3.4).
6. **OpenHolidays-Daten (ODbL 1.0):** keine echten Ferientermine im Repo, `attribution` anzeigen, höchstens ein Abruf im Monat, eigener `User-Agent`, Fenster ≤ 1095 Tage.
7. **Kernfähig bauen:** Config Flow statt YAML, `has_entity_name`, Übersetzungen, stabile `unique_id`, Diagnose ohne Namen, Reparaturhinweise, Entladen ohne Neustart, `mypy --strict`. Quality Scale **Platinum** (`quality_scale.yaml`: jede Regel `done` oder begründet `exempt`) bleibt bei jeder Änderung.

Alle Invarianten mit Nummern stehen in `docs/PROJECT.md § 8`; jede ist durch einen Test abgesichert. Eine Änderung, die eine Invariante oder ein Kernmodul (`standards.yaml`) berührt, ist nie ein Schnellweg (Schritt A).

## Stack und Qualitätstor

| | |
|---|---|
| Runtime | Python 3.14 (CI zusätzlich 3.13 mit HA 2026.1) · Home Assistant ≥ 2026.1 (`hacs.json`) · Node ≥ 22 für die Karten-Tests |
| Einrichten | `python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt` · `git config core.hooksPath .githooks` · Windows: `.venv/Scripts/python`, einmalig `python tools/windows_dev.py` (Stubs für `fcntl`/`resource`; `conftest.py` erlaubt der Event-Loop ihr Socketpaar) |
| Tests | `python -m pytest -q` (Regeln, Integration, Bibliothek; HA-Tests mit `pytest-homeassistant-custom-component`) · `node --test frontend/test/cards.test.mjs frontend/test/logic.test.mjs` |
| Lint | `ruff check .` (120 Zeichen) |
| Typen | `python -m mypy` (strict: Integration und Bibliothek) |
| Generieren | `tools/sync_vendor.py --check` · `tools/build_cards.py` (Version aus `manifest.json`) |
| Veröffentlichungs-Check | `tools/check_publication.py --areas` (Dateien **und** Historie, No-Reply-Autor; in der CI ohne `.storage`, daher nur generische Muster) |
| **Alles** | `bin/check` — ruft die Zeilen oben in dieser Reihenfolge; `.githooks/pre-push` und die CI rufen **nur** diesen Befehl (`--fast`: nur Tests und Lint) |

Vor jedem Commit grün. Kein `--no-verify`, kein `--force`. Bei zwei erfolglosen Runden anhalten, Fehler melden, Entscheidung einholen. Zusätzlich in der CI: hassfest, HACS-Validierung, Job `minimum-ha`. hassfest lokal: sparse checkout von `home-assistant/core` (`script/hassfest`, `script/translations`, `script/util`) im Scratchpad, dort `PATH=.venv/bin:$PATH python -m script.hassfest --action validate --integration-path <Repo>/custom_components/werktage`.

## Projektstruktur

```
lib/openholidays/                  [LIB]   asynchroner API-Client; kein HA-Import; eigene Version
custom_components/werktage/        [INT]   die Integration
  rules.py sources.py storage.py           reine Logik, kein HA-Import — Kernmodule
  coordinator.py                           Store, Mitternachts-Rebuild 00:00:10, Prüfung 03:30, Abruf alle 30 Tage
  sensor.py binary_sensor.py calendar.py   Entitäten je Bewohner, Raum, Haus
  services.py services.yaml                Aktionen und Antwortdienste (SupportsResponse.ONLY)
  config_flow.py                           Einrichtung (fünf Schritte) und Optionen-Menü
  frontend.py www/                         einzige Auslieferung der Karten; www/ ist generiert
  openholidays/ brand/ translations/       Kopie der Bibliothek (generiert); Markenbilder; DE + EN
frontend/src/ frontend/test/       [CARDS] Kartenquelle (logic.js, cards.js) und browserlose Tests
blueprints/automation/werktage/    [INT]   zwei Blueprints (morgens, abends)
tests/                             [INT]   pytest; Haushalt Anna, Ben, Clara; Uhr eingefroren
tools/                             [CI]    build_cards · sync_vendor · check_publication · windows_dev · ci_status
.github/ bin/ .githooks/           [CI] [PROC]  CI, Release-Asset, Vorlagen; Tor; Push-Hook
docs/                              [DOCS]  specification.md (Soll) · PROJECT.md · TESTING.md · BETRIEB.md · REVIEW-<datum>.md
```

**Komponenten (Kürzel für Issue-Titel und Commit-Scopes):** `INT` · `LIB` · `CARDS` · `DOCS` · `CI` · `PROC`.

**Modulvertrag:** Jede Datei beginnt mit einem Docstring, der sagt, was sie besitzt und was sie nicht tun darf (`rules.py`: „pure logic, no Home Assistant imports“).

## Arbeitsweise

> Wahrheitsquelle für offene Arbeit: **GitHub Issues** — https://github.com/nickl3ss/werktage/issues. Keine Backlog-Datei. Issues werden nie gelöscht, nur geschlossen.

**Schritt 0 · Sitzungsbeginn** — `git log --oneline -5` · `gh issue list --state open` · `bin/check` · `docs/PROJECT.md` lesen. Ergebnis kurz melden; Fehlschläge **vor** der ersten Anfrage.

**Schritt A · Anfrage** — Annahmen klären (eine Runde). **Schnellweg** für Kleinigkeiten (ein Anzeigetext, ein CSS-Wert, eine Umbenennung ohne Designentscheidung): Datei nennen, eine Frage zur Motivation, Minimal-Issue, direkt Schritt D. Nicht erlaubt bei Kernmodulen oder Invarianten.

**Schritt B · Issues** — Anfrage in atomare Issues zerlegen, Vorschau zeigen, nach Bestätigung `gh issue create`. Titel `[KÜRZEL] Kurzbeschreibung` · Labels Typ (`bug` / `enhancement` / `documentation`) + `P1`–`P4` + Komponente · Body: Beschreibung · Umsetzung · Betroffene Module (Ändert / Berührt nicht) · Akzeptanzkriterium (Vorlage `.github/ISSUE_TEMPLATE/`).

**Schritt C · Priorisierung** — Top-3 vorschlagen, je ein Satz Begründung.

**Schritt D · Umsetzung je Issue**
- **D1 Bestand prüfen** — neue Regel? → `rules.py` (rein, mit Test in `test_rules.py`) · neuer Dienst? → `services.py` + `services.yaml` + `strings.json` · neuer Anzeigetext? → `strings.json` **und** `translations/en.json` **und** `translations/de.json` · neues Store-Feld? → `storage.py`, `DATA_VERSION` + additive Migration + Test · neue Kartenfunktion? → `frontend/src` + `frontend/test` + `tools/build_cards.py` · Bibliothek geändert? → `tools/sync_vendor.py`, Version in `lib/openholidays/pyproject.toml`.
- **D2 Umsetzen** — Modulvertrag, Sprachdateien DE + EN, Migration nur anhängen, generierte Dateien neu erzeugen, `quality_scale.yaml` bleibt Platinum.
- **D3 Qualitätstor** — `bin/check` grün (max. zwei Runden).
- **D4 Tests** — jedes geänderte Verhalten bekommt einen Test. Nutzersichtbare Änderungen zusätzlich in `docs/TESTING.md` unter **Neu seit dem letzten Push**, im selben Commit.
- **D5 Abschluss** — Akzeptanzkriterien einzeln ✓/✗ kommentieren; schließen nur bei vollständigem ✓: `gh issue close <nr> --reason completed --comment "AC: ✓ … ✓ …"`.
- **D6 Melden** — Issue, geänderte Dateien, Testzahl.

**Schritt E · Push-Tor**
- **E1** Nach Änderungen an Kernmodulen oder dem Schließen eines `P1`/`P2`: fragen „Wesentliche Änderung fertig. Pushen?“ Pushen, Taggen und Releases entscheidet der Eigentümer.
- **E2** `/standards:review` (Prüfer ohne Gesprächsverlauf). Quick Wins sofort beheben und mitpushen, übrige Befunde als Issues (Label `review`). **Kritisch** blockiert den Push.
- **E3** Nach dem Push: „Push erledigt. Bitte testen — Schritte in `docs/TESTING.md`.“ Nach Bestätigung die Schritte in die Regressionssuite verschieben.

## ⛔ Niemals pushen ohne

```
□ D3  bin/check grün                  Tests · Lint · Typen · Build-Sync · Veröffentlichungs-Check
□ D2  Store-Migration / Sprachdateien / www/ und openholidays/ aktuell
□ D4  docs/TESTING.md „Neu seit dem letzten Push“ beschreibt diesen Stand
□ D5  erledigte Issues geschlossen (AC ✓)
□ E2  /standards:review gelaufen · Quick Wins committet · Befunde als Issues · kein Befund „Kritisch“ offen
□ G2  keine privaten Daten im Diff (Grundprinzip 2)
```

## Git

- `main` ist immer lauffähig. Solo-Repo: direkt auf `main`, Commit nennt `#<nr>`; `git pull --rebase` vor jedem Push (Eigentümer committet auch über die GitHub-Oberfläche); nie force-push.
- Commits `<typ>(<kürzel>): <was>` — `feat · fix · test · docs · chore · refactor · perf · build · ci`; Begründung im Text, Issue-Nummer; Trailer `Co-Authored-By`; No-Reply-Adresse (`git config user.email`). `.githooks/commit-msg` prüft das Format.
- Releases als Tags `X.Y.Z` ohne `v` (Ausnahme PRO-16 in `standards.yaml`); Ablauf in `docs/BETRIEB.md § 7`; nur Tags werden ausgerollt. Der Home-Assistant-Host des Eigentümers installiert nur Tags (`git archive <tag>` + `deploy.sh`), nie die Arbeitskopie; Entwicklung findet nie auf dem Host statt.

## Sprache

- Code, Bezeichner, Kommentare, Log-Meldungen, Dienst- und Zustandsschlüssel, Commits, `CHANGELOG.md`, `docs/specification.md`, `README.md` (EN mit DE-Teil), `SECURITY.md`, `VERSIONS.md`, Produkt-Issues: **Englisch** — öffentliches Repo mit internationalen Nutzern (bewusste Abweichung von der Standard-Vorlage).
- `CLAUDE.md`, `docs/PROJECT.md`, `docs/TESTING.md`, `docs/BETRIEB.md`, Reviews und Review-Issues: **Deutsch**.
- Kein Anzeigetext im Code; alles über `strings.json` + `translations/en.json` + `translations/de.json`. Feste Schlüssel: `workday` · `day_off` · `before_workday` · `before_day_off` · `reason: unknown`.

## Daten, Lizenzen, Veröffentlichung

- Fremde Daten nur mit Lizenz und Eintrag in `NOTICE` und `VERSIONS.md` (OpenHolidays ODbL 1.0, python-holidays MIT). Keine Marken im Produkt.
- Vor jedem Release: `/standards:review publish`, dann `docs/BETRIEB.md § 7`.
