"""Cross-locale guards for the shipped string tables.

tests/test_settings_xml.py already validates en_gb on its own: ids exist, msgids are
non-empty, no duplicates. What it cannot see is a *second* locale drifting from it, which
is the failure mode translations actually have -- a string added in English and never
carried across shows up on the device as English inside an otherwise translated screen,
and nothing in the log says so.
"""
import pathlib
import re

import pytest

LANG_DIR = (
    pathlib.Path(__file__).parent.parent
    / "plugin.video.couchseerr"
    / "resources"
    / "language"
)

BASE = "resource.language.en_gb"

#: Declared, not discovered. A locale directory added without a line here fails, which is
#: the point: shipping a translation is a decision, not something a stray directory does.
SHIPPED = {
    "resource.language.en_gb": "en_gb",
    "resource.language.fr_fr": "fr_fr",
    "resource.language.de_de": "de_de",
    "resource.language.es_es": "es_es",
}

ENTRY = re.compile(
    r'msgctxt "#(\d+)"\s*\n'
    r'msgid "((?:[^"\\]|\\.)*)"\s*\n'
    r'msgstr "((?:[^"\\]|\\.)*)"'
)
FIELD = re.compile(r"\{(\d+)\}")


def _po_path(directory):
    return LANG_DIR / directory / "strings.po"


def _entries(directory):
    """(id, msgid, msgstr) triples, in file order."""
    return ENTRY.findall(_po_path(directory).read_text(encoding="utf-8"))


def _table(directory):
    return {sid: (msgid, msgstr) for sid, msgid, msgstr in _entries(directory)}


@pytest.fixture(scope="module")
def base_table():
    return _table(BASE)


def test_exactly_the_declared_locales_ship():
    found = {p.name for p in LANG_DIR.iterdir() if p.is_dir()}
    assert found == set(SHIPPED)


@pytest.mark.parametrize("directory", sorted(SHIPPED))
def test_every_locale_has_a_strings_file(directory):
    assert _po_path(directory).is_file()


@pytest.mark.parametrize("directory", sorted(SHIPPED))
def test_no_locale_repeats_a_string_id(directory):
    ids = [sid for sid, _msgid, _msgstr in _entries(directory)]
    duplicates = sorted({sid for sid in ids if ids.count(sid) > 1})
    assert duplicates == [], "{0}: duplicate ids {1}".format(directory, duplicates)


@pytest.mark.parametrize("directory", sorted(SHIPPED))
def test_the_header_language_matches_the_directory(directory):
    text = _po_path(directory).read_text(encoding="utf-8")
    assert '"Language: {0}\\n"'.format(SHIPPED[directory]) in text


@pytest.mark.parametrize(
    "directory", sorted(d for d in SHIPPED if d != BASE)
)
def test_every_locale_covers_exactly_the_base_ids(directory, base_table):
    """Both directions. Missing ids fall back to English mid-screen; extra ids are dead
    weight that outlives the string they were written for."""
    table = _table(directory)
    assert set(table) == set(base_table), directory


@pytest.mark.parametrize(
    "directory", sorted(d for d in SHIPPED if d != BASE)
)
def test_every_locale_carries_the_english_source_as_its_msgid(directory, base_table):
    """gettext matches on msgid. A translated file whose msgid drifted from en_gb is not
    a translation of the string the code actually asks for."""
    for sid, (msgid, _msgstr) in sorted(_table(directory).items()):
        assert msgid == base_table[sid][0], "{0} #{1}".format(directory, sid)


@pytest.mark.parametrize(
    "directory", sorted(d for d in SHIPPED if d != BASE)
)
def test_every_string_is_actually_translated(directory):
    """Kodi falls back to msgid on a blank msgstr, so an untranslated entry is silent."""
    blank = sorted(
        sid for sid, _msgid, msgstr in _entries(directory) if not msgstr.strip()
    )
    assert blank == [], "{0}: untranslated {1}".format(directory, blank)


def test_the_base_locale_leaves_every_msgstr_blank():
    """Kodi convention: en_gb carries the English in msgid and nothing in msgstr. A
    filled-in msgstr here means someone treated the source file as a translation."""
    filled = sorted(
        sid for sid, _msgid, msgstr in _entries(BASE) if msgstr.strip()
    )
    assert filled == []


@pytest.mark.parametrize(
    "directory", sorted(d for d in SHIPPED if d != BASE)
)
def test_format_placeholders_survive_translation(directory, base_table):
    """`.format()` is called on these. A translation that drops {0} silently loses the
    title or the percentage; one that invents {1} raises IndexError on the device.
    """
    for sid, (_msgid, msgstr) in sorted(_table(directory).items()):
        assert set(FIELD.findall(msgstr)) == set(FIELD.findall(base_table[sid][0])), \
            "{0} #{1}".format(directory, sid)


def test_every_label_the_code_looks_up_is_translated_everywhere(base_table):
    """Closes the loop from routes.LABEL_IDS through to each shipped locale, so a new
    label cannot ship English-only."""
    from couchseerr import routes

    required = {str(value) for value in routes.LABEL_IDS.values()}
    assert required <= set(base_table)
    for directory in sorted(d for d in SHIPPED if d != BASE):
        table = _table(directory)
        missing = sorted(required - set(table))
        assert missing == [], "{0}: {1}".format(directory, missing)
