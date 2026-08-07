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
"""Marker text, in one place.

Glyph coverage varies by skin font and Poster labels are narrow, so this table is
expected to be adjusted once on a real TV. Keeping it here makes that a one-line change.
"""
from .state import TileState

#: Not a TileState -- the DOWNLOADING marker's variant used when the download record
#: carries a time_left. Keeping both templates here, rather than a literal in
#: marker_for, is what keeps the marker text retunable in exactly one place.
DOWNLOADING_WITH_ETA = "downloading_with_eta"

MARKERS = {
    TileState.OWNED: "[✓]",
    TileState.PARTIAL: "[◐]",
    TileState.DOWNLOADING: "[{percent}%]",  # filled in with live percent
    DOWNLOADING_WITH_ETA: "[{percent}% · {eta}]",  # percent + ETA, kept compact
    TileState.MONITORED: "[⋯]",
    TileState.UNRELEASED: "[{date}]",  # filled in with the release date
    TileState.PENDING: "[⌛]",
    TileState.ACTIONABLE: "",
}


def marker_for(state, item, download):
    if state is TileState.DOWNLOADING:
        if download is None:
            # state and download disagree -- rendering the raw template literally
            # would be worse than a crash: it would look like real tile text.
            raise ValueError("marker_for: DOWNLOADING state requires a download, got None")
        # Truncate, never round: 99.6% must read as 99, not 100 -- "100%" is reserved
        # for a download that is actually complete (see DownloadProgress.percent).
        percent = int(download.percent)
        if download.time_left:
            return MARKERS[DOWNLOADING_WITH_ETA].format(percent=percent, eta=download.time_left)
        return MARKERS[TileState.DOWNLOADING].format(percent=percent)
    if state is TileState.UNRELEASED:
        if item.release_date is None:
            raise ValueError("marker_for: UNRELEASED state requires a release_date, got None")
        return MARKERS[TileState.UNRELEASED].format(date=item.release_date.isoformat())
    return MARKERS.get(state, "")
