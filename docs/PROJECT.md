# PROJECT — Werktage

> Das **Ist**: Architektur, Datenmodell, Zustände, Entscheidungen, Invarianten, Löschkonzept, Bedrohungsmodell. Das **Soll** steht in `specification.md` (englisch, Entscheidungen P1–P35). Vorlage aus `nickl3ss/standards` (ARC-21, PRO-12). Stand: 0.3.0.

---

## 1 · Kontext und Container (C4 Stufe 1–2)

```
Bewohner am Handy ──► Dashboard-Karten (custom:werktags-*) ──┐
Administrator      ──► Optionen-Menü, Dienste (werktage.*)   ├──► Integration werktage ──► OpenHolidays API (HTTPS, nur lesen)
Automationen       ──► Sensoren, Binärsensoren, Kalender     ┘          │                  python-holidays (lokal, Executor)
                                                                        ▼                  calendar.* (optional: Schulferienquelle)
                                                        .storage/werktage.data · Config-Eintrag
```

Werktage ist eine Custom Integration, die in jedem Home Assistant ≥ 2026.1 läuft (HACS-Standardliste). Sie entscheidet je Person, ob ein Tag ein Werktag oder frei ist, und leitet daraus Morgen- und Abendmodus für Person, Raum und Haus ab. Es gibt keinen Server des Autors, keine Konten, keine Telemetrie; der einzige Netzzugriff ist der monatliche Abruf der Schulferien.

## 2 · Module und Verträge

| Modul | Besitzt | Darf nicht | Kürzel |
|---|---|---|---|
| `lib/openholidays/src/openholidays/` | HTTP-Client, Modelle, Fenster ≤ 1095 Tage, eigene Version | Home Assistant importieren; Daten interpretieren | `LIB` |
| `custom_components/werktage/rules.py` | Tagestyp, Gründe, Historie (`History[T]`), Kombination Raum/Haus, `next_day` | I/O, Home Assistant, Uhr lesen | `INT` |
| `sources.py` | Feiertage (python-holidays), Jahresspannen, Schulferien aus Perioden | Home Assistant | `INT` |
| `storage.py` | JSON ↔ Datentypen, `DATA_VERSION`, additive Migration | Home Assistant, Regeln | `INT` |
| `coordinator.py` | Store, Zeitplan (00:00:10 Rebuild, 03:30 Prüfung, Abruf alle 30 Tage), Schreibdienste, Reparaturhinweise | Entitätszustände direkt setzen (nur `_notify`) | `INT` |
| `sensor.py` `binary_sensor.py` `calendar.py` `entity.py` | Entitäten und Geräte je Bewohner, Raum, Haus | Regeln rechnen, Store schreiben | `INT` |
| `services.py` `services.yaml` | Schemas, Admin-Prüfung, Antwortdienste | Regeln rechnen | `INT` |
| `config_flow.py` | Fünf Einrichtungsschritte, Optionen-Menü, Prüfabruf | Store direkt schreiben (nur über den Coordinator) | `INT` |
| `frontend.py` `www/` | Einzige Auslieferung des Karten-Bundles unter `/werktage_static/…?v=<hash>` | eigene WebSocket-API, Panel | `INT` |
| `diagnostics.py` `repairs` | Zählungen und Konfiguration | Namen, Personen-IDs ausgeben | `INT` |
| `frontend/src/logic.js` `cards.js` | Vier Karten und Editor; lesen Entitäten (`platform === "werktage"`) und Dienste mit Antwort | Direktzugriff auf Store oder HTTP | `CARDS` |
| `tools/` | Bundle bauen, Bibliothek kopieren, Veröffentlichung prüfen, Windows-Stubs | Laufzeitcode | `CI` |

Abhängigkeitsrichtung: Karten → Entitäten/Dienste → Coordinator → Regeln/Quellen/Store → Bibliothek. Keine Zyklen (ARC-01, ARC-05); `rules.py`, `sources.py`, `storage.py` und die Bibliothek importieren nichts aus Home Assistant (Invariante 3, Test `tests/test_quality.py::test_pure_modules_and_library_import_nothing_from_home_assistant`).

## 3 · Datenmodell

**Store `.storage/werktage.data`** (`storage.py`, `DATA_VERSION` 3 ab 0.3.0; Schlüssel sind interne IDs, nie Namen):

| Feld | Typ | Bedeutung | Personenbezug |
|---|---|---|---|
| `residents[<person_id>].roles` | `History[Role]` (`adult` · `pupil` · `none`), Schritte mit `valid_from` | Rolle ab Datum; `none` beendet die Mitgliedschaft | Personen-ID aus `person.*` (stabil über Umbenennungen) |
| `residents[].short_name`, `order` | 1–2 Zeichen, Reihenfolge | Anzeige in den Karten | Kürzel ist vom Nutzer gewählt |
| `residents[].school_holiday_source` | Quellenschlüssel oder `null` | eigene Schulferienquelle (`openholidays:DE-HE`, `calendar:<entity>`), sonst die der Installation (#1) | Schulort |
| `residents[].off_weekdays` | `History[frozenset[int] \| None]` | persönliche freie Wochentage ab Datum; `None`-Schritt = Haushaltswochenende (P29, #11) | Arbeitsmuster |
| `rooms[<area_id>].residents` | `History[frozenset[str]]` | Bewohner eines Raums ab Datum | Bereichs-ID |
| `rooms[].morning_rule`, `evening_rule` | `day_off_wins` · `workday_wins` | Kombinationsregel | — |
| `exceptions[<date>][<person_id>]` | `DayType` (`workday` · `day_off`) | manuelle Ausnahme, relativ zum Standard normalisiert | Abwesenheitsmuster |
| `school_holidays[<key>]` | je Quellenschlüssel: `source`, `periods[]` (start, end, name), `known_from`, `known_to`, `fetched_at` (UTC), `failures` | Cache je Quelle in Benutzung (Installation und Bewohner, #1); frühere Jahre bleiben erhalten; ungenutzte Quellen werden beim Abruf entfernt | — (öffentliche Daten, ODbL) |
| `house.residents` | `History[frozenset[str] \| None]` | explizit gewählte Hausbewohner; `None`-Schritt = nach Rolle (P30, #11) | — |

**Config-Eintrag** (`const.py`): Land, Region, Wochenende, Schulferienquelle (`openholidays` · `calendar` · `none`) und Kalender-Entität, zusätzliche und entfernte Feiertage, Hausrollen, Haus-Morgen-/Abendregel, `admin_only`. Daten sind lokale Kalendertage; nur `fetched_at` ist ein UTC-Zeitpunkt. Namen kommen zur Laufzeit aus dem HA-Personenregister und werden nie gespeichert.

**Entitäten** je Bewohner, Raum, Haus: `sensor.<x>_morning` (`workday` · `day_off`), `sensor.<x>_evening` (`before_workday` · `before_day_off`), `binary_sensor.<x>_workday`, je Bewohner `calendar.<x>_days_off`, am Haus `calendar.<haus>_school_holidays` (nur mit Schulferienquelle, #14); Attribute `reason`, `holiday_name`, `next_workday`, `next_day_off`, bei Raum und Haus `residents`, `rule`. `unique_id` = `<entry_id>_<resident|room|house>_<key>`. Raum-Geräte tragen den Bereichsnamen, liegen aber nicht im Bereich (sonst doppelte IDs).

## 4 · Zustände

| Zustand | Bedeutung | Übergänge (von → nach, Auslöser) | Ablauf / Watchdog |
|---|---|---|---|
| Tag je Person: `workday` / `day_off` mit `reason` (`weekday`, `weekend`, `public_holiday`, `school_holiday`, `exception`, `unknown`, `none`) | Ergebnis der Regeln für einen Kalendertag | rechnet jeder Rebuild neu | Mitternacht 00:00:10 (P33: Fehler protokolliert, Tag wechselt mit bekannten Daten) |
| Schulferien-Cache: `fresh` (fetched_at < 30 Tage) · `due` · `down` (`failures` ≥ 3 → Reparaturhinweis `school_holidays_unreachable`) · `incomplete` (ab Oktober fehlt der Sommer des Folgejahres → `school_holidays_incomplete`) | Verfügbarkeit der Quelle | `due` → Abruf 03:30 oder nach dem Start; Erfolg → `fresh`, Misserfolg → `failures + 1`; Vollständigkeit wird beim Laden, um Mitternacht und nach jedem Abruf geprüft | Tage außerhalb `known_from`–`known_to` → `unknown` → Werktag (P5) |
| Config-Eintrag: `loaded` · `setup_error` (`store_unreadable`, `country_unsupported`) | Lebenszyklus | Laden → Fehler bei beschädigtem Store oder unbekanntem Land; Entladen ohne Neustart | Reload über HA |
| Reparaturhinweise `person_missing`, `area_missing` | Person oder Bereich in HA gelöscht, aber im Store | jeder Rebuild prüft; Hinweis verschwindet, wenn der Eintrag entfernt ist | — |

## 5 · Fremdsysteme und ihre Regeln (REC-07)

| System | Zugriff | Regeln aus den Nutzungsbedingungen | Fallback bei Ausfall |
|---|---|---|---|
| OpenHolidays API (`openholidaysapi.org`) | HTTPS GET über `lib/openholidays`, HA-Session, Timeout 15 s, `User-Agent werktage/<version> (+repo)` | ODbL 1.0: Namensnennung (`attribution` an jeder Entität und Karte), keine Ferientermine im Repo; höchstens ein Abruf je 30 Tage je Quelle, Fenster ≤ 1095 Tage, drei Kalenderjahre | Cache bleibt; `failures` zählt; ab 3 Reparaturhinweis; unbekannte Tage → Werktag |
| python-holidays | lokal im Executor (`sources.public_holidays`) | MIT; wird von HA mitgeliefert | Fehler um Mitternacht → bekannte Feiertage bleiben (P33); beim Laden → `country_unsupported` |
| Home-Assistant-Kalender (`calendar.get_events`) | nur wenn Quelle `calendar` | ganztägige Ereignisse = Schulferien | `FetchFailed` wie oben; Attribution leer |
| Home Assistant selbst | Personen-, Bereichs-, Entitäts- und Issue-Register; `Store`; Zeitplaner | Entladen ohne Neustart; Diagnose ohne Namen | — |

## 6 · Leistungsbudgets (PERF-01)

| Kernfluss | Budget (p95) | Messung |
|---|---|---|
| Tag frei schalten: `set_days` → Store → Rebuild → Sensoren | < 200 ms für 10 Bewohner, 4 Räume | `tests/test_perf.py::test_set_days_rebuild_budget` |
| Kalenderkarte laden: `get_days` 26 Wochen für 10 Bewohner | < 300 ms | `tests/test_perf.py::test_get_days_budget` |
| Mitternachts-Rebuild mit `next_workday`/`next_day_off` je Bewohner | < 500 ms für 10 Bewohner | `tests/test_perf.py::test_midnight_rebuild_budget` |
| Fremdaufrufe | ≤ 1 Abruf je 30 Tage und Quelle, ≤ 3 Fenster je Abruf | `tests/test_quality.py::test_school_holidays_are_fetched_after_boot_and_checked_daily`, `lib/openholidays/tests/test_client.py::test_long_ranges_are_fetched_in_windows_of_at_most_1095_days` |

Gemessene Werte stehen als Kommentar in `tests/test_perf.py` (Windows, Python 3.14, 2026-10-20); die Schwellen liegen beim Fünffachen, damit die CI nicht flackert (TST-14).

## 7 · Architekturentscheidungen (ADR)

| # | Entscheidung | Grund | Verworfen | Datum | Status |
|---|---|---|---|---|---|
| 1 | Drei Teile: Bibliothek · Integration · Karten (P15, P34) | kernfähig; Bibliothek ohne HA ist Voraussetzung für Core | Monolith; eigene WebSocket-API für die Karten; Panel | 2026-09-29 | gültig |
| 2 | Fehlende Daten = Werktag mit `reason: unknown` (P5) | lieber pünktlich geweckt als verschlafen | „unbekannt = frei“; Entität `unavailable` | 2026-09-29 | gültig |
| 3 | Historie mit `valid_from` statt Überschreiben (3.4, P26) | Vergangenheit bleibt prüfbar; Ausnahmen bleiben gültig | nur aktueller Zustand | 2026-09-30 | gültig |
| 4 | Domain `werktage` statt `werktags` | HACS entfernt `tags/` aus jeder Download-URL | auf HACS-Fix warten | 2026-10-02 (0.2.0) | gültig |
| 5 | Karten-URL stabil + `?v=<hash>` | gecachte Seite darf nie einen gelöschten Pfad laden | Hash im Pfad | 2026-10-06 | gültig |
| 6 | Lokale Markenbilder (`brand/icon*.png`), nur Icon | brands-Repo nimmt keine Custom-Integrationen mehr; HA leitet Logo aus Icon ab | PR an `home-assistant/brands`; doppelte Logo-Dateien (#13) | 2026-10-20 | gültig |
| 7 | Anzeigename **Werktage** (P35, #6); technische Namen bleiben (`custom:werktags-*`, `werktags-cards.js`) | ein Name für Domain und Produkt; Kartennamen zu ändern bräche Dashboards | „Werktags“ behalten und den Unterschied erklären | 2026-10-20 | gültig |
| 8 | Rückkehr zum Haushalts-Standard ist ein Schritt ab `valid_from` (`None`), keine Löschung (#11) | Spezifikation 3.4; Rückfrage in den Karten muss wahr sein | Historie leeren (0.1.0–0.2.3) | 2026-10-20 | gültig, ersetzt Verhalten bis 0.2.3 |
| 9 | Release als ZIP-Asset (`hacs.json` `zip_release`, #7) | GitHub zählt Asset-Downloads; Bundle und Bibliothek im Asset sind geprüft | Quell-Archiv des Tags (nicht zählbar) | 2026-10-20 | gültig; ältere Releases ohne Asset sind über HACS nicht mehr wählbar |
| 10 | Standard `nickl3ss/standards` Stufe **Gold** | öffentliches Repo mit Fremdnutzern | Silber mit Ziel Gold | 2026-10-20 | gültig |
| 11 | Sprache: Produkt und Code Englisch, Prozessdoku und Reviews Deutsch | internationale HACS-Nutzer; Standard-Vorlage ist deutsch | alles Deutsch; alles Englisch | 2026-10-20 | gültig |
| 12 | Windows-Entwicklung über Stubs (`tools/windows_dev.py`, `conftest.py`) statt WSL | Tests laufen in 18 s lokal; kein Neustart, keine Admin-Rechte | WSL; nur CI | 2026-10-20 | gültig |

## 8 · Invarianten (nie verletzen) — jede mit Test (ARC-22)

1. **Fehlende Daten sind ein Werktag mit `reason: unknown`, nie stillschweigend frei** — `tests/test_rules.py::test_unknown_school_holidays_count_as_workday_with_reason_unknown`, `::test_combine_without_residents_is_unknown_and_a_workday`, `tests/test_integration.py::test_unknown_days_count_as_workday`.
2. **Eine Änderung heute schreibt die Vergangenheit nie um** (Rollen, Räume, Wochenmuster, Hausbewohner gelten ab `valid_from`) — `tests/test_rules.py::test_role_none_ends_membership_without_touching_the_past`, `::test_history_uses_the_step_valid_on_the_day`, `::test_exceptions_survive_a_role_change`, `tests/test_integration.py::test_returning_to_the_household_weekend_keeps_the_past` (#11).
3. **Die Bibliothek und die reinen Module importieren nichts aus Home Assistant; die Integration erreicht die API nur über die Bibliothek** — `tests/test_quality.py::test_pure_modules_and_library_import_nothing_from_home_assistant`, `tests/test_vendor.py::test_vendored_openholidays_is_in_sync`.
4. **Keine Hausdaten im Repository und in der Historie; Autoren nur No-Reply** — `tools/check_publication.py --areas` in `bin/check` (0 Befunde Pflicht).
5. **Der Tag wechselt um Mitternacht auch bei Fehlern** — `tests/test_integration.py::test_midnight_rebuild`, `::test_midnight_survives_a_public_holiday_error`.
6. **Höchstens ein Abruf je 30 Tage und Quelle, Fenster ≤ 1095 Tage, eigener User-Agent mit Manifest-Version** — `tests/test_quality.py::test_school_holidays_are_fetched_after_boot_and_checked_daily`, `::test_user_agent_reports_the_manifest_version`, `lib/openholidays/tests/test_client.py::test_school_holidays_sends_the_right_query_and_user_agent`, `::test_long_ranges_are_fetched_in_windows_of_at_most_1095_days`.
7. **Karten lesen nur Entitäten und Dienste mit Antwort; `frontend.py` ist die einzige Auslieferung** — `tests/test_quality.py::test_cards_are_registered_once_when_the_frontend_is_loaded`, `::test_frontend_is_the_only_delivery_and_there_is_no_websocket_api`.
8. **Mit `admin_only` ändern nur Administratoren Daten; Lesen bleibt für alle** — `tests/test_integration.py::test_admin_only_blocks_non_admins`.
9. **Diagnose enthält Zählungen und Konfiguration, nie Namen oder IDs** — `tests/test_quality.py::test_diagnostics_hold_counts_but_no_names`.
10. **Blockierendes läuft im Executor** (python-holidays, Dateizugriff) — `tests/test_config_flow.py::test_the_holidays_library_never_runs_in_the_event_loop`, `tests/test_quality.py::test_cards_are_registered_once_when_the_frontend_is_loaded` (Bundle-Prüfung im Executor).
11. **Version an genau einer Stelle** — `tests/test_quality.py::test_user_agent_reports_the_manifest_version`, `tests/test_cards_build.py`.
12. **Der Store ist versioniert; Migrationen sind additiv; ein neuerer Store wird abgelehnt, nie überschrieben** — `tests/test_sources_storage.py::test_version_1_data_reads_as_version_2`, `::test_newer_version_is_refused`, `tests/test_quality.py::test_unreadable_store_and_unsupported_country_fail_the_setup`, `::test_a_store_with_missing_keys_fails_the_setup_with_the_translated_reason`.
13. **Ein Raum ist seine Bewohner: ohne Zuweisung keine Entitäten** — `tests/test_quality.py::test_a_rule_alone_does_not_create_a_room`, `::test_rooms_without_residents_are_dropped_when_loading`.
14. **Jeder Fehlerschlüssel ist in DE und EN übersetzt** — `tests/test_quality.py::test_every_error_key_is_translated`.

## 9 · Löschkonzept (REC-02)

| Daten | Inhalt | Frist | Durchsetzung |
|---|---|---|---|
| Store `.storage/werktage.data` | Bewohner, Räume, Ausnahmen, Haus, Schulferien-Cache | bis zum Entfernen der Integration | `async_remove_entry` löscht die Datei — `tests/test_quality.py::test_removing_the_integration_deletes_the_store` |
| Ausnahmen (manuelle Tage) | Datum → Person → Typ | bis der Nutzer sie zurücksetzt (`set_days status: default`) oder die Person `none` wird (Einträge bleiben, Entität wird `unavailable`) | Nutzer; keine automatische Frist, weil Historie (3.4) |
| Historienschritte (Rollen, Räume, Wochenmuster, Haus) | `valid_from` + Wert | unbegrenzt (prüfbare Vergangenheit); Schritt entfernbar über `remove_role`, `remove_room_assignment` | Nutzer |
| Schulferien-Cache | Perioden (öffentliche Daten), `fetched_at` | frühere Jahre bleiben; Quelle wechseln verwirft den Cache der alten Quelle | monatlicher Abruf ersetzt die drei aktuellen Jahre |
| Geräte verschwundener Bewohner/Räume | Register-Einträge | bis der Nutzer sie im Gerätedialog löscht | `async_remove_config_entry_device` erlaubt nur verschwundene — `tests/test_quality.py::test_only_devices_of_vanished_residents_and_rooms_may_be_deleted` |
| Logs | Warnungen/Fehler mit IDs, nie Namen | HA-Logrotation | Home Assistant |
| Diagnose-Download | Zählungen, Konfiguration | erzeugt auf Anforderung, nicht gespeichert | — |

## 10 · Bedrohungsmodell light (SEC-01) und Berechtigungsmatrix (SEC-17)

**Werte:** Abwesenheitsmuster des Haushalts (wer ist wann nicht zuhause), Personen- und Bereichs-IDs, Schulferien-Cache (öffentlich). **Vertrauensgrenze:** die Home-Assistant-Anmeldung; alles innerhalb von HA ist vertraut, alles von außen (API-Antworten, Kalenderinhalte) nicht.

| Eingang | Angreifer | Gegenmaßnahme |
|---|---|---|
| Dienste `werktage.*` (WebSocket/REST über HA) | Mitglied ohne Adminrechte | `voluptuous`-Schema je Dienst; Option `admin_only` prüft `context.user_id` bei jedem Schreibdienst (`services.py`); Lesedienste für alle |
| Config-Flow und Optionen | — | nur HA-Administratoren (HA-Regel); Eingaben validiert (Land, Region, Datumsformat, Kalender existiert) |
| OpenHolidays-Antwort | manipulierte oder fehlerhafte Daten | Schema-Prüfung in `lib/openholidays/models.py`; Plausibilität (Sommerferien je Jahr) vor Übernahme; Namen werden in den Karten maskiert (`esc()`) |
| Kalender-Entität als Quelle | Fremdtitel aus geteilten Kalendern | nur ganztägige Ereignisse; Titel maskiert; Fehler an der Grenze gefangen (`FetchFailed`) |
| Statischer Pfad `/werktage_static/` | Fremder ohne Login | liefert nur das Bundle (ohne Daten); kein Verzeichnis-Listing; Cache-Header |
| Diagnose-Download | Mitbewohner mit Adminrechten | enthält keine Namen, keine IDs (Invariante 9) |
| Store-Datei | Mitbewohner mit Dateizugriff | außerhalb des Modells (wer `.storage` lesen kann, hat alle HA-Daten); beschädigte Datei → `store_unreadable`, nie Teilzustand |

| Rolle | Lesen (Sensoren, Kalender, `get_*`) | Schreiben (`set_*`, `remove_*`, `refresh_*`) | Einrichten (Flow, Optionen) |
|---|---|---|---|
| HA-Administrator | ja | ja | ja |
| HA-Nutzer, `admin_only` aus | ja | ja | nein |
| HA-Nutzer, `admin_only` an | ja | nein (`ServiceValidationError`) | nein |
| Nicht angemeldet | nein (HA-Auth); nur das Karten-Bundle | nein | nein |

Sicherheitsabnahme: Invarianten 8 und 9 im Tor; keine eigene Authentifizierung, keine Geheimnisse, keine Kryptografie. Meldeweg in `SECURITY.md`.
