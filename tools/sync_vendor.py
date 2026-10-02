#!/usr/bin/env python3
"""Copy the openholidays library into the integration (vendoring).

The library's source of truth is ``lib/openholidays/src/openholidays``. HACS
installs the integration folder as it is in the repository, so the integration
carries a verbatim copy in ``custom_components/werktage/openholidays``. Run this
after every change to the library; ``tests/test_vendor.py`` fails when the copy
is stale. The core version of the integration would drop the copy and list the
PyPI package in ``manifest.json`` instead.

    python3 tools/sync_vendor.py [--check]
"""
from __future__ import annotations

import filecmp
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "lib" / "openholidays" / "src" / "openholidays"
TARGET = ROOT / "custom_components" / "werktage" / "openholidays"


def differences() -> list[str]:
    if not TARGET.exists():
        return ["<missing>"]
    cmp = filecmp.dircmp(SOURCE, TARGET, ignore=["__pycache__"])
    return sorted(cmp.left_only + cmp.right_only + cmp.diff_files)


def main() -> int:
    if "--check" in sys.argv:
        diff = differences()
        print("vendored copy is up to date" if not diff else f"vendored copy is stale: {diff}")
        return 1 if diff else 0
    shutil.rmtree(TARGET, ignore_errors=True)
    shutil.copytree(SOURCE, TARGET, ignore=shutil.ignore_patterns("__pycache__"))
    print(f"copied {SOURCE.relative_to(ROOT)} -> {TARGET.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
