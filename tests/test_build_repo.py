import hashlib
import xml.etree.ElementTree as ET
import zipfile

import pytest

from build_repo import build, generate_addons_xml, main
from check_repo import verify

SOURCE_ROOT = "."


def test_addons_xml_lists_both_addons():
    root = ET.fromstring(generate_addons_xml(SOURCE_ROOT))
    ids = {a.get("id") for a in root.findall("addon")}
    assert ids == {"plugin.video.couchseerr", "repository.couchseerr"}


def test_addons_xml_includes_the_repository_itself():
    """A repository absent from its own addons.xml can never self-update or self-heal."""
    root = ET.fromstring(generate_addons_xml(SOURCE_ROOT))
    ids = {a.get("id") for a in root.findall("addon")}
    assert "repository.couchseerr" in ids


def test_build_produces_zip_per_addon_at_the_expected_path(tmp_path):
    built = build(SOURCE_ROOT, str(tmp_path))
    for addon_id, zip_path in built.items():
        assert zip_path.endswith(".zip")
        assert "/zips/{0}/".format(addon_id) in zip_path.replace("\\", "/")


def test_zip_contains_the_addon_directory_at_its_root(tmp_path):
    """Kodi requires the addon id as the top-level directory inside the zip."""
    built = build(SOURCE_ROOT, str(tmp_path))
    path = built["plugin.video.couchseerr"]
    with zipfile.ZipFile(path) as zf:
        tops = {name.split("/")[0] for name in zf.namelist()}
    assert tops == {"plugin.video.couchseerr"}


def test_zip_filename_carries_the_version(tmp_path):
    built = build(SOURCE_ROOT, str(tmp_path))
    version = ET.parse("plugin.video.couchseerr/addon.xml").getroot().get("version")
    assert built["plugin.video.couchseerr"].endswith(
        "plugin.video.couchseerr-{0}.zip".format(version)
    )


def test_checksum_file_matches_addons_xml(tmp_path):
    import hashlib

    build(SOURCE_ROOT, str(tmp_path))
    xml_bytes = (tmp_path / "addons.xml").read_bytes()
    expected = hashlib.md5(xml_bytes).hexdigest()
    assert (tmp_path / "addons.xml.md5").read_text().strip().split()[0] == expected


def test_zip_bytes_are_identical_when_built_twice(tmp_path):
    """One version, one artifact. File order comes from os.walk and timestamps come from
    the filesystem, so two builds of the same source produced different bytes -- and a
    published zip that differs from a rebuild of its own tag cannot be verified by
    anyone, including a mirror."""
    first = build(SOURCE_ROOT, str(tmp_path / "a"))
    second = build(SOURCE_ROOT, str(tmp_path / "b"))
    for addon_id, path in first.items():
        with open(path, "rb") as handle:
            digest_a = hashlib.sha256(handle.read()).hexdigest()
        with open(second[addon_id], "rb") as handle:
            digest_b = hashlib.sha256(handle.read()).hexdigest()
        assert digest_a == digest_b, addon_id


def test_zip_entries_carry_a_fixed_timestamp(tmp_path):
    """The load-bearing half of determinism: file order happens to be stable within one
    machine, but mtimes are not stable across a fresh checkout, so without this the same
    tag rebuilds to different bytes anywhere but the machine that first built it."""
    built = build(SOURCE_ROOT, str(tmp_path))
    with zipfile.ZipFile(built["plugin.video.couchseerr"]) as zf:
        stamps = {i.date_time for i in zf.infolist()}
    assert stamps == {(1980, 1, 1, 0, 0, 0)}


def test_zip_entries_are_sorted(tmp_path):
    built = build(SOURCE_ROOT, str(tmp_path))
    with zipfile.ZipFile(built["plugin.video.couchseerr"]) as zf:
        names = zf.namelist()
    assert names == sorted(names)


def test_version_without_an_addon_argument_is_an_error(tmp_path, capsys):
    """`build_repo.py version` with the argument forgotten used to fall through to the
    build branch and treat the word "version" as an output directory, silently creating
    dist-like output in a folder called version."""
    assert main(["version"]) != 0
    assert not (tmp_path / "version").exists()


def test_version_prints_the_addon_version(capsys):
    assert main(["version", "plugin.video.couchseerr"]) == 0
    assert capsys.readouterr().out.strip() == ET.parse(
        "plugin.video.couchseerr/addon.xml"
    ).getroot().get("version")


def test_verify_passes_on_a_freshly_built_tree(tmp_path):
    build(SOURCE_ROOT, str(tmp_path))
    assert verify(str(tmp_path)) == []


def test_verify_catches_a_missing_zip(tmp_path):
    """This is the '404 datadir' failure, made detectable."""
    build(SOURCE_ROOT, str(tmp_path))
    for path in (tmp_path / "zips").rglob("plugin.video.couchseerr-*.zip"):
        path.unlink()
    problems = verify(str(tmp_path))
    assert any("plugin.video.couchseerr" in p for p in problems)


def test_verify_catches_a_repository_absent_from_addons_xml(tmp_path):
    build(SOURCE_ROOT, str(tmp_path))
    xml_path = tmp_path / "addons.xml"
    root = ET.fromstring(xml_path.read_text())
    for addon in root.findall("addon"):
        if addon.get("id") == "repository.couchseerr":
            root.remove(addon)
    xml_path.write_text(ET.tostring(root, encoding="unicode"))
    assert any("repository.couchseerr" in p for p in verify(str(tmp_path)))
