import pathlib
import re

_settings = {
    "seerr_url": "http://seerr.test:5055",
    "api_key": "fixture-key",
    "language": "",
    "view_mode": "",
}

# tests/stubs/xbmcaddon.py -> tests/stubs -> tests -> repo root
_STRINGS_PO = (
    pathlib.Path(__file__).resolve().parents[2]
    / "plugin.video.couchseerr"
    / "resources"
    / "language"
    / "resource.language.en_gb"
    / "strings.po"
)


def _load_strings():
    """Read id -> msgid text out of the shipped strings.po.

    Real Kodi falls back to msgid when msgstr is blank, which every entry in the base
    en_gb file is. A stub that instead echoed back the bare numeric id could never
    exercise a caller's use of `.format(...)` on a localised string -- it would pass
    whether or not the substitution actually worked.
    """
    strings = {}
    try:
        text = _STRINGS_PO.read_text(encoding="utf-8")
    except OSError:
        return strings
    for match in re.finditer(
        r'msgctxt "#(\d+)"\s*\nmsgid "((?:[^"\\]|\\.)*)"', text
    ):
        strings[int(match.group(1))] = match.group(2)
    return strings


_STRINGS = _load_strings()


class Addon:
    def __init__(self, id=None):
        self.id = id or "plugin.video.couchseerr"

    def getSetting(self, key):
        return _settings.get(key, "")

    def getSettingBool(self, key):
        return bool(_settings.get(key))

    def setSetting(self, key, value):
        _settings[key] = value

    def getAddonInfo(self, key):
        return {
            "id": self.id,
            "name": "Couchseerr",
            "version": "0.1.0",
            "profile": "special://profile/addon_data/plugin.video.couchseerr/",
            "path": "special://home/addons/plugin.video.couchseerr/",
        }.get(key, "")

    def getLocalizedString(self, sid):
        # Falls back to the bare id when the string table has nothing for it, e.g. a
        # test id that deliberately does not exist in strings.po.
        return _STRINGS.get(sid, str(sid))
