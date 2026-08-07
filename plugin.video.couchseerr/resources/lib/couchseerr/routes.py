# Couchseerr -- seerr discovery rows for Kodi
# Copyright (C) 2026 yorah
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version.
#
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along with
# this program. If not, see <https://www.gnu.org/licenses/>.
"""URL dispatch. Every path through this module ends the directory exactly once."""
import datetime
import traceback

try:
    from urllib.parse import parse_qsl
except ImportError:  # pragma: no cover
    from urlparse import parse_qsl

import xbmc
import xbmcaddon
import xbmcgui
import xbmcplugin
import xbmcvfs

from .actions.request import send_request
from .cache import FileCache
from .client import SeerrClient
from .detail import build_detail
from .errors import ConfigError, RequestRefused, SeerrAuthError, SeerrError
from .kodi import dialogs, jsonrpc
from .kodi.adapter import render
from .library import external_ids, match_library_id
from .models import media_seasons, parse_seasons
from .request_config import load_config, resolve, save_config
from .rows import ROWS, RowService
from .seasons import build_season_detail, build_season_list
from .state import REQUESTABLE_STATES, SEASON_REQUESTABLE_STATES, TileState, season_state
from .ui.spec import ListItemSpec

IMAGE_BASE = "https://image.tmdb.org/t/p/w780"
ADDON_ID = "plugin.video.couchseerr"

LABEL_IDS = {
    "play": 30040, "request": 30041, "request_with": 30042, "trailer": 30043,
    "configure": 30044, "not_in_library": 30045, "requested": 30056,
    "not_requested": 30057, "no_profile": 30058, "downloading": 30060,
    "monitored": 30061, "unreleased": 30062, "pending": 30063, "partial": 30064,
    "pick_profile": 30084, "profile_saved": 30085, "no_server_movie": 30086,
    "no_server_tv": 30087,
    "seasons": 30088, "season": 30089, "request_season": 30090, "no_seasons": 30091,
}

#: A slot's media type comes from its name, not a passed-in parameter: movie and
#: movie_4k are Radarr, tv and tv_4k are Sonarr.
SLOT_MEDIA_TYPES = {"movie": "movie", "movie_4k": "movie", "tv": "tv", "tv_4k": "tv"}

#: The status line's wording per state, keyed into LABEL_IDS. DOWNLOADING and UNRELEASED
#: are absent on purpose: both take an argument (percent, release date) and are handled
#: explicitly in _status_line, where the argument is available.
STATUS_LABEL_KEYS = {
    TileState.MONITORED: "monitored",
    TileState.PENDING: "pending",
    TileState.PARTIAL: "partial",
}


def parse_args(argv):
    base_url = argv[0]
    handle = int(argv[1])
    query = argv[2][1:] if len(argv) > 2 and argv[2].startswith("?") else ""
    return handle, base_url, dict(parse_qsl(query))


def _build_service(base_url=None):
    addon = xbmcaddon.Addon(ADDON_ID)
    profile = xbmcvfs.translatePath(addon.getAddonInfo("profile"))
    # ISO_639_1, not the default ENGLISH_NAME: this value goes to seerr and on to TMDb,
    # which wants "fr". ENGLISH_NAME would send the literal "French" and TMDb silently
    # answers in en-US, so a French box shows English titles, plots and poster art.
    language = addon.getSetting("language") or xbmc.getLanguage(xbmc.ISO_639_1) or ""
    client = SeerrClient(addon.getSetting("seerr_url"), addon.getSetting("api_key"))
    cache = FileCache(profile.rstrip("/") + "/cache")
    # Expiry is already applied on read, which is correct for serving; but a key
    # that is never read again is never removed, so the cache grows without bound
    # on the device unless something also cleans up on the way in. purge_expired()
    # cannot raise (see cache.py): every internal step already degrades to a no-op.
    cache.purge_expired()
    return RowService(
        client=client,
        cache=cache,
        base_url=base_url or ("plugin://" + ADDON_ID + "/"),
        image_base=IMAGE_BASE,
        language=language,
        today_provider=datetime.date.today,
        labels=_labels(),
    )


def _root_specs(base_url):
    return [
        ListItemSpec(
            label=row.label,
            url="{0}?mode=row&key={1}".format(base_url, row.key),
            is_folder=True,
            art={},
            properties={},
            info={"title": row.label},
        )
        for row in ROWS.values()
    ]


def _apply_view_mode():
    """Optionally switch the container to a user-chosen view, after the listing closes.

    Every marker lives in the label, so an art-only view (Arctic Fuse "Tableau", Estuary
    "Wall") renders tiles with no visible status at all - the one thing this addon exists
    to show. Kodi offers no API for an addon to declare a view, and the ids are
    skin-specific integers, so this can only ever be a value the user supplies for their
    own skin. Blank by default: guessing an id is how a listing ends up in a view worse
    than the one Kodi already remembered.

    This reaches browsing into the addon only. A home-screen widget's layout comes from
    the skin's widget style, which nothing here can touch.
    """
    raw = (xbmcaddon.Addon(ADDON_ID).getSetting("view_mode") or "").strip()
    if not raw:
        return
    try:
        view_id = int(raw)
    except ValueError:
        # Not fatal: the listing is already rendered and correct, only its view is not
        # what the user asked for. Say so in the log rather than failing the row.
        xbmc.log(
            "[couchseerr] ignoring non-numeric view_mode setting {0!r}".format(raw),
            xbmc.LOGWARNING,
        )
        return
    xbmc.executebuiltin("Container.SetViewMode({0})".format(view_id))


def _log_warnings(service):
    # service.warnings, not getattr(service, "warnings", ()): RowService sets it in
    # __init__ and resets it per call, so a missing attribute is a defect that should
    # surface, not a shape production code bends around to suit a thin test double.
    for warning in service.warnings:
        xbmc.log("[couchseerr] {0}".format(warning), xbmc.LOGWARNING)


def _labels():
    addon = xbmcaddon.Addon(ADDON_ID)
    return {key: addon.getLocalizedString(value) for key, value in LABEL_IDS.items()}


def _request_config_path():
    profile = xbmcvfs.translatePath(xbmcaddon.Addon(ADDON_ID).getAddonInfo("profile"))
    return profile.rstrip("/") + "/request_config.json"


def _resolved_default(media_type):
    """The default profile for this media type, or None when it is not configured --
    request_config.resolve()'s own return value, read fresh from disk and from the
    addon's prefer_4k setting. Both build_detail (offer "Demander" or "Configurer") and
    _do_request (the third, lowest-priority resolution step) call this so the two never
    compute the answer two different ways.

    A corrupt request_config.json is reported and treated the same as "nothing
    configured", the same fallback the old presets.json path used: mode=item still
    renders Play/Trailer/whatever else the title has, and mode=request still notifies
    a clear "no default configured" rather than taking the whole listing (or the whole
    request) down with ConfigError.
    """
    try:
        config = load_config(_request_config_path())
    except ConfigError as exc:
        xbmc.log("[couchseerr] {0}".format(exc), xbmc.LOGERROR)
        return None
    prefer_4k = xbmcaddon.Addon(ADDON_ID).getSettingBool("prefer_4k")
    return resolve(config, media_type, prefer_4k)


def _trailer_key(payload):
    for video in (payload.get("relatedVideos") or []):
        if video.get("site") == "YouTube" and video.get("key"):
            return video["key"]
    return None


def _status_line(state, item, labels):
    """The non-actionable line the detail listing shows for a title in flight.

    It carries "progress or the release date" (design), localised. It cannot share the
    text with markers.marker_for: that table is pure core, so it has no access to
    getLocalizedString, and it deliberately emits compact glyphs ("[⋯]", "[◐]") sized for
    a poster label rather than prose for a full-width listing row. What the two do share
    is the question they answer, and that lives in TileState, not in either table.

    Percent is truncated, not rounded, matching marker_for: 99.6% reads as 99, because
    "100" is reserved for a download that is actually finished.

    Returns "" for a state that carries no line -- OWNED and ACTIONABLE, which
    build_detail never asks about, and the two shapes tile_state cannot produce
    (DOWNLOADING with no download record, UNRELEASED with no release date). "" is not a
    failure signal: build_detail already renders no status entry for a blank line.
    """
    download = item.media.best_download if item.media else None
    if state is TileState.DOWNLOADING and download is not None:
        return labels["downloading"].format(int(download.percent))
    if state is TileState.UNRELEASED and item.release_date is not None:
        return labels["unreleased"].format(item.release_date.isoformat())
    key = STATUS_LABEL_KEYS.get(state)
    return labels[key] if key else ""


def _in_library(media_type, payload, item):
    ids = external_ids(payload)
    # Namespace is explicit: a numeric tvdb id can collide with some other scraper's
    # numeric id, and a false match here plays the wrong film.
    namespace = "imdb" if media_type == "movie" else "tvdb"
    wanted = ids[namespace]
    year = item.release_date.year if item.release_date else None
    id_key = "movieid" if media_type == "movie" else "tvshowid"
    return match_library_id(
        jsonrpc.library_records(media_type), id_key, namespace, wanted, item.title, year
    )


def dispatch(argv):
    handle, base_url, params = parse_args(argv)
    mode = params.get("mode", "root")

    try:
        if mode == "root":
            # Four plain folders with no artwork: "movies"/"tvshows" would render
            # them as a wall of blank poster placeholders, so this is "videos".
            render(handle, _root_specs(base_url), content_type="videos")
            return

        if mode == "row":
            key = params.get("key", "")
            row = ROWS.get(key)
            if row is None:
                _fail(handle, "Unknown row: {0}".format(key))
                return
            service = _build_service(base_url)
            if key == "processing":
                specs = service.processing_row()
            else:
                specs = service.discover_row(key)
            _log_warnings(service)
            render(handle, specs, content_type=row.content_type)
            # After render, never before: the view can only be set on a container Kodi
            # has finished loading, and render owns the successful close. Which is also
            # why this cannot be left to dispatch's catch-all: the directory is already
            # closed here, so a raise reaching _fail_unexpected would close it twice.
            try:
                _apply_view_mode()
            except Exception:
                xbmc.log(
                    "[couchseerr] could not apply the view mode:\n" + traceback.format_exc(),
                    xbmc.LOGERROR,
                )
            return

        if mode == "item":
            media_type = params.get("media_type", "movie")
            tmdb_id = int(params.get("tmdb_id", "0"))
            service = _build_service(base_url)
            item, state, payload = service.detail(media_type, tmdb_id)
            # Only a movie's listing ever offers Play, so only a movie needs its Kodi
            # library id resolved here: build_detail no longer reads in_library for a tv
            # title, which offers Seasons instead (see detail.py).
            library_id = (
                _in_library(media_type, payload, item)
                if state is TileState.OWNED and media_type != "tv"
                else None
            )
            labels = _labels()
            # Only requestable states need to know the default; reading the config
            # file for every owned or in-flight title would cost a read for nothing.
            resolved = _resolved_default(media_type) if state in REQUESTABLE_STATES else None
            specs = build_detail(
                item, state, resolved, base_url, IMAGE_BASE, labels,
                in_library=library_id is not None,
                trailer_key=_trailer_key(payload),
                status_line=_status_line(state, item, labels),
            )
            render(handle, specs, content_type="videos")
            return

        if mode == "seasons":
            tmdb_id = int(params.get("tmdb_id", "0"))
            service = _build_service(base_url)
            item, _state, payload = service.detail("tv", tmdb_id)
            labels = _labels()
            specs = build_season_list(
                item, parse_seasons(payload), media_seasons(payload), base_url,
                IMAGE_BASE, labels, service.today_provider(),
            )
            if not specs:
                # A show with no season data must still render something: an empty
                # listing on a TV is indistinguishable from a broken addon. mode=item
                # keeps its whole-show request either way.
                specs = [_line(labels["no_seasons"])]
            render(handle, specs, content_type="seasons")
            # Every marker in this listing lives in the label too, same as mode=row, so
            # the same user-chosen view must apply here -- see _apply_view_mode's
            # docstring. Same guard as mode=row for the same reason: the directory is
            # already closed, so a raise reaching _fail_unexpected would close it twice.
            try:
                _apply_view_mode()
            except Exception:
                xbmc.log(
                    "[couchseerr] could not apply the view mode:\n" + traceback.format_exc(),
                    xbmc.LOGERROR,
                )
            return

        if mode == "season":
            _render_season(handle, base_url, params)
            return

        if mode == "search":
            service = _build_service(base_url)
            specs = service.search_row(params.get("query", ""))
            _log_warnings(service)
            render(handle, specs, content_type="videos")
            return

        if mode == "request":
            _do_request(handle, base_url, params)
            return

        if mode == "play":
            _do_play(handle, base_url, params)
            return

        if mode == "settings":
            # The detail listing's answer to "no default profile configured": open the
            # addon's own settings dialog on the row that configures one, rather than
            # rendering a listing here.
            xbmc.executebuiltin("Addon.OpenSettings({0})".format(ADDON_ID))
            xbmcplugin.endOfDirectory(handle, succeeded=False, cacheToDisc=False)
            return

        if mode == "profile":
            _do_profile(handle, base_url, params)
            return

        if mode == "trailer":
            xbmc.executebuiltin(
                "PlayMedia(plugin://plugin.video.youtube/play/?video_id={0})".format(
                    params.get("youtube_id", "")
                )
            )
            xbmcplugin.endOfDirectory(handle, succeeded=False, cacheToDisc=False)
            return

        # Anything unrecognised must still close the directory, or Kodi spins.
        _fail(handle, "Unknown mode: {0}".format(mode))
    except SeerrAuthError as exc:
        _fail(handle, "Check your seerr URL and API key: {0}".format(exc))
    except SeerrError as exc:
        _fail(handle, str(exc))
    except Exception:
        # Deliberate, narrow exception to "never swallow an error": this is the
        # top-level Kodi entry point, so an uncaught bug anywhere downstream
        # (KeyError, ValueError, OSError from the cache, ...) must not leave
        # endOfDirectory uncalled - that hangs Kodi until the user backs out.
        # The traceback is logged in full; only its propagation is swallowed.
        _fail_unexpected(handle)


def _int_or_none(raw):
    """A URL param is a string or absent; an empty string ("server_id=") means the same
    as absent, not a literal id of nothing."""
    return int(raw) if raw else None


def _resolve_request_settings(service, media_type, params, labels):
    """The three ways `_do_request` learns what to send, in priority order:

    1. Explicit server_id/profile_id params -- a caller (a future custom window) that
       already knows exactly what it wants. Bypasses both the picker and the config.
    2. pick=1 -- the context menu's "Demander avec...": fetches every server's every
       profile and asks. Cancelling returns (None, True): nothing more to notify, the
       user just changed their mind.
    3. Otherwise, the slot request_config.resolve() names for this media type -- the
       context menu's "Demander" and the detail listing's own entry, both of which
       carry no ids at all in their URL.

    Returns (settings, stop) where `stop` means the caller must close the directory
    now without contacting seerr: either the user cancelled a picker, or nothing is
    configured to send. `settings` is only meaningful when `stop` is False.
    """
    server_id = params.get("server_id")
    profile_id = params.get("profile_id")
    # Truthy, not "is not None": an empty string (server_id=, what a template or a skin
    # building the path from an empty property produces) is the same as absent, not a
    # caller's explicit choice. Treating it as explicit would send seerr a body with
    # neither id and report success for a request that was never really configured.
    if server_id or profile_id:
        settings = {
            "serverId": _int_or_none(server_id),
            "profileId": _int_or_none(profile_id),
            "is4k": params.get("is4k") == "1",
        }
        return settings, False

    if params.get("pick") == "1":
        entries = dialogs.choices(service.client, media_type)
        if not entries:
            key = "no_server_movie" if media_type == "movie" else "no_server_tv"
            dialogs.notify(labels[key])
            return None, True
        settings = dialogs.pick_profile(entries, labels)
        return settings, settings is None

    settings = _resolved_default(media_type)
    if settings is None:
        # Sending anyway would hand seerr a body with no serverId/profileId at all,
        # which it accepts and answers as if the request had succeeded -- reporting
        # "Requested" over a request the user never actually configured.
        dialogs.notify(labels["no_profile"])
        return None, True
    return settings, False


def _do_request(handle, base_url, params):
    """Fires a request and closes the directory unsuccessfully: this route renders no
    listing, it acts. Every outcome ends in a notification the user can read."""
    media_type = params.get("media_type", "movie")
    tmdb_id = int(params.get("tmdb_id", "0"))
    season_number = _int_or_none(params.get("season"))
    labels = _labels()
    service = _build_service(base_url)

    settings, stop = _resolve_request_settings(service, media_type, params, labels)
    if stop:
        xbmcplugin.endOfDirectory(handle, succeeded=False, cacheToDisc=False)
        return

    item, state, payload = service.detail(media_type, tmdb_id)
    seasons = None
    if season_number is not None:
        season = _find_season(payload, season_number)
        if season is None:
            # A URL naming a season this show does not have -- the same malformed input
            # _render_season already fails loudly on. Sending anyway would get seerr's
            # silent 200 back and nothing would ever download.
            _fail(handle, "Unknown season: {0}".format(season_number))
            return
        # The season's own state, not the title's: a partial show is precisely the case
        # where the title is not requestable and the season must be.
        state = _season_state_of(season, payload, service.today_provider())
        seasons = [season_number]
    try:
        send_request(service.client, settings, media_type, tmdb_id, state, seasons=seasons)
    except RequestRefused as exc:
        dialogs.notify(labels["not_requested"].format(exc))
    except SeerrError as exc:
        dialogs.notify(labels["not_requested"].format(exc))
    else:
        dialogs.notify(labels["requested"].format(item.title))
        # Order matters: drop the cached payload first, then refresh. The detail payload
        # is cached for fifteen minutes, so a refresh on its own re-renders the state
        # from before the request -- the listing would still offer "Request", and
        # selecting it again would still pass send_request's guard and send a duplicate.
        # The rows self-heal in thirty seconds (TTL_PROGRESS); this one does not.
        service.invalidate_detail(media_type, tmdb_id)
        # The tile's state has changed; the listing behind this action has not.
        jsonrpc.refresh_container()
    xbmcplugin.endOfDirectory(handle, succeeded=False, cacheToDisc=False)


def _find_season(payload, number):
    """Looks up one season by number in a payload already in hand. Returns None when the
    show has no such season at all -- a malformed URL, distinct from a season the show does
    have but seerr has never tracked (see _season_state_of). Shared by every season-scoped
    route so the lookup, and what a miss means, don't drift between them."""
    for season in parse_seasons(payload):
        if season.number == number:
            return season
    return None


def _season_state_of(season, payload, today):
    """The state of a season already confirmed to exist (see _find_season) -- never
    ACTIONABLE as a stand-in for "not found".

    A season with no entry in mediaInfo.seasons is untracked: seerr records a season only
    once something has been requested for it, so ACTIONABLE here is the ordinary case for
    any season nobody has asked for yet, not a fallback. A season absent from the payload's
    seasons[] altogether is a different problem -- the show does not have it at all -- and
    callers must fail loudly on that themselves, before this function ever runs; deriving
    ACTIONABLE for it would send seerr a request for a season that doesn't exist, which
    answers 200 and downloads nothing.
    """
    return season_state(season, media_seasons(payload), today)


def _line(label):
    """A listing entry that says something and does nothing: no URL, not a folder."""
    return ListItemSpec(label=label, url="", is_folder=False, art={}, properties={},
                        info={"title": label})


def _render_season(handle, base_url, params):
    """One season's actions and episodes.

    The season's own state decides whether a request is offered, never the title's: a
    partial show is exactly the case where the title is not requestable and its missing
    seasons must be.
    """
    tmdb_id = int(params.get("tmdb_id", "0"))
    # _int_or_none, not int(): a missing or empty season= must fail loudly as "unknown
    # season" below, the same outcome mode=request already gives it, not raise a
    # ValueError into dispatch's catch-all and report a generic "Unexpected error".
    number = _int_or_none(params.get("season"))
    service = _build_service(base_url)
    item, _state, payload = service.detail("tv", tmdb_id)

    season = _find_season(payload, number)
    if season is None:
        # A URL naming a season this show does not have. Failing loudly beats an empty
        # listing that looks like a season with nothing in it.
        _fail(handle, "Unknown season: {0}".format(number))
        return

    state = _season_state_of(season, payload, service.today_provider())
    resolved = _resolved_default("tv") if state in SEASON_REQUESTABLE_STATES else None
    library_id = _in_library("tv", payload, item)
    records = jsonrpc.episode_records(library_id, number) if library_id is not None else []

    specs = build_season_detail(
        item, season, state, resolved, records, base_url, IMAGE_BASE, _labels(),
    )
    render(handle, specs, content_type="episodes")


def _do_play(handle, base_url, params):
    episode_id = _int_or_none(params.get("episode_id"))
    if episode_id is not None:
        # The id came out of Kodi's own library, so nothing about seerr's view of the show
        # is needed to play it -- and skipping the detail fetch keeps playback instant.
        jsonrpc.play_library_item("episode", episode_id)
        xbmcplugin.endOfDirectory(handle, succeeded=False, cacheToDisc=False)
        return

    media_type = params.get("media_type", "movie")
    tmdb_id = int(params.get("tmdb_id", "0"))
    service = _build_service(base_url)
    item, _state, payload = service.detail(media_type, tmdb_id)
    library_id = _in_library(media_type, payload, item)
    if library_id is None:
        dialogs.notify(_labels()["not_in_library"])
    else:
        jsonrpc.play_library_item(media_type, library_id)
    xbmcplugin.endOfDirectory(handle, succeeded=False, cacheToDisc=False)


def _do_profile(handle, base_url, params):
    """Fetches every server's every profile for a slot's media type, shows a picker,
    and writes the choice back to both request_config.json and the settings row's
    displayed label. Renders no listing of its own; the directory closes exactly once
    on every path through here, matching every other action route.

    A seerr failure while fetching servers or profiles is not caught here: it
    propagates to dispatch's own SeerrError/SeerrAuthError handling, which is the one
    place every route already reports a typed error as a notification and closes the
    directory -- catching it again here would just duplicate that path.
    """
    slot = params.get("slot", "")
    media_type = SLOT_MEDIA_TYPES.get(slot)
    if media_type is None:
        _fail(handle, "Unknown profile slot: {0}".format(slot))
        return

    # The addon-settings dialog is the only way in here, and it is exactly what makes
    # writing a setting from this route unsafe: the dialog holds its own copy of every
    # setting and writes that copy back over the store when it closes, so a setSetting
    # made while it is open survives only until the user leaves the dialog. Measured on
    # the device (Kodi 21.3, 2026-08-05): picking a profile from the open dialog wrote
    # request_config.json correctly, then closing the dialog left profile_movie unset --
    # the row went back to blank while the choice was live. The same picker driven with
    # the dialog closed wrote profile_tv straight through.
    #
    # So close the dialog first and reopen it afterwards. Reopening is not cosmetic: it
    # is what makes a newly discovered 4K row (has_4k_movie / has_4k_tv, written below)
    # appear immediately rather than on the user's next visit to the settings.
    reopen_settings = xbmc.getCondVisibility("Window.IsActive(addonsettings)")
    if reopen_settings:
        # wait=True: the close must have completed, and its clobbering save with it,
        # before anything here writes a setting.
        xbmc.executebuiltin("Dialog.Close(addonsettings)", True)
    try:
        _pick_profile_into(handle, base_url, slot, media_type)
    finally:
        # finally, not a line at the end of the happy path: a seerr failure propagates
        # out of here to dispatch, and leaving the user staring at the home screen with
        # their settings dialog gone would be a worse bug than the one being fixed.
        if reopen_settings:
            xbmc.executebuiltin("Addon.OpenSettings({0})".format(ADDON_ID))


def _pick_profile_into(handle, base_url, slot, media_type):
    """The picker itself: fetch, ask, write. Split out of _do_profile so that the
    settings dialog it runs without is reopened on every path out, exceptions included.
    """
    labels = _labels()

    service = _build_service(base_url)
    entries = dialogs.choices(service.client, media_type)

    # Written here and nowhere else: whatever this fetch just observed about seerr's
    # server list is what un-hides (or re-hides) the 4K settings rows next time the
    # dialog opens. An empty entries list is a legitimate "no 4K server" answer too.
    addon = xbmcaddon.Addon(ADDON_ID)
    flag_id = "has_4k_movie" if media_type == "movie" else "has_4k_tv"
    addon.setSetting(flag_id, "true" if any(e["is4k"] for e in entries) else "false")

    if not entries:
        # seerr has no Radarr/Sonarr configured for this media type at all -- that is
        # something to fix in seerr, not here, so nothing is written.
        no_server_key = "no_server_movie" if media_type == "movie" else "no_server_tv"
        dialogs.notify(labels[no_server_key])
        xbmcplugin.endOfDirectory(handle, succeeded=False, cacheToDisc=False)
        return

    choice = dialogs.pick_profile(entries, labels)
    if choice is None:
        # Cancelling writes nothing: not the JSON, not the settings label. The 4K flag
        # above having already been written is fine -- it mirrors observed server
        # reality, not the user's choice, so there is nothing to roll back.
        xbmcplugin.endOfDirectory(handle, succeeded=False, cacheToDisc=False)
        return

    path = _request_config_path()
    try:
        config = load_config(path)
    except ConfigError as exc:
        # This picker is the only thing that can repair the file, so it must not be the
        # thing that refuses to run because the file is broken. Everywhere else a
        # ConfigError is reported and the caller degrades; here it would be reported and
        # leave the user with no way forward at all -- mode=item offers "Configure
        # default profile", that lands here, and this raised every time.
        #
        # Starting from {} discards nothing recoverable: load_config only raises when the
        # file will not parse or is not an object, so no slot in it can be read anyway,
        # and save_config below writes a whole, valid replacement.
        xbmc.log(
            "[couchseerr] {0} -- starting from an empty configuration".format(exc),
            xbmc.LOGERROR,
        )
        config = {}
    config[slot] = {
        "serverId": choice["serverId"],
        "profileId": choice["profileId"],
        "label": choice["label"],
    }
    save_config(path, config)
    addon.setSetting("profile_" + slot, choice["label"])
    dialogs.notify(labels["profile_saved"].format(choice["label"]))
    xbmcplugin.endOfDirectory(handle, succeeded=False, cacheToDisc=False)


def _fail(handle, message):
    xbmc.log("[couchseerr] {0}".format(message), xbmc.LOGERROR)
    xbmcgui.Dialog().notification("Couchseerr", message)
    xbmcplugin.endOfDirectory(handle, succeeded=False, cacheToDisc=False)


def _fail_unexpected(handle):
    """Catch-all for dispatch(): nothing here may prevent endOfDirectory from
    running, so each risky step is isolated and the close always happens.
    """
    try:
        xbmc.log(
            "[couchseerr] Unexpected error:\n" + traceback.format_exc(),
            xbmc.LOGERROR,
        )
    except Exception:
        pass
    try:
        xbmcgui.Dialog().notification("Couchseerr", "Unexpected error - see log")
    except Exception:
        pass
    xbmcplugin.endOfDirectory(handle, succeeded=False, cacheToDisc=False)
