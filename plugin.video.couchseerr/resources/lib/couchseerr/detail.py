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
"""Build the detail listing: the entries offered for one title.

Every tile click lands here, owned or not, so this module owns the answer to "what can
the user do with this title right now". Pure: the state, a resolved default profile (or
None when the caller has none configured) and labels come in, specs go out.

Each entry carries the *title's* art and info, never its own. The skin's info pane and
DialogVideoInfo render whatever item is focused, so an entry describing itself would
blank the film the moment the user moved onto it.

Every entry but one is a non-folder, and that is what makes RunPlugin semantics apply to
it. The exception is the Seasons entry offered on a tv title: it is a folder, the way
into the season listing, and the only entry this module ever marks as one. Kodi's
CGUIMediaWindow::OnClick branches three ways on a plugin item:

  folder                                -> navigate into the path; the addon is called as
                                           a directory and must render a listing
  non-folder, isplayable not set        -> run the addon as a script, handle -1, exactly
                                           what the RunPlugin builtin does
  non-folder, isplayable true           -> play it; the addon must answer setResolvedUrl

mode=request, mode=play, mode=settings and mode=trailer render no listing: they act and
end with a notification (mode=settings opens the addon's own settings dialog instead).
That is the middle branch, so those entries must be non-folders and must *not* claim
isplayable -- claiming it would make Kodi try to play the plugin URL and raise a
failed-playback dialog. This is why the addon writes no explicit RunPlugin anywhere: the
builtin is the setting-level spelling of the same behaviour (see resources/settings.xml),
and a listing entry gets it from the item flags instead. mode=seasons is the lone
exception: it is meant to be navigated into, so it takes the first branch instead, and
routes.py answers it with an actual listing rather than a notification.
"""
try:
    from urllib.parse import urlencode
except ImportError:  # pragma: no cover
    from urllib import urlencode

from .state import REQUESTABLE_STATES, TileState
from .ui.spec import ListItemSpec, art_and_info, request_context_items, request_urls


def build_detail(item, state, resolved, base_url, image_base, labels,
                 in_library, trailer_key, status_line):
    """`resolved` is the caller's already-resolved default for this title's media type
    -- `request_config.resolve()`'s return value, or None when no default profile is
    configured for it. Resolving here would need the settings file and the addon's own
    prefer_4k setting, neither of which this pure module has access to; the caller
    (routes.py) is the one that reads both and hands the answer in.
    """
    # Shared with build_spec, deliberately: a tile and this listing describe the same
    # title, and a second copy of the backdrop mapping is how the two drift apart.
    art, info = art_and_info(item, image_base)

    # A user standing in this listing must not have to back out to the row to reach a
    # one-off profile override: every entry carries the same two context items a tile
    # does, gated on the exact same condition -- state in REQUESTABLE_STATES -- so an
    # owned or in-flight title's entries stay unreachable for a request, the same gate
    # that keeps a duplicate request unreachable from the tile side. Computed once
    # (not per entry): the state is fixed for the whole call, so every entry gets an
    # identical menu, request_context_items's own "omit both if either label is
    # missing" rule included.
    context_items = []
    if state in REQUESTABLE_STATES:
        request_url, pick_url = request_urls(item, base_url)
        context_items = request_context_items(request_url, pick_url, labels)

    def entry(label, params=None, is_folder=False):
        # params=None is a line the user reads, not an action: the status line and the
        # "not in the Kodi library" explanation. It carries no URL because there is
        # nothing to run, and no isplayable property is ever set here -- see the module
        # docstring for the three branches that flag combination selects.
        url = ""
        if params is not None:
            url = "{0}?{1}".format(base_url, urlencode(params))
        return ListItemSpec(
            label=label, url=url, is_folder=is_folder, art=dict(art),
            properties={"seerr.status": state.value}, info=dict(info),
            context_items=context_items,
        )

    identity = {"tmdb_id": item.tmdb_id, "media_type": item.media_type}
    specs = []

    if state is TileState.OWNED:
        # No whole-show Play: Player.Open has no tvshowid parameter (verified against
        # JSONRPC.Introspect on the target device), so this never worked for a tv title.
        # Seasons, appended below regardless of state, is the way into an owned show and
        # reaches an episode that genuinely plays.
        if item.media_type != "tv":
            if in_library:
                specs.append(entry(labels["play"], dict(identity, mode="play")))
            else:
                specs.append(entry(labels["not_in_library"]))
    elif state in REQUESTABLE_STATES:
        if resolved is None:
            # No default profile configured for this media type: offering "Demander"
            # here would resolve to nothing and send seerr an empty body. Send the user
            # to fix it instead -- the context menu's "Demander avec..." still works
            # without a default, since it always fetches its own choice.
            specs.append(entry(labels["configure"], {"mode": "settings"}))
        else:
            specs.append(entry(labels["request"], dict(identity, mode="request")))
    elif status_line:
        specs.append(entry(status_line))

    if item.media_type == "tv":
        # The one folder in this listing. Whole-show requesting stays above it, unchanged;
        # this is the way to a single season, and the only way a partial show reaches its
        # missing seasons at all.
        specs.append(
            entry(labels["seasons"], {"mode": "seasons", "tmdb_id": item.tmdb_id},
                  is_folder=True)
        )

    if trailer_key:
        specs.append(
            entry(
                labels["trailer"],
                {"mode": "trailer", "youtube_id": trailer_key},
            )
        )
    return specs
