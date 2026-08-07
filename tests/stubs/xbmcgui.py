class InfoTagVideo:
    """Modern (Kodi 20+) metadata API. Records what the adapter sets."""

    def __init__(self):
        self.values = {}

    def setTitle(self, value):
        self.values["title"] = value

    def setPlot(self, value):
        self.values["plot"] = value

    def setYear(self, value):
        self.values["year"] = value

    def setPremiered(self, value):
        self.values["premiered"] = value

    def setPlaycount(self, value):
        self._playcount = value

    def setResumePoint(self, position, total):
        self._resume = (position, total)


class ListItem:
    def __init__(self, label="", label2="", offscreen=False):
        self.label = label
        self.label2 = label2
        self._art = {}
        self._props = {}
        self._info = {}
        self._paths = None
        self._tag = InfoTagVideo()
        self._context_items = None

    def getVideoInfoTag(self):
        return self._tag

    def addContextMenuItems(self, items, replaceItems=False):
        self._context_items = list(items)

    def setArt(self, art):
        self._art.update(art)

    def setProperty(self, key, value):
        self._props[key] = value

    def setProperties(self, props):
        self._props.update(props)

    def setInfo(self, type_, info):
        self._info.setdefault(type_, {}).update(info)

    def setPath(self, path):
        self._paths = path

    def getLabel(self):
        return self.label


#: Module-level record of every notification shown, across Dialog instances.
#: routes._fail() builds a fresh Dialog() per call, so tests need a place to
#: observe notifications that outlives any single instance.
_notifications = []

#: Scripted answers for select()/input(), and a record of every select() heading and
#: options seen -- across Dialog instances, for the same reason _notifications is.
_select_answers = []
_input_answers = []
_selects_seen = []


class Dialog:
    def __init__(self):
        self.notifications = []
        self.selects = []
        self._select_result = -1

    def notification(self, heading, message, icon=None, time=5000, sound=True):
        self.notifications.append((heading, message))
        _notifications.append((heading, message))

    def select(self, heading, options):
        self.selects.append((heading, options))
        _selects_seen.append((heading, list(options)))
        return _select_answers.pop(0) if _select_answers else -1

    def input(self, heading, defaultt="", **kwargs):
        return _input_answers.pop(0) if _input_answers else ""


#: Kodi action ids, as xbmcgui exposes them. Named constants rather than the integers so a
#: caller that gets the name wrong raises here instead of silently never matching.
ACTION_PREVIOUS_MENU = 10
ACTION_NAV_BACK = 92


class Action:
    def __init__(self, action_id):
        self._id = action_id

    def getId(self):
        return self._id


class ControlList:
    """Enough of Kodi's ControlList for the window's dispatch: fill, clear, and report
    which row is selected. It models no layout and no focus behaviour, deliberately.
    """

    def __init__(self, control_id):
        self.control_id = control_id
        self.items = []
        self._selected = 0

    def reset(self):
        self.items = []
        self._selected = 0

    def addItems(self, items):
        self.items.extend(items)

    def size(self):
        return len(self.items)

    def getSelectedPosition(self):
        return self._selected if self.items else -1

    def selectItem(self, position):
        self._selected = position


class WindowXML:
    """Stand-in for xbmcgui.WindowXML. Records properties, hands out ControlLists on
    demand, and records close(). Kodi's own window does far more; nothing in the addon
    may depend on anything this does not model.
    """

    def __init__(self, xmlFilename="", scriptPath="", defaultSkin="Default",
                 defaultRes="720p", isMedia=False):
        self.xmlFilename = xmlFilename
        self.scriptPath = scriptPath
        self.defaultSkin = defaultSkin
        self.defaultRes = defaultRes
        self._properties = {}
        self._controls = {}
        self._focus_id = None
        self._closed = False

    def setProperty(self, key, value):
        self._properties[key] = value

    def getProperty(self, key):
        return self._properties.get(key, "")

    def getControl(self, control_id):
        return self._controls.setdefault(control_id, ControlList(control_id))

    def setFocusId(self, control_id):
        self._focus_id = control_id

    def doModal(self):
        pass

    def close(self):
        self._closed = True

    def onInit(self):
        pass

    def onClick(self, control_id):
        pass

    def onAction(self, action):
        pass


#: Kodi's own id for the home screen. The addon reads the current window to tell a home
#: widget's render apart from the addon being browsed in the video window (10025).
WINDOW_HOME = 10000

_current_window_id = 10025


def getCurrentWindowId():
    return _current_window_id
