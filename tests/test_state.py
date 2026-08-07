import datetime

import pytest

from couchseerr.models import parse_discover_page
from couchseerr.state import (
    REQUESTABLE_STATES,
    SEASON_REQUESTABLE_STATES,
    TileState,
    season_state,
    tile_state,
)

TODAY = datetime.date(2026, 1, 6)


@pytest.fixture
def items(fixture):
    return {i.tmdb_id: i for i in parse_discover_page(fixture("discover_trending"))}


def test_available_is_owned(items):
    assert tile_state(items[101], TODAY) is TileState.OWNED


def test_partially_available_is_partial(items):
    assert tile_state(items[201], TODAY) is TileState.PARTIAL


def test_processing_with_active_download_is_downloading(items):
    assert tile_state(items[103], TODAY) is TileState.DOWNLOADING


def test_processing_released_without_download_is_monitored(items):
    """Status 3 with an empty queue means 'monitored, nothing grabbed' - not 'arriving'."""
    assert tile_state(items[104], TODAY) is TileState.MONITORED


def test_processing_unreleased_is_unreleased(items):
    assert tile_state(items[105], TODAY) is TileState.UNRELEASED


def test_pending_approval_is_pending(items):
    assert tile_state(items[106], TODAY) is TileState.PENDING


def test_no_media_info_is_actionable(items):
    assert tile_state(items[107], TODAY) is TileState.ACTIONABLE


def test_status_one_with_4k_processing_is_not_actionable(items):
    """tmdb 102 is status 1 / status4k 3. Reading only `status` would wrongly offer a
    request for something already in flight."""
    assert tile_state(items[102], TODAY) is not TileState.ACTIONABLE
    assert tile_state(items[102], TODAY) is TileState.MONITORED


def test_release_date_exactly_today_counts_as_released(items):
    item = items[105]
    assert tile_state(item, datetime.date(2027, 12, 25)) is TileState.MONITORED


def test_missing_release_date_falls_back_to_monitored(items):
    item = items[104]
    item.release_date = None
    assert tile_state(item, TODAY) is TileState.MONITORED


def test_downloading_wins_even_when_unreleased(items):
    """A pre-release grab is still a download; progress is the more useful signal."""
    item = items[103]
    item.release_date = datetime.date(2099, 1, 1)
    assert tile_state(item, TODAY) is TileState.DOWNLOADING


def test_every_state_is_reachable_from_the_fixture(items):
    observed = {tile_state(i, TODAY) for i in items.values()}
    assert observed == set(TileState)


def test_unreadable_download_falls_back_to_monitored():
    """A download record with no usable byte counts must not present as an active
    download -- that would be a permanent, indistinguishable-from-real "[0%]"."""
    from couchseerr.models import DiscoverItem, DownloadProgress, MediaState

    unreadable = DownloadProgress(
        size=0, size_left=None, time_left=None, estimated_completion_time=None, status=""
    )
    media = MediaState(status=3, status4k=1, downloads=(unreadable,))
    item = DiscoverItem(tmdb_id=1, media_type="movie", title="Edge", media=media)
    assert tile_state(item, TODAY) is TileState.MONITORED


def _item_with_download(size, size_left):
    from couchseerr.models import DiscoverItem, DownloadProgress, MediaState

    download = DownloadProgress(
        size=size, size_left=size_left, time_left=None,
        estimated_completion_time=None, status="downloading",
    )
    media = MediaState(status=3, status4k=1, downloads=(download,))
    return DiscoverItem(tmdb_id=1, media_type="movie", title="Edge", media=media)


def test_size_present_size_left_none_falls_back_to_monitored():
    """The exact shape one wrong seerr field name would produce: must not render a
    permanent, false "[0%]"."""
    item = _item_with_download(size=100, size_left=None)
    assert item.media.best_download.is_unreadable is True
    assert tile_state(item, TODAY) is TileState.MONITORED


def test_size_none_size_left_present_falls_back_to_monitored():
    item = _item_with_download(size=None, size_left=40)
    assert item.media.best_download.is_unreadable is True
    assert tile_state(item, TODAY) is TileState.MONITORED


def test_size_and_size_left_both_none_falls_back_to_monitored():
    item = _item_with_download(size=None, size_left=None)
    assert item.media.best_download.is_unreadable is True
    assert tile_state(item, TODAY) is TileState.MONITORED


def test_size_zero_falls_back_to_monitored():
    item = _item_with_download(size=0, size_left=0)
    assert item.media.best_download.is_unreadable is True
    assert tile_state(item, TODAY) is TileState.MONITORED


def test_healthy_download_is_still_downloading_not_monitored():
    """Sanity check: the fallback must not swallow a genuinely readable download."""
    item = _item_with_download(size=100, size_left=40)
    assert item.media.best_download.is_unreadable is False
    assert tile_state(item, TODAY) is TileState.DOWNLOADING


def _season(number=1, air_date=None):
    from couchseerr.models import Season
    return Season(number=number, name="Season {0}".format(number), episode_count=8,
                  release_date=air_date, poster_path=None)


def _tracked(number, status, status4k=1):
    return [{"id": 1, "seasonNumber": number, "status": status, "status4k": status4k}]


def test_season_absent_from_mediainfo_is_actionable():
    """The ordinary case, not a degradation path: /tv/82856 has four seasons on TMDb and
    three entries here, so a season nobody requested is simply absent."""
    assert season_state(_season(4), _tracked(1, 5), TODAY) is TileState.ACTIONABLE


def test_season_states_follow_the_status_ladder():
    assert season_state(_season(), _tracked(1, 5), TODAY) is TileState.OWNED
    assert season_state(_season(), _tracked(1, 4), TODAY) is TileState.PARTIAL
    assert season_state(_season(), _tracked(1, 2), TODAY) is TileState.PENDING
    assert season_state(_season(), _tracked(1, 3), TODAY) is TileState.MONITORED


def test_unknown_status_reads_as_actionable():
    """Status 1 is seerr's "unknown". A season nothing is known about is one the user can
    still ask for; refusing would strand it with no action at all."""
    assert season_state(_season(), _tracked(1, 1), TODAY) is TileState.ACTIONABLE


def test_a_4k_track_never_drags_a_season_down():
    """Measured on the instance 2026-08-06: status4k is 1 on every season of a tracked
    show. max() is what keeps that from outranking a real status, exactly as
    MediaState.effective_status already does at title level."""
    assert season_state(_season(), _tracked(1, 5, status4k=1), TODAY) is TileState.OWNED
    assert season_state(_season(), _tracked(1, 1, status4k=5), TODAY) is TileState.OWNED


def test_processing_season_airing_later_is_unreleased():
    later = datetime.date(2027, 1, 14)
    assert season_state(_season(air_date=later), _tracked(1, 3), TODAY) is TileState.UNRELEASED


def test_processing_season_with_no_airdate_is_monitored():
    """UNRELEASED demands a date -- markers.marker_for raises without one -- so a season
    whose airDate did not parse must not derive it."""
    assert season_state(_season(air_date=None), _tracked(1, 3), TODAY) is TileState.MONITORED


def test_season_airing_exactly_today_counts_as_released():
    """The title-level equivalent already exists (test_release_date_exactly_today_
    counts_as_released); this is the same boundary one level down, the one place the
    season rule could silently diverge from it. A `>` vs `>=` mutation in season_state
    must fail this."""
    assert season_state(_season(air_date=TODAY), _tracked(1, 3), TODAY) is TileState.MONITORED


def test_a_downloading_title_does_not_make_a_season_downloading():
    """downloadStatus is title-level and its populated shape has never been observed. A
    percentage attributed to the wrong season is worse than none, so DOWNLOADING is never
    derived per season."""
    assert season_state(_season(), _tracked(1, 3), TODAY) is not TileState.DOWNLOADING


def test_season_requestable_states():
    """PARTIAL means something different per season than per title: a partial season has
    missing episodes a fresh request tells Sonarr to search for. Both tuples live here so
    a tile, a title's detail view and a season's cannot drift apart."""
    assert REQUESTABLE_STATES == (TileState.ACTIONABLE,)
    assert SEASON_REQUESTABLE_STATES == (TileState.ACTIONABLE, TileState.PARTIAL)
