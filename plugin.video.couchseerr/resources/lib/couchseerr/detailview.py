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
"""The window's view model. Pure: no Kodi, no ListItem, no pixels.

This is the addon's only renderer of a title's detail: the three listing routes it
replaced are gone. It still does not decide *which* actions exist -- detail.available_actions
does, and this calls it, so the rule stays somewhere a second renderer could reuse rather
than re-derive.
"""
try:
    from urllib.parse import urlencode
except ImportError:  # pragma: no cover
    from urllib import urlencode

from .detail import available_actions, status_line
from .markers import marker_for
from .seasons import SEASON_REQUEST_LABEL_KEY, episode_label_and_info, season_label
from .state import SEASON_REQUESTABLE_STATES, TileState, season_state
from .ui.spec import ListItemSpec, art_and_info, request_urls


class Action(object):
    __slots__ = ("key", "label", "url")

    def __init__(self, key, label, url):
        self.key = key
        self.label = label
        self.url = url


class SeasonRow(object):
    """No url: a season row is handled inside the window by its `number`. mode=season does
    not exist, so a URL here could only point at a route that was deleted with the listing.
    """

    __slots__ = ("number", "label", "marker", "state", "episode_count")

    def __init__(self, number, label, marker, state, episode_count):
        self.number = number
        self.label = label
        self.marker = marker
        self.state = state
        self.episode_count = episode_count


class EpisodeRow(object):
    """`url` is "" for a row that leads nowhere -- the same sentinel ui/spec.ListItemSpec
    uses for a line the user only reads. One spelling of "no action" across both types,
    so a renderer handling both needs one rule, not two. It is not a failure signal:
    an unowned episode genuinely has no action, because seerr has no episode-level
    request to offer.
    """

    __slots__ = ("number", "title", "air_date", "owned", "label", "url", "art", "info")

    def __init__(self, number, title, air_date, owned, label, url, art, info):
        self.number = number
        self.title = title
        self.air_date = air_date
        self.owned = owned
        self.label = label
        self.url = url
        self.art = art
        self.info = info


class SeasonView(object):
    __slots__ = ("title", "season_name", "art", "actions", "episodes")

    def __init__(self, title, season_name, art, actions, episodes):
        self.title = title
        self.season_name = season_name
        self.art = art
        self.actions = actions
        self.episodes = episodes


class DetailView(object):
    __slots__ = ("title", "year", "plot", "status_line", "art", "actions", "seasons")

    def __init__(self, title, year, plot, status_line, art, actions, seasons):
        self.title = title
        self.year = year
        self.plot = plot
        self.status_line = status_line
        self.art = art
        self.actions = actions
        self.seasons = seasons


#: mode= per action key, spelled once. routes.dispatch answers exactly these modes; a
#: second spelling of one would send a button somewhere the router does not handle.
_ACTION_MODES = {
    "play": "play",
    "request": "request",
    "configure": "settings",
    "trailer": "trailer",
}


def _action_url(key, item, base_url, trailer_key):
    """The params each action's route actually reads, and nothing more.

    "configure" opens the addon's own settings dialog and needs no title at all.
    "trailer" carries only the YouTube id: mode=trailer never reads tmdb_id or
    media_type (see routes.dispatch). "play" resolves against the title itself --
    mode=play re-resolves the Kodi library id from tmdb_id/media_type at click time
    (routes._do_play), so no library id ever belongs in this URL. "request" defers to
    ui.spec.request_urls, the one place that query string is built, rather than
    repeating its params here and risking the two drifting apart.
    """
    mode = _ACTION_MODES[key]
    if key == "configure":
        params = {"mode": mode}
    elif key == "trailer":
        params = {"mode": mode, "youtube_id": trailer_key}
    elif key == "request":
        return request_urls(item, base_url)[0]
    else:
        params = {"mode": mode, "tmdb_id": item.tmdb_id, "media_type": item.media_type}
    return "{0}?{1}".format(base_url, urlencode(params))


def build_view(item, state, resolved, in_library, trailer_key, seasons, media_seasons,
               base_url, image_base, labels, today):
    """`today` is injected, never date.today(): a marker that changes with the wall clock
    cannot be tested.

    `media_seasons` is seerr's raw per-season status list (models.media_seasons), NOT a
    prepared state map: state.season_state is the one place that question is answered, and
    routes._season_state_of calls it exactly this way for the season a user opens. Two
    callers deriving season state differently is precisely the drift this project exists
    to avoid.
    """
    art, info = art_and_info(item, image_base)
    keys = available_actions(state, item.media_type, resolved, in_library, trailer_key)
    # "seasons" is dropped, not absent from available_actions: that function stays the one
    # place deciding what a title offers, and browsing seasons is still one of those things.
    # The window renders the season list itself, so a button beside it would lead nowhere
    # new -- and there is no mode=seasons route left for one to point at.
    actions = [
        Action(key, labels[key], _action_url(key, item, base_url, trailer_key))
        for key in keys
        if key != "seasons"
    ]
    rows = []
    for season in seasons:
        row_state = season_state(season, media_seasons, today)
        rows.append(
            SeasonRow(
                number=season.number,
                label=season_label(season, labels),
                # marker_for(state, item, download): a Season carries release_date, and
                # a season never has a download record of its own.
                marker=marker_for(row_state, season, None),
                state=row_state,
                episode_count=season.episode_count,
            )
        )
    line = status_line(state, item, labels)
    if not line and state is TileState.OWNED and item.media_type != "tv" and not in_library:
        # Said out loud, not left implicit. available_actions returns no action at all
        # here, so without this the screen is a title, artwork and no explanation of why
        # it cannot be played. Same gate available_actions uses for
        # "play", so the two can never disagree about which titles the message applies to.
        line = labels["not_in_library"]
    return DetailView(
        title=item.title,
        year=item.release_date.year if item.release_date else None,
        plot=item.overview,
        status_line=line,
        art=art,
        actions=actions,
        seasons=rows,
    )


def _episode_row(joined, base_url):
    """One episode of the season, from a JoinedEpisode.

    The label, the info dict and the resume rule come from seasons.episode_label_and_info,
    the one place they are decided -- restating them here is how a second row for the same
    episode would start describing it differently.

    seerr has no episode-level request, so an unowned row carries no url at all: there
    is no action it could ever lead to.
    """
    record = joined.record or {}
    label, info = episode_label_and_info(
        joined.number, joined.title, record,
        air_date=joined.air_date, overview=joined.overview,
    )

    url = ""
    if joined.owned and joined.episode_id is not None:
        url = "{0}?{1}".format(
            base_url, urlencode({"mode": "play", "episode_id": joined.episode_id})
        )

    # Kodi's own art wins, because it describes the file that will play. seerr's still is
    # the fallback for a row Kodi has no record of. It is already an absolute URL
    # (models.parse_season_episodes), so image_base is never prefixed to it. Carried data,
    # not yet drawn: the shipped XML's season/episode list has no image control in either
    # layout, so this never renders today -- see CONTEXT.md's entry beside
    # Season.poster_path. Kept for the same reason that entry gives.
    art = dict(record.get("art") or {})
    if not art and joined.still_path:
        art = {"thumb": joined.still_path}
    return EpisodeRow(
        number=joined.number,
        title=joined.title,
        air_date=joined.air_date,
        owned=joined.owned,
        label=label,
        url=url,
        art=art,
        info=info,
    )


def build_season_view(item, season, season_state, resolved, joined_episodes, base_url,
                      image_base, labels):
    """The window's view of one season: a request action when the season's state allows
    one, then the episodes Kodi actually holds.

    `season_state` is the TileState already computed for this season (state.season_state,
    same as build_view's own season rows) -- this function does not recompute it.

    The request gate is SEASON_REQUESTABLE_STATES, not REQUESTABLE_STATES: a PARTIAL
    season is requestable even though a PARTIAL title is not. That is the whole reason
    the two constants are separate; see state.py.
    """
    art, info = art_and_info(item, image_base)
    actions = []
    if season_state in SEASON_REQUESTABLE_STATES:
        if resolved is None:
            # Requesting with nothing resolved would send seerr a body carrying no
            # profile, which it accepts and answers as success -- same rule build_view
            # applies to a whole title, via detail.available_actions.
            actions.append(
                Action("configure", labels["configure"],
                       _action_url("configure", item, base_url, None))
            )
        else:
            # ui.spec.request_urls, season-scoped: the one place this query string is
            # built, so a season row's two URLs can never drift from the whole-title
            # ones built the same way in _action_url above.
            request_url, pick_url = request_urls(item, base_url, season=season.number)
            # labels[SEASON_REQUEST_LABEL_KEY], never labels["request"]: a season-scoped
            # request says so, and the key lives in seasons.py so it is spelled once.
            actions.append(
                Action("request", labels[SEASON_REQUEST_LABEL_KEY], request_url)
            )
            # The season-scoped equivalent of a tile's "Request with...": picking a
            # server and quality profile for this ONE season, not the whole show.
            actions.append(
                Action("request_with", labels["request_with"], pick_url)
            )

    episodes = [_episode_row(joined, base_url) for joined in joined_episodes]
    return SeasonView(
        title=item.title,
        season_name=season_label(season, labels),
        art=art,
        actions=actions,
        episodes=episodes,
    )


def action_spec(action):
    """One action button. Non-folder and carrying no isplayable property, the same flag
    combination every action row in this addon has always used -- see detail.py's module
    docstring for the three branches Kodi selects between.

    `couchseerr.action` lets the XML pick an icon per action without the window needing a
    control id per action, which is exactly the hardcoded-control-id trap that made Kodi's
    own info dialog unusable for this addon.
    """
    return ListItemSpec(
        label=action.label,
        url=action.url,
        is_folder=False,
        art={},
        properties={"couchseerr.action": action.key},
        info={"title": action.label},
        context_items=[],
    )


def season_spec(row, labels):
    """One season row. The marker travels as a property rather than glued onto the label,
    which is the whole point of owning the window: markers.py stays the single source of
    the glyph, and the layout gets to place it in its own column instead of eating the
    first 13 characters of the name.
    """
    detail_text = ""
    if row.episode_count:
        detail_text = labels["episode_count"].format(row.episode_count)
    return ListItemSpec(
        label=row.label,
        # "" means this row leads nowhere on its own: the window swaps its section on the
        # click. Same spelling of "no action" ui/spec.ListItemSpec already documents.
        url="",
        is_folder=False,
        art={},
        properties={
            # seerr.* is a fact about the media; couchseerr.* is how this addon chose to
            # draw it. The state is the fact and means exactly what it means on a tile;
            # the glyph and the "8 episodes" line are this window's presentation of it,
            # and a skin drawing its own badge should read the state, not our glyph.
            "seerr.status": row.state.value,
            "couchseerr.marker": row.marker,
            "couchseerr.detail": detail_text,
        },
        info={"title": row.label},
        context_items=[],
    )


def episode_spec(row):
    """One episode row. `couchseerr.inert` is the XML's handle on "this row is here to be
    read, not clicked" -- seerr has no episode-level request, so an unowned episode can
    carry no action ever. It is derived from the url rather than from `owned` so the
    property and the click behaviour cannot disagree.
    """
    return ListItemSpec(
        label=row.label,
        url=row.url,
        is_folder=False,
        art=dict(row.art or {}),
        properties={"couchseerr.inert": "" if row.url else "1"},
        info=dict(row.info or {}),
        context_items=[],
    )
