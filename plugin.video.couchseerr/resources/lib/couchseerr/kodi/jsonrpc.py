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
"""JSON-RPC calls into Kodi itself. Kodi-facing by definition; holds no decisions.

The matching logic lives in couchseerr.library, which is pure and tested; this module
only fetches records and issues commands.
"""
import json

import xbmc

_LIBRARY_METHODS = {
    "movie": ("VideoLibrary.GetMovies", "movies"),
    "tv": ("VideoLibrary.GetTVShows", "tvshows"),
}
#: No "tv" entry: Player.Open's item accepts movieid/episodeid/... but not tvshowid
#: (verified against JSONRPC.Introspect on the target device), so whole-show Play never
#: worked. detail.available_actions no longer offers it; the window's season list is the
#: way into a show, down to a single episode that genuinely plays.
_PLAY_KEYS = {"movie": "movieid", "episode": "episodeid"}

#: Only "movie": library_file_path serves the play route, and detail.can_play_from_library
#: already refuses every tv title there (Player.Open has no tvshowid, so a whole show was
#: never playable). An episode reaches playback through mode=play, which plays by id and
#: needs no path.
_DETAIL_METHODS = {"movie": ("VideoLibrary.GetMovieDetails", "movieid", "moviedetails")}

#: What Kodi is asked for per episode. seasons.episode_label_and_info reads title,
#: episode, plot, firstaired, playcount and resume, and detailview._episode_row reads art;
#: season and runtime are requested for the skin and for future use, read by neither.
_EPISODE_PROPERTIES = ["title", "episode", "season", "plot", "firstaired", "playcount",
                       "resume", "art", "runtime"]


def _call(method, params):
    payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
    raw = xbmc.executeJSONRPC(json.dumps(payload))
    try:
        return json.loads(raw).get("result") or {}
    except (ValueError, AttributeError):
        # A malformed answer from Kodi is not something a caller can act on, and it is
        # not a seerr failure either: report it as no records rather than invent a shape.
        xbmc.log("[couchseerr] unparseable JSON-RPC reply to " + method, xbmc.LOGWARNING)
        return {}


def library_records(media_type):
    method, key = _LIBRARY_METHODS[media_type]
    result = _call(method, {"properties": ["uniqueid", "year", "title"]})
    return result.get(key) or []


def episode_records(tvshowid, season):
    """Kodi's own episodes for one season. An unscanned season is [] -- a state the caller
    renders, not a failure."""
    result = _call(
        "VideoLibrary.GetEpisodes",
        {"tvshowid": tvshowid, "season": season, "properties": _EPISODE_PROPERTIES,
         "sort": {"method": "episode", "order": "ascending"}},
    )
    return result.get("episodes") or []


def library_file_path(media_type, library_id):
    """Kodi's own path for one library item, or "" when Kodi holds none.

    Wanted only by the play route (routes._play_tile), which has to hand Kodi a path
    rather than start playback itself: Kodi is *asking* what to play, and answering it
    with a Player.Open of our own leaves the request it made unanswered -- measured on
    the device as a "playback failed" dialog over the film it had just been told to play.

    "" is not a swallowed failure. It is a library record carrying no file, which the
    caller renders as "cannot play" exactly like a title Kodi never scraped -- the same
    answer, reached one step later.
    """
    method, id_key, result_key = _DETAIL_METHODS[media_type]
    result = _call(method, {id_key: library_id, "properties": ["file"]})
    return (result.get(result_key) or {}).get("file") or ""


def play_library_item(media_type, library_id):
    params = {"item": {_PLAY_KEYS[media_type]: library_id}}
    if media_type == "episode":
        # Player.Open starts from zero and raises no resume dialog: that dialog belongs to
        # Kodi's GUI click path, not to JSON-RPC. resume:true continues a part-watched
        # episode silently from its stored point, and is a no-op for one never started.
        params["options"] = {"resume": True}
    _call("Player.Open", params)


def refresh_container():
    xbmc.executebuiltin("Container.Refresh")
