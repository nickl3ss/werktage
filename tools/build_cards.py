#!/usr/bin/env python3
"""Bundle the card sources into one file the integration serves.

``frontend/src/logic.js`` (pure functions) and ``frontend/src/cards.js`` (the
custom elements) are joined into ``custom_components/werktage/www/werktags-cards.js``:
the ``export`` keywords and the ``import`` line disappear, the result is one
classic script wrapped in an IIFE. No bundler, no dependencies.

    python3 tools/build_cards.py [--check]
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "frontend" / "src"
TARGET = ROOT / "custom_components" / "werktage" / "www" / "werktags-cards.js"
MANIFEST = ROOT / "custom_components" / "werktage" / "manifest.json"


def bundle() -> str:
    version = json.loads(MANIFEST.read_text(encoding="utf-8"))["version"]
    logic = (SRC / "logic.js").read_text(encoding="utf-8")
    cards = (SRC / "cards.js").read_text(encoding="utf-8")
    logic = re.sub(r"^export (?=(function|const|let|class) )", "", logic, flags=re.MULTILINE)
    cards = re.sub(r"^import \{[^}]*\} from \"\./logic\.js\";\n", "", cards, flags=re.MULTILINE | re.DOTALL)
    return (f"/* Werktags cards v{version} — built from frontend/src by tools/build_cards.py. Do not edit. */\n"
            f"(() => {{\n\"use strict\";\n{logic}\n{cards}\n}})();\n")


def main() -> int:
    built = bundle()
    if "--check" in sys.argv:
        current = TARGET.read_text(encoding="utf-8") if TARGET.exists() else ""
        print("cards bundle is up to date" if current == built else "cards bundle is stale: run tools/build_cards.py")
        return 0 if current == built else 1
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text(built, encoding="utf-8")
    print(f"wrote {TARGET.relative_to(ROOT)} ({len(built)} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
