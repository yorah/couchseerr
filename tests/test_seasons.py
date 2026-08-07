import datetime

from couchseerr.models import DiscoverItem, Season
from couchseerr.seasons import build_season_detail, build_season_list
from couchseerr.state import TileState

BASE = "plugin://plugin.video.couchseerr/"
IMAGE = "https://image.tmdb.org/t/p/w780"
TODAY = datetime.date(2026, 8, 6)
LABELS = {
    "season": "Season {0}",
    "request": "Request",
    "request_with": "Request with...",
    "request_season": "Request this season",
    "configure": "Configure the default profile",
    "not_in_library": "Not in your Kodi library",
}


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
        Season(3, "Season 3", 8, datetime.date(2027, 1, 14), None),
    ]


def _tracked():
    return [
        {"seasonNumber": 1, "status": 5, "status4k": 1},
        {"seasonNumber": 2, "status": 4, "status4k": 1},
        {"seasonNumber": 3, "status": 3, "status4k": 1},
    ]


def _list(media=None):
    return build_season_list(_show(), _seasons(), media if media is not None else _tracked(),
                             BASE, IMAGE, LABELS, TODAY)


def test_every_season_is_a_folder_that_acts_on_nothing():
    """The v2 rule one level down: a click opens the actions, it never takes one. This is
    what lets a partial season be both browsable and re-requestable without the click
    meaning two things."""
    specs = _list()
    assert [s.is_folder for s in specs] == [True, True, True]
    assert "mode=season" in specs[0].url and "season=1" in specs[0].url
    assert "tmdb_id=82856" in specs[0].url


def test_markers_come_from_the_shared_table():
    specs = _list()
    assert specs[0].label == "[✓] Season 1"
    assert specs[1].label == "[◐] Season 2"
    assert specs[2].label == "[2027-01-14] Season 3"


def test_an_untracked_show_renders_every_season_unmarked():
    specs = _list(media=[])
    assert [s.label for s in specs] == ["Season 1", "Season 2", "Season 3"]
    assert [s.properties["seerr.status"] for s in specs] == ["actionable"] * 3


def test_the_season_name_falls_back_to_the_label_format():
    seasons = [Season(4, "", 6, None, None)]
    specs = build_season_list(_show(), seasons, [], BASE, IMAGE, LABELS, TODAY)
    assert specs[0].label == "Season 4"


def test_context_items_only_where_a_request_is_possible():
    """Owned: neither entry, exactly as an owned tile carries neither. Partial and
    actionable: both, scoped to that season."""
    specs = _list()
    assert specs[0].context_items == []
    assert [label for label, _ in specs[1].context_items] == ["Request", "Request with..."]
    assert "season=2" in specs[1].context_items[0][1]
    assert specs[2].context_items == []


def test_season_art_prefers_its_own_poster():
    specs = _list()
    assert specs[0].art["poster"] == IMAGE + "/s1.jpg"
    assert specs[1].art["poster"] == IMAGE + "/p.jpg"
    assert specs[0].art["fanart"] == IMAGE + "/b.jpg"


def test_the_show_info_travels_with_every_entry():
    """The skin's info pane renders whatever is focused; an entry describing itself would
    blank the show the moment the user moved onto it."""
    specs = _list()
    assert specs[0].info["title"] == "The Show"


def test_the_season_number_is_published_for_skins():
    specs = _list()
    assert specs[2].properties["seerr.season"] == "3"


RESOLVED = {"serverId": 0, "profileId": 21, "is4k": False}

RECORDS = [
    {"episodeid": 11, "episode": 1, "title": "Chapter One", "plot": "Begins.",
     "firstaired": "2019-11-12", "playcount": 1, "resume": {"position": 0, "total": 0},
     "art": {"thumb": "image://ep1/"}},
    {"episodeid": 12, "episode": 2, "title": "Chapter Two", "plot": "Continues.",
     "firstaired": "2019-11-15", "playcount": 0,
     "resume": {"position": 420.0, "total": 2400.0}, "art": {}},
]


def _detail(state=TileState.ACTIONABLE, resolved=RESOLVED, records=None):
    return build_season_detail(
        _show(), _seasons()[0], state, resolved, records if records is not None else RECORDS,
        BASE, IMAGE, LABELS,
    )


def test_a_requestable_season_offers_the_request_first():
    specs = _detail()
    assert specs[0].label == "Request this season"
    assert "mode=request" in specs[0].url and "season=1" in specs[0].url
    assert specs[0].is_folder is False


def test_a_partial_season_may_be_re_requested():
    assert _detail(state=TileState.PARTIAL)[0].label == "Request this season"


def test_an_owned_season_offers_no_request():
    labels = [s.label for s in _detail(state=TileState.OWNED)]
    assert labels == ["1. Chapter One", "2. Chapter Two"]


def test_no_default_profile_sends_the_user_to_settings():
    """Offering a request with nothing resolved would send seerr a body with no profile,
    which it accepts and reports as success. Same rule detail.py already applies."""
    specs = _detail(resolved=None)
    assert specs[0].label == "Configure the default profile"
    assert "mode=settings" in specs[0].url


def test_episodes_are_playable_entries():
    specs = _detail(state=TileState.OWNED)
    assert "mode=play" in specs[0].url and "episode_id=11" in specs[0].url
    assert specs[0].is_folder is False
    assert specs[0].properties.get("IsPlayable", "") == ""


def test_episode_info_travels_with_the_entry():
    """Unlike the season list, an episode entry describes itself: it is the thing being
    played, so its own plot and thumb are what the info pane should show."""
    spec = _detail(state=TileState.OWNED)[0]
    assert spec.info["title"] == "Chapter One"
    assert spec.info["plot"] == "Begins."
    assert spec.info["premiered"] == "2019-11-12"
    assert spec.info["playcount"] == 1
    assert spec.art["thumb"] == "image://ep1/"


def test_a_resume_point_is_passed_through_only_when_real():
    watched, part_watched = _detail(state=TileState.OWNED)
    assert "resume" not in watched.info
    assert part_watched.info["resume"] == (420.0, 2400.0)


def test_episode_label_omits_the_number_when_kodi_has_none():
    """Kodi always supplies "episode" for a scanned record; the fallback is only for a
    malformed one, and "0. Title" would read as a real, wrong episode number rather than
    as the degradation it is."""
    records = [dict(RECORDS[0])]
    del records[0]["episode"]
    specs = _detail(state=TileState.OWNED, records=records)
    assert specs[0].label == "Chapter One"


def test_no_episodes_says_so_instead_of_an_empty_listing():
    """Two causes, one line: no Kodi library id for the show, or a season Kodi never
    scanned. An empty listing on a TV looks like a broken addon."""
    specs = _detail(state=TileState.OWNED, records=[])
    assert [s.label for s in specs] == ["Not in your Kodi library"]
    assert specs[0].url == ""


def test_a_requestable_season_keeps_its_request_without_kodi():
    """The request is the whole point of this listing for an unowned season; an absent
    library must not take it away."""
    specs = _detail(records=[])
    assert [s.label for s in specs] == ["Request this season", "Not in your Kodi library"]


def test_the_request_entry_carries_the_same_two_context_items():
    spec = _detail()[0]
    assert [label for label, _ in spec.context_items] == ["Request", "Request with..."]
    assert "season=1" in spec.context_items[1][1] and "pick=1" in spec.context_items[1][1]


def test_the_fixture_show_covers_every_season_state():
    """One payload, every row of the state table. If a future change to the generator
    drops a state, this goes red rather than silently narrowing the suite."""
    import json
    import pathlib

    from couchseerr.models import media_seasons, parse_seasons
    from couchseerr.state import season_state

    path = (pathlib.Path(__file__).parent / "fixtures" / "seerr" / "tv_seasons.json")
    payload = json.loads(path.read_text())
    seasons = parse_seasons(payload)
    tracked = media_seasons(payload)

    states = {s.number: season_state(s, tracked, TODAY) for s in seasons}
    assert set(states.values()) == {
        TileState.OWNED, TileState.PARTIAL, TileState.MONITORED,
        TileState.UNRELEASED, TileState.PENDING, TileState.ACTIONABLE,
    }
    assert 0 not in states, "Specials must not survive parsing"
