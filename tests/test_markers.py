import datetime

import pytest

from couchseerr.markers import marker_for
from couchseerr.models import DiscoverItem, DownloadProgress
from couchseerr.state import TileState


def _item(release_date=None):
    return DiscoverItem(tmdb_id=1, media_type="movie", title="Item", release_date=release_date)


def _download(time_left=None):
    return DownloadProgress(
        size=1000,
        size_left=380,
        time_left=time_left,
        estimated_completion_time=None,
        status="downloading",
    )


def test_downloading_marker_is_percent_only_sans_time_left():
    marker = marker_for(TileState.DOWNLOADING, _item(), _download(time_left=None))
    assert marker == "[62%]"


def test_downloading_marker_includes_eta_with_time_left():
    marker = marker_for(TileState.DOWNLOADING, _item(), _download(time_left="00:14:32"))
    assert marker == "[62% · 00:14:32]"


def test_downloading_marker_omits_eta_for_empty_time_left():
    marker = marker_for(TileState.DOWNLOADING, _item(), _download(time_left=""))
    assert marker == "[62%]"


def test_downloading_state_without_a_download_raises():
    with pytest.raises(ValueError):
        marker_for(TileState.DOWNLOADING, _item(), None)


def test_unreleased_state_without_a_release_date_raises():
    with pytest.raises(ValueError):
        marker_for(TileState.UNRELEASED, _item(release_date=None), None)


def test_unreleased_marker_renders_the_date():
    item = _item(release_date=datetime.date(2027, 12, 25))
    assert marker_for(TileState.UNRELEASED, item, None) == "[2027-12-25]"


def test_owned_marker_ignores_the_download_argument():
    assert marker_for(TileState.OWNED, _item(), None) == "[✓]"


def test_actionable_marker_is_empty():
    assert marker_for(TileState.ACTIONABLE, _item(), None) == ""
