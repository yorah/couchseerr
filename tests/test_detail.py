import datetime

from couchseerr.detail import build_detail
from couchseerr.models import DiscoverItem
from couchseerr.state import TileState

BASE = "plugin://plugin.video.couchseerr/"
IMAGE = "https://image.tmdb.org/t/p/w780"
LABELS = {
    "play": "Lire",
    "request": "Demander",
    "request_with": "Demander avec...",
    "trailer": "Bande-annonce",
    "status": "Statut",
    "configure": "Configurer le profil par defaut",
    "not_in_library": "Absent de la bibliotheque Kodi",
}

RESOLVED = {"serverId": 0, "profileId": 21, "is4k": False}

TV_LABELS = dict(LABELS, seasons="Saisons", season="Saison {0}",
                 request_season="Demander cette saison")


def _item():
    return DiscoverItem(
        tmdb_id=693134, media_type="movie", title="Dune", overview="Sand.",
        poster_path="/p.jpg", backdrop_path="/b.jpg",
        release_date=datetime.date(2024, 2, 28), media=None,
    )


def _labels_of(specs):
    return [s.label for s in specs]


def test_owned_and_in_library_offers_play_first():
    specs = build_detail(_item(), TileState.OWNED, RESOLVED, BASE, IMAGE, LABELS,
                         in_library=True, trailer_key="abc", status_line=None)
    assert _labels_of(specs) == ["Lire", "Bande-annonce"]
    assert "mode=play" in specs[0].url
    assert specs[0].is_folder is False


def test_owned_but_absent_from_library_offers_no_play():
    """Playing would need a library id we do not have. Offering a Play that fails is
    worse than saying why it is missing."""
    specs = build_detail(_item(), TileState.OWNED, RESOLVED, BASE, IMAGE, LABELS,
                         in_library=False, trailer_key=None, status_line=None)
    assert _labels_of(specs) == ["Absent de la bibliotheque Kodi"]
    assert specs[0].url == ""


def test_unrequested_offers_the_default_request_entry():
    """A default profile is configured for this media type, so build_detail offers
    "Demander" with no server_id/profile_id in its URL -- routes._do_request resolves
    the actual default at click time, from the same settings this resolved value came
    from."""
    specs = build_detail(_item(), TileState.ACTIONABLE, RESOLVED, BASE, IMAGE, LABELS,
                         in_library=False, trailer_key="abc", status_line=None)
    assert _labels_of(specs) == ["Demander", "Bande-annonce"]
    assert "mode=request" in specs[0].url
    assert "server_id" not in specs[0].url
    assert "profile_id" not in specs[0].url


def test_no_default_profile_offers_settings_entry():
    """The old "Demander avec..." entry is gone -- the context menu carries it now (see
    ui/spec.py). With no default configured, "Demander" would resolve to nothing, so
    the only entry offered here opens the addon's settings."""
    specs = build_detail(_item(), TileState.ACTIONABLE, None, BASE, IMAGE, LABELS,
                         in_library=False, trailer_key=None, status_line=None)
    assert _labels_of(specs) == ["Configurer le profil par defaut"]
    assert "mode=settings" in specs[0].url


# --- fix round 1: the picker must be reachable from inside the listing too ----


def test_requestable_entries_carry_the_context_menu():
    """A user standing in mode=item currently has to back out to the row to reach a
    one-off profile override; every entry of a requestable title's own listing gets the
    same two context items a tile does, so the picker is reachable from here too --
    including the trailer entry and (when no default is configured) the "Configurer"
    entry, since "Demander avec..." works standalone either way."""
    for resolved, expected_first_label in ((RESOLVED, "Demander"), (None, "Configurer le profil par defaut")):
        specs = build_detail(_item(), TileState.ACTIONABLE, resolved, BASE, IMAGE, LABELS,
                             in_library=False, trailer_key="abc", status_line=None)
        assert _labels_of(specs) == [expected_first_label, "Bande-annonce"]
        for spec in specs:
            assert len(spec.context_items) == 2, (resolved, spec.label)
            labels_seen = [label for label, _action in spec.context_items]
            assert labels_seen == ["Demander", "Demander avec..."], (resolved, spec.label)


def test_non_requestable_entries_carry_no_context_items():
    """Owned and in-flight titles must still carry none -- that gate is what keeps a
    duplicate request unreachable from the entries side too, not only from the tile."""
    specs = build_detail(_item(), TileState.OWNED, RESOLVED, BASE, IMAGE, LABELS,
                         in_library=True, trailer_key="abc", status_line=None)
    for spec in specs:
        assert spec.context_items == [], spec.label

    for state in (TileState.DOWNLOADING, TileState.MONITORED,
                  TileState.UNRELEASED, TileState.PENDING, TileState.PARTIAL):
        specs = build_detail(_item(), state, RESOLVED, BASE, IMAGE, LABELS,
                             in_library=False, trailer_key="abc", status_line="62%")
        for spec in specs:
            assert spec.context_items == [], (state, spec.label)


def test_missing_labels_omit_the_detail_listings_context_items():
    labels = dict(LABELS)
    del labels["request_with"]
    specs = build_detail(_item(), TileState.ACTIONABLE, RESOLVED, BASE, IMAGE, labels,
                         in_library=False, trailer_key=None, status_line=None)
    assert specs
    for spec in specs:
        assert spec.context_items == []


def test_in_flight_states_offer_no_request_at_all():
    """seerr's own duplicate guard is permissive, so a second request from here would
    often be created silently. The tile already knows; refuse before offering."""
    for state in (TileState.DOWNLOADING, TileState.MONITORED,
                  TileState.UNRELEASED, TileState.PENDING, TileState.PARTIAL):
        specs = build_detail(_item(), state, RESOLVED, BASE, IMAGE, LABELS,
                             in_library=False, trailer_key=None, status_line="62%")
        assert not any("mode=request" in s.url for s in specs), state
        assert specs[0].label == "62%"


def test_the_trailer_entry_is_absent_without_a_key():
    specs = build_detail(_item(), TileState.ACTIONABLE, RESOLVED, BASE, IMAGE, LABELS,
                         in_library=False, trailer_key=None, status_line=None)
    assert "Bande-annonce" not in _labels_of(specs)


def test_every_entry_carries_the_titles_art_and_plot():
    """The skin's info pane and DialogVideoInfo both read the focused item. If an action
    entry carried its own bare metadata, standing on it would blank the movie."""
    specs = build_detail(_item(), TileState.ACTIONABLE, RESOLVED, BASE, IMAGE, LABELS,
                         in_library=False, trailer_key="abc", status_line=None)
    for spec in specs:
        assert spec.art["poster"] == IMAGE + "/p.jpg"
        assert spec.art["fanart"] == IMAGE + "/b.jpg"
        assert spec.info["plot"] == "Sand."
        assert spec.info["title"] == "Dune"
        assert spec.info["year"] == 2024


# --- the flags that decide whether an entry does anything at all --------------


def test_every_action_entry_is_a_non_folder_plugin_path():
    """This is what gives an action entry RunPlugin semantics. CGUIMediaWindow::OnClick
    runs a plugin item that is a non-folder and not marked isplayable as a script, with
    handle -1 -- which is exactly right for mode=request, mode=play, mode=settings and
    mode=trailer, none of which render a listing.

    A folder here would instead navigate into the path and wait for a directory that
    never comes; the container would sit on an empty listing.
    """
    for state, kwargs in (
        (TileState.OWNED, {"in_library": True}),
        (TileState.ACTIONABLE, {"in_library": False}),
    ):
        specs = build_detail(_item(), state, RESOLVED, BASE, IMAGE, LABELS,
                             trailer_key="abc", status_line=None, **kwargs)
        actionable = [s for s in specs if s.url]
        assert actionable, state
        for spec in actionable:
            assert spec.is_folder is False, (state, spec.label)
            assert spec.url.startswith(BASE + "?"), (state, spec.label)
            assert "mode=" in spec.url, (state, spec.label)


def test_no_entry_claims_to_be_playable():
    """The third branch of the same OnClick chain: a non-folder plugin item whose
    isplayable property is true is *played*, and the addon is then expected to answer
    with setResolvedUrl. Nothing here does, so claiming it would turn every action entry
    into a failed-playback dialog. Asserting the absence is the guard, because setting it
    is a one-word change that no other test would notice."""
    specs = build_detail(_item(), TileState.ACTIONABLE, RESOLVED, BASE, IMAGE, LABELS,
                         in_library=False, trailer_key="abc", status_line=None)
    assert specs, "no entries built; this guard would pass vacuously"
    for spec in specs:
        assert not any(key.lower() == "isplayable" for key in spec.properties), spec.label


def test_a_line_the_user_only_reads_carries_no_url():
    """The status line and the not-in-library explanation are not actions. Giving them a
    plugin URL would make selecting them run a route for no reason."""
    specs = build_detail(_item(), TileState.MONITORED, RESOLVED, BASE, IMAGE, LABELS,
                         in_library=False, trailer_key=None, status_line="Monitored")
    assert [s.label for s in specs] == ["Monitored"]
    assert specs[0].url == ""


def _show():
    return DiscoverItem(
        tmdb_id=82856, media_type="tv", title="The Show", overview="Plot.",
        poster_path="/p.jpg", backdrop_path="/b.jpg",
        release_date=datetime.date(2019, 11, 12), media=None,
    )


def test_tv_title_offers_seasons_beside_whole_show_request():
    """The whole-show request is the common case and stays one click; Seasons is the way
    to the selective one."""
    specs = build_detail(_show(), TileState.ACTIONABLE, RESOLVED, BASE, IMAGE, TV_LABELS,
                         in_library=False, trailer_key="abc", status_line=None)
    assert _labels_of(specs) == ["Demander", "Saisons", "Bande-annonce"]
    assert "mode=seasons" in specs[1].url and "tmdb_id=82856" in specs[1].url
    # Pinned together, not checked one at a time: a wrongly-defaulted or later-flipped
    # is_folder on either action row would slip past a per-entry membership check but
    # not this one -- on the device it means clicking Demander navigates instead of
    # requesting.
    assert [s.is_folder for s in specs] == [False, True, False]


def test_a_partial_tv_title_can_still_reach_its_seasons():
    """The gap this whole feature exists to close: today a partial show offers no request
    at all, so its missing seasons are unreachable from the TV."""
    specs = build_detail(_show(), TileState.PARTIAL, None, BASE, IMAGE, TV_LABELS,
                         in_library=False, trailer_key=None, status_line="Partiel")
    assert _labels_of(specs) == ["Partiel", "Saisons"]


def test_an_owned_tv_show_offers_only_seasons():
    """Whole-show Play never worked -- Player.Open has no tvshowid parameter -- so it is
    gone. Seasons is the only way into an owned show; a single episode plays from inside
    it instead."""
    specs = build_detail(_show(), TileState.OWNED, RESOLVED, BASE, IMAGE, TV_LABELS,
                         in_library=True, trailer_key=None, status_line=None)
    assert _labels_of(specs) == ["Saisons"]


def test_an_owned_tv_show_not_in_kodi_still_offers_seasons():
    """in_library is now unread for a tv title: Seasons offers whichever seasons the show
    has regardless of whether Kodi has scanned it, unlike the movie Play/not-in-library
    branch above."""
    specs = build_detail(_show(), TileState.OWNED, RESOLVED, BASE, IMAGE, TV_LABELS,
                         in_library=False, trailer_key="abc", status_line=None)
    assert _labels_of(specs) == ["Saisons", "Bande-annonce"]


def test_a_movie_never_offers_seasons():
    specs = build_detail(_item(), TileState.ACTIONABLE, RESOLVED, BASE, IMAGE, TV_LABELS,
                         in_library=False, trailer_key=None, status_line=None)
    assert _labels_of(specs) == ["Demander"]
