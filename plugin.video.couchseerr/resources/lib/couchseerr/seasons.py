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
"""Build the two season-level listings: a show's seasons, and one season's actions.

Pure, like detail.py: parsed values and labels in, ListItemSpecs out. Nothing here
imports Kodi and nothing here builds a ListItem -- ui/spec.py plus kodi/adapter.py remain
the single construction site.

Every season entry is a folder. A season click therefore never performs an action, which
is the v2 rule ("a tile click opens the actions available, it does not take one") applied
one level down. It is also what resolves the one collision in this feature: a partial
season is both browsable and re-requestable, and only a listing can offer both without
the click meaning two different things.
"""
try:
    from urllib.parse import urlencode
except ImportError:  # pragma: no cover
    from urllib import urlencode

from .markers import marker_for
from .state import SEASON_REQUESTABLE_STATES, season_state
from .ui.spec import ListItemSpec, art_and_info, request_context_items, request_urls


def season_label(season, labels):
    """seerr localises a season's name through TMDb, so prefer it; fall back to the
    addon's own localised format when TMDb has no name for it."""
    return season.name or labels["season"].format(season.number)


def build_season_list(item, seasons, media_seasons, base_url, image_base, labels, today):
    """One folder entry per season, each carrying its own marker.

    `media_seasons` is seerr's raw per-season status list (models.media_seasons); `today`
    is the injected clock state.season_state needs for the UNRELEASED boundary.
    """
    show_art, info = art_and_info(item, image_base)
    specs = []
    for season in seasons:
        state = season_state(season, media_seasons, today)
        # marker_for reads release_date off whatever it is given, and a Season carries
        # one; DOWNLOADING is never derived per season, so the download argument is
        # always None here.
        marker = marker_for(state, season, None)
        name = season_label(season, labels)
        label = "{0} {1}".format(marker, name).strip() if marker else name

        art = dict(show_art)
        if season.poster_path:
            art["poster"] = image_base + season.poster_path
            art["thumb"] = art["poster"]

        context_items = []
        if state in SEASON_REQUESTABLE_STATES:
            request_url, pick_url = request_urls(item, base_url, season=season.number)
            context_items = request_context_items(request_url, pick_url, labels)

        url = "{0}?{1}".format(
            base_url,
            urlencode(
                {"mode": "season", "tmdb_id": item.tmdb_id, "season": season.number}
            ),
        )
        specs.append(
            ListItemSpec(
                label=label,
                url=url,
                is_folder=True,
                art=art,
                properties={
                    "seerr.status": state.value,
                    "seerr.season": str(season.number),
                },
                # The show's own info, not the season's: the skin's info pane renders
                # whatever is focused, so an entry describing itself would blank the show
                # the moment the user moved onto it.
                info=dict(info),
                context_items=context_items,
            )
        )
    return specs


def build_season_detail(item, season, state, resolved, records, base_url, image_base,
                        labels):
    """The actions for one season: a request when its state allows one, then the episodes
    of it Kodi actually holds.

    Episodes come from Kodi's own library (`records`, VideoLibrary.GetEpisodes), never from
    seerr. Everything listed is therefore playable by definition, and watched state, resume
    point, thumb and plot are Kodi's own and correct. Episodes the user does not own are not
    listed at all: seerr cannot request a single episode, so an entry for one could only sit
    there doing nothing.

    An empty `records` produces an explanatory line rather than an empty listing, which on
    a TV is indistinguishable from a broken addon. One line covers both causes -- no library
    id for the show, or a season Kodi never scanned -- because the user's position is the
    same in both.
    """
    show_art, show_info = art_and_info(item, image_base)
    specs = []

    if state in SEASON_REQUESTABLE_STATES:
        if resolved is None:
            # Requesting with nothing resolved would send seerr a body carrying no
            # profile, which it accepts and answers as success. Same rule as detail.py.
            specs.append(
                _action(labels["configure"], {"mode": "settings"}, base_url, show_art,
                        show_info, state, [])
            )
        else:
            request_url, pick_url = request_urls(item, base_url, season=season.number)
            specs.append(
                _action(
                    labels["request_season"],
                    {"mode": "request", "tmdb_id": item.tmdb_id,
                     "media_type": item.media_type, "season": season.number},
                    base_url, show_art, show_info, state,
                    request_context_items(request_url, pick_url, labels),
                )
            )

    if not records:
        specs.append(
            _action(labels["not_in_library"], None, base_url, show_art, show_info,
                    state, [])
        )
        return specs

    for record in records:
        specs.append(_episode(record, base_url, state))
    return specs


def _action(label, params, base_url, art, info, state, context_items):
    """One non-folder action row carrying the show's art and info.

    params=None is a line the user reads, not an action, so it carries no URL. No
    isplayable property is set here: see detail.py's module docstring for why that flag
    combination is the one that makes Kodi run the addon rather than try to play the URL.
    """
    url = ""
    if params is not None:
        url = "{0}?{1}".format(base_url, urlencode(params))
    return ListItemSpec(
        label=label, url=url, is_folder=False, art=dict(art),
        properties={"seerr.status": state.value}, info=dict(info),
        context_items=context_items,
    )


def _episode(record, base_url, state):
    """One episode of Kodi's own library.

    This entry describes *itself*, unlike every other entry in this addon: it is the thing
    that gets played, so its own plot, thumb and watched state are what the info pane
    should show while it is focused.

    It carries no marker. Being owned is a precondition of appearing here, so a marker
    would be constant and say nothing.
    """
    info = {"title": record.get("title") or "", "plot": record.get("plot") or ""}
    aired = record.get("firstaired")
    if aired:
        info["premiered"] = aired
    if record.get("playcount") is not None:
        info["playcount"] = record["playcount"]
    resume = record.get("resume") or {}
    # A zero position is "never started", not a resume point: passing it would make Kodi
    # offer to resume from the beginning of every unwatched episode.
    if resume.get("position"):
        info["resume"] = (resume["position"], resume.get("total") or 0)

    url = "{0}?{1}".format(
        base_url, urlencode({"mode": "play", "episode_id": record["episodeid"]})
    )
    number = record.get("episode")
    # Kodi always supplies this for a scanned episode; the fallback exists only for a
    # malformed record, and "0. Title" would read as a real, wrong episode number rather
    # than as the degradation it is -- so fall back to the bare title instead.
    label = ("{0}. {1}".format(number, info["title"]) if number else info["title"]).strip()
    return ListItemSpec(
        label=label,
        url=url,
        is_folder=False,
        art=dict(record.get("art") or {}),
        properties={"seerr.status": state.value},
        info=info,
        context_items=[],
    )
