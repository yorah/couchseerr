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
"""Derive the single tile state from a parsed item. Pure; the clock is a parameter."""
from enum import Enum

from .models import effective_status

STATUS_UNKNOWN = 1
STATUS_PENDING = 2
STATUS_PROCESSING = 3
STATUS_PARTIALLY_AVAILABLE = 4
STATUS_AVAILABLE = 5


class TileState(Enum):
    OWNED = "owned"
    PARTIAL = "partial"
    DOWNLOADING = "downloading"
    MONITORED = "monitored"
    UNRELEASED = "unreleased"
    PENDING = "pending"
    ACTIONABLE = "actionable"


# The one place this question is answered. A tile that advertises itself as requestable
# and a detail window that offers a request must never disagree.
REQUESTABLE_STATES = (TileState.ACTIONABLE,)

#: The states from which a *season* may be requested. Wider than REQUESTABLE_STATES by
#: TileState.PARTIAL on purpose: a partial title may have every season already requested,
#: while a partial season is one with missing episodes that a fresh request tells Sonarr
#: to search for. Both tuples live here, next to the one derivation, so a tile, a title's
#: detail view and a season's cannot answer "is this requestable" differently.
SEASON_REQUESTABLE_STATES = (TileState.ACTIONABLE, TileState.PARTIAL)


def tile_state(item, today):
    media = item.media
    if media is None:
        return TileState.ACTIONABLE

    status = media.effective_status

    if status == STATUS_AVAILABLE:
        return TileState.OWNED
    if status == STATUS_PARTIALLY_AVAILABLE:
        return TileState.PARTIAL
    if status == STATUS_PENDING:
        return TileState.PENDING
    if status == STATUS_PROCESSING:
        # An active grab is the strongest signal available, so it outranks the release
        # date: a pre-release download is still arriving. A download record that
        # yielded no usable byte counts is not a real 0% -- treat it as if there
        # were no active download rather than render a false "[0%]" forever.
        download = media.best_download
        if download is not None and not download.is_unreadable:
            return TileState.DOWNLOADING
        if item.release_date is not None and item.release_date > today:
            return TileState.UNRELEASED
        return TileState.MONITORED
    return TileState.ACTIONABLE


def season_state(season, media_seasons, today):
    """The state of one season. Pure; the clock is a parameter.

    `media_seasons` is seerr's raw `mediaInfo.seasons` list (see models.media_seasons).
    A season with no entry in it is ACTIONABLE, which is the ordinary case rather than a
    fallback: seerr records a season only once something has been requested for it.

    DOWNLOADING is never derived here. `downloadStatus` is title-level in the payload and
    its populated shape has never been observed, so a per-season percentage would be a
    guess attributed to a specific season.
    """
    entry = None
    for raw in (media_seasons or []):
        if raw.get("seasonNumber") == season.number:
            entry = raw
            break
    if entry is None:
        return TileState.ACTIONABLE

    # Same rule as MediaState.effective_status, through the one function both answer it
    # with: a season in flight on either track is in flight, and STATUS_UNKNOWN (1) ranks
    # lowest so a 4K track nobody uses never wins.
    status = effective_status(entry.get("status") or 0, entry.get("status4k") or 0)

    if status == STATUS_AVAILABLE:
        return TileState.OWNED
    if status == STATUS_PARTIALLY_AVAILABLE:
        return TileState.PARTIAL
    if status == STATUS_PENDING:
        return TileState.PENDING
    if status == STATUS_PROCESSING:
        # UNRELEASED demands a release_date -- markers.marker_for raises without one --
        # so a season whose airDate did not parse stays MONITORED.
        if season.release_date is not None and season.release_date > today:
            return TileState.UNRELEASED
        return TileState.MONITORED
    return TileState.ACTIONABLE
