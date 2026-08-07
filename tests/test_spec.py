import datetime

import pytest

from couchseerr.models import parse_discover_page
from couchseerr.state import TileState, tile_state
from couchseerr.ui.spec import build_spec, request_urls

TODAY = datetime.date(2026, 1, 6)
BASE = "plugin://plugin.video.couchseerr/"
IMAGES = "https://image.tmdb.org/t/p/w780"
LABELS = {"request": "Request", "request_with": "Request with..."}


@pytest.fixture
def specs(fixture):
    out = {}
    for item in parse_discover_page(fixture("discover_trending")):
        out[item.tmdb_id] = build_spec(item, tile_state(item, TODAY), BASE, IMAGES, LABELS)
    return out


def test_owned_marker_is_in_the_label(specs):
    """The marker must be in the label: a plot marker is invisible unless the tile is
    focused, which defeats scanning a row."""
    assert "Fixture One" in specs[101].label
    assert specs[101].label != "Fixture One"


def test_actionable_tile_is_unmarked(specs):
    assert specs[107].label == "Fixture Seven"


def test_downloading_label_carries_percent(specs):
    assert "62%" in specs[103].label


def test_downloading_properties_carry_progress_and_eta(specs):
    props = specs[103].properties
    assert props["seerr.status"] == "downloading"
    assert props["seerr.progress"] == "62"
    assert props["seerr.eta"] == "00:14:32"


def test_non_downloading_tile_has_empty_progress_properties(specs):
    props = specs[104].properties
    assert props["seerr.status"] == "monitored"
    assert props["seerr.progress"] == ""
    assert props["seerr.eta"] == ""


def test_every_spec_sets_a_status_property(specs):
    for spec in specs.values():
        assert "seerr.status" in spec.properties


def test_unreleased_label_shows_the_date(specs):
    assert "2027" in specs[105].label


def test_backdrop_maps_to_both_fanart_and_landscape(specs):
    """seerr serves no landscape artwork; without this every row is forced to Poster."""
    art = specs[101].art
    assert art["fanart"] == IMAGES + "/fixtureBackdrop.jpg"
    assert art["landscape"] == art["fanart"]
    assert art["poster"] == IMAGES + "/fixturePoster.jpg"


def test_missing_artwork_omits_the_key():
    from couchseerr.models import DiscoverItem

    item = DiscoverItem(tmdb_id=1, media_type="movie", title="Bare")
    spec = build_spec(item, TileState.ACTIONABLE, BASE, IMAGES, LABELS)
    assert "poster" not in spec.art
    assert "fanart" not in spec.art


def test_url_encodes_tmdb_id_and_media_type(specs):
    url = specs[101].url
    assert url.startswith(BASE)
    assert "tmdb_id=101" in url
    assert "media_type=movie" in url


def test_tv_item_uses_tv_media_type(specs):
    assert "media_type=tv" in specs[201].url


def test_info_carries_title_plot_and_year(specs):
    info = specs[101].info
    assert info["title"] == "Fixture One"
    assert info["plot"].startswith("Placeholder")
    assert info["year"] == 2025


def _downloading_item(size, size_left):
    from couchseerr.models import DiscoverItem, DownloadProgress, MediaState

    download = DownloadProgress(
        size=size,
        size_left=size_left,
        time_left="00:00:00",
        estimated_completion_time=None,
        status="downloading",
    )
    media = MediaState(status=3, status4k=1, downloads=(download,))
    return DiscoverItem(tmdb_id=999, media_type="movie", title="Edge", media=media)


def test_near_complete_percent_truncates_instead_of_rounding():
    """99.6% must read as 99, never as the false claim "100" -- the user is deciding
    whether a title is worth waiting for tonight."""
    item = _downloading_item(size=1000, size_left=4)
    spec = build_spec(item, TileState.DOWNLOADING, BASE, IMAGES, LABELS)
    assert "99%" in spec.label
    assert spec.properties["seerr.progress"] == "99"


def test_actually_complete_download_shows_100_percent():
    item = _downloading_item(size=1000, size_left=0)
    spec = build_spec(item, TileState.DOWNLOADING, BASE, IMAGES, LABELS)
    assert "100%" in spec.label
    assert spec.properties["seerr.progress"] == "100"


def test_zero_percent_download_renders_as_zero():
    item = _downloading_item(size=1000, size_left=1000)
    spec = build_spec(item, TileState.DOWNLOADING, BASE, IMAGES, LABELS)
    assert "0%" in spec.label
    assert spec.properties["seerr.progress"] == "0"


def test_unreadable_download_fallback_has_empty_progress():
    """When a download record is unreadable, tile_state() has already fallen back to
    MONITORED (see state.py), but best_download is still the unreadable record --
    seerr.progress must not render its "0" alongside a "monitored" status, which
    would read as a real 0% progress on a tile whose label says "monitored"."""
    item = _downloading_item(size=100, size_left=None)
    spec = build_spec(item, TileState.MONITORED, BASE, IMAGES, LABELS)
    assert spec.properties["seerr.status"] == "monitored"
    assert spec.properties["seerr.progress"] == ""


def _item():
    from couchseerr.models import DiscoverItem

    return DiscoverItem(tmdb_id=1, media_type="movie", title="Test")


def test_actionable_is_requestable():
    spec = build_spec(_item(), TileState.ACTIONABLE, BASE, IMAGES, LABELS)
    assert spec.properties["seerr.requestable"] == "1"
    assert "mode=request" in spec.properties["seerr.action.request"]


def test_requestable_property_is_empty_for_every_other_state():
    """A skin badge and a skin button both read this. Marking an owned or already
    pending title requestable is how a skin ends up offering a duplicate request."""
    from couchseerr.models import DiscoverItem

    # Test states that don't require special item attributes
    for state in (
        TileState.OWNED, TileState.PARTIAL,
        TileState.MONITORED, TileState.PENDING,
    ):
        spec = build_spec(_item(), state, BASE, IMAGES, LABELS)
        assert spec.properties["seerr.requestable"] == "", state
        assert spec.properties["seerr.action.request"] == "", state

    # DOWNLOADING state requires an item with a download
    spec = build_spec(_downloading_item(1000, 500), TileState.DOWNLOADING, BASE, IMAGES, LABELS)
    assert spec.properties["seerr.requestable"] == "", TileState.DOWNLOADING
    assert spec.properties["seerr.action.request"] == "", TileState.DOWNLOADING

    # UNRELEASED state requires a release_date
    unreleased_item = DiscoverItem(
        tmdb_id=2, media_type="movie", title="Unreleased",
        release_date=datetime.date(2027, 1, 1)
    )
    spec = build_spec(unreleased_item, TileState.UNRELEASED, BASE, IMAGES, LABELS)
    assert spec.properties["seerr.requestable"] == "", TileState.UNRELEASED
    assert spec.properties["seerr.action.request"] == "", TileState.UNRELEASED


def test_a_tile_opens_the_detail_window():
    spec = build_spec(_item(), TileState.ACTIONABLE, BASE, IMAGES, LABELS)
    assert "mode=detail" in spec.url
    assert "tmdb_id=1" in spec.url
    assert "media_type=movie" in spec.url


def test_a_tile_is_a_non_folder_that_runs_the_addon():
    """CGUIMediaWindow::OnClick branches three ways on a plugin item: a folder is
    navigated into (a real handle, a directory listing demanded); a non-folder with no
    isplayable is *run as a script* like RunPlugin, with handle -1 -- the same branch
    mode=request and mode=play already take; a non-folder marked isplayable is played
    and must answer with setResolvedUrl, which mode=detail cannot do. Tiles must take
    the middle branch, for every state, so that the click opens the detail window
    instead of a failed-playback dialog or a directory listing that no longer exists.
    """
    for state in (TileState.OWNED, TileState.ACTIONABLE):
        spec = build_spec(_item(), state, BASE, IMAGES, LABELS)
        assert spec.is_folder is False
        assert "isplayable" not in {key.lower() for key in spec.properties}


# --- the context menu: every tile can be requested without opening it first ---


def test_requestable_tile_carries_exactly_two_context_items():
    spec = build_spec(_item(), TileState.ACTIONABLE, BASE, IMAGES, LABELS)
    assert len(spec.context_items) == 2
    labels_seen = [label for label, _action in spec.context_items]
    assert labels_seen == [LABELS["request"], LABELS["request_with"]]


def test_context_items_run_the_request_route():
    spec = build_spec(_item(), TileState.ACTIONABLE, BASE, IMAGES, LABELS)
    (_request_label, request_action), (_pick_label, pick_action) = spec.context_items

    assert request_action.startswith("RunPlugin(")
    assert request_action.endswith(")")
    assert "mode=request" in request_action
    assert "tmdb_id=1" in request_action
    assert "media_type=movie" in request_action
    assert "pick=1" not in request_action

    assert pick_action.startswith("RunPlugin(")
    assert "mode=request" in pick_action
    assert "pick=1" in pick_action


def test_non_requestable_tile_carries_no_context_items():
    """Owned, downloading, monitored, unreleased and pending tiles offer neither entry
    -- offering one there is how a duplicate request gets created underneath
    actions/request.py's own refusal."""
    from couchseerr.models import DiscoverItem

    for state in (TileState.OWNED, TileState.PARTIAL, TileState.MONITORED, TileState.PENDING):
        spec = build_spec(_item(), state, BASE, IMAGES, LABELS)
        assert spec.context_items == [], state

    spec = build_spec(_downloading_item(1000, 500), TileState.DOWNLOADING, BASE, IMAGES, LABELS)
    assert spec.context_items == []

    unreleased_item = DiscoverItem(
        tmdb_id=2, media_type="movie", title="Unreleased",
        release_date=datetime.date(2027, 1, 1)
    )
    spec = build_spec(unreleased_item, TileState.UNRELEASED, BASE, IMAGES, LABELS)
    assert spec.context_items == []


def test_missing_labels_omit_context_items_not_blank_entries():
    """A requestable tile built with an empty (or partial) labels dict must not emit a
    context item with an empty label -- still clickable, impossible to read, worse than
    no menu at all. Omit both items rather than one, so a menu with only "Demander" and
    no "Demander avec..." never silently drops the picker without saying why. The
    skin-facing seerr.requestable/seerr.action.request properties are unaffected: they
    carry no label at all, so a missing localised string has nothing to blank there."""
    spec = build_spec(_item(), TileState.ACTIONABLE, BASE, IMAGES, {})
    assert spec.context_items == []
    assert spec.properties["seerr.requestable"] == "1"
    assert spec.properties["seerr.action.request"]

    spec = build_spec(_item(), TileState.ACTIONABLE, BASE, IMAGES, {"request": "Demander"})
    assert spec.context_items == []


def test_context_items_default_to_empty_on_the_spec_itself():
    """ListItemSpec's own default, independent of build_spec: any other pure-core
    caller that does not pass context_items must not crash the adapter."""
    from couchseerr.ui.spec import ListItemSpec

    spec = ListItemSpec(
        label="X", url="", is_folder=False, art={}, properties={}, info={},
    )
    assert spec.context_items == []


# --- art and info are shaped in one place -------------------------------------


def _spec_item():
    from couchseerr.models import DiscoverItem

    return DiscoverItem(
        tmdb_id=693134, media_type="movie", title="Dune", overview="Sand.",
        poster_path="/p.jpg", backdrop_path="/b.jpg",
        release_date=datetime.date(2024, 2, 28),
    )


def test_art_and_info_returns_fresh_dicts_each_call():
    """Every caller hands its copy on to Kodi, which mutates through it; a shared dict
    would leak one row's edits into all the others."""
    from couchseerr.ui.spec import art_and_info

    item = _spec_item()
    first_art, first_info = art_and_info(item, IMAGES)
    second_art, second_info = art_and_info(item, IMAGES)

    assert first_art == second_art and first_art is not second_art
    assert first_info == second_info and first_info is not second_info


def test_a_tile_and_the_window_describe_the_same_title():
    """The rule this file exists for, one layer up: a tile and the detail window it opens
    describe the same title. When these were built twice, adding an art key or fixing the
    backdrop mapping in one place left the other silently behind."""
    import datetime

    from couchseerr.detailview import build_view

    item = _spec_item()
    tile = build_spec(item, TileState.ACTIONABLE, BASE, IMAGES, LABELS)
    resolved = {"serverId": 0, "profileId": 21, "is4k": False}
    view = build_view(
        item, TileState.ACTIONABLE, resolved, None, "yt", [], [], BASE, IMAGES,
        {"request": "Request", "trailer": "Trailer", "configure": "Configure"},
        datetime.date(2026, 8, 24),
    )

    assert tile.art, "no art built; this guard would pass vacuously"
    assert view.art == tile.art
    # The window carries the same three info values the tile does, as named fields
    # rather than as an info dict: it renders them itself instead of handing them to
    # Kodi's info pane.
    assert view.title == tile.info["title"]
    assert view.plot == tile.info["plot"]
    assert view.year == tile.info["year"]


def test_art_and_info_maps_every_key_from_one_title():
    """The whole mapping in one assertion, now that it exists in one function: poster to
    thumb, and backdrop to both fanart and landscape because seerr serves no landscape
    artwork and without it the rows are forced into Poster styling."""
    from couchseerr.ui.spec import art_and_info

    art, info = art_and_info(_spec_item(), IMAGES)
    assert art == {
        "poster": IMAGES + "/p.jpg",
        "thumb": IMAGES + "/p.jpg",
        "fanart": IMAGES + "/b.jpg",
        "landscape": IMAGES + "/b.jpg",
    }
    assert info == {
        "title": "Dune", "plot": "Sand.", "year": 2024, "premiered": "2024-02-28",
    }


def test_request_urls_without_a_season_are_unchanged():
    item = _item()
    request_url, pick_url = request_urls(item, BASE)
    assert "season" not in request_url and "season" not in pick_url


def test_request_urls_carry_the_season():
    item = _item()
    request_url, pick_url = request_urls(item, BASE, season=4)
    assert "season=4" in request_url
    assert "season=4" in pick_url and "pick=1" in pick_url


def test_art_and_info_omit_what_the_title_does_not_have():
    """seerr serves titles with no artwork and no release date. Prefixing image_base onto
    an absent path would produce a URL that 404s behind every tile, and a year key built
    from a missing date would crash the builder."""
    from couchseerr.models import DiscoverItem
    from couchseerr.ui.spec import art_and_info

    art, info = art_and_info(
        DiscoverItem(tmdb_id=1, media_type="movie", title="No art"), IMAGES
    )
    assert art == {}
    assert "year" not in info and "premiered" not in info


def _a_movie():
    from couchseerr.models import DiscoverItem

    return DiscoverItem(
        tmdb_id=693134, media_type="movie", title="Dune", overview="Sand.",
        poster_path="/p.jpg", backdrop_path="/b.jpg",
        release_date=datetime.date(2021, 9, 15), media=None,
    )


def test_resolved_spec_carries_the_path_as_its_url():
    """Kodi asked what to play; the answer is a path, and the spec's url is where every
    other spec already keeps "where this row leads"."""
    from couchseerr.ui.spec import resolved_spec

    spec = resolved_spec(_a_movie(), "/mnt/movies/Dune.mkv", IMAGES)

    assert spec.url == "/mnt/movies/Dune.mkv"
    assert spec.label == "Dune"
    assert spec.is_folder is False
    assert spec.info["title"] == "Dune"
    assert spec.art["poster"] == IMAGES + "/p.jpg"


def test_unplayable_spec_leads_nowhere():
    """Kodi wants a ListItem alongside a failed resolve, and an empty url is this
    project's one spelling of "this row leads nowhere" -- which is what lets the adapter
    decide succeeded from the spec alone."""
    from couchseerr.ui.spec import unplayable_spec

    spec = unplayable_spec()

    assert spec.url == ""
    assert spec.label == ""
    assert spec.art == {}
    assert spec.info is None


def test_a_widget_tile_is_a_folder_that_says_open():
    """A tile rendered into a skin's home widget cannot be clicked the way a tile in the
    addon's own row is: the skin answers a non-folder with Kodi's video info dialog, and
    the addon never hears about it. A folder is the one shape whose click reaches the
    addon there, and `open=1` is how that arrival is told apart from Kodi asking to play
    the same url."""
    from couchseerr.models import parse_discover_page

    item = parse_discover_page(
        {"results": [{"id": 77, "mediaType": "movie", "title": "Dune", "overview": "",
                      "releaseDate": "2021-09-15"}]}
    )[0]
    spec = build_spec(item, TileState.ACTIONABLE, BASE, IMAGES, LABELS, widget=True)

    assert spec.is_folder is True
    assert "open=1" in spec.url
    assert "mode=detail" in spec.url


def test_an_ordinary_tile_is_neither(specs):
    """The default stays what the device is verified against: a non-folder tile whose
    click runs the addon as a script, and whose url Kodi's own Play answers by state."""
    spec = specs[101]

    assert spec.is_folder is False
    assert "open=" not in spec.url
