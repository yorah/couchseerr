SORT_METHOD_UNSORTED = 0

_added = []
_ended = []
_content = []


def addDirectoryItem(handle, url, listitem, isFolder=False, totalItems=0):
    _added.append((handle, url, listitem, isFolder))
    return True


def addDirectoryItems(handle, items, totalItems=0):
    for url, li, is_folder in items:
        _added.append((handle, url, li, is_folder))
    return True


def endOfDirectory(handle, succeeded=True, updateListing=False, cacheToDisc=True):
    _ended.append((handle, succeeded, cacheToDisc))


def setContent(handle, content):
    _content.append((handle, content))


def setPluginCategory(handle, category):
    pass
