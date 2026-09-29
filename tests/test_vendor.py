"""The vendored copy of the openholidays library must match its source of truth."""
from __future__ import annotations

import importlib.util
from pathlib import Path


def test_vendored_openholidays_is_in_sync():
    tool = Path(__file__).resolve().parents[1] / "tools" / "sync_vendor.py"
    spec = importlib.util.spec_from_file_location("sync_vendor", tool)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.differences() == [], "run tools/sync_vendor.py"
