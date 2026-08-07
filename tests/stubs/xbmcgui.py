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
