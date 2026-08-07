import datetime
from datetime import date

from couchseerr.models import (
    media_seasons,
    parse_discover_item,
    parse_discover_page,
    parse_media_state,
    parse_season_episodes,
    parse_seasons,
)


def test_parses_movie_item(fixture):
    raw = fixture("discover_trending")["results"][0]
    item = parse_discover_item(raw)
    assert item.tmdb_id == 101
    assert item.media_type == "movie"
    assert item.title == "Fixture One"
    assert item.release_date == datetime.date(2025, 6, 1)
    assert item.poster_path == "/fixturePoster.jpg"
    assert item.backdrop_path == "/fixtureBackdrop.jpg"


def test_parses_tv_item_using_name_and_first_air_date(fixture):
    raw = fixture("discover_trending")["results"][7]
    item = parse_discover_item(raw)
    assert item.media_type == "tv"
    assert item.title == "Fixture Series A"
    assert item.release_date == datetime.date(2024, 1, 1)


def test_item_without_media_info_has_no_media(fixture):
    raw = fixture("discover_trending")["results"][6]
    assert parse_discover_item(raw).media is None


def test_effective_status_takes_the_maximum_of_both_tracks(fixture):
    """A title can be absent on the standard track but in-flight on 4K. Reading only
    `status` misreports it as absent - the defect this guards."""
    raw = fixture("discover_trending")["results"][1]["mediaInfo"]
    state = parse_media_state(raw)
    assert state.status == 1
    assert state.status4k == 3
    assert state.effective_status == 3


def test_download_progress_percent(fixture):
    raw = fixture("discover_trending")["results"][2]["mediaInfo"]
    state = parse_media_state(raw)
    download = state.best_download
    assert download is not None
    assert download.size == 8_000_000_000
    assert download.size_left == 3_040_000_000
    assert round(download.percent, 1) == 62.0
    assert download.time_left == "00:14:32"


def test_empty_download_status_is_not_an_error(fixture):
    """The arrays are empty whenever the *arr queue is empty, which is the normal case."""
    raw = fixture("discover_trending")["results"][3]["mediaInfo"]
    state = parse_media_state(raw)
    assert state.downloads == ()
    assert state.best_download is None


def test_percent_is_zero_when_size_is_zero():
    state = parse_media_state(
        {
            "status": 3,
            "status4k": 1,
            "downloadStatus": [{"size": 0, "sizeLeft": 0, "status": "queued"}],
            "downloadStatus4k": [],
        }
    )
    assert state.best_download.percent == 0.0


def test_missing_size_left_is_unknown_not_complete():
    """seerr omitting sizeLeft must not render as 100% -- unknown progress is not the
    same claim as zero bytes remaining."""
    state = parse_media_state(
        {
            "status": 3,
            "status4k": 1,
            "downloadStatus": [{"size": 100, "status": "queued"}],
            "downloadStatus4k": [],
        }
    )
    assert state.best_download.size_left is None
    assert state.best_download.percent == 0.0


def test_null_size_left_is_unknown_not_complete():
    state = parse_media_state(
        {
            "status": 3,
            "status4k": 1,
            "downloadStatus": [{"size": 100, "sizeLeft": None, "status": "queued"}],
            "downloadStatus4k": [],
        }
    )
    assert state.best_download.size_left is None
    assert state.best_download.percent == 0.0


def test_download_with_no_size_and_no_size_left_is_unreadable():
    """size==0 and size_left is None means the record could not be interpreted at
    all, not that the download is genuinely at 0%."""
    state = parse_media_state(
        {
            "status": 3,
            "status4k": 1,
            "downloadStatus": [{"status": "downloading"}],
            "downloadStatus4k": [],
        }
    )
    assert state.best_download.is_unreadable is True


def test_download_with_size_but_no_size_left_is_unreadable():
    """size is present but sizeLeft is missing, so `percent` has already given up
    (see test_missing_size_left_is_unknown_not_complete) -- `is_unreadable` must
    agree, or this is exactly the "wrong field name" case the fallback exists for."""
    state = parse_media_state(
        {
            "status": 3,
            "status4k": 1,
            "downloadStatus": [{"size": 100, "status": "queued"}],
            "downloadStatus4k": [],
        }
    )
    assert state.best_download.is_unreadable is True


def test_download_with_size_left_but_no_size_is_unreadable():
    """size missing (falsy) means `percent` gives up regardless of sizeLeft, so
    `is_unreadable` must too."""
    state = parse_media_state(
        {
            "status": 3,
            "status4k": 1,
            "downloadStatus": [{"sizeLeft": 40, "status": "queued"}],
            "downloadStatus4k": [],
        }
    )
    assert state.best_download.is_unreadable is True


def test_download_size_zero_is_unreadable():
    """size == 0 is falsy, so `percent` gives up on it just like a missing size --
    `is_unreadable` must match, even when sizeLeft is explicit real data."""
    state = parse_media_state(
        {
            "status": 3,
            "status4k": 1,
            "downloadStatus": [{"size": 0, "sizeLeft": 0, "status": "queued"}],
            "downloadStatus4k": [],
        }
    )
    assert state.best_download.is_unreadable is True


def test_healthy_download_is_not_unreadable():
    """size and sizeLeft both present is the ordinary case: `percent` returns a real
    number and `is_unreadable` must not flag it."""
    state = parse_media_state(
        {
            "status": 3,
            "status4k": 1,
            "downloadStatus": [{"size": 100, "sizeLeft": 40, "status": "downloading"}],
            "downloadStatus4k": [],
        }
    )
    download = state.best_download
    assert download.is_unreadable is False
    assert download.percent == 60.0


def test_best_download_picks_the_most_advanced():
    state = parse_media_state(
        {
            "status": 3,
            "status4k": 1,
            "downloadStatus": [
                {"size": 100, "sizeLeft": 90, "status": "downloading"},
                {"size": 100, "sizeLeft": 10, "status": "downloading"},
            ],
            "downloadStatus4k": [],
        }
    )
    assert state.best_download.size_left == 10


def test_downloads_merge_both_tracks():
    """Whole-value assertions on purpose: a count alone passes just as happily when a
    field is read from the wrong key, dropped, or when both tracks collapse onto one
    record. Standard track first, then 4K."""
    state = parse_media_state(
        {
            "status": 3,
            "status4k": 3,
            "downloadStatus": [{"size": 100, "sizeLeft": 25, "status": "downloading"}],
            "downloadStatus4k": [{"size": 800, "sizeLeft": 400, "status": "queued"}],
        }
    )
    assert [(d.size, d.size_left, d.status) for d in state.downloads] == [
        (100, 25, "downloading"),
        (800, 400, "queued"),
    ]
    assert [d.percent for d in state.downloads] == [75.0, 50.0]
    # best_download picks across both tracks, not just the first one present.
    assert state.best_download.size == 100


def test_release_date_reads_a_full_iso_timestamp():
    """seerr returns a plain date on discover rows but a full timestamp on some detail
    payloads, and _hydrate feeds both through the same parser."""
    item = parse_discover_item(
        {
            "id": 1,
            "mediaType": "movie",
            "title": "Timestamped",
            "releaseDate": "2026-08-04T00:00:00.000Z",
        }
    )
    assert item.release_date == datetime.date(2026, 8, 4)


def test_release_date_that_is_not_a_string_is_none():
    """A non-string date makes value[:10] or strptime raise TypeError, not ValueError.
    Uncaught, that kills the whole row from inside a pure parser -- the one place with
    no error handling around it."""
    for bad in (2026, 20260804.0, ["2026-08-04"], {"date": "2026-08-04"}):
        item = parse_discover_item(
            {"id": 1, "mediaType": "movie", "title": "Bad Date", "releaseDate": bad}
        )
        assert item.release_date is None, bad


def test_release_date_that_is_malformed_is_none():
    for bad in ("not-a-date", "2026-13-45", "04/08/2026", "2026-08"):
        item = parse_discover_item(
            {"id": 1, "mediaType": "movie", "title": "Bad Date", "releaseDate": bad}
        )
        assert item.release_date is None, bad


def test_missing_release_date_is_none():
    item = parse_discover_item(
        {"id": 1, "mediaType": "movie", "title": "No Date", "releaseDate": ""}
    )
    assert item.release_date is None


def test_parse_page_returns_every_result(fixture):
    items = parse_discover_page(fixture("discover_trending"))
    assert len(items) == 10
    assert {i.media_type for i in items} == {"movie", "tv"}


def test_parse_seasons_drops_specials_and_empty_seasons():
    """Season 0 is Specials and is noise on a TV; a season with no episodes is TMDb's
    placeholder for an announced-but-unmade season, and requesting it downloads nothing
    while looking like it worked. Both are dropped at parse time so no consumer has to
    remember the rule. Shape confirmed live 2026-08-06 against /tv/1396."""
    payload = {"seasons": [
        {"seasonNumber": 0, "name": "Specials", "episodeCount": 9,
         "airDate": "2009-02-17", "posterPath": "/sp.jpg"},
        {"seasonNumber": 1, "name": "Season 1", "episodeCount": 7,
         "airDate": "2008-01-20", "posterPath": "/s1.jpg"},
        {"seasonNumber": 2, "name": "Season 2", "episodeCount": 0,
         "airDate": None, "posterPath": None},
    ]}
    seasons = parse_seasons(payload)

    assert [s.number for s in seasons] == [1]
    assert seasons[0].name == "Season 1"
    assert seasons[0].episode_count == 7
    assert seasons[0].release_date == datetime.date(2008, 1, 20)
    assert seasons[0].poster_path == "/s1.jpg"


def test_parse_seasons_sorts_and_survives_junk():
    """seerr returns them in order today; sorting makes the listing deterministic anyway.
    A season with no usable number cannot be requested or rendered, so it is dropped
    rather than rendered as a row that cannot act."""
    payload = {"seasons": [
        {"seasonNumber": 3, "name": "Season 3", "episodeCount": 10},
        {"seasonNumber": None, "name": "Broken", "episodeCount": 4},
        {"seasonNumber": 1, "name": "Season 1", "episodeCount": 10},
    ]}
    assert [s.number for s in parse_seasons(payload)] == [1, 3]


def test_parse_seasons_of_a_payload_without_seasons():
    """A movie payload, or a show seerr returned without season data. The caller must
    still render a listing, so this is an empty list, never a failure."""
    assert parse_seasons({}) == []
    assert parse_seasons({"seasons": None}) == []


def test_parse_seasons_keeps_an_unparseable_airdate_as_none():
    """A season with no usable airDate is still requestable; only its UNRELEASED marker
    is unavailable, and state.season_state falls back to MONITORED for it (Task 2)."""
    payload = {"seasons": [{"seasonNumber": 1, "name": "S1", "episodeCount": 3,
                            "airDate": "not-a-date"}]}
    assert parse_seasons(payload)[0].release_date is None


def test_media_seasons_of_an_untracked_show():
    """mediaInfo is null for a show seerr does not track -- confirmed live 2026-08-06
    against /tv/1396. Every season then derives ACTIONABLE (Task 2), which is what makes
    an untracked show requestable at all."""
    assert media_seasons({"mediaInfo": None}) == []
    assert media_seasons({}) == []
    assert media_seasons({"mediaInfo": {"seasons": None}}) == []


def test_media_seasons_passes_through_the_raw_entries():
    """Shape confirmed live 2026-08-06 against /tv/82856: four seasons on TMDb, three
    entries here, status4k 1 (unknown) throughout."""
    raw = [{"id": 35, "seasonNumber": 1, "status": 3, "status4k": 1},
           {"id": 50, "seasonNumber": 2, "status": 5, "status4k": 1}]
    assert media_seasons({"mediaInfo": {"seasons": raw}}) == raw


def test_season_episodes_parse_in_ascending_order(fixture):
    episodes = parse_season_episodes(fixture("tv_season_partial"))
    assert [e.number for e in episodes] == [1, 2, 3, 4]
    assert episodes[0].title == "Groundwave"
    assert episodes[0].season == 2


def test_season_episode_air_date_becomes_a_date(fixture):
    episodes = parse_season_episodes(fixture("tv_season_1"))
    assert episodes[0].air_date == date(2019, 11, 12)


def test_a_payload_with_no_episodes_parses_to_empty():
    # The error body seerr returns for an unreachable season, should a caller ever
    # hand it here instead of letting the client raise.
    assert parse_season_episodes({"message": "Unable to retrieve season."}) == []


def test_still_path_is_kept_verbatim_as_an_absolute_url(fixture):
    """Measured: seerr returns stillPath absolute, unlike posterPath. Prefixing it with
    image_base would produce a broken URL, so it is stored exactly as received."""
    episodes = parse_season_episodes(fixture("tv_season_1"))
    assert episodes[0].still_path.startswith("https://image.tmdb.org/")


def test_an_unaired_episode_has_no_still(fixture):
    episodes = parse_season_episodes(fixture("tv_season_partial"))
    assert episodes[2].still_path is None


def test_an_episode_without_a_number_is_dropped():
    # An entry with no episodeNumber cannot be joined against Kodi and cannot be
    # ordered, so it would render as an unplaceable row.
    raw = {"episodes": [{"name": "Nameless"}, {"episodeNumber": 1, "name": "Real"}]}
    assert [e.title for e in parse_season_episodes(raw)] == ["Real"]


def test_an_unparseable_air_date_is_none_not_a_raise():
    raw = {"episodes": [{"episodeNumber": 1, "name": "X", "airDate": "soon"}]}
    assert parse_season_episodes(raw)[0].air_date is None
