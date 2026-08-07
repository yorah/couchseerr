import pytest
import xbmcgui
import xbmcplugin

from couchseerr.kodi.adapter import render, to_list_item
from couchseerr.routes import parse_args
from couchseerr.ui.spec import ListItemSpec


def _a_settings():
    return {"serverId": 0, "profileId": 21, "is4k": False}


#: Shared with test_detail.py, test_seasons.py and test_spec.py's own BASE constant.
BASE = "plugin://plugin.video.couchseerr/"

#: Same shape _a_settings() returns; named for what the season routes resolve it as.
RESOLVED_DEFAULT = _a_settings()


class _DetailService(object):
    warnings = []
    client = None

    def __init__(self):
        self.invalidated = []

    def invalidate_detail(self, media_type, tmdb_id):
        self.invalidated.append((media_type, tmdb_id))

    def detail(self, media_type, tmdb_id):
        from couchseerr.models import DiscoverItem
        from couchseerr.state import TileState

        item = DiscoverItem(tmdb_id=tmdb_id, media_type=media_type, title="Dune",
                            overview="", poster_path=None, backdrop_path=None,
                            release_date=None, media=None)
        return item, TileState.ACTIONABLE, {"imdbId": "tt15239678", "relatedVideos": []}


def make_spec(label="Item", context_items=None):
    return ListItemSpec(
        label=label,
        url="plugin://plugin.video.couchseerr/?mode=item",
        is_folder=True,
        art={"poster": "http://img/p.jpg", "landscape": "http://img/b.jpg"},
        properties={"seerr.status": "owned", "seerr.progress": "", "seerr.eta": ""},
        info={"title": label, "plot": "text", "year": 2025},
        context_items=context_items,
    )


def setup_function():
    del xbmcplugin._added[:]
    del xbmcplugin._ended[:]
    del xbmcplugin._content[:]
    del xbmcgui._notifications[:]


def test_to_list_item_transfers_label_art_and_properties():
    li = to_list_item(make_spec("Fixture"))
    assert li.getLabel() == "Fixture"
    assert li._art["poster"] == "http://img/p.jpg"
    assert li._art["landscape"] == "http://img/b.jpg"
    assert li._props["seerr.status"] == "owned"


def test_info_goes_through_the_info_tag_when_setters_exist():
    """Kodi 20+ path."""
    li = to_list_item(make_spec("Fixture"))
    tag = li.getVideoInfoTag()
    assert tag.values["title"] == "Fixture"
    assert tag.values["year"] == 2025
    assert li._info == {}


def test_info_falls_back_to_set_info_on_older_kodi(monkeypatch):
    """Kodi 19 exposes an InfoTagVideo without setters; setInfo is the only route."""
    import xbmcgui

    from couchseerr.kodi.adapter import apply_info

    class LegacyTag(object):
        pass  # no setTitle - mirrors Kodi 19

    item = xbmcgui.ListItem(label="Legacy")
    monkeypatch.setattr(item, "getVideoInfoTag", lambda: LegacyTag(), raising=False)
    apply_info(item, {"title": "Legacy", "plot": "p", "year": 2020})
    assert item._info["video"]["title"] == "Legacy"


def test_older_kodi_setinfo_drops_the_resume_tuple(monkeypatch):
    """setInfo has no way to express a resume point (that's a two-argument InfoTagVideo
    setter). A tuple leaking through would not raise -- it would just sit in the dict --
    so this asserts on the whole dict setInfo received, not just presence of the other
    keys, to catch that regression."""
    import xbmcgui

    from couchseerr.kodi.adapter import apply_info

    class LegacyTag(object):
        pass  # no setTitle - mirrors Kodi 19

    item = xbmcgui.ListItem(label="Legacy")
    monkeypatch.setattr(item, "getVideoInfoTag", lambda: LegacyTag(), raising=False)
    apply_info(item, {"title": "Legacy", "plot": "p", "resume": (420.0, 2400.0)})
    assert item._info["video"] == {"title": "Legacy", "plot": "p"}


def test_properties_are_set_individually_not_in_bulk(monkeypatch):
    """setProperties (plural) is unreliable on Kodi 19, so it must never be called."""
    import xbmcgui

    def explode(self, props):
        raise AssertionError("setProperties must not be used")

    monkeypatch.setattr(xbmcgui.ListItem, "setProperties", explode)
    li = to_list_item(make_spec("Fixture"))
    assert li._props["seerr.status"] == "owned"


def test_context_items_are_applied_when_present():
    """ui/spec.py is the only ListItem construction site; the adapter's job here is
    strictly to apply what the spec already decided, not to choose anything itself."""
    items = [("Demander", "RunPlugin(plugin://plugin.video.couchseerr/?mode=request)")]
    li = to_list_item(make_spec("Fixture", context_items=items))
    assert li._context_items == items


def test_no_context_items_skips_addcontextmenuitems():
    """Most specs (every non-requestable tile, every detail-listing entry) carry no
    context items at all; the adapter must not call addContextMenuItems for them."""
    li = to_list_item(make_spec("Fixture"))
    assert li._context_items is None


def test_unknown_info_keys_are_ignored_rather_than_crashing():
    from couchseerr.kodi.adapter import apply_info
    import xbmcgui

    item = xbmcgui.ListItem(label="X")
    apply_info(item, {"title": "X", "not_a_real_field": 1})
    assert item.getVideoInfoTag().values["title"] == "X"


def test_apply_info_sets_playcount_through_the_info_tag():
    from couchseerr.kodi.adapter import apply_info

    item = xbmcgui.ListItem(label="x")
    apply_info(item, {"title": "Chapter One", "playcount": 1})
    assert item.getVideoInfoTag()._playcount == 1


def test_apply_info_sets_a_resume_point():
    from couchseerr.kodi.adapter import apply_info

    item = xbmcgui.ListItem(label="x")
    apply_info(item, {"title": "Chapter One", "resume": (420.0, 2400.0)})
    assert item.getVideoInfoTag()._resume == (420.0, 2400.0)


def test_resume_point_is_skipped_when_the_tag_has_no_setter(monkeypatch):
    """Every other InfoTagVideo setter in apply_info is guarded with getattr(tag, ...,
    None); setResumePoint was not, so a tag missing it (a case not currently reachable on
    a supported Kodi, but every sibling setter is guarded against exactly this) would
    raise inside render instead of just skipping the resume bar."""
    from couchseerr.kodi.adapter import apply_info

    class TagWithoutResume(object):
        def setTitle(self, value):
            self.title = value

    tag = TagWithoutResume()
    item = xbmcgui.ListItem(label="x")
    monkeypatch.setattr(item, "getVideoInfoTag", lambda: tag, raising=False)
    apply_info(item, {"title": "Chapter One", "resume": (420.0, 2400.0)})
    assert tag.title == "Chapter One"
    assert not hasattr(tag, "_resume")


def test_render_adds_every_item_and_ends_the_directory():
    render(7, [make_spec("A"), make_spec("B")])
    assert len(xbmcplugin._added) == 2
    assert xbmcplugin._ended == [(7, True, False)]


def test_render_of_an_empty_row_still_ends_the_directory():
    render(7, [])
    assert xbmcplugin._ended == [(7, True, False)]


def test_parse_args_extracts_handle_base_and_params():
    handle, base, params = parse_args(
        ["plugin://plugin.video.couchseerr/", "7", "?mode=row&key=trending"]
    )
    assert handle == 7
    assert base == "plugin://plugin.video.couchseerr/"
    assert params == {"mode": "row", "key": "trending"}


def test_parse_args_with_no_query_returns_empty_params():
    handle, base, params = parse_args(["plugin://plugin.video.couchseerr/", "3", ""])
    assert params == {}


def test_parse_args_without_a_third_argument():
    """Kodi passes three argv entries, but a widget path invoked through some skins and
    through JSON-RPC Files.GetDirectory arrives with the query missing entirely. Indexing
    argv[2] unconditionally would raise before anything can close the directory."""
    handle, base, params = parse_args(["plugin://plugin.video.couchseerr/", "4"])
    assert (handle, params) == (4, {})


def test_parse_args_ignores_query_without_leading_question_mark():
    handle, base, params = parse_args(
        ["plugin://plugin.video.couchseerr/", "5", "mode=row"]
    )
    assert params == {}


def test_parse_args_decodes_percent_encoding():
    handle, base, params = parse_args(
        ["plugin://plugin.video.couchseerr/", "6", "?mode=row&key=on%20the%20way"]
    )
    assert params["key"] == "on the way"


def test_parse_args_keeps_the_last_of_a_repeated_parameter():
    """dict(parse_qsl(...)) collapses duplicates last-wins. Documented here because the
    alternative -- first-wins or a list -- changes which row a crafted path opens."""
    handle, base, params = parse_args(
        ["plugin://plugin.video.couchseerr/", "7", "?mode=row&key=trending&key=popular_tv"]
    )
    assert params["key"] == "popular_tv"


def test_unknown_mode_still_ends_the_directory(monkeypatch):
    """A fall-through that never calls endOfDirectory leaves Kodi spinning forever."""
    from couchseerr import routes

    monkeypatch.setattr(routes, "_build_service", lambda *a, **k: None)
    routes.dispatch(["plugin://plugin.video.couchseerr/", "9", "?mode=nonsense"])
    assert xbmcplugin._ended == [(9, False, False)]
    assert xbmcgui._notifications


def test_client_failure_is_reported_and_directory_is_closed(monkeypatch):
    from couchseerr import routes
    from couchseerr.errors import SeerrUnavailable

    class Failing(object):
        def discover_row(self, key):
            raise SeerrUnavailable("down")

    monkeypatch.setattr(routes, "_build_service", lambda *a, **k: Failing())
    routes.dispatch(["plugin://plugin.video.couchseerr/", "4", "?mode=row&key=trending"])
    assert xbmcplugin._ended == [(4, False, False)]
    assert xbmcgui._notifications


def test_key_error_from_service_ends_directory_once(monkeypatch):
    """An untyped bug downstream must not leave Kodi hanging with no message."""
    from couchseerr import routes

    class Failing(object):
        def discover_row(self, key):
            raise KeyError(key)

    monkeypatch.setattr(routes, "_build_service", lambda *a, **k: Failing())
    routes.dispatch(["plugin://plugin.video.couchseerr/", "5", "?mode=row&key=trending"])
    assert xbmcplugin._ended == [(5, False, False)]
    assert xbmcgui._notifications


def test_value_error_from_service_ends_directory_once(monkeypatch):
    from couchseerr import routes

    class Failing(object):
        def discover_row(self, key):
            raise ValueError("bad key")

    monkeypatch.setattr(routes, "_build_service", lambda *a, **k: Failing())
    routes.dispatch(["plugin://plugin.video.couchseerr/", "6", "?mode=row&key=trending"])
    assert xbmcplugin._ended == [(6, False, False)]
    assert xbmcgui._notifications


def test_runtime_error_from_service_ends_directory_once(monkeypatch):
    """Any arbitrary uncaught exception must still close the directory exactly once."""
    from couchseerr import routes

    class Failing(object):
        def discover_row(self, key):
            raise RuntimeError("boom")

    monkeypatch.setattr(routes, "_build_service", lambda *a, **k: Failing())
    routes.dispatch(["plugin://plugin.video.couchseerr/", "8", "?mode=row&key=trending"])
    assert xbmcplugin._ended == [(8, False, False)]
    assert xbmcgui._notifications


def test_exception_in_render_loop_ends_dir_once(monkeypatch):
    """Exception during item loop must not double-close the directory."""
    from couchseerr import routes

    def explode(spec):
        raise RuntimeError("item processing failed")

    monkeypatch.setattr("couchseerr.kodi.adapter.to_list_item", explode)

    class Working(object):
        def discover_row(self, key):
            return [make_spec("Item")]

    monkeypatch.setattr(routes, "_build_service", lambda *a, **k: Working())
    routes.dispatch(["plugin://plugin.video.couchseerr/", "10", "?mode=row&key=trending"])
    assert xbmcplugin._ended == [(10, False, False)]
    assert xbmcgui._notifications


# --- mode=root / _root_specs -------------------------------------------------
# Every dispatch test above stubs _build_service away, so none of it exercises
# _root_specs or mode=root itself. These do, against the real ROWS registry.


def test_root_specs_lists_every_row_with_the_row_url_and_label():
    from couchseerr.rows import ROWS
    from couchseerr.routes import _root_specs

    base = "plugin://plugin.video.couchseerr/"
    specs = _root_specs(base)

    assert len(specs) == len(ROWS)
    by_key = {}
    for spec, row in zip(specs, ROWS.values()):
        assert spec.label == row.label
        assert spec.url == "{0}?mode=row&key={1}".format(base, row.key)
        assert spec.is_folder is True
        by_key[row.key] = spec
    assert set(by_key) == set(ROWS)


def test_mode_root_ends_the_directory_successfully_end_to_end():
    from couchseerr import routes

    routes.dispatch(["plugin://plugin.video.couchseerr/", "11", "?mode=root"])
    assert xbmcplugin._ended == [(11, True, False)]
    assert xbmcplugin._content == [(11, "videos")]
    assert len(xbmcplugin._added) == 4
    assert not xbmcgui._notifications


# --- _build_service -----------------------------------------------------------
# The only place xbmcaddon, xbmcvfs, FileCache, SeerrClient and RowService meet.
# A wrong keyword name or a swapped argument here would pass every other test
# and fail only on a real device.


def test_build_service_wires_a_row_service_from_addon_settings(monkeypatch, tmp_path):
    """Runs against the xbmcaddon/xbmcvfs stubs' actual settings, not a mock of
    _build_service itself. chdir into tmp_path because FileCache.__init__ really
    creates the (stub, non-absolute) profile directory on disk."""
    from couchseerr import routes
    from couchseerr.client import SeerrClient
    from couchseerr.rows import RowService

    monkeypatch.chdir(tmp_path)
    service = routes._build_service("plugin://plugin.video.couchseerr/")

    assert isinstance(service, RowService)
    assert service.base_url == "plugin://plugin.video.couchseerr/"
    # xbmcaddon stub's "language" setting is blank -- the shipped default -- so this
    # falls back to xbmc.getLanguage(). It must ask for ISO_639_1 ("en"), not the
    # default ENGLISH_NAME ("English"), which TMDb cannot parse.
    assert service.language == "en"
    assert isinstance(service.client, SeerrClient)
    assert service.client.base_url == "http://seerr.test:5055"
    assert service.client.api_key == "fixture-key"
    assert service.cache.root.endswith("plugin.video.couchseerr/cache")


def test_build_service_defaults_base_url_when_none_given(monkeypatch, tmp_path):
    from couchseerr import routes

    monkeypatch.chdir(tmp_path)
    service = routes._build_service()
    assert service.base_url == "plugin://plugin.video.couchseerr/"


def test_build_service_purges_expired_cache_entries_once(monkeypatch, tmp_path):
    """The cache grows without bound if nothing ever cleans up entries that are
    never read again; this must run once per dispatch through _build_service."""
    from couchseerr import routes
    from couchseerr.cache import FileCache

    monkeypatch.chdir(tmp_path)
    calls = []
    original = FileCache.purge_expired

    def spy(self):
        calls.append(self)
        return original(self)

    monkeypatch.setattr(FileCache, "purge_expired", spy)
    routes._build_service("plugin://plugin.video.couchseerr/")
    assert len(calls) == 1


def test_build_service_purge_actually_removes_stale_cache_files(monkeypatch, tmp_path):
    """Exercises the real purge_expired() through the real cache directory
    _build_service wires up -- not a mock -- so this also confirms the "already
    degrades, but confirm" half of the ruling: a pre-existing, expired file on
    disk is cleaned up and building the service does not raise."""
    import json

    from couchseerr import routes

    monkeypatch.chdir(tmp_path)
    cache_dir = (
        tmp_path
        / "special:"
        / "profile"
        / "addon_data"
        / "plugin.video.couchseerr"
        / "cache"
    )
    cache_dir.mkdir(parents=True)
    (cache_dir / "stale.json").write_text(json.dumps({"expires": 1, "value": "old"}))
    (cache_dir / "fresh.json").write_text(
        json.dumps({"expires": 9999999999, "value": "new"})
    )

    service = routes._build_service("plugin://plugin.video.couchseerr/")

    assert service is not None
    assert not (cache_dir / "stale.json").exists()
    assert (cache_dir / "fresh.json").exists()


# --- content type / row warnings, through dispatch with a fake service --------


def test_dispatch_uses_the_row_content_type(monkeypatch):
    from couchseerr import routes

    class Working(object):
        warnings = []

        def discover_row(self, key):
            return [make_spec("Item")]

    monkeypatch.setattr(routes, "_build_service", lambda *a, **k: Working())
    routes.dispatch(["plugin://plugin.video.couchseerr/", "12", "?mode=row&key=popular_tv"])
    assert xbmcplugin._content == [(12, "tvshows")]
    assert xbmcplugin._ended == [(12, True, False)]


def test_dispatch_search_renders_and_ends_directory_once(monkeypatch):
    from couchseerr import routes

    class Working(object):
        warnings = []

        def search_row(self, query):
            assert query == "dune"
            return [make_spec("Dune")]

    monkeypatch.setattr(routes, "_build_service", lambda *a, **k: Working())
    routes.dispatch(["plugin://plugin.video.couchseerr/", "14", "?mode=search&query=dune"])
    assert xbmcplugin._content == [(14, "videos")]
    assert len(xbmcplugin._added) == 1
    assert xbmcplugin._ended == [(14, True, False)]


def test_dispatch_logs_each_service_warning_at_warning_level(monkeypatch):
    import xbmc
    from couchseerr import routes

    class Working(object):
        warnings = ["unreadable download progress for movie/104: size=0 size_left=None status=''"]

        def discover_row(self, key):
            return []

    del xbmc._log_calls[:]
    monkeypatch.setattr(routes, "_build_service", lambda *a, **k: Working())
    routes.dispatch(["plugin://plugin.video.couchseerr/", "13", "?mode=row&key=trending"])

    warning_calls = [c for c in xbmc._log_calls if c[1] == xbmc.LOGWARNING]
    assert len(warning_calls) == 1
    assert "unreadable download progress" in warning_calls[0][0]


# --- optional view mode ------------------------------------------------------


class _ViewRow(object):
    warnings = []

    def discover_row(self, key):
        return [make_spec("Item")]


def _dispatch_row(monkeypatch, handle):
    import xbmc
    import xbmcaddon
    from couchseerr import routes

    del xbmc._builtins[:]
    del xbmc._log_calls[:]
    monkeypatch.setattr(routes, "_build_service", lambda *a, **k: _ViewRow())
    routes.dispatch(
        ["plugin://plugin.video.couchseerr/", str(handle), "?mode=row&key=trending"]
    )
    return xbmc, xbmcaddon


def test_blank_view_mode_leaves_kodis_own_choice_alone(monkeypatch):
    """The shipped default. Guessing a skin-specific id would override a view the user
    already picked, so blank must issue no builtin at all."""
    xbmc, _ = _dispatch_row(monkeypatch, 20)
    assert xbmc._builtins == []


def test_view_mode_setting_switches_the_container_view(monkeypatch):
    import xbmcaddon

    xbmcaddon.Addon().setSetting("view_mode", "55")
    try:
        xbmc, _ = _dispatch_row(monkeypatch, 21)
        assert xbmc._builtins == ["Container.SetViewMode(55)"]
    finally:
        xbmcaddon.Addon().setSetting("view_mode", "")


def test_view_mode_is_applied_after_the_directory_closes(monkeypatch):
    """SetViewMode only takes on a container Kodi has finished loading, and render owns
    the successful close, so the builtin must come after endOfDirectory."""
    import xbmcaddon
    import xbmcplugin

    xbmcaddon.Addon().setSetting("view_mode", "55")
    del xbmcplugin._ended[:]
    try:
        xbmc, _ = _dispatch_row(monkeypatch, 22)
        assert xbmcplugin._ended == [(22, True, False)]
        assert xbmc._builtins == ["Container.SetViewMode(55)"]
    finally:
        xbmcaddon.Addon().setSetting("view_mode", "")


def test_non_numeric_view_mode_is_logged_and_ignored(monkeypatch):
    """The listing itself is fine; only the view is not what was asked for. Warn, do not
    fail the row."""
    import xbmcaddon

    xbmcaddon.Addon().setSetting("view_mode", "paysage")
    try:
        xbmc, _ = _dispatch_row(monkeypatch, 23)
        assert xbmc._builtins == []
        warnings = [c for c in xbmc._log_calls if c[1] == xbmc.LOGWARNING]
        assert len(warnings) == 1
        assert "view_mode" in warnings[0][0]
    finally:
        xbmcaddon.Addon().setSetting("view_mode", "")


def test_failing_view_mode_does_not_close_twice(monkeypatch):
    """_apply_view_mode runs after render has already closed the listing, but still
    inside dispatch's try. Anything it raises would otherwise reach _fail_unexpected and
    call endOfDirectory again on a handle Kodi has finished with. The listing is already
    rendered and correct at that point, so the failure is a log line, nothing more."""
    import xbmc
    import xbmcplugin
    from couchseerr import routes

    def boom():
        raise RuntimeError("no such window")

    monkeypatch.setattr(routes, "_apply_view_mode", boom)
    del xbmcplugin._ended[:]
    xbmc, _ = _dispatch_row(monkeypatch, 24)

    assert xbmcplugin._ended == [(24, True, False)]
    errors = [c for c in xbmc._log_calls if c[1] == xbmc.LOGERROR]
    assert len(errors) == 1
    assert "no such window" in errors[0][0]


def test_row_service_always_exposes_warnings():
    """dispatch reads service.warnings directly rather than through a getattr default.
    RowService sets it in __init__ and resets it per call, so a missing attribute would
    be a real defect worth a traceback, not something production code should paper over
    to accommodate a thin test double."""
    from couchseerr.rows import RowService

    service = RowService(
        client=None, cache=None, base_url="", image_base="", language="",
        today_provider=None,
    )
    assert service.warnings == []


# --- mode=item / request / play / settings / trailer -------------------------


def test_item_mode_renders_the_detail_listing(monkeypatch):
    """v1 answered "Unknown mode: item". Every tile click lands here now."""
    import xbmcplugin
    from couchseerr import routes
    from couchseerr.models import DiscoverItem
    from couchseerr.state import TileState

    item = DiscoverItem(tmdb_id=693134, media_type="movie", title="Dune",
                        overview="Sand.", poster_path=None, backdrop_path=None,
                        release_date=None, media=None)

    class Service(object):
        warnings = []

        def detail(self, media_type, tmdb_id):
            return item, TileState.ACTIONABLE, {"imdbId": "tt15239678", "relatedVideos": []}

    monkeypatch.setattr(routes, "_build_service", lambda *a, **k: Service())
    monkeypatch.setattr(routes, "_resolved_default", lambda media_type: None)
    routes.dispatch(["plugin://plugin.video.couchseerr/", "30",
                     "?mode=item&tmdb_id=693134&media_type=movie"])

    assert xbmcplugin._ended == [(30, True, False)]
    # Which entries, not just "some entry": a truthiness check on _added passes for one
    # entry, for the wrong entry, for any entry at all. An actionable title with no
    # default profile configured can only offer the way to configure one.
    labels = [li.getLabel() for _handle, _url, li, _folder in xbmcplugin._added]
    assert labels == [routes._labels()["configure"]]
    assert "mode=settings" in xbmcplugin._added[0][1]


def test_item_mode_offers_request_when_default_configured(monkeypatch):
    import xbmcplugin
    from couchseerr import routes
    from couchseerr.models import DiscoverItem
    from couchseerr.state import TileState

    item = DiscoverItem(tmdb_id=693134, media_type="movie", title="Dune",
                        overview="Sand.", poster_path=None, backdrop_path=None,
                        release_date=None, media=None)

    class Service(object):
        warnings = []

        def detail(self, media_type, tmdb_id):
            return item, TileState.ACTIONABLE, {"imdbId": "tt15239678", "relatedVideos": []}

    monkeypatch.setattr(routes, "_build_service", lambda *a, **k: Service())
    monkeypatch.setattr(routes, "_resolved_default", lambda media_type: _a_settings())
    routes.dispatch(["plugin://plugin.video.couchseerr/", "45",
                     "?mode=item&tmdb_id=693134&media_type=movie"])

    labels = [li.getLabel() for _handle, _url, li, _folder in xbmcplugin._added]
    assert labels == [routes._labels()["request"]]
    assert "mode=request" in xbmcplugin._added[0][1]
    assert xbmcplugin._ended == [(45, True, False)]


def test_request_mode_reports_success_and_refreshes(monkeypatch):
    import xbmc
    import xbmcgui
    from couchseerr import routes

    sent = {}
    monkeypatch.setattr(routes, "_build_service", lambda *a, **k: _DetailService())
    monkeypatch.setattr(routes, "_resolved_default", lambda media_type: _a_settings())
    monkeypatch.setattr(routes, "send_request",
                        lambda client, settings, mt, tid, state, seasons=None: sent.setdefault(
                            "body", (settings, mt, tid)) or {"id": 1})
    del xbmc._builtins[:]

    routes.dispatch(["plugin://plugin.video.couchseerr/", "31",
                     "?mode=request&tmdb_id=693134&media_type=movie"])

    assert sent["body"] == (_a_settings(), "movie", 693134)
    # An action route renders no listing of its own: it must close the directory
    # exactly once, unsuccessfully, whatever the outcome of the request itself.
    assert xbmcplugin._ended == [(31, False, False)]
    assert xbmcgui._notifications
    # Not just "a notification fired": a path that notified "Not requested: ..." would
    # also satisfy that. The message must actually say what was requested.
    assert "Dune" in xbmcgui._notifications[-1][1]
    assert any("Container.Refresh" in b for b in xbmc._builtins)


def test_a_request_drops_the_cached_detail_then_refreshes(monkeypatch):
    """The refresh re-enters mode=item, which re-reads the detail cache. That entry
    lives for TTL_DISCOVER (fifteen minutes) and still says "not requested", so without
    the invalidation the refreshed listing shows the pre-request state, still offers
    Request, and still passes send_request's state guard -- a duplicate request, around
    the guard that exists to prevent duplicates. Order is asserted, not just the call:
    invalidating after the refresh would refresh from the stale payload."""
    import xbmc
    from couchseerr import routes

    service = _DetailService()
    order = []
    monkeypatch.setattr(routes, "_build_service", lambda *a, **k: service)
    monkeypatch.setattr(routes, "_resolved_default", lambda media_type: _a_settings())
    monkeypatch.setattr(routes, "send_request", lambda *a, **k: {"id": 1})
    monkeypatch.setattr(
        service, "invalidate_detail",
        lambda mt, tid: order.append(("invalidate", mt, tid)),
    )
    monkeypatch.setattr(routes.jsonrpc, "refresh_container",
                        lambda: order.append(("refresh",)))

    routes.dispatch(["plugin://plugin.video.couchseerr/", "38",
                     "?mode=request&tmdb_id=693134&media_type=movie"])

    assert order == [("invalidate", "movie", 693134), ("refresh",)]
    assert xbmcplugin._ended == [(38, False, False)]


def test_a_refused_request_leaves_the_cached_detail_alone(monkeypatch):
    """Nothing changed at seerr, so the cached payload is still accurate; dropping it
    would cost a refetch on the way back for no gain."""
    from couchseerr import routes
    from couchseerr.errors import RequestRefused

    service = _DetailService()

    def refuse(*args, **kwargs):
        raise RequestRefused("movie/1 is already downloading")

    monkeypatch.setattr(routes, "_build_service", lambda *a, **k: service)
    monkeypatch.setattr(routes, "_resolved_default", lambda media_type: _a_settings())
    monkeypatch.setattr(routes, "send_request", refuse)

    routes.dispatch(["plugin://plugin.video.couchseerr/", "39",
                     "?mode=request&tmdb_id=693134&media_type=movie"])

    assert service.invalidated == []


def test_request_mode_reports_a_refusal_not_success(monkeypatch):
    import xbmcgui
    import xbmcplugin
    from couchseerr import routes
    from couchseerr.errors import RequestRefused

    def refuse(*args, **kwargs):
        raise RequestRefused("movie/1 is already downloading")

    monkeypatch.setattr(routes, "_build_service", lambda *a, **k: _DetailService())
    monkeypatch.setattr(routes, "_resolved_default", lambda media_type: _a_settings())
    monkeypatch.setattr(routes, "send_request", refuse)
    del xbmcgui._notifications[:]

    routes.dispatch(["plugin://plugin.video.couchseerr/", "32",
                     "?mode=request&tmdb_id=1&media_type=movie"])

    assert xbmcplugin._ended == [(32, False, False)]
    assert xbmcgui._notifications
    assert "downloading" in xbmcgui._notifications[-1][1]


def test_request_mode_reports_a_seerr_rejection_not_success(monkeypatch):
    """The pre-flight RequestRefused is not the only way a request can fail: seerr
    itself can refuse once contacted (quota, a duplicate it does catch, ...). Reporting
    "Requested" over that rejection is the exact failure this project exists to prevent,
    so seerr's own message must reach the user, not a generic "something went wrong"."""
    import xbmcgui
    import xbmcplugin
    from couchseerr import routes
    from couchseerr.errors import SeerrRequestError

    def reject(*args, **kwargs):
        raise SeerrRequestError(409, "Request already exists")

    monkeypatch.setattr(routes, "_build_service", lambda *a, **k: _DetailService())
    monkeypatch.setattr(routes, "_resolved_default", lambda media_type: _a_settings())
    monkeypatch.setattr(routes, "send_request", reject)
    del xbmcgui._notifications[:]

    routes.dispatch(["plugin://plugin.video.couchseerr/", "35",
                     "?mode=request&tmdb_id=1&media_type=movie"])

    assert xbmcplugin._ended == [(35, False, False)]
    assert xbmcgui._notifications
    assert "Request already exists" in xbmcgui._notifications[-1][1]


# --- mode=request's three-way resolution -- task 18 ---------------------------


def test_unset_default_notifies_and_never_contacts_seerr(monkeypatch):
    """No server_id/profile_id, no pick=1, and resolve() returns None: sending anyway
    would hand seerr a body with neither key at all, which it accepts and answers as a
    success. Nothing about seerr may be touched here, not even a GET."""
    import xbmcgui
    import xbmcplugin
    from couchseerr import routes

    class Untouchable(object):
        client = None

        def detail(self, media_type, tmdb_id):
            raise AssertionError("must not contact seerr when no default is configured")

    def explode(*args, **kwargs):
        raise AssertionError("send_request must not run when no default is configured")

    monkeypatch.setattr(routes, "_build_service", lambda *a, **k: Untouchable())
    monkeypatch.setattr(routes, "_resolved_default", lambda media_type: None)
    monkeypatch.setattr(routes, "send_request", explode)
    del xbmcgui._notifications[:]

    routes.dispatch(["plugin://plugin.video.couchseerr/", "62",
                     "?mode=request&tmdb_id=1&media_type=movie"])

    assert xbmcplugin._ended == [(62, False, False)]
    assert xbmcgui._notifications
    assert xbmcgui._notifications[-1][1] == routes._labels()["no_profile"]


def test_pick_opens_the_cross_server_picker(monkeypatch):
    """pick=1 is the context menu's "Demander avec...": it fetches every server's every
    profile and asks, ignoring whatever the config names."""
    from couchseerr import routes

    chosen = {"serverId": 9, "profileId": 77, "is4k": True, "label": "Radarr 4K - Remux"}
    sent = {}

    monkeypatch.setattr(routes, "_build_service", lambda *a, **k: _DetailService())
    monkeypatch.setattr(routes.dialogs, "choices", lambda client, media_type: [chosen])
    monkeypatch.setattr(routes.dialogs, "pick_profile", lambda entries, labels: chosen)

    def explode(media_type):
        raise AssertionError("the config must not be consulted when pick=1")

    monkeypatch.setattr(routes, "_resolved_default", explode)
    monkeypatch.setattr(routes, "send_request",
                        lambda client, settings, mt, tid, state, seasons=None: sent.setdefault(
                            "settings", settings) or {"id": 1})

    routes.dispatch(["plugin://plugin.video.couchseerr/", "63",
                     "?mode=request&tmdb_id=693134&media_type=movie&pick=1"])

    assert sent["settings"] == chosen


def test_cancelling_the_picker_ends_directory_unsent(monkeypatch):
    from couchseerr import routes

    def explode(*args, **kwargs):
        raise AssertionError("send_request must not run when the picker is cancelled")

    monkeypatch.setattr(routes, "_build_service", lambda *a, **k: _DetailService())
    monkeypatch.setattr(routes.dialogs, "choices",
                        lambda client, media_type: [{"serverId": 0, "profileId": 21,
                                                     "is4k": False, "label": "Radarr - HD"}])
    monkeypatch.setattr(routes.dialogs, "pick_profile", lambda entries, labels: None)
    monkeypatch.setattr(routes, "send_request", explode)

    routes.dispatch(["plugin://plugin.video.couchseerr/", "64",
                     "?mode=request&tmdb_id=693134&media_type=movie&pick=1"])

    assert xbmcplugin._ended == [(64, False, False)]


def test_pick_with_no_servers_notifies_and_does_not_send(monkeypatch):
    import xbmcgui
    from couchseerr import routes

    def explode(*args, **kwargs):
        raise AssertionError("send_request must not run when seerr has no servers")

    monkeypatch.setattr(routes, "_build_service", lambda *a, **k: _DetailService())
    monkeypatch.setattr(routes.dialogs, "choices", lambda client, media_type: [])
    monkeypatch.setattr(routes, "send_request", explode)
    del xbmcgui._notifications[:]

    routes.dispatch(["plugin://plugin.video.couchseerr/", "65",
                     "?mode=request&tmdb_id=693134&media_type=movie&pick=1"])

    assert xbmcgui._notifications
    assert xbmcgui._notifications[-1][1] == routes._labels()["no_server_movie"]


def test_explicit_ids_bypass_both_the_picker_and_the_config(monkeypatch):
    """A caller that already names server_id/profile_id (a future custom window) skips
    both the cross-server picker and request_config.resolve() entirely."""
    from couchseerr import routes

    sent = {}

    def explode_picker(client, media_type):
        raise AssertionError("the picker must not be consulted with explicit ids")

    def explode_config(media_type):
        raise AssertionError("the config must not be consulted with explicit ids")

    monkeypatch.setattr(routes, "_build_service", lambda *a, **k: _DetailService())
    monkeypatch.setattr(routes.dialogs, "choices", explode_picker)
    monkeypatch.setattr(routes, "_resolved_default", explode_config)
    monkeypatch.setattr(routes, "send_request",
                        lambda client, settings, mt, tid, state, seasons=None: sent.setdefault(
                            "settings", settings) or {"id": 1})

    routes.dispatch(["plugin://plugin.video.couchseerr/", "66",
                     "?mode=request&tmdb_id=693134&media_type=movie"
                     "&server_id=5&profile_id=99&is4k=1"])

    assert sent["settings"] == {"serverId": 5, "profileId": 99, "is4k": True}


def test_explicit_server_id_alone_still_bypasses_resolution(monkeypatch):
    """Either id present is enough to count as "explicit": a caller naming only a
    server (accepting the server's own default profile) must not fall through to the
    config either."""
    from couchseerr import routes

    sent = {}

    def explode_config(media_type):
        raise AssertionError("the config must not be consulted with an explicit server_id")

    monkeypatch.setattr(routes, "_build_service", lambda *a, **k: _DetailService())
    monkeypatch.setattr(routes, "_resolved_default", explode_config)
    monkeypatch.setattr(routes, "send_request",
                        lambda client, settings, mt, tid, state, seasons=None: sent.setdefault(
                            "settings", settings) or {"id": 1})

    routes.dispatch(["plugin://plugin.video.couchseerr/", "67",
                     "?mode=request&tmdb_id=693134&media_type=movie&server_id=5"])

    assert sent["settings"] == {"serverId": 5, "profileId": None, "is4k": False}


def test_settings_mode_opens_settings_and_ends_directory(monkeypatch):
    """mode=settings is the detail listing's "Configurer" entry when no default profile
    is configured: it opens the addon's own settings dialog and renders no listing of
    its own."""
    import xbmc
    import xbmcplugin
    from couchseerr import routes

    del xbmc._builtins[:]

    routes.dispatch(["plugin://plugin.video.couchseerr/", "68", "?mode=settings"])

    assert any(
        b == "Addon.OpenSettings(plugin.video.couchseerr)" for b in xbmc._builtins
    )
    assert xbmcplugin._ended == [(68, False, False)]


# --- fix round 1 ---------------------------------------------------------------


def test_empty_explicit_ids_fall_through_to_configured_default(monkeypatch):
    """A params dict carrying literally server_id="" and profile_id="" -- what a
    template or a skin building the path from empty properties produces -- is not "the
    caller supplied ids": it is the same as absent. Treating an empty string as
    explicit sends seerr a body with neither id and reports success for a request that
    was never really configured.

    Called against _do_request directly with a hand-built params dict, not through a
    literal "?server_id=&profile_id=" URL and dispatch(): parse_args' own parse_qsl
    already drops a blank query value before params exists at all
    (keep_blank_values=False, the default), so a full-dispatch version of this test
    cannot tell the fixed condition apart from the buggy one -- both see server_id
    simply absent. The condition inside _resolve_request_settings must be correct on
    its own terms, for any caller that hands it a dict shaped this way, not merely
    lucky because of what parse_args happens to do today.
    """
    from couchseerr import routes

    sent = {}
    default = _a_settings()

    def explode_picker(client, media_type):
        raise AssertionError("the picker must not run when ids are merely empty")

    monkeypatch.setattr(routes, "_build_service", lambda *a, **k: _DetailService())
    monkeypatch.setattr(routes.dialogs, "choices", explode_picker)
    monkeypatch.setattr(routes, "_resolved_default", lambda media_type: default)
    monkeypatch.setattr(routes, "send_request",
                        lambda client, settings, mt, tid, state, seasons=None: sent.setdefault(
                            "settings", settings) or {"id": 1})

    routes._do_request(99, "plugin://plugin.video.couchseerr/", {
        "tmdb_id": "693134", "media_type": "movie",
        "server_id": "", "profile_id": "",
    })

    assert sent["settings"] == default


def test_build_service_passes_labels_to_the_row_service(monkeypatch, tmp_path):
    """Dropping this argument fails only on the device, and invisibly: a context menu
    with entries whose text is blank, still clickable, impossible to read."""
    from couchseerr import routes

    monkeypatch.chdir(tmp_path)
    service = routes._build_service("plugin://plugin.video.couchseerr/")

    assert service.labels == routes._labels()
    assert service.labels["request"]
    assert service.labels["request_with"]


def test_corrupt_request_config_degrades_the_detail_listing(monkeypatch, tmp_path):
    """The old preset path logged a corrupt presets.json and fell back to offering
    configuration; request_config.json must cost the same, not take the whole listing
    down with a hard failure -- Play/Trailer/whatever else the title has must still
    render."""
    import xbmc
    from couchseerr import routes
    from couchseerr.models import DiscoverItem
    from couchseerr.state import TileState

    monkeypatch.chdir(tmp_path)
    _prepare_profile_dir(tmp_path)
    _request_config_file(tmp_path).write_text("{not json")

    item = DiscoverItem(tmdb_id=1, media_type="movie", title="Dune",
                        overview="", poster_path=None, backdrop_path=None,
                        release_date=None, media=None)

    class Service(object):
        warnings = []

        def detail(self, media_type, tmdb_id):
            return item, TileState.ACTIONABLE, {"relatedVideos": []}

    monkeypatch.setattr(routes, "_build_service", lambda *a, **k: Service())
    del xbmc._log_calls[:]

    routes.dispatch(["plugin://plugin.video.couchseerr/", "73",
                     "?mode=item&tmdb_id=1&media_type=movie"])

    assert xbmcplugin._ended == [(73, True, False)]
    labels = [li.getLabel() for _h, _u, li, _f in xbmcplugin._added]
    assert labels == [routes._labels()["configure"]]
    assert any(level == xbmc.LOGERROR for _msg, level in xbmc._log_calls)


def test_corrupt_request_config_falls_through_on_request_too(monkeypatch, tmp_path):
    """The same degrade must apply to _do_request's own use of the config, not only to
    the detail listing's: a corrupt file notifies "no default configured" instead of
    raising through dispatch's generic failure path."""
    import xbmcgui
    from couchseerr import routes

    monkeypatch.chdir(tmp_path)
    _prepare_profile_dir(tmp_path)
    _request_config_file(tmp_path).write_text("{not json")

    monkeypatch.setattr(routes, "_build_service", lambda *a, **k: _DetailService())
    del xbmcgui._notifications[:]

    routes.dispatch(["plugin://plugin.video.couchseerr/", "74",
                     "?mode=request&tmdb_id=1&media_type=movie"])

    assert xbmcplugin._ended == [(74, False, False)]
    assert xbmcgui._notifications
    assert xbmcgui._notifications[-1][1] == routes._labels()["no_profile"]


def test_play_mode_resolves_the_library_id_and_opens_the_player(monkeypatch):
    import xbmc
    import xbmcplugin
    from couchseerr import routes

    played = {}
    xbmc._jsonrpc_responses["VideoLibrary.GetMovies"] = {
        "movies": [{"movieid": 12, "label": "Dune", "year": 2024,
                    "uniqueid": {"imdb": "tt15239678"}}]
    }
    monkeypatch.setattr(routes, "_build_service", lambda *a, **k: _DetailService())
    monkeypatch.setattr(routes.jsonrpc, "play_library_item",
                        lambda mt, lid: played.setdefault("id", (mt, lid)))

    routes.dispatch(["plugin://plugin.video.couchseerr/", "33",
                     "?mode=play&tmdb_id=693134&media_type=movie"])

    assert played["id"] == ("movie", 12)
    assert xbmcplugin._ended == [(33, False, False)]


def test_play_mode_says_so_when_the_title_is_not_in_the_library(monkeypatch):
    import xbmc
    import xbmcgui
    import xbmcplugin
    from couchseerr import routes

    xbmc._jsonrpc_responses["VideoLibrary.GetMovies"] = {"movies": []}
    monkeypatch.setattr(routes, "_build_service", lambda *a, **k: _DetailService())
    del xbmcgui._notifications[:]

    routes.dispatch(["plugin://plugin.video.couchseerr/", "34",
                     "?mode=play&tmdb_id=693134&media_type=movie"])

    assert xbmcgui._notifications
    assert xbmcplugin._ended == [(34, False, False)]


# --- mode=profile -- task 17's profile picker ---------------------------------


class _ProfileClient(object):
    """A client whose server_detail() answer depends on which server was asked, so a
    test can tell a real 4K server's profiles apart from an ordinary one's."""

    def __init__(self, servers, details):
        self._servers = servers
        self._details = details

    def servers(self, media_type):
        return self._servers.get(media_type, [])

    def server_detail(self, media_type, server_id):
        return self._details[(media_type, server_id)]


class _ProfileService(object):
    warnings = []

    def __init__(self, client):
        self.client = client


def _request_config_file(tmp_path):
    return (
        tmp_path / "special:" / "profile" / "addon_data"
        / "plugin.video.couchseerr" / "request_config.json"
    )


def _prepare_profile_dir(tmp_path):
    """save_config(), like save_presets(), does not create its own directory -- on a
    real device Kodi has already created addon_data/<id>/ by the time any setting can
    be touched. Tests must recreate that precondition explicitly."""
    _request_config_file(tmp_path).parent.mkdir(parents=True)


def test_profile_mode_cancel_writes_neither_config_nor_setting(monkeypatch, tmp_path):
    """Cancelling the picker must leave request_config.json absent and the settings
    row's mirrored label untouched -- a half-applied change is worse than none, because
    the row would then display a profile the JSON does not actually hold."""
    import xbmcaddon
    import xbmcplugin
    from couchseerr import routes

    monkeypatch.chdir(tmp_path)
    client = _ProfileClient(
        {"movie": [{"id": 0, "name": "Radarr"}]},
        {("movie", 0): {"profiles": [{"id": 21, "name": "HD-1080p"}]}},
    )
    monkeypatch.setattr(routes, "_build_service", lambda *a, **k: _ProfileService(client))
    xbmcaddon.Addon().setSetting("profile_movie", "")
    xbmcgui._select_answers.append(-1)  # cancel the picker

    routes.dispatch(["plugin://plugin.video.couchseerr/", "50", "?mode=profile&slot=movie"])

    assert not _request_config_file(tmp_path).exists()
    assert xbmcaddon.Addon().getSetting("profile_movie") == ""
    assert xbmcplugin._ended == [(50, False, False)]


def test_profile_mode_choice_writes_config_and_setting(monkeypatch, tmp_path):
    import json

    import xbmcaddon
    import xbmcplugin
    from couchseerr import routes

    monkeypatch.chdir(tmp_path)
    client = _ProfileClient(
        {"movie": [{"id": 0, "name": "Radarr"}]},
        {("movie", 0): {"profiles": [{"id": 21, "name": "HD-1080p"}]}},
    )
    monkeypatch.setattr(routes, "_build_service", lambda *a, **k: _ProfileService(client))
    _prepare_profile_dir(tmp_path)
    xbmcgui._select_answers.append(0)  # the only entry: Radarr - HD-1080p

    routes.dispatch(["plugin://plugin.video.couchseerr/", "51", "?mode=profile&slot=movie"])

    stored = json.loads(_request_config_file(tmp_path).read_text())
    assert stored["movie"] == {"serverId": 0, "profileId": 21, "label": "Radarr - HD-1080p"}
    assert xbmcaddon.Addon().getSetting("profile_movie") == "Radarr - HD-1080p"
    assert xbmcplugin._ended == [(51, False, False)]
    assert xbmcgui._notifications


def test_profile_mode_writes_into_the_right_slot_by_media_type(monkeypatch, tmp_path):
    """tv and tv_4k are Sonarr; picking tv_4k must not touch the movie slots and must
    derive its media type (tv) from the slot name, not from a passed-in parameter."""
    import json

    import xbmcaddon
    from couchseerr import routes

    monkeypatch.chdir(tmp_path)
    client = _ProfileClient(
        {"tv": [{"id": 2, "name": "Sonarr 4K", "is4k": True}]},
        {("tv", 2): {"profiles": [{"id": 9, "name": "Ultra-HD"}]}},
    )
    monkeypatch.setattr(routes, "_build_service", lambda *a, **k: _ProfileService(client))
    _prepare_profile_dir(tmp_path)
    xbmcgui._select_answers.append(0)

    routes.dispatch(["plugin://plugin.video.couchseerr/", "52", "?mode=profile&slot=tv_4k"])

    stored = json.loads(_request_config_file(tmp_path).read_text())
    assert stored["tv_4k"] == {"serverId": 2, "profileId": 9, "label": "Sonarr 4K - Ultra-HD"}
    assert "movie" not in stored
    assert xbmcaddon.Addon().getSetting("profile_tv_4k") == "Sonarr 4K - Ultra-HD"


def test_profile_mode_sets_has_4k_flag_when_a_server_is_4k(monkeypatch, tmp_path):
    """has_4k_movie / has_4k_tv are written only here, from whichever server list this
    fetch just pulled -- this is what un-hides the 4K settings rows."""
    import xbmcaddon
    from couchseerr import routes

    monkeypatch.chdir(tmp_path)
    client = _ProfileClient(
        {"movie": [{"id": 0, "name": "Radarr"}, {"id": 1, "name": "Radarr 4K", "is4k": True}]},
        {
            ("movie", 0): {"profiles": [{"id": 21, "name": "HD-1080p"}]},
            ("movie", 1): {"profiles": [{"id": 7, "name": "Ultra-HD"}]},
        },
    )
    monkeypatch.setattr(routes, "_build_service", lambda *a, **k: _ProfileService(client))
    _prepare_profile_dir(tmp_path)
    xbmcaddon.Addon().setSetting("has_4k_movie", "false")
    xbmcgui._select_answers.append(0)

    routes.dispatch(["plugin://plugin.video.couchseerr/", "53", "?mode=profile&slot=movie"])

    assert xbmcaddon.Addon().getSetting("has_4k_movie") == "true"


def test_profile_mode_clears_has_4k_flag_when_no_server_is_4k(monkeypatch, tmp_path):
    import xbmcaddon
    from couchseerr import routes

    monkeypatch.chdir(tmp_path)
    client = _ProfileClient(
        {"movie": [{"id": 0, "name": "Radarr"}]},
        {("movie", 0): {"profiles": [{"id": 21, "name": "HD-1080p"}]}},
    )
    monkeypatch.setattr(routes, "_build_service", lambda *a, **k: _ProfileService(client))
    _prepare_profile_dir(tmp_path)
    xbmcaddon.Addon().setSetting("has_4k_movie", "true")
    xbmcgui._select_answers.append(0)

    routes.dispatch(["plugin://plugin.video.couchseerr/", "54", "?mode=profile&slot=movie"])

    assert xbmcaddon.Addon().getSetting("has_4k_movie") == "false"


def test_profile_mode_cancel_writes_flags_but_not_choice(monkeypatch, tmp_path):
    """The rule the brief's fix round pins down: has_4k_movie/has_4k_tv follow the
    server-list fetch regardless of whether the user finishes the pick, but the JSON
    slot and its mirrored settings label are conditioned on an actual choice and stay
    untouched on cancel. A fix that moved the flag write inside the "choice made"
    branch, or one that let cancel write the JSON too, both pass every other test in
    this file -- only this one exercises the combination that tells the two apart."""
    import xbmcaddon
    import xbmcplugin
    from couchseerr import routes

    monkeypatch.chdir(tmp_path)
    client = _ProfileClient(
        {"movie": [{"id": 0, "name": "Radarr"}, {"id": 1, "name": "Radarr 4K", "is4k": True}]},
        {
            ("movie", 0): {"profiles": [{"id": 21, "name": "HD-1080p"}]},
            ("movie", 1): {"profiles": [{"id": 7, "name": "Ultra-HD"}]},
        },
    )
    monkeypatch.setattr(routes, "_build_service", lambda *a, **k: _ProfileService(client))
    xbmcaddon.Addon().setSetting("has_4k_movie", "false")
    xbmcaddon.Addon().setSetting("profile_movie", "")
    xbmcgui._select_answers.append(-1)  # cancel

    routes.dispatch(["plugin://plugin.video.couchseerr/", "60", "?mode=profile&slot=movie"])

    assert xbmcaddon.Addon().getSetting("has_4k_movie") == "true"
    assert not _request_config_file(tmp_path).exists()
    assert xbmcaddon.Addon().getSetting("profile_movie") == ""
    assert xbmcplugin._ended == [(60, False, False)]


def test_profile_mode_unknown_slot_notifies_and_writes_nothing(monkeypatch, tmp_path):
    """An unrecognised slot= (a typo'd URL, a stale settings.xml) must not crash or
    hang -- it notifies, writes nothing, and still closes the directory exactly once,
    the same as any other unrecognised input this route can be handed."""
    import xbmcplugin
    from couchseerr import routes

    monkeypatch.chdir(tmp_path)
    del xbmcgui._notifications[:]

    routes.dispatch(["plugin://plugin.video.couchseerr/", "61", "?mode=profile&slot=bogus"])

    assert xbmcgui._notifications
    assert not _request_config_file(tmp_path).exists()
    assert xbmcplugin._ended == [(61, False, False)]


def test_profile_mode_no_servers_notifies_and_writes_nothing(monkeypatch, tmp_path):
    """seerr has no Radarr/Sonarr configured for this media type -- that is something
    the user must fix in seerr, not here, so nothing is written."""
    import xbmcaddon
    import xbmcplugin
    from couchseerr import routes

    monkeypatch.chdir(tmp_path)
    client = _ProfileClient({"movie": []}, {})
    monkeypatch.setattr(routes, "_build_service", lambda *a, **k: _ProfileService(client))
    xbmcaddon.Addon().setSetting("profile_movie", "")
    del xbmcgui._notifications[:]

    routes.dispatch(["plugin://plugin.video.couchseerr/", "55", "?mode=profile&slot=movie"])

    assert not _request_config_file(tmp_path).exists()
    assert xbmcaddon.Addon().getSetting("profile_movie") == ""
    assert xbmcgui._notifications
    assert xbmcplugin._ended == [(55, False, False)]


def test_profile_mode_seerr_failure_reaches_the_user(monkeypatch, tmp_path):
    """client.servers() failing must surface as a notification through the same typed-
    error path every other route uses, never as a picker that silently shows nothing."""
    import xbmcplugin
    from couchseerr import routes
    from couchseerr.errors import SeerrUnavailable

    monkeypatch.chdir(tmp_path)

    class Failing(object):
        client = None

        def servers(self, media_type):
            raise SeerrUnavailable("down")

    class FailingService(object):
        warnings = []
        client = Failing()

    monkeypatch.setattr(routes, "_build_service", lambda *a, **k: FailingService())
    del xbmcgui._notifications[:]

    routes.dispatch(["plugin://plugin.video.couchseerr/", "56", "?mode=profile&slot=movie"])

    assert xbmcplugin._ended == [(56, False, False)]
    assert xbmcgui._notifications
    assert not _request_config_file(tmp_path).exists()


def _settings_dialog_open(monkeypatch):
    """Put the stub in the state this route is actually reached from: the addon's own
    settings dialog open, since its row is the only thing that runs mode=profile."""
    import xbmc

    monkeypatch.setattr(xbmc, "_cond_visibility", {"Window.IsActive(addonsettings)"})


def test_profile_closes_dialog_first(monkeypatch, tmp_path):
    """Kodi's addon-settings dialog writes its own copy of every setting back over the
    store when it closes, so a setSetting made while it is open is discarded the moment
    the user leaves -- measured on the device: request_config.json held the choice, the
    settings row was blank. The close must therefore land *before* the write, and the
    reopen after it, or the label the user sees is a lie about what was saved."""
    import xbmc
    import xbmcaddon
    from couchseerr import routes

    monkeypatch.chdir(tmp_path)
    client = _ProfileClient(
        {"movie": [{"id": 0, "name": "Radarr"}]},
        {("movie", 0): {"profiles": [{"id": 21, "name": "HD-1080p"}]}},
    )
    monkeypatch.setattr(routes, "_build_service", lambda *a, **k: _ProfileService(client))
    _prepare_profile_dir(tmp_path)
    _settings_dialog_open(monkeypatch)
    xbmcgui._select_answers.append(0)
    del xbmc._builtins[:]

    # One ordered log of both kinds of event: asserting on the two lists separately
    # could not tell "closed, then wrote" from "wrote, then closed", which is the whole
    # of the bug.
    events = []
    monkeypatch.setattr(
        xbmc, "executebuiltin", lambda fn, wait=False: events.append(("builtin", fn))
    )
    monkeypatch.setattr(
        xbmcaddon.Addon,
        "setSetting",
        lambda self, key, value: events.append(("set", key, value)),
    )

    routes.dispatch(["plugin://plugin.video.couchseerr/", "57", "?mode=profile&slot=movie"])

    kinds = [event[0] for event in events]
    assert events[0] == ("builtin", "Dialog.Close(addonsettings)")
    assert events[-1] == ("builtin", "Addon.OpenSettings(plugin.video.couchseerr)")
    assert ("set", "profile_movie", "Radarr - HD-1080p") in events
    # Every write, the 4K flag included, sits between the close and the reopen.
    assert kinds.count("builtin") == 2


def test_profile_no_dialog_no_close(monkeypatch, tmp_path):
    """The same route reached with the dialog closed (a skin shortcut, a test harness)
    must not open a settings dialog the user never asked for."""
    import xbmc
    from couchseerr import routes

    monkeypatch.chdir(tmp_path)
    client = _ProfileClient(
        {"movie": [{"id": 0, "name": "Radarr"}]},
        {("movie", 0): {"profiles": [{"id": 21, "name": "HD-1080p"}]}},
    )
    monkeypatch.setattr(routes, "_build_service", lambda *a, **k: _ProfileService(client))
    _prepare_profile_dir(tmp_path)
    monkeypatch.setattr(xbmc, "_cond_visibility", set())
    xbmcgui._select_answers.append(0)
    del xbmc._builtins[:]

    routes.dispatch(["plugin://plugin.video.couchseerr/", "58", "?mode=profile&slot=movie"])

    assert xbmc._builtins == []


def test_profile_reopens_on_each_exit(monkeypatch, tmp_path):
    """Cancel and a seerr failure both leave the dialog closed unless the reopen is in a
    finally: the user asked for a picker, not for their settings to disappear."""
    import xbmc
    from couchseerr import routes
    from couchseerr.errors import SeerrUnavailable

    monkeypatch.chdir(tmp_path)
    _prepare_profile_dir(tmp_path)
    reopen = "Addon.OpenSettings(plugin.video.couchseerr)"

    client = _ProfileClient(
        {"movie": [{"id": 0, "name": "Radarr"}]},
        {("movie", 0): {"profiles": [{"id": 21, "name": "HD-1080p"}]}},
    )
    monkeypatch.setattr(routes, "_build_service", lambda *a, **k: _ProfileService(client))
    _settings_dialog_open(monkeypatch)
    xbmcgui._select_answers.append(-1)  # cancel
    del xbmc._builtins[:]
    routes.dispatch(["plugin://plugin.video.couchseerr/", "59", "?mode=profile&slot=movie"])
    assert xbmc._builtins[-1] == reopen

    class Failing(object):
        client = None

        def servers(self, media_type):
            raise SeerrUnavailable("down")

    class FailingService(object):
        warnings = []
        client = Failing()

    monkeypatch.setattr(routes, "_build_service", lambda *a, **k: FailingService())
    del xbmc._builtins[:]
    routes.dispatch(["plugin://plugin.video.couchseerr/", "62", "?mode=profile&slot=movie"])
    assert xbmc._builtins[-1] == reopen


def test_profile_repairs_a_corrupt_config(monkeypatch, tmp_path):
    """The picker is the only thing that can repair request_config.json, so a corrupt
    file must not stop it running -- mode=item offers "Configure default profile"
    precisely when the config cannot be read, and that entry lands here. Nothing
    recoverable is lost: load_config only raises when the file will not parse at all."""
    import json

    import xbmc
    import xbmcaddon
    from couchseerr import routes

    monkeypatch.chdir(tmp_path)
    _prepare_profile_dir(tmp_path)
    _request_config_file(tmp_path).write_text("{not json")
    client = _ProfileClient(
        {"movie": [{"id": 0, "name": "Radarr"}]},
        {("movie", 0): {"profiles": [{"id": 21, "name": "HD-1080p"}]}},
    )
    monkeypatch.setattr(routes, "_build_service", lambda *a, **k: _ProfileService(client))
    xbmcgui._select_answers.append(0)
    del xbmc._log_calls[:]

    routes.dispatch(["plugin://plugin.video.couchseerr/", "64", "?mode=profile&slot=movie"])

    stored = json.loads(_request_config_file(tmp_path).read_text())
    assert stored == {
        "movie": {"serverId": 0, "profileId": 21, "label": "Radarr - HD-1080p"}
    }
    assert xbmcaddon.Addon().getSetting("profile_movie") == "Radarr - HD-1080p"
    # Reported, not silently swallowed: the file really was broken.
    assert any(level == xbmc.LOGERROR for _msg, level in xbmc._log_calls)


def test_profile_bad_slot_keeps_dialog(monkeypatch, tmp_path):
    """The slot guard rejects before anything is written, so there is nothing to protect
    the write from -- closing the dialog there would throw away the user's place in it
    for no reason at all."""
    import xbmc
    from couchseerr import routes

    monkeypatch.chdir(tmp_path)
    _settings_dialog_open(monkeypatch)
    del xbmc._builtins[:]

    routes.dispatch(["plugin://plugin.video.couchseerr/", "63", "?mode=profile&slot=nope"])

    assert xbmc._builtins == []


def test_trailer_mode_plays_and_ends_the_directory_exactly_once(monkeypatch):
    import xbmc
    import xbmcplugin
    from couchseerr import routes

    del xbmc._builtins[:]

    routes.dispatch(["plugin://plugin.video.couchseerr/", "37",
                     "?mode=trailer&youtube_id=abc123"])

    assert any("abc123" in b for b in xbmc._builtins)
    assert xbmcplugin._ended == [(37, False, False)]


# --- the pure helpers behind the detail listing -------------------------------
# _status_line, _trailer_key and _in_library decide what mode=item renders, and each
# was reachable only through a full dispatch until now.


def _labels():
    from couchseerr import routes

    return routes._labels()


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
    from couchseerr import routes
    from couchseerr.state import TileState

    line = routes._status_line(
        TileState.DOWNLOADING, _downloading_item(1000, 380), _labels()
    )
    assert line == "Downloading 62%"


def test_status_line_truncates_the_percentage():
    """marker_for truncates so 99.6% never reads as the false claim "100". The detail
    listing must not disagree with the tile it was opened from."""
    from couchseerr import routes
    from couchseerr.state import TileState

    line = routes._status_line(
        TileState.DOWNLOADING, _downloading_item(1000, 4), _labels()
    )
    assert line == "Downloading 99%"


def test_status_line_carries_an_unreleased_date():
    """The design says this line carries "progress or the release date". Returning the
    bare enum name dropped a date the payload already had."""
    import datetime

    from couchseerr import routes
    from couchseerr.models import DiscoverItem
    from couchseerr.state import TileState

    item = DiscoverItem(tmdb_id=1, media_type="movie", title="Dune",
                        release_date=datetime.date(2027, 12, 25))
    assert routes._status_line(TileState.UNRELEASED, item, _labels()) == \
        "Releasing 2027-12-25"


def test_status_line_is_localised_for_every_in_flight_state():
    """Not state.value: the raw lowercase enum name is untranslated English, and it is
    what a French box used to render in the middle of an otherwise localised listing.
    Derived from TileState so a new member cannot quietly reintroduce the fallback."""
    from couchseerr import routes
    from couchseerr.state import TileState

    labels = _labels()
    for state in (TileState.MONITORED, TileState.PENDING, TileState.PARTIAL):
        line = routes._status_line(state, _downloading_item(1000, 380), labels)
        assert line and line != state.value, state
        assert line == labels[routes.STATUS_LABEL_KEYS[state]]


def test_every_status_label_key_has_a_string_id():
    """A key with no LABEL_IDS entry raises KeyError inside _status_line and takes the
    whole detail listing down with it."""
    from couchseerr import routes

    assert set(routes.STATUS_LABEL_KEYS.values()) <= set(routes.LABEL_IDS)


def test_status_line_is_blank_for_states_that_carry_no_line():
    """OWNED and ACTIONABLE never reach build_detail's status branch, and the two
    impossible shapes below cannot come out of tile_state. A blank line is not a failure
    signal: build_detail renders no entry for it."""
    from couchseerr import routes
    from couchseerr.models import DiscoverItem
    from couchseerr.state import TileState

    labels = _labels()
    bare = DiscoverItem(tmdb_id=1, media_type="movie", title="Dune")
    assert routes._status_line(TileState.OWNED, bare, labels) == ""
    assert routes._status_line(TileState.ACTIONABLE, bare, labels) == ""
    # DOWNLOADING with no download record, UNRELEASED with no release date.
    assert routes._status_line(TileState.DOWNLOADING, bare, labels) == ""
    assert routes._status_line(TileState.UNRELEASED, bare, labels) == ""


def test_trailer_key_picks_the_first_youtube_video():
    from couchseerr import routes

    payload = {"relatedVideos": [
        {"site": "YouTube", "key": "first"},
        {"site": "YouTube", "key": "second"},
    ]}
    assert routes._trailer_key(payload) == "first"


def test_trailer_key_ignores_a_video_that_is_not_on_youtube():
    """The trailer entry runs plugin.video.youtube, so a Vimeo key handed to it would
    open a player on an id that host has never heard of."""
    from couchseerr import routes

    payload = {"relatedVideos": [
        {"site": "Vimeo", "key": "vimeo-only"},
        {"site": "YouTube", "key": "yt"},
    ]}
    assert routes._trailer_key(payload) == "yt"


def test_trailer_key_is_none_without_a_youtube_video():
    from couchseerr import routes

    payload = {"relatedVideos": [{"site": "Vimeo", "key": "vimeo-only"}]}
    assert routes._trailer_key(payload) is None


def test_trailer_key_ignores_a_youtube_entry_with_no_key():
    from couchseerr import routes

    payload = {"relatedVideos": [{"site": "YouTube"}, {"site": "YouTube", "key": "yt"}]}
    assert routes._trailer_key(payload) == "yt"


def test_trailer_key_handles_missing_related_videos():
    """seerr omits relatedVideos entirely for some titles and sends null for others."""
    from couchseerr import routes

    assert routes._trailer_key({}) is None
    assert routes._trailer_key({"relatedVideos": []}) is None
    assert routes._trailer_key({"relatedVideos": None}) is None


def test_in_library_matches_a_movie_on_its_imdb_id():
    import xbmc
    from couchseerr import routes
    from couchseerr.models import DiscoverItem

    xbmc._jsonrpc_responses["VideoLibrary.GetMovies"] = {"movies": [
        {"movieid": 12, "title": "Dune", "year": 2024,
         "uniqueid": {"imdb": "tt15239678"}},
    ]}
    item = DiscoverItem(tmdb_id=693134, media_type="movie", title="Dune")
    assert routes._in_library("movie", {"imdbId": "tt15239678"}, item) == 12


def test_in_library_reads_tvdb_for_a_show_not_imdb():
    """A show carries both ids; Kodi's shows are scraped with tvdb. Reading imdb here
    would miss every show in the measured library."""
    import xbmc
    from couchseerr import routes
    from couchseerr.models import DiscoverItem

    xbmc._jsonrpc_responses["VideoLibrary.GetTVShows"] = {"tvshows": [
        {"tvshowid": 7, "title": "Severance", "year": 2022,
         "uniqueid": {"tvdb": "371980"}},
    ]}
    item = DiscoverItem(tmdb_id=95396, media_type="tv", title="Severance")
    payload = {"imdbId": "tt11280740", "externalIds": {"tvdbId": 371980,
                                                       "imdbId": "tt11280740"}}
    assert routes._in_library("tv", payload, item) == 7


def test_in_library_falls_back_to_title_and_year():
    """The one title per library with no ids at all. The year comes off the parsed
    item's release_date, which is the only place _in_library sources it."""
    import datetime

    import xbmc
    from couchseerr import routes
    from couchseerr.models import DiscoverItem

    xbmc._jsonrpc_responses["VideoLibrary.GetMovies"] = {"movies": [
        {"movieid": 44, "title": "Dune", "year": 2024, "uniqueid": {}},
    ]}
    item = DiscoverItem(tmdb_id=693134, media_type="movie", title="Dune",
                        release_date=datetime.date(2024, 2, 28))
    assert routes._in_library("movie", {}, item) == 44


def test_in_library_returns_none_with_no_id_and_no_release_date():
    """No id and no year means no fallback is even attempted: an exact-title-only match
    would play a remake. None here is "not resolvable", not a hidden failure."""
    import xbmc
    from couchseerr import routes
    from couchseerr.models import DiscoverItem

    xbmc._jsonrpc_responses["VideoLibrary.GetMovies"] = {"movies": [
        {"movieid": 44, "title": "Dune", "year": 2024, "uniqueid": {}},
    ]}
    item = DiscoverItem(tmdb_id=693134, media_type="movie", title="Dune")
    assert routes._in_library("movie", {}, item) is None


# --- the owned journey, across the module seam --------------------------------


class _OwnedService(object):
    """An owned movie whose seerr payload carries the imdb id Kodi's library stores."""

    warnings = []
    client = None

    def __init__(self):
        self.invalidated = []

    def invalidate_detail(self, media_type, tmdb_id):
        self.invalidated.append((media_type, tmdb_id))

    def detail(self, media_type, tmdb_id):
        import datetime

        from couchseerr.models import DiscoverItem
        from couchseerr.state import TileState

        item = DiscoverItem(
            tmdb_id=tmdb_id, media_type=media_type, title="Dune", overview="Sand.",
            poster_path="/p.jpg", backdrop_path="/b.jpg",
            release_date=datetime.date(2024, 2, 28), media=None,
        )
        payload = {
            "imdbId": "tt15239678",
            "relatedVideos": [{"site": "YouTube", "key": "yt-dune"}],
        }
        return item, TileState.OWNED, payload


def test_an_owned_tile_offers_play_and_that_entry_plays(monkeypatch):
    """The whole owned journey across the seam the per-module tests never crossed:
    mode=item resolves the library id from the payload's imdb id, renders Lire, and the
    URL that entry carries is itself dispatchable back into play_library_item.

    Dispatching the rendered URL rather than a hand-written one is the point: a wrong id,
    a wrong parameter name or a wrong media_type in the URL builder would pass every
    existing test and fail only on the device.
    """
    import xbmc
    import xbmcplugin
    from couchseerr import routes

    xbmc._jsonrpc_responses["VideoLibrary.GetMovies"] = {"movies": [
        {"movieid": 12, "title": "Dune", "year": 2024,
         "uniqueid": {"imdb": "tt15239678"}},
    ]}
    played = []
    monkeypatch.setattr(routes, "_build_service", lambda *a, **k: _OwnedService())
    monkeypatch.setattr(routes.jsonrpc, "play_library_item",
                        lambda mt, lid: played.append((mt, lid)))

    routes.dispatch(["plugin://plugin.video.couchseerr/", "40",
                     "?mode=item&tmdb_id=693134&media_type=movie"])

    assert xbmcplugin._ended == [(40, True, False)]
    labels = [li.getLabel() for _handle, _url, li, _folder in xbmcplugin._added]
    assert labels == ["Play", "Trailer"]

    play_url = xbmcplugin._added[0][1]
    assert "mode=play" in play_url
    assert "tmdb_id=693134" in play_url
    assert "media_type=movie" in play_url

    query = play_url[len("plugin://plugin.video.couchseerr/"):]
    routes.dispatch(["plugin://plugin.video.couchseerr/", "41", query])

    assert played == [("movie", 12)]
    assert xbmcplugin._ended == [(40, True, False), (41, False, False)]


def test_an_owned_tile_absent_from_the_library_offers_no_play(monkeypatch):
    """Same journey with an empty library: the Lire entry must not be offered at all,
    because selecting it would resolve nothing and play nothing."""
    import xbmc
    import xbmcplugin
    from couchseerr import routes

    xbmc._jsonrpc_responses["VideoLibrary.GetMovies"] = {"movies": []}
    monkeypatch.setattr(routes, "_build_service", lambda *a, **k: _OwnedService())

    routes.dispatch(["plugin://plugin.video.couchseerr/", "42",
                     "?mode=item&tmdb_id=693134&media_type=movie"])

    labels = [li.getLabel() for _handle, _url, li, _folder in xbmcplugin._added]
    assert labels == ["Not in the Kodi library", "Trailer"]
    assert not any("mode=play" in url for _h, url, _li, _f in xbmcplugin._added)


class _ShowService(object):
    warnings = []

    def __init__(self, payload=None, state=None):
        from couchseerr.state import TileState

        self.payload = payload if payload is not None else _SHOW_PAYLOAD
        self.state = state or TileState.PARTIAL
        self.client = None
        self.invalidated = []

    def detail(self, media_type, tmdb_id):
        from couchseerr.models import parse_discover_item
        merged = dict(self.payload, id=tmdb_id, mediaType=media_type)
        return parse_discover_item(merged), self.state, self.payload

    def today_provider(self):
        """Named for what routes.py calls, not for what it returns: RowService carries
        `today_provider` as the injected clock, and a double with a differently named
        method passes here and fails on the device."""
        import datetime
        return datetime.date(2026, 8, 6)

    def invalidate_detail(self, media_type, tmdb_id):
        """_do_request calls this after every successful request. A double without it
        raises AttributeError inside dispatch's catch-all, which reads as a route bug."""
        self.invalidated.append((media_type, tmdb_id))


_SHOW_PAYLOAD = {
    "name": "The Show", "overview": "Plot.", "posterPath": "/p.jpg",
    "firstAirDate": "2019-11-12",
    "seasons": [
        {"seasonNumber": 0, "name": "Specials", "episodeCount": 3, "airDate": "2019-11-12"},
        {"seasonNumber": 1, "name": "Season 1", "episodeCount": 8, "airDate": "2019-11-12"},
        {"seasonNumber": 2, "name": "Season 2", "episodeCount": 8, "airDate": "2020-10-30"},
    ],
    "mediaInfo": {"status": 4, "status4k": 1, "tvdbId": 90001,
                  "seasons": [{"seasonNumber": 1, "status": 5, "status4k": 1}]},
    "externalIds": {"tvdbId": 90001},
}


def test_seasons_route_renders_one_entry_per_season(monkeypatch):
    import xbmcplugin
    from couchseerr import routes

    monkeypatch.setattr(routes, "_build_service", lambda *a, **k: _ShowService())
    del xbmcplugin._added[:]
    del xbmcplugin._ended[:]
    routes.dispatch([BASE, "30", "?mode=seasons&tmdb_id=82856"])

    labels = [item.getLabel() for _handle, _url, item, _folder in xbmcplugin._added]
    assert labels == ["[✓] Season 1", "Season 2"]
    assert xbmcplugin._content[-1][1] == "seasons"
    assert xbmcplugin._ended == [(30, True, False)]


def test_seasons_route_says_so_when_there_are_none(monkeypatch):
    """A show whose payload carries no season data must still render something, and must
    not lose the whole-show request that mode=item already offers."""
    import xbmcplugin
    from couchseerr import routes

    payload = dict(_SHOW_PAYLOAD, seasons=[])
    monkeypatch.setattr(routes, "_build_service", lambda *a, **k: _ShowService(payload))
    del xbmcplugin._added[:]
    routes.dispatch([BASE, "31", "?mode=seasons&tmdb_id=82856"])

    labels = [item.getLabel() for _h, _u, item, _f in xbmcplugin._added]
    assert len(labels) == 1 and labels[0]


def test_seasons_route_applies_the_view_mode(monkeypatch):
    """Every marker in this listing lives in the label, same as mode=row -- an art-only
    view hides them just as completely one level down, so the same setting must apply
    here too."""
    import xbmc
    import xbmcaddon
    import xbmcplugin
    from couchseerr import routes

    xbmcaddon.Addon().setSetting("view_mode", "55")
    del xbmc._builtins[:]
    try:
        monkeypatch.setattr(routes, "_build_service", lambda *a, **k: _ShowService())
        routes.dispatch([BASE, "35", "?mode=seasons&tmdb_id=82856"])
        assert xbmc._builtins == ["Container.SetViewMode(55)"]
    finally:
        xbmcaddon.Addon().setSetting("view_mode", "")


def test_seasons_view_mode_failure_does_not_close_twice(monkeypatch):
    """Same guard as mode=row: _apply_view_mode runs after render has already closed the
    seasons listing, so anything it raises must not reach _fail_unexpected and close the
    handle a second time."""
    import xbmc
    import xbmcplugin
    from couchseerr import routes

    def boom():
        raise RuntimeError("no such window")

    monkeypatch.setattr(routes, "_build_service", lambda *a, **k: _ShowService())
    monkeypatch.setattr(routes, "_apply_view_mode", boom)
    del xbmcplugin._ended[:]
    del xbmc._log_calls[:]
    routes.dispatch([BASE, "36", "?mode=seasons&tmdb_id=82856"])

    assert xbmcplugin._ended == [(36, True, False)]
    errors = [c for c in xbmc._log_calls if c[1] == xbmc.LOGERROR]
    assert len(errors) == 1
    assert "no such window" in errors[0][0]


def test_season_route_lists_the_request_and_the_episodes(monkeypatch):
    import xbmc
    import xbmcplugin
    from couchseerr import routes

    xbmc._jsonrpc_responses["VideoLibrary.GetTVShows"] = {"tvshows": [
        {"tvshowid": 7, "title": "The Show", "year": 2019, "uniqueid": {"tvdb": "90001"}}
    ]}
    xbmc._jsonrpc_responses["VideoLibrary.GetEpisodes"] = {"episodes": [
        {"episodeid": 11, "episode": 1, "title": "Chapter One", "playcount": 0}
    ]}
    monkeypatch.setattr(routes, "_build_service", lambda *a, **k: _ShowService())
    monkeypatch.setattr(routes, "_resolved_default", lambda media_type: RESOLVED_DEFAULT)
    del xbmcplugin._added[:]
    routes.dispatch([BASE, "32", "?mode=season&tmdb_id=82856&season=2"])

    labels = [item.getLabel() for _h, _u, item, _f in xbmcplugin._added]
    assert labels[0] == "Request this season"
    assert labels[1] == "1. Chapter One"
    assert xbmcplugin._content[-1][1] == "episodes"


def test_season_route_uses_that_seasons_own_state(monkeypatch):
    """Season 1 is available while the title is partial. The request entry must follow the
    season, not the title."""
    import xbmc
    import xbmcplugin
    from couchseerr import routes

    xbmc._jsonrpc_responses["VideoLibrary.GetTVShows"] = {"tvshows": []}
    xbmc._jsonrpc_responses["VideoLibrary.GetEpisodes"] = {"episodes": []}
    monkeypatch.setattr(routes, "_build_service", lambda *a, **k: _ShowService())
    del xbmcplugin._added[:]
    routes.dispatch([BASE, "33", "?mode=season&tmdb_id=82856&season=1"])

    labels = [item.getLabel() for _h, _u, item, _f in xbmcplugin._added]
    assert "Request this season" not in labels


def test_an_unknown_season_number_fails_loudly(monkeypatch):
    import xbmcplugin
    from couchseerr import routes

    monkeypatch.setattr(routes, "_build_service", lambda *a, **k: _ShowService())
    del xbmcplugin._ended[:]
    routes.dispatch([BASE, "34", "?mode=season&tmdb_id=82856&season=9"])

    assert xbmcplugin._ended == [(34, False, False)]


def test_render_season_empty_param_fails_loudly(monkeypatch):
    """The URL layer drops a blank season= before it ever reaches params (parse_qsl's
    default keep_blank_values=False), so this exercises _render_season's own parsing
    directly with the shape a differently-built caller could still hand it: season=""
    present but empty. _int_or_none turns that into the same "unknown season" failure a
    fully absent key gets, rather than int()'s bare ValueError escaping uncaught."""
    import xbmcgui
    import xbmcplugin
    from couchseerr import routes

    monkeypatch.setattr(routes, "_build_service", lambda *a, **k: _ShowService())
    del xbmcplugin._ended[:]
    del xbmcgui._notifications[:]
    routes._render_season(37, BASE, {"tmdb_id": "82856", "season": ""})

    assert xbmcplugin._ended == [(37, False, False)]
    assert "Unknown season" in xbmcgui._notifications[-1][1]


def test_requesting_one_season_sends_only_that_season(monkeypatch):
    import xbmcplugin
    from couchseerr import routes
    from couchseerr.state import TileState

    sent = []
    monkeypatch.setattr(routes, "_build_service", lambda *a, **k: _ShowService())
    monkeypatch.setattr(routes, "_resolved_default", lambda media_type: RESOLVED_DEFAULT)
    monkeypatch.setattr(routes, "send_request",
                        lambda client, settings, mt, tmdb, state, seasons=None:
                        sent.append((tmdb, state, seasons)) or {"id": 1})
    monkeypatch.setattr(routes.jsonrpc, "refresh_container", lambda: None)
    del xbmcplugin._ended[:]
    routes.dispatch([BASE, "40", "?mode=request&media_type=tv&tmdb_id=82856&season=2"])

    assert sent == [(82856, TileState.ACTIONABLE, [2])]
    assert xbmcplugin._ended == [(40, False, False)]


def test_a_season_request_is_gated_on_its_own_state(monkeypatch):
    """Season 1 is available while the title is partial: the guard must see OWNED, which
    send_request then refuses."""
    from couchseerr import routes
    from couchseerr.state import TileState

    seen = []
    monkeypatch.setattr(routes, "_build_service", lambda *a, **k: _ShowService())
    monkeypatch.setattr(routes, "_resolved_default", lambda media_type: RESOLVED_DEFAULT)
    monkeypatch.setattr(routes, "send_request",
                        lambda client, settings, mt, tmdb, state, seasons=None:
                        seen.append(state) or {"id": 1})
    monkeypatch.setattr(routes.jsonrpc, "refresh_container", lambda: None)
    routes.dispatch([BASE, "41", "?mode=request&media_type=tv&tmdb_id=82856&season=1"])

    assert seen == [TileState.OWNED]


def test_a_whole_show_request_still_sends_no_seasons(monkeypatch):
    from couchseerr import routes
    from couchseerr.state import TileState

    sent = []
    monkeypatch.setattr(routes, "_build_service", lambda *a, **k: _ShowService(state=TileState.ACTIONABLE))
    monkeypatch.setattr(routes, "_resolved_default", lambda media_type: RESOLVED_DEFAULT)
    monkeypatch.setattr(routes, "send_request",
                        lambda client, settings, mt, tmdb, state, seasons=None:
                        sent.append(seasons) or {"id": 1})
    monkeypatch.setattr(routes.jsonrpc, "refresh_container", lambda: None)
    routes.dispatch([BASE, "42", "?mode=request&media_type=tv&tmdb_id=82856"])

    assert sent == [None]


def test_playing_an_episode_asks_kodi_directly(monkeypatch):
    """No seerr call at all: the episode id came from Kodi's library, so nothing about
    seerr's view of the show is needed to play it."""
    import xbmcplugin
    from couchseerr import routes

    played = []
    monkeypatch.setattr(routes.jsonrpc, "play_library_item",
                        lambda media_type, library_id: played.append((media_type, library_id)))
    monkeypatch.setattr(routes, "_build_service",
                        lambda *a, **k: pytest.fail("play must not contact seerr"))
    del xbmcplugin._ended[:]
    routes.dispatch([BASE, "43", "?mode=play&episode_id=11"])

    assert played == [("episode", 11)]
    assert xbmcplugin._ended == [(43, False, False)]


def test_requesting_an_unknown_season_fails_loudly(monkeypatch):
    """Same bad input _render_season already fails loudly on: a season number the show
    does not have at all, not merely one seerr has never tracked. Sending it anyway would
    get seerr's silent 200 back and nothing would ever download."""
    import xbmcgui
    import xbmcplugin
    from couchseerr import routes

    def explode(*args, **kwargs):
        raise AssertionError("send_request must not run for a season the show doesn't have")

    monkeypatch.setattr(routes, "_build_service", lambda *a, **k: _ShowService())
    monkeypatch.setattr(routes, "_resolved_default", lambda media_type: RESOLVED_DEFAULT)
    monkeypatch.setattr(routes, "send_request", explode)
    del xbmcgui._notifications[:]
    del xbmcplugin._ended[:]
    routes.dispatch([BASE, "44", "?mode=request&media_type=tv&tmdb_id=82856&season=9"])

    assert xbmcgui._notifications
    assert xbmcplugin._ended == [(44, False, False)]
