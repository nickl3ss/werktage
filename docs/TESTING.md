# TESTING — Werktage

> Manuelles Prüfprotokoll (TST-13). Automatischer Teil: `bin/check`. Hier steht nur, was eine Maschine nicht prüfen kann: Sichtprüfung im Dashboard, Companion-App, Handy-Breite, Optionen-Dialoge in Home Assistant. Bei jeder nutzersichtbaren Änderung im selben Commit aktualisieren (Schritt D4). Nach bestätigtem Test wandern die Schritte in die Regressionssuite (`docs(testing): Abschnitt „Neu seit dem letzten Push“ nach bestätigtem Test geleert`).

Testumgebung: ein Home Assistant ≥ 2026.1 mit der installierten Version aus dem Tag (nie die Arbeitskopie), ein Handy mit der Companion-App, der Haushalt aus `tests/conftest.py` (Anna, Ben, Clara; Räume Bedroom, Nursery, Kitchen) oder ein eigener.

## Neu seit dem letzten Push

### N1 · Review 2026-10-20 — Anzeigename „Werktage“ (#6, P35)

| # | Schritt | Erwartet |
|---|---|---|
| N1-1 | HACS → Suche „Werktage“ | Eintrag heißt *Werktage*, Beschreibung aus `hacs.json` |
| N1-2 | *Einstellungen → Geräte & Dienste → Integration hinzufügen* | Eintrag *Werktage*, Icon sichtbar (nur `icon.png` im Paket, Logo aus dem Icon abgeleitet) |
| N1-3 | Bestehende Installation nach dem Update | Entitäts-IDs, Karten (`custom:werktags-*`) und Daten unverändert |

### N2 · Zielgrößen in der Kalenderkarte (UX-2)

| # | Schritt | Erwartet |
|---|---|---|
| N2-1 | Kalenderkarte am Handy (Breite ≤ 600 px, Listenansicht) | Datum-Schaltfläche und Kürzel-Schalter sind mit dem Daumen treffbar (≥ 24 px), Chip-✕ ebenso |
| N2-2 | Rasteransicht (Breite > 600 px) | Zellen nicht höher als zuvor, Schalter 32 px hoch |

### N3 · Kürzel zu lang im Optionen-Dialog (UX-1)

| # | Schritt | Erwartet |
|---|---|---|
| N3-1 | *Werktage → Konfigurieren → Bewohner hinzufügen oder ändern*, Kürzel „ABC“ | Fehltext „ein oder zwei Zeichen“ (DE) bzw. „one or two characters“ (EN), nicht „bereits vergeben“ |

### N4 · Statuszeile der Kalenderkarte

| # | Schritt | Erwartet |
|---|---|---|
| N4-1 | Kalenderkarte, Zeile unter der Legende | Nennt Quelle, „bekannt bis“ und den Zeitpunkt des letzten Abrufs |

### N5 · Schulferienquelle je Bewohner (#1)

| # | Schritt | Erwartet |
|---|---|---|
| N5-1 | Bewohnerkarte: bei einem Schüler *Schulferien wie* auf eine andere Region stellen, *Übernehmen* | Kalenderkarte markiert für diesen Schüler die Ferien der anderen Region; die übrigen Bewohner unverändert; Statuszeile unverändert (Quelle der Installation) |
| N5-2 | *Werktage → Konfigurieren → Bewohner*: Feld *Schulferien wie* zeigt Regionen des Landes und Kalender-Entitäten (nicht die eigenen Werktage-Kalender) | Auswahl wird gespeichert; Reparaturhinweise nennen die Quelle |
| N5-3 | Quelle wieder auf *wie die Installation* | Ferien folgen wieder der Installation; nach *Schulferien aktualisieren* verschwindet die Quelle aus `get_overview` → `status.sources` |

### N6 · Schulferien-Kalender am Haus (#14)

| # | Schritt | Erwartet |
|---|---|---|
| N6-1 | `calendar.<haus>_school_holidays` in der Kalender-Ansicht von Home Assistant | ganztägige Ereignisse mit den Ferien-Namen der Quelle der Installation |
| N6-2 | Quelle *keine* in den Einstellungen | Entität verschwindet nach dem Neuladen |

### N7 · Persönliche Kalender als Quelle freier Tage (#2)

| # | Schritt | Erwartet |
|---|---|---|
| N7-1 | Bewohnerkarte: *Freie Tage aus Kalender* auf einen eigenen Kalender stellen, Stichwort „Urlaub“, *Übernehmen* | Ganztägige Urlaubstermine erscheinen in der Kalenderkarte als frei mit gepunktetem Rand; Termine ohne Stichwort und Termine mit Uhrzeit nicht |
| N7-2 | Einen Kalendertag in der Kalenderkarte antippen | Tag wird zur Ausnahme (Werktag, gelber Rand); erneut antippen → wieder Kalendertag, keine Ausnahme gespeichert |
| N7-3 | Termin im Kalender verschieben, 30 s warten | Kalenderkarte folgt ohne Neuladen der Integration |
| N7-4 | Kalender-Integration stoppen, Tag abwarten | Tage bleiben wie zuletzt gelesen, Warnung im Protokoll, kein „unbekannt“ |
| N7-5 | *Werktage → Konfigurieren → Bewohner* ohne Kalenderfelder speichern | Kalender der Person entfernt |

## Regressionssuite

Vor jedem Release vollständig, nach jedem Push die betroffenen Abschnitte.

### R0 · Start und Grundlagen

| # | Schritt | Erwartet |
|---|---|---|
| R0-1 | `bin/check` | grün |
| R0-2 | Neue Installation: Integration hinzufügen, fünf Schritte durchlaufen | Eintrag *Werktage* mit Haus-Gerät; Kalenderkarte zeigt Leerzustand mit nächstem Schritt („Bewohner hinzufügen“) (UX-11) |
| R0-3 | Erste Karte auf einem Dashboard einfügen, Seite neu laden | Karte rendert; ohne Neuladen „Konfigurationsfehler“ (Skript-URL ist Teil der Seite) — dokumentiert in README |
| R0-4 | Integration entladen und neu laden (*Neu laden* im Eintrag) | Entitäten bleiben, kein Fehler im Log |
| R0-5 | Integration entfernen | Store `.storage/werktage.data` gelöscht, Geräte entfernt |

### R1 · Kernaufgabe 1 — einen Tag frei schalten (1 Tipp)

| # | Schritt | Erwartet |
|---|---|---|
| R1-1 | Kalenderkarte, Kürzel eines Bewohners an einem Werktag tippen | Schalter sofort markiert (optimistisch), Sensor `sensor.<name>_morning` wechselt auf `day_off`, `reason: exception` |
| R1-2 | Denselben Schalter erneut tippen | zurück zum Standard; `reason` wieder `weekday`/`weekend`/… |
| R1-3 | Kürzel an einem Wochenendtag tippen | Rückfrage „alle arbeiten am freien Tag“ nur beim Haus-Schalter; Einzelperson wird Werktag |
| R1-4 | Tag in der Vergangenheit tippen | ohne Rückfrage (P28 Einzeltage) |

### R2 · Kernaufgabe 2 — Zeitraum setzen (3 Interaktionen)

| # | Schritt | Erwartet |
|---|---|---|
| R2-1 | Zeitraumkarte: Person, Bis-Datum, *Übernehmen* | Vorschau nennt Anzahl Tage; danach Ausnahmen gesetzt |
| R2-2 | Von > Bis | Validierungsfehler in der Karte, kein Dienstaufruf |

### R3 · Kernaufgabe 3 — Morgenstatus ablesen

| # | Schritt | Erwartet |
|---|---|---|
| R3-1 | `sensor.<name>_morning`, `_evening`, `binary_sensor.<name>_workday` je Bewohner, Raum, Haus | Attribute `reason`, `holiday_name`, `next_workday`, `next_day_off`; Räume und Haus zeigen `residents` und `rule` |
| R3-2 | Blueprint *Morgens öffnen* mit einem Cover anlegen | Automation läuft an der Uhrzeit des Tagesstatus |
| R3-3 | 00:00:10 abwarten (oder Uhr stellen) | Sensoren wechseln den Tag; bei Feiertagsfehler Logeintrag, Tag wechselt trotzdem (P33) |

### R4 · Bewohner, Räume, Haus (Optionen-Menü und Karten)

| # | Schritt | Erwartet |
|---|---|---|
| R4-1 | *Konfigurieren → Bewohner*: Rolle Schüler ab Datum, Kürzel | Bewohnerkarte zeigt ihn; `calendar.<name>_days_off` listet Ferien |
| R4-2 | Wochenmuster (freie Wochentage) setzen, dann „wie Haushalt“ | Rückfrage bei rückwirkendem Datum; Vergangenheit unverändert (#11) |
| R4-3 | Raum zuweisen, Regel wechseln | Raum-Sensor folgt der Regel; Raum ohne Bewohner hat keine Entitäten |
| R4-4 | Hausbewohner explizit wählen, dann „nach Rolle“ | Haus folgt der Auswahl ab `valid_from`; frühere Tage unverändert |

### R5 · Schulferien und Feiertage

| # | Schritt | Erwartet |
|---|---|---|
| R5-1 | Quelle OpenHolidays, Land/Region wählen | Prüfabruf beim Einrichten; Statuszeile „bekannt bis“ |
| R5-2 | Quelle *Kalender* mit einem Kalender ganztägiger Ereignisse | Ferien aus dem Kalender; Attribution leer |
| R5-3 | Netz trennen, *Schulferien aktualisieren* aufrufen | Reparaturhinweis nach drei Fehlschlägen; Tage bleiben Werktag mit `reason: unknown` nur außerhalb des bekannten Bereichs |
| R5-4 | Zusätzlicher Feiertag `YYYY-MM-DD Name` in den Einstellungen | Tag frei mit `holiday_name`; entfernter Feiertag wird Werktag |

### R6 · Update und Rollback (OPS-02, `docs/BETRIEB.md`)

| # | Schritt | Erwartet |
|---|---|---|
| R6-1 | HACS: neue Version herunterladen, Neustart | Daten erhalten; bei Store-Migration Logzeile mit alter und neuer Version |
| R6-2 | HACS: vorherige Version erneut herunterladen | Nur zulässig, wenn die Store-Version nicht gestiegen ist; sonst `.storage/werktage.data` aus dem Backup zurückspielen (BETRIEB.md § Rollback) |

### R8 · Companion-App

| # | Schritt | Erwartet |
|---|---|---|
| R8-1 | Dashboard mit Karten in der App öffnen | Karten rendern wie im Browser |
| R8-2 | Nach einem Update „Konfigurationsfehler“ auf jeder Karte | Einmal *Einstellungen → Companion-App → Fehlerbehebung → Frontend-Cache zurücksetzen*; danach normal (README, Hinweis 0.2.1) |

### R9 · Barrierefreiheit und Mobile (UX-08, UX-09)

| # | Schritt | Erwartet |
|---|---|---|
| R9-1 | Kalenderkarte nur mit Tastatur | Schalter per Tab erreichbar, `role="switch"`, Fokus sichtbar, Leertaste schaltet |
| R9-2 | Breite 360 px | Listenansicht, kein horizontales Scrollen |
| R9-3 | Dunkles Theme | Legende und Schalter lesbar (Kontrast), gestreifte „teilweise“-Fläche erkennbar |

## Protokoll je Issue (Abnahme)

### #6 · Anzeigename Werktage
- [ ] N1-1 bis N1-3 — Beleg: Screenshot HACS und Integrationsliste
