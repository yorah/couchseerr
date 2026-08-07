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
"""Parsing of seerr responses into typed values. No I/O, no Kodi, no clock."""
import datetime


class DownloadProgress(object):
    __slots__ = ("size", "size_left", "time_left", "estimated_completion_time", "status")

    def __init__(self, size, size_left, time_left, estimated_completion_time, status):
        self.size = size
        self.size_left = size_left
        self.time_left = time_left
        self.estimated_completion_time = estimated_completion_time
        self.status = status

    @property
    def percent(self):
        # size_left is None when seerr omits or nulls sizeLeft -- unknown progress,
        # not zero bytes remaining -- and must not read as "complete".
        if not self.size or self.size_left is None:
            return 0.0
        if self.size_left <= 0:
            return 100.0
        done = self.size - self.size_left
        return max(0.0, min(100.0, (done / float(self.size)) * 100.0))

    @property
    def is_unreadable(self):
        """True whenever `percent` cannot produce a meaningful value.

        Mirrors `percent`'s own give-up condition (`not size or size_left is None`)
        exactly: a falsy `size` (missing or zero) OR a missing `size_left` each mean
        "we received a download record we could not interpret", not "0% done". The
        populated `downloadStatus` shape has never been observed live (see
        docs/private/CONTEXT.md), so this is the one signal that must not be allowed
        to silently render as a real percentage.
        """
        return not self.size or self.size_left is None

    def __repr__(self):
        return "<DownloadProgress {0:.0f}%>".format(self.percent)


def effective_status(status, status4k):
    """A title -- or a season, which carries the same two fields -- in flight on either
    track is in flight. The one home for this rule: MediaState.effective_status below and
    state.season_state both answer it through here, so it cannot read one way for a title
    and another for its own seasons."""
    return max(status, status4k)


class MediaState(object):
    __slots__ = ("status", "status4k", "downloads")

    def __init__(self, status, status4k, downloads):
        self.status = status
        self.status4k = status4k
        self.downloads = downloads

    @property
    def effective_status(self):
        """A title in flight on either track is in flight."""
        return effective_status(self.status, self.status4k)

    @property
    def best_download(self):
        if not self.downloads:
            return None
        return max(self.downloads, key=lambda d: d.percent)


class DiscoverItem(object):
    __slots__ = (
        "tmdb_id",
        "media_type",
        "title",
        "overview",
        "poster_path",
        "backdrop_path",
        "release_date",
        "media",
    )

    def __init__(
        self,
        tmdb_id,
        media_type,
        title,
        overview="",
        poster_path=None,
        backdrop_path=None,
        release_date=None,
        media=None,
    ):
        self.tmdb_id = tmdb_id
        self.media_type = media_type
        self.title = title
        self.overview = overview
        self.poster_path = poster_path
        self.backdrop_path = backdrop_path
        self.release_date = release_date
        self.media = media


class Season(object):
    """One season of a show, as the season listing needs it.

    `release_date` is named for what markers.marker_for reads off an item, not for what
    seerr calls it (`airDate`): a Season is handed to marker_for directly, and a
    differently named attribute would fail only on the device.
    """

    __slots__ = ("number", "name", "episode_count", "release_date", "poster_path")

    def __init__(self, number, name, episode_count, release_date, poster_path):
        self.number = number
        self.name = name
        self.episode_count = episode_count
        self.release_date = release_date
        self.poster_path = poster_path


def _parse_download(raw):
    return DownloadProgress(
        size=raw.get("size") or 0,
        # Missing or explicit null must stay None (unknown), not collapse to 0
        # (which means "nothing left, complete"). See DownloadProgress.percent.
        size_left=raw.get("sizeLeft"),
        time_left=raw.get("timeLeft"),
        estimated_completion_time=raw.get("estimatedCompletionTime"),
        status=raw.get("status") or "",
    )


def parse_media_state(raw):
    downloads = [
        _parse_download(d)
        for key in ("downloadStatus", "downloadStatus4k")
        for d in (raw.get(key) or [])
    ]
    return MediaState(
        status=raw.get("status") or 0,
        status4k=raw.get("status4k") or 0,
        downloads=tuple(downloads),
    )


def _parse_date(value):
    """Leading 10 characters, so a plain date and a full ISO timestamp both parse.

    Anything that is not a string is rejected up front rather than left to fail inside
    the slice: seerr's dates come straight from TMDb, and a number raises TypeError while
    a dict raises KeyError (slices are hashable from Python 3.12). Enumerating the ways a
    wrong type can fail is how one of them gets missed. This runs inside a pure parser
    with no handling above it before dispatch's catch-all, so an uncaught raise here
    costs the entire row.
    """
    if not value or not isinstance(value, str):
        return None
    try:
        return datetime.datetime.strptime(value[:10], "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def parse_discover_item(raw):
    media_type = raw.get("mediaType") or "movie"
    if media_type == "tv":
        title = raw.get("name") or raw.get("originalName") or ""
        released = raw.get("firstAirDate")
    else:
        title = raw.get("title") or raw.get("originalTitle") or ""
        released = raw.get("releaseDate")

    media_info = raw.get("mediaInfo")
    return DiscoverItem(
        tmdb_id=raw.get("id"),
        media_type=media_type,
        title=title,
        overview=raw.get("overview") or "",
        poster_path=raw.get("posterPath"),
        backdrop_path=raw.get("backdropPath"),
        release_date=_parse_date(released),
        media=parse_media_state(media_info) if media_info else None,
    )


def parse_discover_page(raw):
    return [parse_discover_item(r) for r in (raw.get("results") or [])]


def parse_seasons(raw):
    """Seasons worth showing, ascending by number.

    Two are dropped here rather than in a builder, so that no consumer can forget the
    rule: season 0 (Specials, which seerr returns first) and any season with no episodes,
    which is TMDb's placeholder for an announced-but-unmade season. Requesting the latter
    downloads nothing while reporting success.
    """
    seasons = []
    for entry in (raw.get("seasons") or []):
        number = entry.get("seasonNumber")
        if not isinstance(number, int) or number <= 0:
            continue
        if not entry.get("episodeCount"):
            continue
        seasons.append(
            Season(
                number=number,
                name=entry.get("name") or "",
                episode_count=entry["episodeCount"],
                release_date=_parse_date(entry.get("airDate")),
                poster_path=entry.get("posterPath"),
            )
        )
    return sorted(seasons, key=lambda season: season.number)


def media_seasons(raw):
    """seerr's per-season status entries, or [] when it tracks nothing.

    Three shapes mean the same thing and are all real: no mediaInfo at all (a movie
    payload), mediaInfo null (a show seerr does not track, measured 2026-08-06), and
    mediaInfo carrying a null seasons key. All are "no season is tracked", which is a
    state, not a failure.
    """
    info = raw.get("mediaInfo") or {}
    return info.get("seasons") or []
