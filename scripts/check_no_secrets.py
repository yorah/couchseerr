#!/usr/bin/env python3
# scripts/check_no_secrets.py
"""Fail if anything that looks like real installation data reaches the repo."""
import pathlib
import re
import sys

PATTERNS = {
    "email": re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
    "private-ip": re.compile(
        r"\b(?:192\.168\.\d{1,3}\.\d{1,3}|10\.\d{1,3}\.\d{1,3}\.\d{1,3}|172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3})\b"
    ),
    "api-key-ish": re.compile(r"\b[A-Za-z0-9+/_-]{60,}={0,2}\b"),
}
# Only genuine synthetic placeholders belong here (e.g. user@example.com, reserved
# for documentation by RFC 2606). Never add a real-looking private IP, hostname, or
# key to this set to silence a finding -- this allowlist is applied to every scanned
# file, so one bad entry makes the guard permanently blind to that exact value
# anywhere in the repo. Regression tests that need example private IPs (see
# tests/test_guard_scripts.py) must build them at runtime instead of writing them
# as literals, so no matching text ever lands in a scanned file in the first place.
ALLOWED = {"user@example.com"}
# Every tracked path that a human writes prose into. docs/ is deliberately absent: it is
# gitignored and exists to hold exactly the infrastructure details this guard rejects.
SCAN = [
    "tests",
    "plugin.video.couchseerr",
    "scripts",
    ".github",
    "README.md",
    "CLAUDE.md",
]


def main():
    failures = []
    scanned = 0
    for target in SCAN:
        base = pathlib.Path(target)
        if not base.exists():
            continue
        paths = [base] if base.is_file() else [p for p in base.rglob("*") if p.is_file()]
        for path in paths:
            try:
                text = path.read_text()
            except (UnicodeDecodeError, OSError):
                continue
            scanned += 1
            for label, pattern in PATTERNS.items():
                for hit in pattern.findall(text):
                    if hit not in ALLOWED:
                        failures.append(f"{path}: {label}: {hit}")

    # SCAN holds relative paths, so from the wrong working directory every entry is
    # missing, nothing is read and the guard reports success. Clean is only meaningful
    # once something has actually been read.
    if scanned == 0:
        print("FAIL scanned no files; run this from the repository root")
        return 2

    for line in failures:
        print(f"FAIL {line}")
    print("no secrets found" if not failures else f"{len(failures)} finding(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
