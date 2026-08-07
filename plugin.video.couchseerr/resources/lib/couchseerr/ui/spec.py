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
"""The single ListItem construction site.

Pure by design: it emits a description of a list item, and the Kodi adapter turns that
into an xbmcgui.ListItem. Duplicating this logic per view is what makes status handling
drift between views, so there is exactly one of it.
"""
try:
    from urllib.parse import urlencode
except ImportError:  # pragma: no cover - Python 2 never runs this addon
    from urllib import urlencode

from ..markers import marker_for
from ..state import REQUESTABLE_STATES, TileState


class ListItemSpec(object):
    __slots__ = ("label", "url", "is_folder", "art", "properties", "info", "context_items")

    def __init__(self, label, url, is_folder, art, properties, info, context_items=None):
        self.label = label
        self.url = url
        self.is_folder = is_folder
        self.art = art
        self.properties = properties
        self.info = info
        # A list of (label, action) pairs for ListItem.addContextMenuItems. Data on the
        # spec, not a second construction site: kodi/adapter.py only ever *applies* what
        # is here, it never decides what belongs on a tile's context menu. Defaults to
        # none -- most specs (the detail listing's own action rows, the four root
        # folders) offer no context menu at all.
        self.context_items = list(context_items) if context_items else []


def art_and_info(item, image_base):
    """The art and info dicts for one title, in one place.

    Both the row tiles and the detail listing's entries describe the same title, so both
    need the same two dicts. Building them twice is how the backdrop mapping below drifts
    between the two views without anything noticing -- the exact class of bug the single
    construction site exists to prevent, one layer up. This is data shaping only: it
    builds no ListItem and no ListItemSpec, so build_spec remains the only builder and
    adapter.to_list_item the only construction site.

    Returns fresh dicts on every call. Callers store them on specs that Kodi mutates
    through, so a shared dict would leak one entry's edits into every other.
    """
    art = {}
    if item.poster_path:
        art["poster"] = image_base + item.poster_path
        art["thumb"] = art["poster"]
    if item.backdrop_path:
        # seerr returns no landscape artwork; mapping the backdrop to both keys is what
        # frees rows from being forced to Poster styling.
        art["fanart"] = image_base + item.backdrop_path
        art["landscape"] = art["fanart"]

    info = {"title": item.title, "plot": item.overview}
    if item.release_date is not None:
        info["year"] = item.release_date.year
        info["premiered"] = item.release_date.isoformat()

    return art, info


def request_urls(item, base_url, season=None):
    """The two request URLs a requestable title can carry: the ordinary defaults, and the
    same route with pick=1 to force the cross-server picker. Built once so the
    skin-facing property and every context menu action (a tile's, a requestable title's
    own listing entries, and a season's) never drift into two different copies of the
    same query string.

    `season` scopes both URLs to one season. Absent means the whole show, which is what
    every movie and every whole-show request passes.
    """
    params = {"mode": "request", "tmdb_id": item.tmdb_id, "media_type": item.media_type}
    if season is not None:
        params["season"] = season
    request_url = "{0}?{1}".format(base_url, urlencode(params))
    pick_url = "{0}?{1}".format(base_url, urlencode(dict(params, pick=1)))
    return request_url, pick_url


def request_context_items(request_url, pick_url, labels):
    """The two context-menu items ("Demander" / "Demander avec...") for a requestable
    title, given its two request URLs -- or [] when either label is missing.

    Shared by build_spec (every tile) and detail.py's build_detail (every entry of a
    requestable title's own listing) so the two menus can never drift into two
    different shapes. Omits *both* items when either label is blank, rather than
    emitting one with a blank label: an unlabelled, still-clickable menu entry is worse
    than none, and a menu carrying only "Demander" with no "Demander avec..." would
    silently drop the picker with nothing to say why.
    """
    request_label = labels.get("request")
    request_with_label = labels.get("request_with")
    if not request_label or not request_with_label:
        return []
    return [
        (request_label, "RunPlugin({0})".format(request_url)),
        (request_with_label, "RunPlugin({0})".format(pick_url)),
    ]


def build_spec(item, state, base_url, image_base, labels):
    download = item.media.best_download if item.media else None
    marker = marker_for(state, item, download)
    label = "{0} {1}".format(marker, item.title).strip() if marker else item.title

    art, info = art_and_info(item, image_base)

    properties = {
        "seerr.status": state.value,
        # Truncate, matching markers.marker_for, so the label and this property never
        # disagree and 99.6% is never shown as the false claim "100".
        # A download record can be present but unreadable, in which case tile_state()
        # has already fallen back to a non-DOWNLOADING state (see state.py); progress
        # must follow that fallback rather than render the unreadable record's "0".
        "seerr.progress": (
            str(int(download.percent)) if download and state is TileState.DOWNLOADING else ""
        ),
        "seerr.eta": (download.time_left or "") if download else "",
    }

    requestable = state in REQUESTABLE_STATES
    properties["seerr.requestable"] = "1" if requestable else ""

    request_url, pick_url = request_urls(item, base_url)
    # A ready-to-run path, so a skin can offer a request without composing a URL out of
    # properties it would have to keep in sync with this addon's routing.
    properties["seerr.action.request"] = request_url if requestable else ""

    # Every tile, owned or not, carries a request without opening the detail listing
    # first -- see the "Choosing a different profile for one title" section of the
    # design doc. A tile that is owned, downloading, monitored, unreleased or pending
    # gets neither entry: offering one there is how a duplicate request gets created
    # underneath actions/request.py's own refusal.
    context_items = (
        request_context_items(request_url, pick_url, labels) if requestable else []
    )

    url = "{0}?{1}".format(
        base_url,
        urlencode(
            {"mode": "item", "tmdb_id": item.tmdb_id, "media_type": item.media_type}
        ),
    )

    return ListItemSpec(
        label=label,
        url=url,
        is_folder=True,
        art=art,
        properties=properties,
        info=info,
        context_items=context_items,
    )
