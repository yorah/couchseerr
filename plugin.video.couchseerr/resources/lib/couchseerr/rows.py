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
"""Fetch a row's data and turn it into ListItemSpecs."""
from concurrent.futures import ThreadPoolExecutor

from .cache import TTL_DISCOVER, TTL_PROGRESS
from .errors import SeerrRequestError
from .models import parse_discover_item, parse_discover_page, parse_media_state
from .state import tile_state
from .ui.spec import build_spec


class Row(object):
    __slots__ = ("key", "label", "path", "content_type")

    def __init__(self, key, label, path, content_type):
        self.key = key
        self.label = label
        self.path = path
        # Kodi content type for xbmcplugin.setContent(). "movies"/"tvshows" get
        # skins to render a proper poster wall; a mixed row must not claim either,
        # or a title of the wrong media type renders with the wrong art heuristics.
        self.content_type = content_type


ROWS = {
    "trending": Row("trending", "Trending", "/discover/trending", "movies"),
    "upcoming_movies": Row(
        "upcoming_movies", "Upcoming movies", "/discover/movies/upcoming", "movies"
    ),
    "popular_tv": Row("popular_tv", "Popular series", "/discover/tv", "tvshows"),
    "processing": Row("processing", "On the way", "/media", "videos"),
}

# The skin's search screen rebuilds this route's container path on every keystroke, so
# search_row() is re-entered once per letter typed. Below this length, a query is one
# API call for results nobody reads; MIN_QUERY holds the line at "no call at all".
MIN_QUERY = 3


class RowService(object):
    def __init__(self, client, cache, base_url, image_base, language, today_provider,
                 labels=None, max_workers=4):
        self.client = client
        self.cache = cache
        self.base_url = base_url
        self.image_base = image_base
        self.language = language
        self.today_provider = today_provider
        # Passed through unchanged to build_spec() for the two context-menu labels
        # ("Demander" / "Demander avec..."). RowService is pure core and cannot call
        # getLocalizedString itself, so routes.py resolves the strings once and hands
        # the dict in. Defaults to {} for callers (mostly tests) that only exercise
        # code paths build_spec never reaches.
        self.labels = labels if labels is not None else {}
        self.max_workers = max_workers
        # Populated fresh by each discover_row()/processing_row() call: one entry per
        # item whose download record carried no usable progress. Pure core cannot log
        # (no xbmc import allowed here), so it exposes the condition here instead and
        # the Kodi/routes layer is responsible for logging it.
        self.warnings = []

    def _spec(self, item):
        state = tile_state(item, self.today_provider())
        download = item.media.best_download if item.media else None
        if download is not None and download.is_unreadable:
            self.warnings.append(
                "unreadable download progress for {0}/{1}: size={2} size_left={3} "
                "status={4!r}".format(
                    item.media_type, item.tmdb_id, download.size, download.size_left,
                    download.status,
                )
            )
        return build_spec(item, state, self.base_url, self.image_base, self.labels)

    def search_row(self, query):
        """Search seerr for a title.

        The skin's search screen rebuilds this container's path on every keystroke, so
        this route is re-entered per letter. Two consequences are handled here: nothing
        below MIN_QUERY characters reaches the API at all, and every answer is cached
        under a normalised key so backspacing replays instead of re-querying.
        """
        self.warnings = []
        normalised = (query or "").strip().lower()
        if len(normalised) < MIN_QUERY:
            return []

        cache_key = "search:{0}:{1}".format(normalised, self.language)
        payload = self.cache.get(cache_key)
        if payload is None:
            payload = self.client.search(normalised, language=self.language or None)
            self.cache.set(cache_key, payload, TTL_PROGRESS)

        results = [
            raw for raw in (payload.get("results") or [])
            if raw.get("mediaType") in ("movie", "tv")
        ]
        return [self._spec(parse_discover_item(raw)) for raw in results]

    def discover_row(self, key):
        if key == "processing":
            raise ValueError(
                "discover_row() cannot serve 'processing'; call processing_row() instead"
            )
        self.warnings = []
        row = ROWS[key]
        cache_key = "row:{0}:{1}".format(key, self.language)
        payload = self.cache.get(cache_key)
        if payload is None:
            payload = self.client.get(row.path, {"language": self.language or None})
            # Discover payloads embed downloadStatus, so the whole payload -- titles
            # and live progress alike -- is cached at TTL_PROGRESS, not TTL_DISCOVER.
            # Progress correctness on the headline feature outweighs call volume.
            self.cache.set(cache_key, payload, TTL_PROGRESS)
        return [self._spec(item) for item in parse_discover_page(payload)]

    def processing_row(self):
        # Deliberately /media, not /request: titles monitored without a seerr request
        # are the majority here and are the reason this row exists.
        self.warnings = []
        cache_key = "row:processing"
        payload = self.cache.get(cache_key)
        if payload is None:
            payload = self.client.get("/media", {"filter": "processing", "take": 40})
            self.cache.set(cache_key, payload, TTL_PROGRESS)

        results = payload.get("results") or []
        specs = []
        skipped = 0
        hydratable = [thin for thin in results if thin.get("tmdbId") is not None]
        for thin in results:
            if thin.get("tmdbId") is None:
                # Nothing can be fetched or rendered for it, and dropping it quietly
                # would both hide the anomaly and let a row of entirely unusable
                # entries pass as "nothing is on the way".
                skipped += 1
                self.warnings.append(
                    "skipped {0} entry: no tmdbId in the /media payload".format(
                        thin.get("mediaType") or "movie"
                    )
                )

        # A whole _hydrate runs on the worker, cache lookup and cache write included.
        # That is safe for a narrow and load-bearing reason, not because the writes come
        # back to this thread: FileCache is one file per key written through os.replace,
        # and every item has its own key, so concurrent writes never touch the same file.
        # It follows that *no shared cache key may be written concurrently* -- a row-level
        # aggregate or a "last seen" marker added inside _hydrate would break this, and
        # would not look like it was breaking anything.
        #
        # Splitting the cache out of _hydrate would mean duplicating its key construction
        # on the calling thread, which is the likelier bug.
        #
        # warnings and the spec build stay on this thread: futures are consumed in
        # submission order, which also makes the row's order the payload's order.
        with ThreadPoolExecutor(max_workers=self.max_workers) as pool:
            futures = [pool.submit(self._hydrate, thin) for thin in hydratable]
            for thin, future in zip(hydratable, futures):
                try:
                    item = future.result()
                except SeerrRequestError as exc:
                    # /media reads seerr's own DB; /<type>/<id> is a live TMDb passthrough,
                    # so the two disagree for ids TMDb has deleted, merged or never
                    # published -- Radarr's announced placeholders (year 0) above all --
                    # and seerr answers 500. A /media row carries no title and no artwork,
                    # so such an item has nothing renderable behind it; it is reported
                    # through warnings and left out. Transport and auth failures are not
                    # per-item and still propagate.
                    skipped += 1
                    self.warnings.append(
                        "skipped {0}/{1}: {2}".format(
                            thin.get("mediaType") or "movie", thin.get("tmdbId"), exc
                        )
                    )
                    continue
                specs.append(self._spec(item))

        # Every detail failing is not a row of dead placeholders, it is TMDb or seerr
        # being unreachable. Returning [] there would report that as "nothing is on the
        # way", which is a lie the user cannot see through, so it fails loudly instead.
        if results and skipped == len(results):
            raise SeerrRequestError(
                502, "all {0} processing titles failed to resolve".format(skipped)
            )
        return specs

    def _detail_key(self, media_type, tmdb_id):
        """The one place the detail cache key is spelled: detail(), _hydrate() and
        invalidate_detail() must agree, or an invalidation silently misses."""
        return "detail:{0}:{1}:{2}".format(media_type, tmdb_id, self.language)

    def invalidate_detail(self, media_type, tmdb_id):
        """Forget this title's cached detail payload.

        The detail payload is cached at TTL_DISCOVER, fifteen minutes, because titles and
        artwork do not move. Its mediaInfo does: the moment a request succeeds, the cached
        copy describes a title that is no longer requestable. Without this, the container
        refresh fired after a request re-renders from the same payload, still offers
        "Request", and still passes send_request's state guard -- a duplicate request, for
        the whole TTL, around the guard built to prevent exactly that.
        """
        self.cache.delete(self._detail_key(media_type, tmdb_id))

    def detail(self, media_type, tmdb_id):
        """Fetch one title's detail, returning the parsed item, its state and the raw
        payload. The raw payload carries externalIds and relatedVideos, which the detail
        route needs and the parsed item deliberately does not model."""
        cache_key = self._detail_key(media_type, tmdb_id)
        payload = self.cache.get(cache_key)
        if payload is None:
            payload = self.client.get(
                "/{0}/{1}".format(media_type, tmdb_id),
                {"language": self.language or None},
            )
            self.cache.set(cache_key, payload, TTL_DISCOVER)

        merged = dict(payload)
        merged.setdefault("id", tmdb_id)
        merged["mediaType"] = media_type
        item = parse_discover_item(merged)
        return item, tile_state(item, self.today_provider()), payload

    def _hydrate(self, thin):
        """A /media row has ids and status but no title or artwork; fetch the detail.

        Callers screen out entries with no tmdbId; this never returns None, so nothing
        downstream has to treat a falsy result as a hidden failure.
        """
        tmdb_id = thin["tmdbId"]
        media_type = thin.get("mediaType") or "movie"

        cache_key = self._detail_key(media_type, tmdb_id)
        detail = self.cache.get(cache_key)
        if detail is None:
            detail = self.client.get(
                "/{0}/{1}".format(media_type, tmdb_id),
                {"language": self.language or None},
            )
            self.cache.set(cache_key, detail, TTL_DISCOVER)

        merged = dict(detail)
        merged.setdefault("id", tmdb_id)
        merged["mediaType"] = media_type
        # The detail response's own mediaInfo may be cached and stale; the /media row is
        # the fresher source for status and progress, so it wins.
        merged["mediaInfo"] = thin
        item = parse_discover_item(merged)
        item.media = parse_media_state(thin)
        return item
