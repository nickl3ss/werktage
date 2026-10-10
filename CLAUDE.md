# Werktags — Hinweise für die Arbeit in diesem Repository

Custom Integration für Home Assistant: Werktage je Person mit Schulferien,
Ausnahmen, Raum- und Hausmodi. Lizenz MIT. Das Repository ist **öffentlich**
auf GitHub (`github.com/nickl3ss/werktage`) und wird als HACS-Repository
entwickelt; alles darin kann jederzeit von jedem gelesen werden.

## Verbindliche Regeln

1. **Keine Hausdaten im Repository.** Keine echten Namen, Personen-IDs,
   Bereichsnamen, IP-Adressen oder freien Tage — weder im Code noch in Tests,
   Beispielen oder Commit-Nachrichten. Tests und Beispiele benutzen erfundene
   Namen (Anna, Ben, Clara, David, Emil). Vor jedem Commit:
   `python3 tools/check_publication.py`.
2. **Spezifikation:** [docs/specification.md](docs/specification.md)
   (englisch, allgemein, Produktentscheidungen P1–P32). Abweichungen werden
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
   Quality Scale; Stand ist **Platinum** (`quality_scale.yaml`: jede Regel
   `done` oder begründet `exempt`), und das bleibt bei jeder Änderung so.
6. **Daten der OpenHolidays API** stehen unter ODbL 1.0: keine echten
   Ferientermine ins Repository, Namensnennung als `attribution`, höchstens
   ein Abruf im Monat mit eigenem `User-Agent` (Spezifikation Abschnitt 4).
7. **Fehlende Daten** gelten wie ein Werktag, mit `reason: unknown` — nie
   stillschweigend frei.

## Entwickeln und prüfen

    python3 -m venv .venv && .venv/bin/pip install -e lib/openholidays "holidays>=0.60" pytest-homeassistant-custom-component mypy ruff pytest-cov
    # unter Windows: .venv/Scripts/python statt .venv/bin/python; node bekommt die Testdateien einzeln.
    # Home Assistant importiert fcntl: tests/test_integration.py, test_config_flow.py, test_quality.py und die
    # Blueprint-Tests laufen nur unter Linux (WSL, Container oder die CI). Ohne HA laufen:
    # PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -p asyncio -p pytest_socket lib/openholidays/tests
    # PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -p asyncio --noconftest tests/test_rules.py tests/test_sources_storage.py tests/test_cards_build.py tests/test_vendor.py
    .venv/bin/python -m pytest -q          # Regeln, Integration (tests/) und Bibliothek (lib/openholidays/tests)
    python3 tools/sync_vendor.py            # nach jeder Aenderung an lib/openholidays
    python3 tools/build_cards.py            # nach jeder Aenderung an frontend/src
    node --test frontend/test/*.test.mjs    # Karten browserlos (Node, z. B. apk add nodejs)
    # CI-Ergebnis eines Commits (Token aus einer lokalen Datei, nie ausgeben):
    GH_TOKEN="$(sed -n 's/^GH_TOKEN=//p' <Token-Datei>)" .venv/bin/python tools/ci_status.py <sha>
    # hassfest: sparse checkout von home-assistant/core (script/hassfest, script/translations, script/util)
    # im Scratchpad, dann dort: PATH=.venv/bin:$PATH .venv/bin/python -m script.hassfest --action validate \
    #   --integration-path <Repository>/custom_components/werktage
    .venv/bin/ruff check .                  # Lint, 120 Zeichen
    .venv/bin/python -m mypy                # strict, Integration und Bibliothek
    python3 tools/check_publication.py --areas
    # Mindestversion (hacs.json "homeassistant") pruefen: eigene venv mit Python 3.13 und
    # pytest-homeassistant-custom-component==0.13.308 (HA 2026.1.3), wie der CI-Job minimum-ha

Alle müssen vor einem Commit sauber sein. `rules.py`, `sources.py` und
`storage.py` importieren nichts aus Home Assistant und sind auch ohne das
HA-Testpaket prüfbar.

## Ausrollen in die eigene Installation

`./deploy.sh <Konfigurationsverzeichnis>` kopiert `custom_components/werktage/`
(samt der einkopierten Bibliothek) dorthin; der Zielpfad ist ein Argument und
steht nicht im Repository. Danach `ha core check` und Neustart; eingerichtet
wird über *Einstellungen → Integrationen → Werktags*.

## Veröffentlichung

Remote `origin` = `github.com/nickl3ss/werktage` (öffentlich). Entwickelt wird
in einem eigenen Arbeitsverzeichnis, nicht auf dem Home-Assistant-Host; der
Host installiert nur veröffentlichte Tags (`git archive <tag>`, dann
`deploy.sh` aus diesem Stand). Pushen, Taggen und Releases entscheidet der
Eigentümer. Commits laufen
unter der anonymen GitHub-Adresse (`git config user.email`), damit keine
private E-Mail-Adresse in der Historie steht; `tools/check_publication.py`
prüft das mit. Das Skript durchsucht auch die gesamte Historie (Diffs und
Commit-Nachrichten); weitere private Suchbegriffe (Handles, Domains, Orte)
stehen zeilenweise in der lokalen, ignorierten Datei `.publication-terms`.
