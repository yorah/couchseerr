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
        # "" means "this row leads nowhere" -- a line the user reads, not an action. The
        # one spelling of that across the addon (detailview.EpisodeRow uses it too), so a
        # renderer never has to remember which type says "" and which says None.
        self.url = url
        self.is_folder = is_folder
        self.art = art
        self.properties = properties
        self.info = info
        # A list of (label, action) pairs for ListItem.addContextMenuItems. Data on the
        # spec, not a second construction site: kodi/adapter.py only ever *applies* what
        # is here, it never decides what belongs on a tile's context menu. Defaults to
        # none -- most specs (the window's own action rows, the four root folders) offer
        # no context menu at all.
        self.context_items = list(context_items) if context_items else []


def art_and_info(item, image_base):
    """The art and info dicts for one title, in one place.

    A row tile and the detail window describe the same title, so both need the same two
    dicts. Building them twice is how the backdrop mapping below drifts
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

    build_spec is the only caller: every tile's context menu goes through this one
    function, so no two menus can drift into two different shapes. Omits *both* items
    when either label is blank, rather than
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


def build_spec(item, state, base_url, image_base, labels, widget=False):
    """`widget` says this listing is being rendered into a skin's home widget rather than
    browsed in Kodi's video window, which changes the one thing a tile cannot decide for
    itself: what a click on it does.

    Browsed, a non-folder tile runs the addon as a script and opens the detail window.
    In a widget, the skin never lets that click reach the addon at all -- Arctic Fuse
    answers it with Kodi's own video info dialog (measured on the device, with the tile
    both playable and not). A folder does reach the addon there, so a widget tile is one,
    and carries `open=1` so routes.dispatch can tell that arrival apart from Kodi asking
    to *play* the very same url, which looks identical otherwise: both come in with a
    real handle.
    """
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

    # Every tile, owned or not, carries a request without opening the detail window
    # first -- see the "Choosing a different profile for one title" section of the
    # design doc. A tile that is owned, downloading, monitored, unreleased or pending
    # gets neither entry: offering one there is how a duplicate request gets created
    # underneath actions/request.py's own refusal.
    context_items = (
        request_context_items(request_url, pick_url, labels) if requestable else []
    )

    params = {"mode": "detail", "tmdb_id": item.tmdb_id, "media_type": item.media_type}
    if widget:
        params["open"] = 1
    url = "{0}?{1}".format(base_url, urlencode(params))

    return ListItemSpec(
        label=label,
        url=url,
        # Browsed: not a folder, and no isplayable property. That combination is Kodi's
        # run-the-addon-as-a-script branch, which is how mode=detail gets a handle of -1
        # and opens a window instead of rendering a listing. Claiming isplayable would
        # make Kodi try to play the plugin URL instead.
        #
        # In a widget it *is* a folder, because the skin gives a non-folder tile to
        # Kodi's info dialog rather than to us. The directory that folder asks for is
        # never rendered: mode=detail ends it immediately and re-enters as a script (see
        # routes._reopen_as_script), which is the context the window can open in.
        is_folder=widget,
        art=art,
        properties=properties,
        info=info,
        context_items=context_items,
    )


def resolved_spec(item, path, image_base):
    """The row Kodi gets back when it asked to *play* a tile rather than open it.

    Kodi offers "Play" on every tile in a video listing -- its own context entry, which
    an addon cannot remove while the tile carries a video info tag (measured on the
    device: dropping the tag removes the entry, and every other lever, replaceItems
    included, changes nothing). So the tile answers that question honestly instead:
    routes._play_tile hands this spec the path Kodi's own library holds for the film.

    Deliberately carries no properties and no context items. Nothing reads a resolved
    item's tile state -- it is the file about to play, not a row in a wall.
    """
    art, info = art_and_info(item, image_base)
    return ListItemSpec(
        label=item.title, url=path, is_folder=False, art=art, properties={}, info=info,
    )


def unplayable_spec():
    """The row Kodi gets back when there is nothing to play: an owned film missing from
    the Kodi library, a title nobody has requested yet, a whole tv show.

    setResolvedUrl demands a ListItem even to say "no", so this is that item. Its empty
    url is the same "leads nowhere" spelling ListItemSpec.url already carries, which is
    what lets kodi.adapter.resolve read success straight off the spec.
    """
    return ListItemSpec(
        label="", url="", is_folder=False, art={}, properties={}, info=None,
    )
