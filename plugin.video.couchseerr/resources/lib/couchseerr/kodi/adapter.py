# Couchseerr -- seerr discovery rows for Kodi
# Copyright (C) 2026 yorah
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version.
#
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along with
# this program. If not, see <https://www.gnu.org/licenses/>.
"""Translate ListItemSpec into Kodi objects. Deliberately contains no decisions.

Kodi 19 through 22 are supported, which constrains two calls:
  * setProperties (plural) is unreliable on 19, so properties are set one at a time.
  * setInfo is deprecated from Kodi 20 and may be gone in 22, while InfoTagVideo setters
    do not exist before 20 - so apply_info picks whichever the running Kodi offers.
"""
import xbmcgui
import xbmcplugin

_INFO_TAG_SETTERS = {
    "title": "setTitle",
    "plot": "setPlot",
    "year": "setYear",
    "premiered": "setPremiered",
    "playcount": "setPlaycount",
}


def apply_info(item, info):
    """Set video metadata using whichever API this Kodi provides."""
    tag = None
    getter = getattr(item, "getVideoInfoTag", None)
    if getter is not None:
        candidate = getter()
        # Kodi 19 returns an InfoTagVideo with getters only; the setters arrived in 20.
        if hasattr(candidate, "setTitle"):
            tag = candidate

    if tag is not None:
        for key, value in info.items():
            if key == "resume":
                # Two arguments, so it cannot go through the single-setter table above.
                # Guarded the same way every setter in that table is: Kodi 19's
                # InfoTagVideo has no setResumePoint at all, and calling it unguarded
                # would raise inside render, losing the whole listing to
                # _fail_unexpected over a missing resume bar. The episode still plays
                # either way, and JSON-RPC resumes it regardless.
                position, total = value
                setter = getattr(tag, "setResumePoint", None)
                if setter is not None:
                    setter(position, total)
                continue
            setter = getattr(tag, _INFO_TAG_SETTERS.get(key, ""), None)
            if setter is not None:
                setter(value)
        return

    item.setInfo("video", {k: v for k, v in info.items() if k != "resume"})


def to_list_item(spec):
    item = xbmcgui.ListItem(label=spec.label)
    if spec.art:
        item.setArt(spec.art)
    for key, value in (spec.properties or {}).items():
        item.setProperty(key, value)
    if spec.info:
        apply_info(item, spec.info)
    if spec.context_items:
        item.addContextMenuItems(spec.context_items)
    return item


def resolve(handle, spec):
    """Answer Kodi's "what do I play for this item?" with the spec's url.

    Kodi asks that whenever someone picks its own Play entry on a tile, or presses the
    remote's Play key on one -- a question a tile cannot dodge, only answer. Success is
    read off the spec rather than passed in: a spec whose url is "" leads nowhere, which
    is this project's one spelling of that, and a failed resolve is Kodi's own silent
    "nothing to play" (the route notifies the reason).

    setPath is what Kodi actually plays; the ListItem itself still comes from
    to_list_item, so this adds no second construction site.
    """
    item = to_list_item(spec)
    item.setPath(spec.url)
    xbmcplugin.setResolvedUrl(handle, bool(spec.url), item)


def render(handle, specs, content_type="videos"):
    """Add every spec, then close the directory on success.

    Closes only when the loop completes without error. dispatch() owns every
    failure close (typed and catch-all alike), so an exception here must
    propagate untouched rather than close the directory a second time.

    `content_type` must reflect what the row actually contains: "movies" or
    "tvshows" get skins to render a proper poster wall, but applying either to a
    mixed row (or the four-folder root menu) renders it as a wall of blank
    poster placeholders instead. Callers pass the row's own content type.

    `cacheToDisc=False` on every call, success or failure: the default `True`
    lets Kodi re-serve a cached directory listing on the way back in, bypassing
    the cache TTL below it entirely -- most consequentially for the 30s-TTL
    processing row, whose whole point is showing live progress.
    """
    for spec in specs:
        xbmcplugin.addDirectoryItem(
            handle, spec.url, to_list_item(spec), spec.is_folder
        )
    xbmcplugin.setContent(handle, content_type)
    xbmcplugin.endOfDirectory(handle, cacheToDisc=False)
