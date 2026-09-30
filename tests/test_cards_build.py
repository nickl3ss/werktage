"""The served card bundle must match the sources in frontend/src."""
from __future__ import annotations

import importlib.util
from pathlib import Path


def test_cards_bundle_is_in_sync():
    tool = Path(__file__).resolve().parents[1] / "tools" / "build_cards.py"
    spec = importlib.util.spec_from_file_location("build_cards", tool)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    target = module.TARGET
    assert target.exists(), "run tools/build_cards.py"
    assert target.read_text(encoding="utf-8") == module.bundle(), "run tools/build_cards.py"
