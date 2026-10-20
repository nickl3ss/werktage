#!/usr/bin/env python3
"""Make the Home Assistant test suite importable on Windows (development only).

Home Assistant imports ``fcntl`` and ``resource``, which Python on Windows does not
have; both are used only in ``homeassistant.runner.run()``, never by the tests.
This script writes two stub modules into the active environment's site-packages
so that ``pytest`` can import Home Assistant. The event-loop socket shim lives in
``conftest.py`` at the repository root. Run once per virtual environment:

    .venv/Scripts/python tools/windows_dev.py
"""
from __future__ import annotations

import sys
import sysconfig
from pathlib import Path

STUBS = {
    "fcntl.py": '''"""Stub for Windows: Home Assistant locks a file in runner.run(), which tests never call."""
LOCK_EX = 2
LOCK_NB = 4
LOCK_UN = 8


def flock(fd, operation):
    raise OSError("fcntl.flock is not available on Windows")
''',
    "resource.py": '''"""Stub for Windows: Home Assistant raises RLIMIT_NOFILE only in runner.run()."""
RLIMIT_NOFILE = 7
RLIM_INFINITY = -1


def getrlimit(resource):
    return (RLIM_INFINITY, RLIM_INFINITY)


def setrlimit(resource, limits):
    return None
''',
}


def main() -> int:
    if sys.platform != "win32":
        print("not Windows: nothing to do")
        return 0
    target = Path(sysconfig.get_paths()["purelib"])
    for name, body in STUBS.items():
        path = target / name
        if path.exists():
            print(f"exists: {path}")
            continue
        path.write_text(body, encoding="utf-8")
        print(f"written: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
