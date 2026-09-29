# Werktags — Hinweise für die Arbeit in diesem Repository

Custom Integration für Home Assistant: Werktage je Person mit Schulferien,
Ausnahmen, Raum- und Hausmodi. Lizenz MIT. Das Repository liegt **privat** auf
GitHub (`github.com/nickl3ss/werktags`) und wird so gehalten, dass es
jederzeit öffentlich werden kann.

## Verbindliche Regeln

1. **Keine Hausdaten im Repository.** Keine echten Namen, Personen-IDs,
   Bereichsnamen, IP-Adressen oder freien Tage — weder im Code noch in Tests,
   Beispielen oder Commit-Nachrichten. Tests und Beispiele benutzen erfundene
   Namen (Anna, Ben, Clara, David, Emil). Vor jedem Commit:
   `python3 tools/check_publication.py`.
2. **Spezifikation:** [docs/specification.md](docs/specification.md)
   (englisch, allgemein, Produktentscheidungen P1–P28). Abweichungen werden
   dort nachgetragen. Wie eine bestimmte Installation eingerichtet wird, steht
   **nicht** hier, sondern bei der jeweiligen Installation.
3. **Englisch im Code**: Bezeichner, Kommentare, Docstrings, Log-Meldungen,
   Dienst- und Zustandsschlüssel. Deutsch und Englisch nur über
   `strings.json` und `translations/`.
4. **Drei Teile, sauber getrennt** (Spezifikation Abschnitt 1):
   - `lib/openholidays/` importiert nichts aus Home Assistant;
   - die Integration greift auf die API nur über diese Bibliothek zu;
   - Karten lesen nur über Entitäten und Dienste mit Antwort, keine eigene
     WebSocket-API, kein Panel. `frontend.py` ist die einzige Stelle, die
     Karten ausliefert.
5. **Kernfähig bauen**: Config Flow statt YAML, `has_entity_name`,
   Übersetzungen, stabile `unique_id`, Diagnose, Reparaturhinweise, Entladen
   ohne Neustart, Typangaben (`mypy --strict`), Tests mit
   `pytest-homeassistant-custom-component`. Leitlinie ist die Integration
   Quality Scale, Ziel Silber.
6. **Daten der OpenHolidays API** stehen unter ODbL 1.0: keine echten
   Ferientermine ins Repository, Namensnennung als `attribution`, höchstens
   ein Abruf im Monat mit eigenem `User-Agent` (Spezifikation Abschnitt 4).
7. **Fehlende Daten** gelten wie ein Werktag, mit `reason: unknown` — nie
   stillschweigend frei.

## Entwickeln und prüfen

    python3 -m venv .venv && .venv/bin/pip install -e lib/openholidays pytest pytest-asyncio aiohttp holidays mypy ruff
    .venv/bin/python -m pytest -q          # Regeln (tests/) und Bibliothek (lib/openholidays/tests)
    .venv/bin/ruff check .                  # Lint, 120 Zeichen
    .venv/bin/python -m mypy                # strict, Integration und Bibliothek
    python3 tools/check_publication.py --areas

Alle vier müssen vor einem Commit sauber sein. `custom_components/werktags/__init__.py`
bleibt ohne Home-Assistant-Import, solange die Integration nicht gebaut ist,
damit `rules.py` ohne Home Assistant testbar ist.

## Ausrollen in die eigene Installation

Noch nicht vorhanden. Geplant ist ein `deploy.sh`, das
`custom_components/werktags/` samt `lib/openholidays/` in das
`custom_components/`-Verzeichnis der Installation kopiert; der Zielpfad wird
als Argument übergeben, nicht im Repository festgeschrieben.

## Veröffentlichung

Remote `origin` = `github.com/nickl3ss/werktags` (privat), Zugriff über einen
Deploy-Key nur für dieses Repository. Commits laufen
unter der anonymen GitHub-Adresse (`git config user.email`), damit keine
private E-Mail-Adresse in der Historie steht; `tools/check_publication.py`
prüft das mit.
