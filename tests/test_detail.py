"""detail.py's two pure rules: what a title offers, and what its state says.

Both are read by the detail window (detailview.py), which is the addon's only renderer of
a title. The rules live here rather than in the window so a second renderer could reuse
them instead of re-deriving them; the tests below therefore call them directly, with no
window and no Kodi anywhere in sight.
"""
from couchseerr.detail import available_actions, can_play_from_library
from couchseerr.state import TileState

RESOLVED = {"serverId": 0, "profileId": 21, "is4k": False}


# --- available_actions: the one rule a second renderer must reuse, not redecide -----


def test_an_owned_movie_in_the_library_offers_play():
    assert available_actions(TileState.OWNED, "movie", None, 42, None) == ["play"]


def test_an_owned_movie_not_in_the_library_offers_nothing():
    assert available_actions(TileState.OWNED, "movie", None, None, None) == []


def test_an_actionable_movie_with_a_default_offers_request():
    assert available_actions(TileState.ACTIONABLE, "movie", RESOLVED, None, None) == ["request"]


def test_an_actionable_movie_without_a_default_offers_configure():
    assert available_actions(TileState.ACTIONABLE, "movie", None, None, None) == ["configure"]


def test_a_show_offers_seasons_whatever_its_state():
    for state in TileState:
        assert "seasons" in available_actions(state, "tv", None, None, None), state


def test_a_trailer_is_offered_in_every_state():
    for state in TileState:
        assert "trailer" in available_actions(state, "movie", None, None, "abc123"), state


def test_the_action_order_is_the_display_order():
    """The list is display order: it decides which button the user reaches first in the
    window. Nothing else pins it, so a silent reordering here would change what the user
    sees with every test still green."""
    assert available_actions(TileState.ACTIONABLE, "tv", RESOLVED, None, "abc") == [
        "request", "seasons", "trailer"]
    assert available_actions(TileState.ACTIONABLE, "tv", None, None, "abc") == [
        "configure", "seasons", "trailer"]
    assert available_actions(TileState.OWNED, "movie", None, 42, "abc") == [
        "play", "trailer"]
    assert available_actions(TileState.OWNED, "tv", None, 42, None) == ["seasons"]


def test_a_show_never_offers_play():
    """Kodi's Playlist.Item has no tvshowid; an episode is the smallest playable thing."""
    for state in TileState:
        assert "play" not in available_actions(state, "tv", None, 42, None), state


# --- status_line: the line the detail window shows for a title in flight -----


#: The status-line labels, spelled out rather than read back through routes._labels():
#: detail.py is pure core, and a test of it has no business loading the Kodi adapter to
#: find out what a label says. Values match resources/language/.../strings.po.
STATUS_LABELS = {
    "downloading": "Downloading {0}%",
    "monitored": "Monitored",
    "unreleased": "Releasing {0}",
    "pending": "Awaiting approval",
    "partial": "Partially available",
}


def _labels():
    return dict(STATUS_LABELS)


def _downloading_item(percent_size, size_left, time_left=None):
    from couchseerr.models import DiscoverItem, DownloadProgress, MediaState

    download = DownloadProgress(size=percent_size, size_left=size_left,
                                time_left=time_left, estimated_completion_time=None,
                                status="downloading")
    return DiscoverItem(
        tmdb_id=1, media_type="movie", title="Dune",
        media=MediaState(status=3, status4k=1, downloads=[download]),
    )


def test_status_line_localises_the_download_percentage():
    from couchseerr import detail
    from couchseerr.state import TileState

    line = detail.status_line(
        TileState.DOWNLOADING, _downloading_item(1000, 380), _labels()
    )
    assert line == "Downloading 62%"


def test_status_line_truncates_the_percentage():
    """marker_for truncates so 99.6% never reads as the false claim "100". The window
    must not disagree with the tile it was opened from."""
    from couchseerr import detail
    from couchseerr.state import TileState

    line = detail.status_line(
        TileState.DOWNLOADING, _downloading_item(1000, 4), _labels()
    )
    assert line == "Downloading 99%"


def test_status_line_carries_an_unreleased_date():
    """The design says this line carries "progress or the release date". Returning the
    bare enum name dropped a date the payload already had."""
    import datetime

    from couchseerr import detail
    from couchseerr.models import DiscoverItem
    from couchseerr.state import TileState

    item = DiscoverItem(tmdb_id=1, media_type="movie", title="Dune",
                        release_date=datetime.date(2027, 12, 25))
    assert detail.status_line(TileState.UNRELEASED, item, _labels()) == \
        "Releasing 2027-12-25"


def test_status_line_is_localised_for_every_in_flight_state():
    """Not state.value: the raw lowercase enum name is untranslated English, and it is
    what a French box used to render in the middle of an otherwise localised listing.
    Derived from TileState so a new member cannot quietly reintroduce the fallback."""
    from couchseerr import detail
    from couchseerr.state import TileState

    labels = _labels()
    for state in (TileState.MONITORED, TileState.PENDING, TileState.PARTIAL):
        line = detail.status_line(state, _downloading_item(1000, 380), labels)
        assert line and line != state.value, state
        assert line == labels[detail.STATUS_LABEL_KEYS[state]]


def test_status_line_is_blank_for_states_that_carry_no_line():
    """OWNED and ACTIONABLE carry no line of their own, and the two impossible shapes
    below cannot come out of tile_state. A blank line is not a failure signal:
    detailview.build_view renders no status line for it."""
    from couchseerr import detail
    from couchseerr.models import DiscoverItem
    from couchseerr.state import TileState

    labels = _labels()
    bare = DiscoverItem(tmdb_id=1, media_type="movie", title="Dune")
    assert detail.status_line(TileState.OWNED, bare, labels) == ""
    assert detail.status_line(TileState.ACTIONABLE, bare, labels) == ""
    # DOWNLOADING with no download record, UNRELEASED with no release date.
    assert detail.status_line(TileState.DOWNLOADING, bare, labels) == ""
    assert detail.status_line(TileState.UNRELEASED, bare, labels) == ""


def test_only_an_owned_movie_can_ever_offer_play():
    """The predicate routes.py uses to decide whether resolving a Kodi library id is
    worth a JSON-RPC round trip. It must agree with available_actions' own gate, which
    is the point of it existing rather than being spelled twice."""
    assert can_play_from_library(TileState.OWNED, "movie") is True
    assert can_play_from_library(TileState.OWNED, "tv") is False
    assert can_play_from_library(TileState.ACTIONABLE, "movie") is False
    assert can_play_from_library(TileState.PARTIAL, "movie") is False


def test_the_play_gate_is_answered_in_exactly_one_place():
    """available_actions must route its play decision through the same predicate, or the
    two drift the moment one of them changes."""
    for state in TileState:
        for media_type in ("movie", "tv"):
            offered = "play" in available_actions(
                state, media_type, None, True, None
            )
            assert offered is can_play_from_library(state, media_type)
