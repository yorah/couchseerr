"""Guards on the shipped window XML.

kodi/window.py names two control ids and eight window properties. A renamed id or a
mistyped property is invisible to every other test here and shows up only on the device,
as a control that never fills or a label that never draws. These close that gap.
"""
import pathlib
import re
import xml.etree.ElementTree as ET

import pytest

from couchseerr import detailview
from couchseerr.kodi import window

ADDON = pathlib.Path(__file__).parent.parent / "plugin.video.couchseerr"
XML = ADDON / "resources" / "skins" / window.SKIN / window.RES / window.XML_FILE
MEDIA = ADDON / "resources" / "skins" / window.SKIN / "media"

#: A readable statement of what the contract *should* be. Kept as an assertion
#: (test_the_property_literal_matches_the_source below), never as the thing the parity
#: tests below compare against -- a literal compared only to itself proves nothing about
#: window.py, which is exactly how a deleted setProperty call or a dead new one could slip
#: past this file unnoticed.
PROPERTIES = ("title", "year_status", "plot", "poster", "fanart",
              "section", "section_header")

WINDOW_SOURCE = pathlib.Path(window.__file__).read_text(encoding="utf-8")
DETAILVIEW_SOURCE = pathlib.Path(detailview.__file__).read_text(encoding="utf-8")

#: Row properties the window sets on purpose and the shipped layout deliberately does not
#: draw. This tuple is the record of that decision: an entry here is a claim that nothing
#: renders it *and that this is intended*, so adding one is a choice someone has to make
#: rather than a check quietly going green.
#:
#: couchseerr.action is the per-action icon hook, kept so a skin shipping its own copy of
#: this window can pick an icon per action without needing a control id per action.
#: seerr.status on a season row is the same media fact a tile carries, offered to a skin
#: override for a badge; our own layout shows the state through couchseerr.marker instead.
UNREAD_ROW_PROPERTIES = ("couchseerr.action", "seerr.status")

#: Same readable-statement role as PROPERTIES above, for the row properties.
ROW_PROPERTIES = ("couchseerr.action", "couchseerr.marker", "couchseerr.detail",
                  "couchseerr.inert", "seerr.status")


def _properties_set_by_window():
    r"""Every property name window.py actually passes to setProperty(...), read from the
    source rather than hand-maintained -- \s also matches the newline in the one
    multi-line call (section_header's conditional value)."""
    return set(re.findall(r'setProperty\(\s*"(\w+)"', WINDOW_SOURCE))


def _properties_read_by_xml():
    text = XML.read_text(encoding="utf-8")
    return set(re.findall(r"Window\.Property\((\w+)\)", text))


def _row_properties_set_by_detailview():
    """Every ListItem property name detailview.py's spec builders actually set, read from
    the source. Scoped to detailview.py on purpose: ui/spec.py sets the tile properties,
    and no tile is ever rendered inside this window."""
    return set(re.findall(r'"((?:seerr|couchseerr)\.[\w.]+)":', DETAILVIEW_SOURCE))


def _row_properties_read_by_xml():
    text = XML.read_text(encoding="utf-8")
    return set(re.findall(r"ListItem\.Property\(([\w.]+)\)", text))


@pytest.fixture(scope="module")
def root():
    return ET.parse(str(XML)).getroot()


def test_the_window_xml_ships_where_kodi_looks():
    """WindowXML(xml, path, SKIN, RES) resolves to resources/skins/SKIN/RES/xml, and
    CoreELEC's filesystem is case sensitive, so this path is the whole contract."""
    assert XML.is_file(), XML


def test_the_xml_root_is_a_window(root):
    assert root.tag == "window"


def test_both_control_ids_exist_as_lists(root):
    lists = {c.get("id"): c for c in root.iter("control") if c.get("type") == "list"}
    assert str(window.SECTION_ID) in lists
    assert str(window.ACTIONS_ID) in lists


def test_every_list_has_both_layouts(root):
    for control in root.iter("control"):
        if control.get("type") != "list":
            continue
        assert control.find("itemlayout") is not None, control.get("id")
        assert control.find("focusedlayout") is not None, control.get("id")


def test_the_default_control_is_a_real_control(root):
    default = root.findtext("defaultcontrol", "").strip()
    ids = {c.get("id") for c in root.iter("control")}
    assert default in ids


def test_the_property_literal_matches_the_source():
    """PROPERTIES exists to be a readable statement of the contract; this keeps it
    honest. Neither parity test below compares against this literal -- both compare
    against _properties_set_by_window(), read straight from window.py, so a deleted or
    added setProperty call fails here first."""
    assert set(PROPERTIES) == _properties_set_by_window()


def test_every_property_the_window_sets_is_read():
    """A property nothing reads is a label that never draws, with nothing in the log.
    Compared against the window's actual setProperty calls, not the PROPERTIES literal --
    deleting a setProperty from window.py must fail this test even if no one updates the
    literal to match."""
    set_by_window = _properties_set_by_window()
    read_by_xml = _properties_read_by_xml()
    assert set_by_window <= read_by_xml, sorted(set_by_window - read_by_xml)


def test_every_property_the_xml_reads_is_set():
    """And the reverse: a $INFO naming a property the window never sets is dead markup.
    Same reasoning as above -- adding a stray setProperty("subtitle", ...) that no layout
    reads must fail this test even though the XML itself never changed."""
    set_by_window = _properties_set_by_window()
    read_by_xml = _properties_read_by_xml()
    assert read_by_xml <= set_by_window, sorted(read_by_xml - set_by_window)


def _labels_reading(root, info):
    """Every label control in the section list whose text is `info`."""
    section = [c for c in root.iter("control")
               if c.get("type") == "list" and c.get("id") == "50"][0]
    found = []
    for layout in ("itemlayout", "focusedlayout"):
        for control in section.find(layout).iter("control"):
            label = control.find("label")
            if control.get("type") == "label" and label is not None and info in label.text:
                found.append(control)
    return found


def test_focused_rows_are_drawn_only_where_the_focus_is(root):
    """Kodi draws a list's focusedlayout for its selected row whether or not that list
    holds the focus, so without a condition both lists light a row at once and the screen
    stops saying where the remote is.

    Two halves to get right, and the second is the one that bites: gating the lit
    treatment is easy to remember, and forgetting to draw the *unfocused* selection makes
    that row's text disappear the moment focus moves to the other list. So every control
    must answer to its own list's focus, and every piece of text drawn under focus must
    still be drawn without it.
    """
    for list_id in ("50", "51"):
        control = [c for c in root.iter("control")
                   if c.get("type") == "list" and c.get("id") == list_id][0]
        focused_text, unfocused_text = set(), set()
        for child in control.find("focusedlayout"):
            visible = child.find("visible")
            assert visible is not None, (list_id, child.get("type"))
            condition = visible.text
            assert "Control.HasFocus({0})".format(list_id) in condition
            if child.get("type") != "label":
                continue
            drawn = focused_text
            if "!Control.HasFocus({0})".format(list_id) in condition:
                drawn = unfocused_text
            drawn.add(child.find("label").text)
        assert focused_text, list_id
        assert focused_text == unfocused_text, list_id


def test_the_marker_column_hugs_the_title(root):
    """The column is sized for the longest marker markers.py can build, so short ones
    have to sit at its right edge -- left-aligned, "[◐]" floats a column away from the
    season name it describes. Also pins the column out of the title's way: widening it
    over the title is the other way this row goes wrong."""
    markers = _labels_reading(root, "couchseerr.marker")
    titles = _labels_reading(root, "ListItem.Label")
    assert markers and titles
    title_left = min(int(c.find("left").text) for c in titles)
    for control in markers:
        assert control.find("align") is not None
        assert control.find("align").text == "right"
        right_edge = int(control.find("left").text) + int(control.find("width").text)
        assert right_edge <= title_left
        assert title_left - right_edge <= 24


def test_every_texture_the_xml_names_is_shipped(root):
    """A missing texture draws nothing and logs nothing. Every non-$INFO texture must be a
    file in the addon's own media folder."""
    missing = []
    for texture in root.iter("texture"):
        name = (texture.text or "").strip()
        if not name or name.startswith("$"):
            continue
        if not (MEDIA / name).is_file():
            missing.append(name)
    assert missing == [], missing


def test_the_shipped_texture_is_a_real_png():
    data = (MEDIA / "white.png").read_bytes()
    assert data.startswith(b"\x89PNG\r\n\x1a\n")


def test_the_row_property_literal_matches_the_source():
    """ROW_PROPERTIES is a readable statement of the contract; this is what keeps it
    honest, so the two parity tests below can lean on the source instead."""
    assert _row_properties_set_by_detailview() == set(ROW_PROPERTIES)


def test_every_row_property_the_xml_reads_is_set():
    """A $INFO naming a ListItem property no spec builder sets draws nothing, silently."""
    read = _row_properties_read_by_xml()
    unset = read - _row_properties_set_by_detailview()
    assert unset == set(), sorted(unset)


def test_every_row_property_set_is_read_or_declared_unread():
    """And the reverse. A property nothing draws is either a mistake or a deliberate hook
    -- UNREAD_ROW_PROPERTIES is where the deliberate ones are declared, so a genuinely
    orphaned one cannot hide among them."""
    orphaned = (
        _row_properties_set_by_detailview()
        - _row_properties_read_by_xml()
        - set(UNREAD_ROW_PROPERTIES)
    )
    assert orphaned == set(), sorted(orphaned)


def test_the_unread_row_declarations_are_all_real():
    """An entry in UNREAD_ROW_PROPERTIES for a property that is no longer set, or that the
    layout has since started drawing, is a stale claim -- exactly the kind of allow-list
    that rots into a blanket exemption."""
    set_by_source = _row_properties_set_by_detailview()
    read_by_xml = _row_properties_read_by_xml()
    for name in UNREAD_ROW_PROPERTIES:
        assert name in set_by_source, "{0} is declared unread but nothing sets it".format(name)
        assert name not in read_by_xml, "{0} is declared unread but the XML reads it".format(name)


def test_the_row_property_scan_is_not_vacuous():
    """Both sides must find something. A regex that silently stopped matching would make
    every parity test above pass by comparing two empty sets."""
    assert _row_properties_set_by_detailview()
    assert _row_properties_read_by_xml()


README = pathlib.Path(__file__).parent.parent / "README.md"


def _readme_backticked_names():
    """Every `code-quoted` token in README's skinner section that looks like one of our
    property names. The section is a published contract; this is what stops it becoming a
    published lie."""
    text = README.read_text(encoding="utf-8")
    start = text.index("## For skinners")
    end = text.index("## Not implemented", start)
    return set(re.findall(r"`((?:seerr|couchseerr)\.[\w.]+)`", text[start:end]))


def test_the_readme_documents_only_real_properties():
    """A property named in the skinner docs that nothing sets is worse than an undocumented
    one: a skinner builds against it and gets silence."""
    tile_source = pathlib.Path(
        ADDON / "resources" / "lib" / "couchseerr" / "ui" / "spec.py"
    ).read_text(encoding="utf-8")
    real = (
        _row_properties_set_by_detailview()
        | set(re.findall(r'"((?:seerr|couchseerr)\.[\w.]+)"', tile_source))
    )
    documented = _readme_backticked_names()
    assert documented, "found no property names in the skinner section; guard is vacuous"
    assert documented <= real, sorted(documented - real)


def test_the_readme_documents_every_window_row_property():
    """And the reverse, for the window's own rows: a property the window sets but the
    skinner docs omit is a contract a skin override cannot discover."""
    missing = _row_properties_set_by_detailview() - _readme_backticked_names()
    assert missing == set(), sorted(missing)
