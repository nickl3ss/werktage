#!/usr/bin/env python3
"""Check that no private household data ended up in the repository.

Reads the names of the people defined in the local Home Assistant installation
at run time (nothing private is stored in this script), plus extra terms from
the untracked file `.publication-terms` (one per line, e.g. handles, domains or
place names), and searches every file git would publish for them, plus private
IP addresses, MAC addresses and e-mail addresses. The whole history (every
diff and commit message on every branch) is searched as well, because a term
that was removed later is still published with the history. Also checks that
every commit author and committer uses a GitHub no-reply address.

    python3 tools/check_publication.py [--storage /config/.storage] [--areas] [--terms FILE] [--no-history]

Exit code 0: nothing found. Exit code 1: findings are listed.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Fictitious names used in tests and examples; never reported.
ALLOWED_NAMES = {"anna", "ben", "clara", "david", "emil"}

# Public addresses that may appear in files and commits.
ALLOWED_EMAILS = {"noreply@anthropic.com", "noreply@github.com"}

PATTERNS = {
    "private IPv4 address": re.compile(
        r"\b(?:10|192\.168|172\.(?:1[6-9]|2\d|3[01]))\.\d{1,3}\.\d{1,3}(?:\.\d{1,3})?\b"),
    "MAC address": re.compile(r"\b[0-9a-f]{2}(?::[0-9a-f]{2}){5}\b", re.IGNORECASE),
    "e-mail address": re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"),
}


# File names like "icon@2x.png" look like e-mail addresses.
IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".svg", ".webp", ".gif")


def is_allowed(value: str) -> bool:
    """Public addresses and image file names that the generic patterns match."""
    return (value in ALLOWED_EMAILS or value.endswith("@users.noreply.github.com")
            or value.lower().endswith(IMAGE_SUFFIXES))


def published_files() -> list[Path]:
    """Tracked files plus untracked files that are not ignored."""
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=ROOT, capture_output=True, text=True, check=True,
    )
    return [ROOT / line for line in result.stdout.splitlines() if line]


def private_names(storage: Path, with_areas: bool) -> set[str]:
    """First and last names of all persons (and optionally area names)."""
    names: set[str] = set()
    person_file = storage / "person"
    if person_file.exists():
        for item in json.loads(person_file.read_text(encoding="utf-8"))["data"]["items"]:
            names.update(part.lower() for part in item["name"].split() if len(part) >= 3)
    if with_areas:
        area_file = storage / "core.area_registry"
        if area_file.exists():
            for area in json.loads(area_file.read_text(encoding="utf-8"))["data"]["areas"]:
                names.add(area["name"].lower())
    return names - ALLOWED_NAMES


def extra_terms(path: Path) -> set[str]:
    """Additional private terms from a local, untracked file (one per line, # comments)."""
    if not path.exists():
        return set()
    lines = (line.split("#", 1)[0].strip().lower() for line in path.read_text(encoding="utf-8").splitlines())
    return {line for line in lines if line}


def history_findings(name_pattern: re.Pattern[str] | None) -> list[tuple[str, str, str]]:
    """Private names and generic patterns in added lines and messages of every commit."""
    result = subprocess.run(
        ["git", "log", "--all", "-p", "--no-color", "--format=%x00%H%n%B"],
        cwd=ROOT, capture_output=True, text=True, errors="replace", check=False,
    )
    findings: dict[tuple[str, str, str], None] = {}
    commit = ""
    for line in result.stdout.splitlines():
        if line.startswith("\0"):
            commit = line[1:13]
            continue
        if line.startswith(("-", "diff --git", "index ", "@@")):
            continue                                   # removed lines were published by an earlier added line
        if name_pattern and (match := name_pattern.search(line)):
            findings[(commit, "name", match.group(0))] = None
        for label, pattern in PATTERNS.items():
            for match in pattern.finditer(line):
                value = match.group(0)
                if is_allowed(value):
                    continue
                findings[(commit, label, value)] = None
    return list(findings)


def private_commit_emails() -> set[str]:
    """Author and committer addresses in the history that are not GitHub no-reply."""
    result = subprocess.run(
        ["git", "log", "--all", "--format=%ae%n%ce"], cwd=ROOT, capture_output=True, text=True, check=False,
    )
    return {e for e in result.stdout.split() if e and not e.endswith("@users.noreply.github.com")
            and e not in ALLOWED_EMAILS}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--storage", type=Path, default=Path("/config/.storage"),
                        help="Home Assistant .storage directory (default: /config/.storage)")
    parser.add_argument("--areas", action="store_true", help="also search for area names")
    parser.add_argument("--terms", type=Path, default=ROOT / ".publication-terms",
                        help="untracked file with extra private terms (default: .publication-terms)")
    parser.add_argument("--no-history", action="store_true", help="only check the files, not the git history")
    args = parser.parse_args()

    names = private_names(args.storage, args.areas) | (extra_terms(args.terms) - ALLOWED_NAMES)
    if not names:
        print(f"warning: no names found in {args.storage}; only generic patterns are checked")
    name_pattern = (re.compile(r"\b(" + "|".join(map(re.escape, sorted(names))) + r")\b", re.IGNORECASE)
                    if names else None)

    findings = []
    for path in published_files():
        if not path.is_file() or path.name in {"LICENSE", "NOTICE"}:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for number, line in enumerate(text.splitlines(), start=1):
            if name_pattern and (match := name_pattern.search(line)):
                findings.append((path, number, "name", match.group(0)))
            for label, pattern in PATTERNS.items():
                for match in pattern.finditer(line):
                    value = match.group(0)
                    if is_allowed(value):
                        continue
                    findings.append((path, number, label, value))

    if not args.no_history:
        for commit, label, value in history_findings(name_pattern):
            findings.append((ROOT / ".git", 0, f"history {commit}: {label}", value))

    for email in sorted(private_commit_emails()):
        findings.append((ROOT / ".git", 0, "commit e-mail (not no-reply)", email))

    for path, number, label, value in findings:
        print(f"{path.relative_to(ROOT)}:{number}: {label}: {value}")
    print(f"{len(findings)} finding(s) in {len(published_files())} file(s), "
          f"{len(names)} private name(s) or term(s) checked")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
