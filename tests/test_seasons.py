"""seasons.py's pure season-level facts: the name of a season, the seerr/Kodi episode
join, and how one episode row reads.

Nothing here builds a listing any more -- detailview.py renders these values for the
detail window, and tests of that rendering live in tests/test_detailview.py.
"""
import datetime

from couchseerr.models import Episode, Season
from couchseerr.seasons import episode_label_and_info, join_episodes, season_label
from couchseerr.state import TileState

TODAY = datetime.date(2026, 8, 6)
LABELS = {"season": "Season {0}"}


def test_a_season_name_comes_from_seerr_when_it_has_one():
    assert season_label(Season(1, "Chapitre un", 8, None, None), LABELS) == "Chapitre un"


def test_a_season_name_falls_back_to_the_label_format():
    """seerr leaves `name` empty for a season TMDb has no name for. "Season 4" is the
    addon's own localised fallback; a blank row label would be the alternative."""
    assert season_label(Season(4, "", 6, None, None), LABELS) == "Season 4"


def test_an_episode_label_leads_with_its_number():
    label, _info = episode_label_and_info(3, "Homecoming", {})
    assert label == "3. Homecoming"


def test_an_episode_label_omits_a_number_kodi_never_supplied():
    """Kodi always supplies "episode" for a scanned record; the fallback is only for a
    malformed one, and "0. Title" would read as a real, wrong episode number rather than
    as the degradation it is."""
    label, _info = episode_label_and_info(None, "Chapter One", {})
    assert label == "Chapter One"


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


def test_an_exact_match_is_owned_and_carries_its_kodi_id():
    seerr = [Episode(number=1, season=1, title="Carrier Wave")]
    kodi = [{"episodeid": 11, "episode": 1, "season": 1, "title": "Carrier Wave"}]
    joined = join_episodes(seerr, kodi, 1)
    assert [(j.number, j.owned, j.episode_id) for j in joined] == [(1, True, 11)]


def test_an_episode_kodi_lacks_is_listed_but_not_owned():
    seerr = [Episode(number=1, season=1, title="A"), Episode(number=2, season=1, title="B")]
    joined = join_episodes(seerr, [{"episodeid": 11, "episode": 1, "season": 1}], 1)
    assert [(j.number, j.owned, j.episode_id) for j in joined] == [(1, True, 11), (2, False, None)]


def test_kodi_title_wins_over_seerr_for_an_owned_episode():
    """Kodi describes the file that will actually play."""
    seerr = [Episode(number=1, season=1, title="TMDb Title")]
    kodi = [{"episodeid": 11, "episode": 1, "season": 1, "title": "Library Title"}]
    assert join_episodes(seerr, kodi, 1)[0].title == "Library Title"


def test_a_wrong_season_record_never_matches():
    """A numbering disagreement must not attach play to the wrong episode."""
    seerr = [Episode(number=1, season=2, title="A")]
    kodi = [{"episodeid": 11, "episode": 1, "season": 1, "title": "Other season"}]
    joined = join_episodes(seerr, kodi, 2)
    assert joined[0].owned is False and joined[0].episode_id is None


def test_a_kodi_episode_seerr_lacks_is_appended_not_dropped():
    """Degrade to "more rows than expected", never to a missing playable episode."""
    seerr = [Episode(number=1, season=1, title="A")]
    kodi = [{"episodeid": 11, "episode": 1, "season": 1},
            {"episodeid": 12, "episode": 2, "season": 1, "title": "Extra"}]
    joined = join_episodes(seerr, kodi, 1)
    assert [(j.number, j.owned) for j in joined] == [(1, True), (2, True)]


def test_no_kodi_records_yields_every_episode_unowned():
    seerr = [Episode(number=1, season=1, title="A"), Episode(number=2, season=1, title="B")]
    assert all(not j.owned for j in join_episodes(seerr, [], 1))


def test_no_seerr_episodes_still_lists_what_kodi_holds():
    kodi = [{"episodeid": 11, "episode": 1, "season": 1, "title": "Only local"}]
    joined = join_episodes([], kodi, 1)
    assert [(j.number, j.owned, j.title) for j in joined] == [(1, True, "Only local")]


def test_duplicate_kodi_records_collapse_to_one_row():
    """Two library records for one episode -- a second rip of it -- deliberately leave
    one row, the last seen. The row leads to one playable file, and choosing between
    versions of it is Kodi's own job, not this join's. Documented rather than fixed."""
    seerr = [Episode(number=1, season=1, title="A")]
    kodi = [{"episodeid": 11, "episode": 1, "season": 1},
            {"episodeid": 12, "episode": 1, "season": 1}]
    joined = join_episodes(seerr, kodi, 1)
    assert [(j.number, j.episode_id) for j in joined] == [(1, 12)]


def test_the_join_carries_seerrs_overview_and_still():
    """An unowned episode has no Kodi record to describe it, so seerr's own plot and
    still are the only description its row can ever carry."""
    still = "https://image.tmdb.org/t/p/original" + "/still.jpg"
    seerr = [Episode(number=1, season=1, title="A", overview="Sand.", still_path=still)]
    joined = join_episodes(seerr, [], 1)
    assert joined[0].overview == "Sand."
    assert joined[0].still_path == still
