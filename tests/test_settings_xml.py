"""The settings dialog is unreachable from a test harness, so its definition is checked
here instead. Every one of these failures is silent on the device: Kodi logs a line and
renders a dialog that is simply missing the setting, and nothing in Python ever notices.
"""
import pathlib
import re
import xml.etree.ElementTree as ET
from urllib.parse import parse_qsl, urlparse

import pytest

ADDON = pathlib.Path(__file__).resolve().parent.parent / "plugin.video.couchseerr"
SETTINGS_XML = ADDON / "resources" / "settings.xml"
STRINGS_PO = ADDON / "resources" / "language" / "resource.language.en_gb" / "strings.po"
ROUTES_PY = ADDON / "resources" / "lib" / "couchseerr" / "routes.py"

# <option label="Some text"> is the one place a literal is legal: option labels are not
# resolved through the string table.
LABELLED_TAGS = ("section", "category", "group", "setting")


@pytest.fixture(scope="module")
def settings():
    return [s for s in ET.parse(str(SETTINGS_XML)).getroot().iter("setting") if s.get("id")]


@pytest.fixture(scope="module")
def root():
    return ET.parse(str(SETTINGS_XML)).getroot()


@pytest.fixture(scope="module")
def po_ids():
    return set(re.findall(r'^msgctxt\s+"#(\d+)"', STRINGS_PO.read_text(), re.MULTILINE))


def test_settings_that_ship_blank_declare_allowempty(settings):
    """Verified on Kodi 21.3: CSettingString logs "error reading the default value" and
    drops the whole setting when its default is empty *or* absent, unless the setting
    declares allowempty. Shipped without it, api_key and language never appeared in the
    settings dialog at all and could only be configured by editing addon_data by hand.

    Omitting <default> is not the fix -- that was tried on the device and failed the same
    way. allowempty is what suppresses the error.

    Action-type settings are excluded: they have no default value and do not trigger
    CSettingString's default-value check.
    """
    broken = []
    for setting in settings:
        # Action settings don't have defaults and don't need allowempty
        if setting.get("type") == "action":
            continue
        default = setting.find("default")
        if default is not None and (default.text or "").strip():
            continue  # a real default: nothing to allow
        allow = setting.find("constraints/allowempty")
        if allow is None or (allow.text or "").strip() != "true":
            broken.append(setting.get("id"))
    assert broken == [], (
        "these ship blank without <constraints><allowempty>true</allowempty>, so Kodi "
        "drops them from the dialog: {0}".format(broken)
    )


def test_every_setting_read_by_routes_is_declared(settings):
    """A getSetting() call for an id the dialog does not declare returns "" forever, with
    no error anywhere -- the setting simply appears to be permanently blank."""
    declared = {s.get("id") for s in settings}
    read = set(re.findall(r'getSetting\(\s*"([^"]+)"', ROUTES_PY.read_text()))
    assert read, "no getSetting() calls found; this guard would pass vacuously"
    assert read <= declared, "read but not declared: {0}".format(sorted(read - declared))


def test_labels_are_numeric_string_ids(root):
    """Verified against Kodi's own parser (xbmc/settings/lib/ISetting.cpp):

        if (element->QueryIntAttribute(SETTING_XML_ATTR_LABEL, &iValue) == TIXML_SUCCESS
            && iValue > 0)
          m_label = iValue;

    In a version="1" settings document, label and help are *string ids*, not text. A
    literal fails QueryIntAttribute, is silently discarded, and the row renders with an
    empty label -- which is what shipped: no labels on any category or setting.
    """
    literal = []
    for element in root.iter():
        if element.tag not in LABELLED_TAGS:
            continue
        for attr in ("label", "help"):
            value = element.get(attr)
            if value is None:
                continue
            if not (value.isdigit() and int(value) > 0):
                literal.append("{0}[{1}] {2}={3!r}".format(
                    element.tag, element.get("id"), attr, value))
    assert literal == [], (
        "label/help must be a positive string id; Kodi drops these and renders a blank "
        "label: {0}".format(literal)
    )


def test_every_label_id_exists_in_strings_po(root, po_ids):
    """An id with no msgctxt resolves to the empty string, which looks exactly like the
    literal-label bug on the device and is just as invisible in the log."""
    missing = []
    for element in root.iter():
        if element.tag not in LABELLED_TAGS:
            continue
        for attr in ("label", "help"):
            value = element.get(attr)
            if value and value.isdigit() and value not in po_ids:
                missing.append("{0}[{1}] {2}=#{3}".format(
                    element.tag, element.get("id"), attr, value))
    assert missing == [], "not defined in strings.po: {0}".format(missing)


def test_string_ids_are_in_the_addon_range(po_ids):
    """30000-30999 is the range reserved for a plugin's own strings. Kodi resolves ids
    outside it against its global table, silently yielding someone else's text."""
    out_of_range = sorted(i for i in po_ids if not 30000 <= int(i) <= 30999)
    assert out_of_range == [], out_of_range


def test_every_setting_has_a_control_and_a_level(settings):
    """Both are required for a setting to render at all."""
    for setting in settings:
        assert setting.find("control") is not None, setting.get("id")
        assert setting.find("level") is not None, setting.get("id")


def test_control_types_are_valid_and_action_settings_use_button(root):
    """An invalid control type makes Kodi drop the setting *and* hide its entire category,
    logging only 'error <CSetting>: error reading <control> tag of "[setting_id]"', with
    nothing visible in the settings dialog to hint at what went wrong.

    In settings.xml version="1", type="action" settings must use <control type="button"
    format="action">, not <control type="action">. The action is in the format, not the type.

    Verified against Kodi's SettingControl.cpp: valid control types are toggle, spinner,
    edit, button, list, slider, range, title, label, colorbutton. Any other type fails
    CSettingControlCreator::CreateControl and drops the setting.
    """
    VALID_CONTROL_TYPES = {
        "toggle", "spinner", "edit", "button", "list", "slider", "range", "title", "label", "colorbutton"
    }
    invalid_controls = []
    action_settings_with_wrong_control = []

    for setting in root.iter("setting"):
        control = setting.find("control")
        if control is not None:
            control_type = control.get("type")
            if control_type not in VALID_CONTROL_TYPES:
                invalid_controls.append("{0}[control type={1!r}]".format(setting.get("id"), control_type))

    for setting in root.iter("setting"):
        if setting.get("type") == "action":
            control = setting.find("control")
            if control is None:
                action_settings_with_wrong_control.append("{0}[no control]".format(setting.get("id")))
            elif control.get("type") != "button" or control.get("format") != "action":
                action_settings_with_wrong_control.append(
                    "{0}[control type={1!r} format={2!r}]".format(
                        setting.get("id"), control.get("type"), control.get("format")
                    )
                )

    assert invalid_controls == [], (
        "invalid control types (Kodi drops the setting and hides its category): {0}".format(
            invalid_controls
        )
    )
    assert action_settings_with_wrong_control == [], (
        "action-type settings must use <control type='button' format='action'>: {0}".format(
            action_settings_with_wrong_control
        )
    )


def test_no_action_type_settings_remain(root):
    """`configure_presets` (a `type="action"` setting) was replaced by four
    `type="string"` profile-picker rows -- see the "Request configuration" section of
    the design doc. There is no longer any action-type setting in the file; the
    action-settings-use-button-format branch of
    `test_control_types_are_valid_and_action_settings_use_button` stays in place to
    guard any future one.
    """
    actions = [s for s in root.iter("setting") if s.get("type") == "action"]
    assert actions == []


#: Every literal `mode == "..."` the dispatch elif-chain in routes.py matches on.
_MODE_RE = re.compile(r'mode == "(\w+)"')

#: Modes referenced by settings.xml that routes.dispatch does not yet handle. Empty
#: now that task 17 wires mode=profile into routes.py; kept as a set (not deleted) so a
#: future mode can be forward-referenced from settings.xml the same way, with
#: test_pending_modes_are_still_pending guarding against it lingering once handled.
_PENDING_MODES = set()


def test_runplugin_data_targets_a_mode_routes_dispatch_handles(root):
    """A typo'd mode (`mode=proflie`) would parse as a fine-looking URL and fail only on
    the device, where the row falls through to dispatch's generic "Unknown mode" path
    with nothing for a test to catch. Every `RunPlugin(plugin://...)` data value in the
    settings dialog must target a URL for this addon whose `mode` is either handled by
    routes.dispatch today or explicitly acknowledged as pending in _PENDING_MODES above.
    """
    handled = set(_MODE_RE.findall(ROUTES_PY.read_text())) | _PENDING_MODES
    assert handled, "no modes found in routes.py; this guard would pass vacuously"

    checked = 0
    for data in root.iter("data"):
        text = (data.text or "").strip()
        match = re.match(r"RunPlugin\((.+)\)$", text)
        if not match:
            continue
        url = match.group(1)
        parsed = urlparse(url)
        assert parsed.scheme == "plugin", url
        assert parsed.netloc == "plugin.video.couchseerr", url
        mode = dict(parse_qsl(parsed.query)).get("mode")
        assert mode, "RunPlugin URL with no mode: {0}".format(url)
        assert mode in handled, "RunPlugin targets an unhandled mode {0!r}: {1}".format(mode, url)
        checked += 1
    assert checked, "no RunPlugin(...) data values found; this guard would pass vacuously"


def test_dependencies_reference_existing_settings(root, settings):
    """A `<dependency>` naming a setting id that does not exist is dead weight Kodi
    silently ignores -- the row it was meant to hide or show just behaves as if the
    dependency were never written, with nothing in the log to say why.
    """
    declared = {s.get("id") for s in settings}
    bad = []
    found_any = False
    for setting in settings:
        # .// so conditions wrapped in <or>/<and>/<not> inside <dependency> are found
        # too, not just direct dependency/condition children.
        for condition in setting.findall("dependencies/dependency//condition"):
            found_any = True
            ref = condition.get("setting")
            if ref not in declared:
                bad.append("{0} -> {1}".format(setting.get("id"), ref))
    assert found_any, "no <dependency><condition> elements found; this guard would pass vacuously"
    assert bad == [], "dependency references a setting id that does not exist: {0}".format(bad)


def test_pending_modes_are_still_pending():
    """_PENDING_MODES exists solely because mode=profile is not wired into
    routes.dispatch yet (task-15-report.md defers that migration to a later task). It
    is a temporary allowance, not a permanent exemption: the moment a later task adds
    `if mode == "profile":` to routes.py, this assertion goes red, forcing whoever
    wired it up to delete the now-stale entry rather than let it linger unnoticed.
    """
    handled = set(_MODE_RE.findall(ROUTES_PY.read_text()))
    still_pending = _PENDING_MODES & handled
    assert not still_pending, (
        "these modes are now handled by routes.dispatch; remove them from "
        "_PENDING_MODES: {0}".format(sorted(still_pending))
    )


#: A profile-picker setting's id is "profile_" plus its slot verbatim
#: (profile_movie -> movie, profile_tv_4k -> tv_4k), so the mapping is a plain prefix
#: strip, not a lookup table that could itself drift out of sync.
_PROFILE_SETTING_PREFIX = "profile_"


def test_profile_row_slot_matches_its_own_setting_id(root):
    """Each profile-picker row's RunPlugin(...&slot=X) must write back to the same slot
    its own row displays. A copy-paste error -- profile_tv_4k pointing at slot=movie_4k
    -- passes every other guard here: the URL still parses, still targets a pending
    mode, still names no missing setting. The bug is invisible on the device too: the
    wrong slot gets written, and the row simply shows a label for a profile it did not
    set, with nothing to say the two have diverged.
    """
    checked = 0
    bad = []
    for setting in root.iter("setting"):
        setting_id = setting.get("id") or ""
        if not setting_id.startswith(_PROFILE_SETTING_PREFIX):
            continue
        expected_slot = setting_id[len(_PROFILE_SETTING_PREFIX):]
        data = setting.find("control/data")
        assert data is not None and data.text, "{0}: no control/data".format(setting_id)
        match = re.search(r"RunPlugin\((.+)\)$", data.text.strip())
        assert match, "{0}: data is not a RunPlugin(...) call: {1}".format(setting_id, data.text)
        parsed = urlparse(match.group(1))
        actual_slot = dict(parse_qsl(parsed.query)).get("slot")
        checked += 1
        if actual_slot != expected_slot:
            bad.append("{0}: slot={1!r}, expected {2!r}".format(setting_id, actual_slot, expected_slot))
    assert checked, "no profile_* settings found; this guard would pass vacuously"
    assert bad == [], "row's slot= does not match its own setting id: {0}".format(bad)


def test_every_v2_label_id_is_defined_and_nonempty():
    """The labels the pure builders receive are looked up by id at runtime; a missing one
    renders as an empty entry in the detail listing, which looks like a broken addon.

    An id that resolves to an empty string renders as a blank row on the device and looks
    exactly like the literal-label bug that shipped once already, equally invisible in
    the log. Every v2 string must have a non-empty msgid.

    Required ids are read from routes.LABEL_IDS itself, not hand-copied here: a hardcoded
    duplicate of that dict is exactly the kind of leftover the named-preset -> default
    profile migration left behind once already (ten ids that nothing referenced, caught
    only by rereading the source). Settings.xml's own label/help ids (the 30070-30087
    profile-row range, and 30030) are covered separately by
    test_every_label_id_exists_in_strings_po, which reads them from settings.xml itself.
    """
    from couchseerr import routes

    po_text = STRINGS_PO.read_text()
    # Extract all msgctxt ids and their corresponding msgids
    entries = re.findall(
        r'msgctxt\s+"#(\d+)"\nmsgid\s+"([^"]*)"',
        po_text
    )
    po_dict = dict(entries)

    # Every id routes.py actually looks up at runtime.
    required_ids = {str(value) for value in routes.LABEL_IDS.values()}

    missing = required_ids - set(po_dict.keys())
    assert not missing, "missing string ids: {0}".format(sorted(missing))

    empty = [id_ for id_ in required_ids if not po_dict.get(id_, "").strip()]
    assert not empty, "these ids have empty msgid: {0}".format(sorted(empty))


def test_strings_po_integrity():
    """Validate .po file structure without external tools.

    Every msgctxt id must be unique (no duplicates). Every msgid other than the
    single gettext header entry must be non-empty. Empty msgids create holes in
    the string table that render as blank rows on the device.
    """
    po_text = STRINGS_PO.read_text()

    # Check for duplicate msgctxt ids
    all_ids = re.findall(r'msgctxt\s+"#(\d+)"', po_text)
    duplicates = [id_ for id_ in set(all_ids) if all_ids.count(id_) > 1]
    assert not duplicates, "duplicate msgctxt ids: {0}".format(sorted(duplicates))

    # Check for empty msgids (except the gettext header, which has an empty msgid)
    # The header is the first msgctxt-less entry followed by msgid ""
    entries = re.split(r'\nmsgctxt\s+"#\d+"', po_text)
    if len(entries) > 1:
        # Skip the header (first entry before first msgctxt)
        for entry in entries[1:]:
            # Each entry starts with \nmsgid "..."
            match = re.search(r'\nmsgid\s+"([^"]*)"', entry)
            if match:
                msgid = match.group(1)
                # Extract the msgctxt for error reporting
                ctx_match = re.search(r'msgctxt\s+"#(\d+)"', entry)
                ctx = ctx_match.group(1) if ctx_match else "unknown"
                assert msgid.strip(), "empty msgid for id {0}".format(ctx)
