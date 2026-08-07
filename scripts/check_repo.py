#!/usr/bin/env python3
# scripts/check_repo.py
"""Verify a built repository datadir before it is published.

Guards the two failures that silently strand users: a datadir whose zips are missing, and
a repository addon absent from its own addons.xml.
"""
import hashlib
import os
import sys
import xml.etree.ElementTree as ET

REPO_ADDON_ID = "repository.couchseerr"


def verify(out_dir):
    problems = []

    xml_path = os.path.join(out_dir, "addons.xml")
    md5_path = os.path.join(out_dir, "addons.xml.md5")
    if not os.path.exists(xml_path):
        return ["addons.xml is missing from {0}".format(out_dir)]
    if not os.path.exists(md5_path):
        problems.append("addons.xml.md5 is missing")

    with open(xml_path, "rb") as handle:
        raw = handle.read()
    if os.path.exists(md5_path):
        with open(md5_path) as handle:
            recorded = handle.read().strip().split()[0]
        if recorded != hashlib.md5(raw).hexdigest():
            problems.append("addons.xml.md5 does not match addons.xml")

    root = ET.fromstring(raw.decode("utf-8"))
    entries = {a.get("id"): a.get("version") for a in root.findall("addon")}

    if REPO_ADDON_ID not in entries:
        problems.append(
            "{0} is absent from addons.xml, so it can never self-update".format(REPO_ADDON_ID)
        )

    for addon_id, version in entries.items():
        expected = os.path.join(
            out_dir, "zips", addon_id, "{0}-{1}.zip".format(addon_id, version)
        )
        if not os.path.exists(expected):
            problems.append("addons.xml lists {0} {1} but {2} does not exist".format(
                addon_id, version, expected
            ))

    return problems


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "dist"
    found = verify(target)
    for line in found:
        print("FAIL {0}".format(line))
    print("repository datadir is valid" if not found else "{0} problem(s)".format(len(found)))
    sys.exit(1 if found else 0)
