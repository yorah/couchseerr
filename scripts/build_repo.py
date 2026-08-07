#!/usr/bin/env python3
# scripts/build_repo.py
"""Build the Kodi repository datadir: zips, addons.xml and its checksum.

Layout Kodi expects under the datadir:
    zips/<addon.id>/<addon.id>-<version>.zip
"""
import hashlib
import os
import sys
import xml.etree.ElementTree as ET
import zipfile

ADDONS = ["plugin.video.couchseerr", "repository.couchseerr"]
EXCLUDE_DIRS = {"__pycache__", ".git"}
EXCLUDE_SUFFIXES = (".pyc", ".pyo")
ZIP_EPOCH = (1980, 1, 1, 0, 0, 0)


def _addon_version(source_root, addon_id):
    path = os.path.join(source_root, addon_id, "addon.xml")
    return ET.parse(path).getroot().get("version")


def generate_addons_xml(source_root):
    """Concatenate every addon.xml, including the repository's own entry.

    Omitting the repository from this file is what leaves a repo unable to update itself.
    """
    lines = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>', "<addons>"]
    for addon_id in ADDONS:
        tree = ET.parse(os.path.join(source_root, addon_id, "addon.xml"))
        lines.append(ET.tostring(tree.getroot(), encoding="unicode").strip())
    lines.append("</addons>")
    return "\n".join(lines) + "\n"


def _zip_addon(source_root, addon_id, out_dir):
    version = _addon_version(source_root, addon_id)
    target_dir = os.path.join(out_dir, "zips", addon_id)
    os.makedirs(target_dir, exist_ok=True)
    target = os.path.join(target_dir, "{0}-{1}.zip".format(addon_id, version))

    base = os.path.join(source_root, addon_id)
    # Deterministic on purpose: os.walk order and on-disk mtimes made two builds of one
    # source tree produce different bytes, so a published zip could not be checked
    # against a rebuild of its own tag. Entries are sorted and stamped with a fixed
    # timestamp -- ZIP's own epoch, the earliest value the format can store.
    entries = []
    for root, dirs, files in os.walk(base):
        dirs[:] = sorted(d for d in dirs if d not in EXCLUDE_DIRS)
        for name in sorted(files):
            if name.endswith(EXCLUDE_SUFFIXES):
                continue
            full = os.path.join(root, name)
            # Kodi requires the addon id as the top-level directory in the zip.
            arc = "/".join([addon_id] + os.path.relpath(full, base).split(os.sep))
            entries.append((arc, full))

    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as zf:
        for arc, full in sorted(entries):
            info = zipfile.ZipInfo(arc, date_time=ZIP_EPOCH)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            with open(full, "rb") as handle:
                zf.writestr(info, handle.read())
    return target


def build(source_root, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    built = {}
    for addon_id in ADDONS:
        built[addon_id] = _zip_addon(source_root, addon_id, out_dir)

    xml_text = generate_addons_xml(source_root)
    xml_path = os.path.join(out_dir, "addons.xml")
    with open(xml_path, "w") as handle:
        handle.write(xml_text)

    with open(xml_path, "rb") as handle:
        digest = hashlib.md5(handle.read()).hexdigest()
    with open(os.path.join(out_dir, "addons.xml.md5"), "w") as handle:
        handle.write(digest + "\n")

    return built


def _print_version(arg):
    """CLI helper: print an addon's version, parsed from its addon.xml root element.

    `arg` is either an addon id resolved against the current directory (the normal case,
    e.g. "plugin.video.couchseerr"), or a direct path to an addon.xml file (used by CI to
    read a version out of a file fetched from another git ref via `git show`).

    This exists so workflow YAML never greps addon.xml for a version attribute - the XML
    declaration's own version="1.0" is a false match `grep -oP` cannot tell apart from the
    addon's actual version.
    """
    if arg.endswith("addon.xml") and os.path.exists(arg):
        path = arg
    else:
        path = os.path.join(".", arg, "addon.xml")
    print(ET.parse(path).getroot().get("version"))


def main(argv):
    """usage: build_repo.py [<out-dir>] | build_repo.py version <addon-id|addon.xml>"""
    if argv and argv[0] == "version":
        # Without this check, a forgotten argument fell through to the build branch and
        # built the whole repository into a directory literally named "version".
        if len(argv) < 2:
            print("usage: build_repo.py version <addon-id|path-to-addon.xml>", file=sys.stderr)
            return 2
        _print_version(argv[1])
        return 0

    out = argv[0] if argv else "dist"
    for addon_id, path in build(".", out).items():
        print("built {0} -> {1}".format(addon_id, path))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
