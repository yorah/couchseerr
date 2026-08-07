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
"""Send a request, or refuse it. UI-agnostic on purpose.

Takes ids and an explicit {"serverId", "profileId", "is4k"} settings dict -- the shape
`request_config.resolve()` and the cross-server picker both already return -- and
returns seerr's response or raises. It knows nothing about listings, dialogs, settings
files or windows, so the detail window, the context menu and any future caller are all
just callers.
"""
from ..errors import RequestRefused
from ..request_config import request_body
from ..state import REQUESTABLE_STATES, SEASON_REQUESTABLE_STATES, TileState

# Reason strings for refused states. If a state is not in this map, fall back to the
# state's enum value name. This ensures a new TileState member is caught immediately,
# not silently permitted as a duplicate-in-flight request.
REFUSAL_REASONS = {
    TileState.OWNED: "already available",
    TileState.PARTIAL: "already partially available",
    TileState.DOWNLOADING: "already downloading",
    TileState.MONITORED: "already monitored",
    TileState.UNRELEASED: "already monitored, not yet released",
    TileState.PENDING: "already requested, awaiting approval",
}


def send_request(client, settings, media_type, tmdb_id, state, seasons=None):
    """Request a title, or specific seasons of it, with the given settings.

    `state` is the tile's own state, or None when the caller has none (a skin invoking the
    request path directly). When present it is authoritative and costs no API call: seerr's
    duplicate guard blocks only some states, so relying on it alone creates duplicates that
    surface much later, downstream in Radarr or Sonarr.

    When `seasons` is passed, `state` is that *season's* state, checked against
    SEASON_REQUESTABLE_STATES rather than the title-level tuple. The title's own state
    never gates a season request: a partial show is precisely the one whose missing seasons
    must still be requestable.
    """
    allowed = REQUESTABLE_STATES if seasons is None else SEASON_REQUESTABLE_STATES
    if state is not None and state not in allowed:
        reason = REFUSAL_REASONS.get(state, state.value)
        raise RequestRefused(
            "{0}/{1} is {2}".format(media_type, tmdb_id, reason), state
        )
    body = request_body(
        settings, media_type, tmdb_id, "all" if seasons is None else seasons
    )
    return client.post("/request", body)
