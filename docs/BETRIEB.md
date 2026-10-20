# BETRIEB — Werktage

> Betriebshandbuch (OPS-10): Ausrollen, Update, Rollback, Backup, Logs, häufige Fehler, Release-Ablauf. Die Integration läuft im Home Assistant des Nutzers; es gibt keinen Server des Autors.

## 1 · Ausrollen

| Weg | Befehl / Klick | Wann |
|---|---|---|
| HACS (Standardliste) | HACS → Suche *Werktage* → Herunterladen → Home Assistant neu starten | normale Installation und jedes Update |
| Von Hand | `custom_components/werktage/` aus dem Release-Archiv in `<config>/custom_components/` kopieren, Neustart | ohne HACS |
| Entwicklerhost des Autors | `git archive <tag> \| tar -x -C <tmp>` → `<tmp>/deploy.sh /homeassistant` → `ha core check` → `ha core restart` | **nur Tags**, nie die Arbeitskopie (CLAUDE.md § Git) |

`deploy.sh <config>` kopiert nur die Integration (samt der einkopierten Bibliothek) und prüft vorher `tools/sync_vendor.py --check`. Der Zielpfad ist ein Argument und steht nicht im Repo. Ein Neuladen des Eintrags lädt keinen neuen Code; nach jeder Codeänderung ist ein Neustart nötig.

**Gesundheit nach dem Start:** Eintrag *Werktage* ist *geladen*; `sensor.<haus>_morning` hat einen Zustand; keine Reparaturhinweise der Integration; `custom_components.werktage` ohne `ERROR` im Protokoll. Die Karten laden unter `/werktage_static/werktags-cards.js?v=<hash>` (Entwicklerwerkzeuge des Browsers → Netzwerk).

## 2 · Update

1. CHANGELOG des Releases lesen (Breaking Changes stehen mit Migrationsanleitung oben).
2. HACS → *Werktage* → neue Version → Neustart.
3. Der Store `.storage/werktage.data` wird beim ersten Start migriert (`DATA_VERSION` in `storage.py`; Logzeile `Migrated store from version N to M`). Eine Migration ist additiv und läuft genau einmal.
4. Companion-App: zeigt sie nach einem Update auf jeder Karte *Konfigurationsfehler*, einmal *Einstellungen → Companion-App → Fehlerbehebung → Frontend-Cache zurücksetzen* (Seite aus der Zeit vor 0.2.0 lädt noch `/werktags_static/`).

## 3 · Rollback

| Fall | Schritte |
|---|---|
| Store-Version unverändert (siehe CHANGELOG) | HACS → *Werktage* → *Erneut herunterladen* → vorherige Version wählen → Neustart. Daten bleiben. |
| Store-Version gestiegen | Ältere Versionen lesen den neuen Store nicht (`store_unreadable`, Eintrag geht auf *Fehler*). Vor dem Rollback `.storage/werktage.data` aus dem Home-Assistant-Backup von vor dem Update zurückspielen (Backup → Wiederherstellen → nur `.storage` oder Datei von Hand ersetzen bei gestopptem Core), dann die ältere Version herunterladen und neu starten. |
| Ohne HACS | Vorheriges Release-Archiv entpacken, Verzeichnis ersetzen, Neustart. |

Der Rollback-Pfad ist noch nicht geprobt; beim nächsten Update auf dem Host einmal durchführen und hier das Datum eintragen (`docs/TESTING.md` R6-2).

## 4 · Backup

Alle Daten der Integration liegen in `.storage/werktage.data` (Bewohner, Räume, Haus, Ausnahmen, Schulferien-Cache) und im Config-Eintrag (`.storage/core.config_entries`). Beide sind Teil des normalen Home-Assistant-Backups. Ein eigenes Backup gibt es nicht (Ausnahme OPS-05 in `standards.yaml`). Nach einem Verlust: Backup einspielen; ohne Backup Bewohner, Räume und Ausnahmen über das Optionen-Menü oder die Dienste neu anlegen; der Schulferien-Cache wird beim nächsten Abruf neu gefüllt.

## 5 · Logs

| Logger | Inhalt |
|---|---|
| `custom_components.werktage` | Warnungen (je einmal, bis es wieder geht): Schulferienquelle nicht abrufbar, persönliche Kalender nicht lesbar, Export in den Zielkalender fehlgeschlagen; ignorierte Feiertagseinträge; Fehler: Feiertage zu Mitternacht nicht berechenbar (Tag wechselt trotzdem, P33) |
| `custom_components.werktage.frontend` | Debug: Karten nicht ausgeliefert (kein Frontend, kein Bundle) |
| `openholidays` (Bibliothek) | Debug: Anfragen mit Zeitraum |

Debug einschalten: *Einstellungen → Geräte & Dienste → Werktage → Debug-Protokollierung aktivieren* oder in `configuration.yaml`:

```yaml
logger:
  logs:
    custom_components.werktage: debug
```

Logs enthalten Personen-IDs und Bereichs-IDs, nie Namen oder freie Tage (REC-05); Diagnose-Downloads enthalten nur Zählungen und Konfiguration.

## 6 · Häufige Fehler

| Symptom | Ursache | Abhilfe |
|---|---|---|
| Jede Karte *Konfigurationsfehler* | Seite aus dem Cache lädt das alte Skript oder die Seite war vor der Einrichtung offen | Browser neu laden; Companion-App: Frontend-Cache zurücksetzen |
| Tage einer Person `reason: unknown` | Schulferien für den Zeitraum nicht bekannt (Quelle noch nicht abgerufen, außerhalb des bekannten Bereichs) | *Schulferien aktualisieren* aufrufen; Reparaturhinweis beachten; Tage gelten bis dahin als Werktag (P5) |
| Reparaturhinweis *Schulferien nicht erreichbar* | drei Abrufe in Folge fehlgeschlagen | Netz prüfen; `openholidaysapi.org` erreichbar? Hinweis verschwindet beim nächsten Erfolg |
| Reparaturhinweis *Schulferien unvollständig* | ab Oktober sind die Sommerferien des Folgejahres noch nicht veröffentlicht | wartet auf die Quelle; monatlicher Abruf holt sie nach |
| Eintrag *Fehler*: `store_unreadable` | Store von einer neueren Version oder von Hand beschädigt | Rollback-Tabelle oben; Datei aus dem Backup |
| Eintrag *Fehler*: `country_unsupported` | `holidays` kennt Land/Region nicht (nach HA-Update entfallen) | Region in den Einstellungen prüfen |
| Raum ohne Entitäten | Raum hat keinen zugewiesenen Bewohner („ein Raum ist seine Bewohner“) | Bewohner zuweisen |
| Reparaturhinweis *Freie Tage konnten nicht exportiert werden* | Zielkalender nimmt Termine nicht an (schreibgeschützte Freigabe, abgelaufene Zugangsdaten, Integration nicht geladen) | Freigabe und Zugangsdaten der Kalender-Integration prüfen oder in den Optionen einen anderen Kalender wählen; der Export wird nach jeder Änderung und täglich wiederholt |
| Persönlicher Kalender liefert keine freien Tage | Termine haben eine Uhrzeit, das Stichwort passt nicht, oder die Termine stammen aus dem eigenen Export (Marker) | ganztägige Termine ohne Marker; Stichwort prüfen; bei unlesbarem Kalender Warnung im Protokoll, letzte Tage bleiben |

## 7 · Release-Ablauf (OPS-16, PRO-16)

1. `## Unreleased` in `CHANGELOG.md` → `## x.y.z — Datum` mit den Rubriken Added / Changed / Fixed / Removed / Security und `Decision:`-Zeilen.
2. `manifest.json` `version` erhöhen; `const.VERSION` folgt (Test `test_user_agent_reports_the_manifest_version`).
3. README-Statuszeilen (EN und DE) anpassen.
4. `tools/build_cards.py` (Version im Bundle-Kopf).
5. `bin/check` grün; `/standards:review publish` (öffentliches Repo, Stufe Gold).
6. Commit `chore(int): release x.y.z`, Tag `x.y.z` (ohne `v`, Ausnahme PRO-16), `git push origin main x.y.z`.
7. CI abwarten (hassfest, HACS, `check`, `minimum-ha`).
8. GitHub-Release aus dem Tag (`gh release create x.y.z --verify-tag --title "Werktage x.y.z" --notes-file …`). Der Workflow `release.yml` hängt danach `werktage.zip` an (Tag muss der Manifest-Version entsprechen); HACS installiert aus diesem Asset (`hacs.json` `zip_release`) und GitHub zählt die Downloads (#7). Erst wenn das Asset da ist (etwa eine Minute), kann HACS die Version installieren.
9. Installation auf dem eigenen Host nur aus dem Tag (§ 1); `docs/TESTING.md § Regressionssuite` durchgehen.
10. Installierte Version im privaten Handoff des Hosts notieren.
