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
import pytest
import xbmc

from couchseerr.kodi import jsonrpc


def setup_function():
    del xbmc._jsonrpc_calls[:]
    del xbmc._log_calls[:]
    xbmc._jsonrpc_responses.clear()
    xbmc._jsonrpc_raw.clear()


def test_library_records_asks_for_the_fields_the_matcher_needs():
    xbmc._jsonrpc_responses["VideoLibrary.GetMovies"] = {
        "movies": [{"movieid": 1, "label": "Dune", "year": 2021,
                    "uniqueid": {"imdb": "tt1160419"}}]
    }
    records = jsonrpc.library_records("movie")

    assert records[0]["movieid"] == 1
    params = xbmc._jsonrpc_calls[0]["params"]
    assert set(params["properties"]) == {"uniqueid", "year", "title"}


def test_library_records_uses_gettvshows_for_tv():
    xbmc._jsonrpc_responses["VideoLibrary.GetTVShows"] = {"tvshows": []}
    assert jsonrpc.library_records("tv") == []
    assert xbmc._jsonrpc_calls[0]["method"] == "VideoLibrary.GetTVShows"


def test_library_records_empty_when_kodi_reports_no_result():
    """An empty library is not a failure; it is a library with nothing scraped."""
    assert jsonrpc.library_records("movie") == []


def test_library_records_warns_on_unparseable_reply():
    """A malformed reply is not a failure a caller can act on, but it must not be
    swallowed silently either: it has to reach the log as a warning."""
    xbmc._jsonrpc_raw["VideoLibrary.GetMovies"] = "not json"

    assert jsonrpc.library_records("movie") == []

    warnings = [msg for msg, level in xbmc._log_calls if level == xbmc.LOGWARNING]
    assert any("VideoLibrary.GetMovies" in msg for msg in warnings)


def test_play_opens_the_movie_by_library_id():
    jsonrpc.play_library_item("movie", 12)
    call = xbmc._jsonrpc_calls[0]
    assert call["method"] == "Player.Open"
    assert call["params"]["item"] == {"movieid": 12}


def test_play_library_item_has_no_whole_show_key():
    """Player.Open's item accepts movieid/episodeid/... but not tvshowid (verified
    against JSONRPC.Introspect on the target device); the old "tv" -> "tvshowid" entry
    sent a call Kodi silently rejected, so whole-show Play never worked. It is gone, and
    nothing above this function calls play_library_item("tv", ...) any more --
    detail.available_actions offers Seasons instead -- so the KeyError below is unreachable
    from the addon's own URLs, not a live failure mode."""
    assert "tv" not in jsonrpc._PLAY_KEYS
    with pytest.raises(KeyError):
        jsonrpc.play_library_item("tv", 34)


def test_episode_records_asks_kodi_for_one_season():
    xbmc._jsonrpc_responses["VideoLibrary.GetEpisodes"] = {
        "episodes": [{"episodeid": 11, "episode": 1, "title": "Chapter One"}]
    }
    records = jsonrpc.episode_records(7, 1)

    assert records[0]["episodeid"] == 11
    params = xbmc._jsonrpc_calls[0]["params"]
    assert params["tvshowid"] == 7
    assert params["season"] == 1
    assert set(params["properties"]) >= {"title", "episode", "playcount", "resume", "art"}
    assert params["sort"] == {"method": "episode", "order": "ascending"}


def test_episode_records_empty_when_kodi_reports_none():
    """A season Kodi has not scanned is a state, not a failure: the caller renders a line
    saying so."""
    xbmc._jsonrpc_responses["VideoLibrary.GetEpisodes"] = {}
    assert jsonrpc.episode_records(7, 1) == []


def test_playing_an_episode_asks_kodi_to_resume():
    """Player.Open starts at zero and raises no resume dialog -- that dialog belongs to
    Kodi's GUI click path, not the JSON-RPC one -- so a part-watched episode would restart
    from the beginning without this."""
    jsonrpc.play_library_item("episode", 11)
    call = xbmc._jsonrpc_calls[0]
    assert call["method"] == "Player.Open"
    assert call["params"]["item"] == {"episodeid": 11}
    assert call["params"]["options"] == {"resume": True}


def test_playing_a_movie_is_unchanged():
    jsonrpc.play_library_item("movie", 3)
    assert xbmc._jsonrpc_calls[0]["params"] == {"item": {"movieid": 3}}


def test_library_file_path_asks_kodi_for_the_file():
    xbmc._jsonrpc_responses["VideoLibrary.GetMovieDetails"] = {
        "moviedetails": {"movieid": 148, "file": "/mnt/movies/Dune.mkv"}
    }
    path = jsonrpc.library_file_path("movie", 148)

    assert path == "/mnt/movies/Dune.mkv"
    params = xbmc._jsonrpc_calls[0]["params"]
    assert params["movieid"] == 148
    assert params["properties"] == ["file"]


def test_library_file_path_empty_when_kodi_holds_none():
    """A library record with no path is a fact about Kodi's library, not a failure:
    the caller renders "cannot play" rather than resolving to an empty path."""
    xbmc._jsonrpc_responses["VideoLibrary.GetMovieDetails"] = {"moviedetails": {}}
    assert jsonrpc.library_file_path("movie", 148) == ""
