import datetime

from urllib.parse import parse_qsl

from couchseerr.detailview import (
    Action, EpisodeRow, SeasonRow, action_spec, build_season_view, build_view,
    episode_spec, season_spec,
)
from couchseerr.models import DiscoverItem, Episode, Season
from couchseerr.seasons import JoinedEpisode, join_episodes
from couchseerr.state import TileState
from couchseerr.ui.spec import request_urls

BASE = "plugin://plugin.video.couchseerr/"
IMAGE = "https://image.tmdb.org/t/p/w780"
TODAY = datetime.date(2026, 8, 24)

RESOLVED = {"serverId": 0, "profileId": 21, "is4k": False}

# seerr hands back an absolute still URL (models.parse_season_episodes), so nothing is
# ever prefixed to it.
STILL_URL = "https://image.tmdb.org/t/p/original/still.jpg"


def _movie():
    return DiscoverItem(
        tmdb_id=693134, media_type="movie", title="Dune: Part Two", overview="Sand.",
        poster_path="/p.jpg", backdrop_path="/b.jpg",
        release_date=datetime.date(2024, 2, 28), media=None,
    )


def _show():
    return DiscoverItem(
        tmdb_id=82856, media_type="tv", title="The Show", overview="Plot.",
        poster_path="/p.jpg", backdrop_path="/b.jpg",
        release_date=datetime.date(2019, 11, 12), media=None,
    )


def _seasons():
    return [
        Season(1, "Season 1", 8, datetime.date(2019, 11, 12), "/s1.jpg"),
        Season(2, "Season 2", 8, datetime.date(2020, 10, 30), None),
    ]


def _labels():
    return {
        "play": "Play",
        "request": "Request",
        "request_with": "Request with...",
        "request_season": "Request this season",
        "configure": "Configure the default profile",
        "trailer": "Trailer",
        "seasons": "Seasons",
        "season": "Season {0}",
        "episode_count": "{0} episodes",
        "monitored": "Monitored",
        "pending": "Pending approval",
        "partial": "Partially available",
        "downloading": "Downloading {0}%",
        "unreleased": "Available {0}",
        "not_in_library": "Not in your Kodi library",
    }


def test_a_movie_view_has_no_season_rows():
    view = build_view(_movie(), TileState.OWNED, None, 42, None, [], [],
                      BASE, IMAGE, _labels(), TODAY)
    assert view.seasons == []
    assert [a.key for a in view.actions] == ["play"]


def test_a_view_carries_the_titles_own_art_and_plot():
    view = build_view(_movie(), TileState.OWNED, None, 42, None, [], [],
                      BASE, IMAGE, _labels(), TODAY)
    assert view.title == "Dune: Part Two"
    assert view.year == 2024
    assert view.plot
    assert view.art["poster"] and view.art["fanart"]


def test_every_action_carries_a_resolvable_url():
    view = build_view(_show(), TileState.ACTIONABLE, RESOLVED, None, "abc",
                      _seasons(), [], BASE, IMAGE, _labels(), TODAY)
    for action in view.actions:
        assert action.url.startswith(BASE + "?mode=")
        assert action.label


def test_season_rows_carry_marker_and_state():
    # seerr's raw per-season status entries, the shape models.media_seasons returns.
    media_seasons = [{"seasonNumber": 1, "status": 5}, {"seasonNumber": 2, "status": 3}]
    view = build_view(_show(), TileState.PARTIAL, None, None, None, _seasons(),
                      media_seasons, BASE, IMAGE, _labels(), TODAY)
    by_number = {row.number: row for row in view.seasons}
    assert by_number[1].state is TileState.OWNED
    assert by_number[1].marker
    # Season 2 is tracked but not available, so it is not requestable.
    assert by_number[2].state is not TileState.ACTIONABLE


def test_a_season_row_label_comes_from_seerr_not_fallback():
    view = build_view(_show(), TileState.PARTIAL, None, None, None, _seasons(), [],
                      BASE, IMAGE, _labels(), TODAY)
    assert view.seasons[0].label == "Season 1"


def test_the_view_holds_no_action_the_state_forbids():
    view = build_view(_movie(), TileState.DOWNLOADING, RESOLVED, None, None, [], [],
                      BASE, IMAGE, _labels(), TODAY)
    assert "request" not in [a.key for a in view.actions]


def test_no_in_flight_state_offers_a_request():
    """seerr's own duplicate guard is permissive, so a second request from here would
    often be created silently. The state already knows; refuse before offering. Every
    in-flight state, not just one: a gate loosened for a single member would pass a
    one-state check."""
    labels = _labels()
    for state in (TileState.DOWNLOADING, TileState.MONITORED, TileState.UNRELEASED,
                  TileState.PENDING, TileState.PARTIAL):
        view = build_view(_movie(), state, RESOLVED, None, None, [], [],
                          BASE, IMAGE, labels, TODAY)
        assert [a.key for a in view.actions] == [], state
        if state is not TileState.DOWNLOADING:
            # ...and the user is told what the title is doing instead of being left with
            # an actionless screen and no explanation. DOWNLOADING is excluded only
            # because this fixture carries no download record for it to read a percentage
            # from -- a shape tile_state cannot produce, and status_line's own tests
            # already pin the "" it degrades to.
            assert view.status_line, state


def test_a_partial_show_still_reaches_its_seasons():
    """The gap this whole feature exists to close: a partial show offers no whole-show
    request at all, so without the season rows its missing seasons are unreachable."""
    view = build_view(_show(), TileState.PARTIAL, RESOLVED, None, None,
                      _seasons(), [], BASE, IMAGE, _labels(), TODAY)
    assert [a.key for a in view.actions] == []
    assert [row.number for row in view.seasons] == [1, 2]


def test_an_owned_show_offers_its_seasons_and_nothing_else():
    """Whole-show Play never worked -- Player.Open has no tvshowid -- so an owned show
    has no action of its own; the season rows are the way in, and Kodi not having scanned
    the show does not take them away."""
    for in_library in (True, False):
        view = build_view(_show(), TileState.OWNED, RESOLVED, in_library, None,
                          _seasons(), [], BASE, IMAGE, _labels(), TODAY)
        assert view.actions == [], in_library
        assert [row.number for row in view.seasons] == [1, 2], in_library


def test_season_markers_come_from_the_shared_table():
    """markers.marker_for is the single source of the glyph, and the window reads it per
    season rather than restating a table of its own."""
    seasons = [
        Season(1, "Season 1", 8, datetime.date(2019, 11, 12), None),
        Season(2, "Season 2", 8, datetime.date(2020, 10, 30), None),
        Season(3, "Season 3", 8, datetime.date(2027, 1, 14), None),
    ]
    media_seasons = [{"seasonNumber": 1, "status": 5, "status4k": 1},
                     {"seasonNumber": 2, "status": 4, "status4k": 1},
                     {"seasonNumber": 3, "status": 3, "status4k": 1}]
    view = build_view(_show(), TileState.PARTIAL, None, None, None, seasons,
                      media_seasons, BASE, IMAGE, _labels(), TODAY)
    assert [row.marker for row in view.seasons] == ["[\u2713]", "[\u25d0]", "[2027-01-14]"]


def test_an_untracked_shows_seasons_are_all_requestable():
    """seerr records a season only once something has been asked for it, so a show nobody
    has requested carries no per-season status at all -- every season is actionable and
    unmarked, not unknown."""
    view = build_view(_show(), TileState.ACTIONABLE, RESOLVED, None, None,
                      _seasons(), [], BASE, IMAGE, _labels(), TODAY)
    assert [row.state for row in view.seasons] == [TileState.ACTIONABLE] * 2
    assert [row.marker for row in view.seasons] == ["", ""]


def test_a_season_name_falls_back_to_the_label_format():
    """seerr leaves a season's name empty when TMDb has none for it; the row must still
    read as a season rather than as a blank."""
    view = build_view(_show(), TileState.ACTIONABLE, RESOLVED, None, None,
                      [Season(4, "", 6, None, None)], [], BASE, IMAGE, _labels(), TODAY)
    assert view.seasons[0].label == "Season 4"


def test_an_owned_episode_row_carries_a_play_url():
    joined = [JoinedEpisode(number=1, title="A", owned=True, episode_id=11)]
    view = build_season_view(_show(), _seasons()[0], TileState.OWNED, None, joined,
                             BASE, IMAGE, _labels())
    assert view.episodes[0].url == BASE + "?mode=play&episode_id=11"


def test_an_unowned_episode_row_carries_no_url():
    """seerr has no episode-level request, so this row can never be actioned."""
    joined = [JoinedEpisode(number=5, title="Nightfall", owned=False)]
    view = build_season_view(_show(), _seasons()[0], TileState.PARTIAL, None, joined,
                             BASE, IMAGE, _labels())
    assert view.episodes[0].url == ""
    assert view.episodes[0].owned is False


def test_an_episode_label_leads_with_its_number():
    joined = [JoinedEpisode(number=3, title="Homecoming", owned=True, episode_id=13)]
    view = build_season_view(_show(), _seasons()[0], TileState.OWNED, None, joined,
                             BASE, IMAGE, _labels())
    assert view.episodes[0].label == "3. Homecoming"


def test_a_requestable_season_offers_a_season_scoped_request():
    view = build_season_view(_show(), _seasons()[0], TileState.ACTIONABLE, RESOLVED,
                             [], BASE, IMAGE, _labels())
    request = [a for a in view.actions if a.key == "request"][0]
    assert "season=1" in request.url


def test_a_partial_season_may_be_re_requested():
    """The gate here is SEASON_REQUESTABLE_STATES, wider than a title's: a partial season
    is one with missing episodes, and a fresh request is what tells Sonarr to search."""
    view = build_season_view(_show(), _seasons()[0], TileState.PARTIAL, RESOLVED, [],
                             BASE, IMAGE, _labels())
    assert [a.key for a in view.actions] == ["request", "request_with"]


def test_an_unreleased_season_offers_no_request():
    """Nothing to search for yet, and seerr accepts the request anyway -- so refuse to
    offer it rather than reporting a success that downloads nothing."""
    view = build_season_view(_show(), _seasons()[0], TileState.UNRELEASED, RESOLVED, [],
                             BASE, IMAGE, _labels())
    assert view.actions == []


def test_a_season_with_no_default_sends_user_to_settings():
    """Requesting with nothing resolved would send seerr a body carrying no profile,
    which it accepts and reports as success. Same rule a whole title already applies."""
    view = build_season_view(_show(), _seasons()[0], TileState.ACTIONABLE, None, [],
                             BASE, IMAGE, _labels())
    assert [a.key for a in view.actions] == ["configure"]
    assert "mode=settings" in view.actions[0].url


def test_a_requestable_season_keeps_its_request_when_empty():
    """The request is the whole point of opening an unowned season; an empty episode list
    must not take it away."""
    view = build_season_view(_show(), _seasons()[0], TileState.ACTIONABLE, RESOLVED, [],
                             BASE, IMAGE, _labels())
    assert view.episodes == []
    assert [a.key for a in view.actions] == ["request", "request_with"]


def test_an_owned_season_offers_no_request():
    view = build_season_view(_show(), _seasons()[0], TileState.OWNED, RESOLVED, [],
                             BASE, IMAGE, _labels())
    assert "request" not in [a.key for a in view.actions]


def test_the_season_view_keeps_the_shows_art():
    """The header still describes the show; only the list changed."""
    view = build_season_view(_show(), _seasons()[0], TileState.OWNED, None, [],
                             BASE, IMAGE, _labels())
    assert view.art["fanart"]
    assert view.season_name == "Season 1"


# --- the URLs the one renderer emits ------------------------------------------


def _params(url):
    """A URL's query as a sorted pair list: parse_qsl is what routes.dispatch reads them
    back with anyway, and the dict order urlencode happens to emit is not the contract.
    """
    return sorted(parse_qsl(url.split("?", 1)[1])) if "?" in url else []


def test_every_action_url_carries_what_its_route_reads():
    """Pinned param for param, not merely "starts with mode=": routes.dispatch reads
    tmdb_id and media_type for play and request, only youtube_id for trailer, and nothing
    at all for settings. A param dropped or spelled differently here fails only on the
    device, as an action that runs and does nothing."""
    labels = _labels()
    by_key = {
        action.key: action
        for action in build_view(_show(), TileState.ACTIONABLE, RESOLVED, None, "abc",
                                 [], [], BASE, IMAGE, labels, TODAY).actions
    }
    assert _params(by_key["request"].url) == sorted(
        [("mode", "request"), ("tmdb_id", "82856"), ("media_type", "tv")])
    assert _params(by_key["trailer"].url) == [("mode", "trailer"), ("youtube_id", "abc")]

    owned = build_view(_movie(), TileState.OWNED, None, 42, None, [], [],
                       BASE, IMAGE, labels, TODAY)
    assert _params(owned.actions[0].url) == sorted(
        [("mode", "play"), ("tmdb_id", "693134"), ("media_type", "movie")])

    unconfigured = build_view(_movie(), TileState.ACTIONABLE, None, None, None, [], [],
                              BASE, IMAGE, labels, TODAY)
    assert _params(unconfigured.actions[0].url) == [("mode", "settings")]


def test_a_season_request_is_scoped_and_says_so():
    """The season number is what makes this a season request rather than a duplicate
    whole-show one, and the label is read from SEASON_REQUEST_LABEL_KEY so a season-scoped
    action never renders as the bare "Request" a whole title offers."""
    labels = _labels()
    view = build_season_view(_show(), _seasons()[0], TileState.ACTIONABLE, RESOLVED, [],
                             BASE, IMAGE, labels)
    assert _params(view.actions[0].url) == sorted(
        [("mode", "request"), ("tmdb_id", "82856"), ("media_type", "tv"), ("season", "1")])
    assert view.actions[0].label == labels["request_season"]
    assert view.actions[0].label != labels["request"]


def test_a_season_offers_both_request_actions():
    """The lost "Request with..." for a single season: a resolved, requestable season
    must offer the picker alongside the plain request, exactly as a whole title does."""
    view = build_season_view(_show(), _seasons()[0], TileState.ACTIONABLE, RESOLVED, [],
                             BASE, IMAGE, _labels())
    assert [a.key for a in view.actions] == ["request", "request_with"]
    request, request_with = view.actions
    assert sorted(_params(request.url) + [("pick", "1")]) == _params(request_with.url)


def test_the_whole_title_request_url_comes_from_request_urls():
    """_action_url's "request" branch must defer to ui.spec.request_urls rather than
    build its own copy of the query string -- the drift this fix removes."""
    item = _show()
    view = build_view(item, TileState.ACTIONABLE, RESOLVED, None, "abc", [], [],
                      BASE, IMAGE, _labels(), TODAY)
    request = [a for a in view.actions if a.key == "request"][0]
    assert request.url == request_urls(item, BASE)[0]


def _record(**overrides):
    record = {"episodeid": 11, "episode": 1, "season": 1, "title": "Carrier Wave",
              "plot": "Dust.", "firstaired": "2019-11-12", "playcount": 0,
              "resume": {"position": 120.0, "total": 2400.0},
              "art": {"thumb": "special://library/thumb.jpg"}}
    record.update(overrides)
    return record


def _episode_row(joined, state=TileState.OWNED):
    view = build_season_view(_show(), _seasons()[0], state, None, [joined],
                             BASE, IMAGE, _labels())
    return view.episodes[0]


def test_a_joined_episode_reaches_the_row_as_kodi_describes_it():
    """The seam between join_episodes and the row it becomes: Kodi describes the file
    that will actually play, so its title must survive all the way onto the label and
    into the info dict rather than seerr's TMDb one."""
    record = _record()
    joined = join_episodes([Episode(number=1, season=1, title="TMDb")], [record], 1)
    view = build_season_view(_show(), _seasons()[0], TileState.OWNED, None, joined,
                             BASE, IMAGE, _labels())
    row = view.episodes[0]
    assert row.label == "1. Carrier Wave"
    assert row.info["title"] == "Carrier Wave"
    assert _params(row.url) == [("episode_id", "11"), ("mode", "play")]


def test_an_episode_row_carries_kodis_own_info_and_art():
    row = _episode_row(JoinedEpisode(number=1, title="Carrier Wave", owned=True,
                                     episode_id=11, record=_record()))
    assert row.info == {"title": "Carrier Wave", "plot": "Dust.",
                        "premiered": "2019-11-12", "playcount": 0,
                        "resume": (120.0, 2400.0)}
    assert row.art == {"thumb": "special://library/thumb.jpg"}


def test_a_never_started_episode_carries_no_resume():
    """Position 0 is "never started". Passing it makes Kodi offer to resume every
    unwatched episode from the beginning."""
    record = _record(resume={"position": 0, "total": 2400.0})
    row = _episode_row(JoinedEpisode(number=1, title="Carrier Wave", owned=True,
                                     episode_id=11, record=record))
    assert "resume" not in row.info


def test_an_unowned_row_falls_back_to_what_seerr_knows():
    """Kodi has no record of this episode, so its plot, its air date and its still are
    the only description the row can carry."""
    row = _episode_row(
        JoinedEpisode(number=2, title="Nightfall", owned=False,
                      air_date=datetime.date(2020, 1, 2), overview="Seerr plot.",
                      still_path=STILL_URL),
        state=TileState.PARTIAL,
    )
    assert row.info["plot"] == "Seerr plot."
    assert row.info["premiered"] == "2020-01-02"
    assert row.art == {"thumb": STILL_URL}
    assert row.url == ""


def test_kodis_art_wins_over_seerrs_still():
    row = _episode_row(JoinedEpisode(number=1, title="Carrier Wave", owned=True,
                                     episode_id=11, record=_record(),
                                     still_path=STILL_URL))
    assert row.art == {"thumb": "special://library/thumb.jpg"}


def test_a_view_carries_the_localised_status_line():
    """Not the bare enum name: state.value is untranslated English in the middle of an
    otherwise localised window."""
    labels = _labels()
    view = build_view(_movie(), TileState.UNRELEASED, None, None, None, [], [],
                      BASE, IMAGE, labels, TODAY)
    assert view.status_line == "Available 2024-02-28"

    view = build_view(_movie(), TileState.MONITORED, None, None, None, [], [],
                      BASE, IMAGE, labels, TODAY)
    assert view.status_line == "Monitored"
    assert view.status_line != TileState.MONITORED.value


def test_a_state_with_nothing_to_say_carries_no_status_line():
    view = build_view(_movie(), TileState.OWNED, None, 42, None, [], [],
                      BASE, IMAGE, _labels(), TODAY)
    assert view.status_line == ""


# --- season rows carry no url, and the window drops its seasons button ----------


def test_season_rows_carry_no_url():
    view = build_view(_show(), TileState.ACTIONABLE, RESOLVED, False, None,
                      _seasons(), [], BASE, IMAGE, _labels(), TODAY)
    assert not hasattr(view.seasons[0], "url")


def test_the_window_gets_no_seasons_button():
    """The window renders the season list itself, and mode=seasons no longer exists."""
    view = build_view(_show(), TileState.ACTIONABLE, RESOLVED, False, "abc123",
                      _seasons(), [], BASE, IMAGE, _labels(), TODAY)
    assert [a.key for a in view.actions] == ["request", "trailer"]


def test_an_owned_movie_kodi_lacks_says_so():
    view = build_view(_movie(), TileState.OWNED, None, False, None, [], [],
                      BASE, IMAGE, _labels(), TODAY)
    assert view.actions == []
    assert view.status_line == _labels()["not_in_library"]


def test_an_owned_movie_kodi_has_shows_no_message():
    view = build_view(_movie(), TileState.OWNED, None, True, None, [], [],
                      BASE, IMAGE, _labels(), TODAY)
    assert [a.key for a in view.actions] == ["play"]
    assert view.status_line == ""


def test_an_owned_show_never_says_not_in_library():
    """A tv title browses its seasons regardless, so the movie-only message would lie."""
    view = build_view(_show(), TileState.OWNED, None, False, None,
                      _seasons(), [], BASE, IMAGE, _labels(), TODAY)
    assert view.status_line == ""


def test_an_action_spec_is_a_plain_non_folder_row():
    spec = action_spec(Action("play", "Play", BASE + "?mode=play"))
    assert (spec.label, spec.url, spec.is_folder) == ("Play", BASE + "?mode=play", False)
    assert spec.properties["couchseerr.action"] == "play"
    assert spec.context_items == []


def test_a_season_spec_carries_marker_and_count():
    row = SeasonRow(number=2, label="Season 2", marker="[◐]",
                    state=TileState.PARTIAL, episode_count=8)
    spec = season_spec(row, _labels())
    assert spec.label == "Season 2"
    assert spec.url == ""
    assert spec.is_folder is False
    assert spec.properties["couchseerr.marker"] == "[◐]"
    assert spec.properties["seerr.status"] == "partial"
    assert spec.properties["couchseerr.detail"] == "8 episodes"


def test_a_season_spec_with_no_count_shows_no_detail():
    row = SeasonRow(number=2, label="Season 2", marker="",
                    state=TileState.ACTIONABLE, episode_count=0)
    assert season_spec(row, _labels()).properties["couchseerr.detail"] == ""


def test_an_owned_episode_spec_keeps_its_play_url():
    row = EpisodeRow(number=1, title="Chapter 1", air_date=None, owned=True,
                     label="1. Chapter 1", url=BASE + "?mode=play&episode_id=7",
                     art={"thumb": "t.jpg"}, info={"title": "Chapter 1"})
    spec = episode_spec(row)
    assert spec.url == BASE + "?mode=play&episode_id=7"
    assert spec.properties["couchseerr.inert"] == ""
    assert spec.art == {"thumb": "t.jpg"}


def test_no_spec_the_window_builds_claims_to_be_playable():
    """The third branch of Kodi's OnClick chain (see detail.py): a non-folder plugin item
    whose isplayable property is true is *played*, and the addon is then expected to
    answer with setResolvedUrl. Nothing here does, so claiming it would turn every row
    into a failed-playback dialog. Asserting the absence is the guard, because setting it
    is a one-word change no other test would notice."""
    specs = [
        action_spec(Action("play", "Play", BASE + "?mode=play")),
        season_spec(SeasonRow(number=1, label="Season 1", marker="",
                              state=TileState.OWNED, episode_count=8), _labels()),
        episode_spec(EpisodeRow(number=1, title="Chapter 1", air_date=None, owned=True,
                                label="1. Chapter 1", url=BASE + "?mode=play&episode_id=7",
                                art={}, info={})),
    ]
    for spec in specs:
        assert spec.is_folder is False, spec.label
        assert not any(key.lower() == "isplayable" for key in spec.properties), spec.label


def test_an_unowned_episode_spec_is_marked_inert():
    row = EpisodeRow(number=4, title="Chapter 4", air_date=None, owned=False,
                     label="4. Chapter 4", url="", art={}, info={"title": "Chapter 4"})
    spec = episode_spec(row)
    assert spec.url == ""
    assert spec.properties["couchseerr.inert"] == "1"
