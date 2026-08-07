import datetime

import pytest

from couchseerr.cache import TTL_DISCOVER, TTL_PROGRESS, FileCache
from couchseerr.client import SeerrClient
from couchseerr.errors import SeerrRequestError, SeerrUnavailable
from couchseerr.rows import ROWS, RowService

TODAY = datetime.date(2026, 1, 6)
LABELS = {"request": "Request", "request_with": "Request with..."}


class FakeClock(object):
    def __init__(self, now=1000.0):
        self.now = now

    def __call__(self):
        return self.now


class RecordingClient(object):
    """Stands in for SeerrClient, serving fixtures and counting calls."""

    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def get(self, path, params=None):
        self.calls.append((path, params))
        for prefix, payload in self.responses.items():
            if path.startswith(prefix):
                return payload
        raise AssertionError("unexpected path {0}".format(path))


def make_service(client, tmp_path, language="fr", cache=None):
    return RowService(
        client=client,
        cache=cache if cache is not None else FileCache(str(tmp_path)),
        base_url="plugin://plugin.video.couchseerr/",
        image_base="https://image.tmdb.org/t/p/w780",
        language=language,
        today_provider=lambda: TODAY,
        labels=LABELS,
    )


def test_row_registry_has_the_four_browse_rows():
    assert set(ROWS) == {"trending", "upcoming_movies", "popular_tv", "processing"}


def test_discover_row_returns_a_spec_per_result(fixture, tmp_path):
    client = RecordingClient({"/discover/trending": fixture("discover_trending")})
    specs = make_service(client, tmp_path).discover_row("trending")
    assert len(specs) == 10
    assert any("62%" in s.label for s in specs)


def test_language_is_passed_to_discover(fixture, tmp_path):
    client = RecordingClient({"/discover/trending": fixture("discover_trending")})
    make_service(client, tmp_path).discover_row("trending")
    assert client.calls[0][1]["language"] == "fr"


def test_blank_language_is_omitted(fixture, tmp_path):
    client = RecordingClient({"/discover/trending": fixture("discover_trending")})
    make_service(client, tmp_path, language="").discover_row("trending")
    assert not client.calls[0][1].get("language")


def test_second_call_is_served_from_cache(fixture, tmp_path):
    client = RecordingClient({"/discover/trending": fixture("discover_trending")})
    service = make_service(client, tmp_path)
    service.discover_row("trending")
    service.discover_row("trending")
    assert len(client.calls) == 1


def test_unknown_row_key_raises(tmp_path):
    with pytest.raises(KeyError):
        make_service(RecordingClient({}), tmp_path).discover_row("nope")


def test_discover_row_cached_at_progress_ttl_not_discover(fixture, tmp_path):
    """Discover payloads embed downloadStatus, so caching them at the long TTL serves
    up to 15 minutes of stale percent/ETA on a downloading tile. TTL_PROGRESS must win."""
    assert TTL_PROGRESS < TTL_DISCOVER  # otherwise this test would not distinguish them
    clock = FakeClock()
    cache = FileCache(str(tmp_path), clock=clock)
    client = RecordingClient({"/discover/trending": fixture("discover_trending")})
    service = make_service(client, tmp_path, cache=cache)

    service.discover_row("trending")
    assert len(client.calls) == 1

    clock.now += TTL_PROGRESS + 1  # well past TTL_PROGRESS, nowhere near TTL_DISCOVER
    service.discover_row("trending")
    assert len(client.calls) == 2, "payload should have expired by TTL_PROGRESS"


def test_row_registry_assigns_content_type_per_row():
    assert ROWS["trending"].content_type == "movies"
    assert ROWS["upcoming_movies"].content_type == "movies"
    assert ROWS["popular_tv"].content_type == "tvshows"
    assert ROWS["processing"].content_type == "videos"


def test_processing_row_hydrates_thin_media_rows(fixture, tmp_path):
    """/media rows carry no title or artwork, so each needs a detail call."""
    detail = {r["id"]: r for r in fixture("discover_trending")["results"]}
    client = RecordingClient({})

    def get(path, params=None):
        client.calls.append((path, params))
        if path.startswith("/media"):
            return fixture("media_processing")
        tmdb_id = int(path.rsplit("/", 1)[1])
        return detail[tmdb_id]

    client.get = get
    specs = make_service(client, tmp_path).processing_row()
    assert len(specs) == 3
    labels = " ".join(s.label for s in specs)
    assert "Fixture Three" in labels
    assert "62%" in labels


def test_processing_row_thin_status_overrides_detail(fixture, tmp_path):
    """The fresher /media row must win even when detail's own mediaInfo disagrees."""
    detail = {r["id"]: r for r in fixture("discover_trending")["results"]}
    stale = dict(detail[103])
    stale["mediaInfo"] = dict(stale["mediaInfo"])
    stale["mediaInfo"]["status"] = 5  # detail claims available (stale cache)...
    stale["mediaInfo"]["status4k"] = 5
    stale["mediaInfo"]["downloadStatus"] = []
    detail[103] = stale

    def get(path, params=None):
        if path.startswith("/media"):
            return fixture("media_processing")  # ...but the thin row says downloading.
        return detail[int(path.rsplit("/", 1)[1])]

    client = RecordingClient({})
    client.get = get
    specs = make_service(client, tmp_path).processing_row()
    statuses = {s.properties["seerr.status"] for s in specs}
    assert "downloading" in statuses
    assert "owned" not in statuses


def test_discover_row_rejects_processing_key(tmp_path):
    with pytest.raises(ValueError):
        make_service(RecordingClient({}), tmp_path).discover_row("processing")


def test_processing_row_falls_back_to_monitored_on_unreadable(fixture, tmp_path):
    """A downloadStatus entry with no usable byte counts must not render as a
    permanent, indistinguishable-from-real "[0%]" -- fall back to monitored and
    surface the condition via service.warnings for the Kodi layer to log."""
    detail = {r["id"]: r for r in fixture("discover_trending")["results"]}
    media = {
        "id": 104,
        "tmdbId": 104,
        "mediaType": "movie",
        "status": 3,
        "status4k": 1,
        # No "size" and no "sizeLeft" at all -- an unparseable/unexpected record.
        "downloadStatus": [{"status": "downloading"}],
        "downloadStatus4k": [],
    }

    def get(path, params=None):
        if path.startswith("/media"):
            return {"results": [media]}
        return detail[int(path.rsplit("/", 1)[1])]

    client = RecordingClient({})
    client.get = get
    service = make_service(client, tmp_path)
    specs = service.processing_row()

    assert len(specs) == 1
    assert specs[0].properties["seerr.status"] == "monitored"
    assert "0%" not in specs[0].label
    assert len(service.warnings) == 1
    assert "104" in service.warnings[0]


def test_discover_and_processing_row_reset_warnings_per_call(fixture, tmp_path):
    """Seeded on purpose: asserting an empty list after a clean call passes just as well
    with both resets deleted, because the list starts empty. Only a warning left over
    from a previous call can prove the reset runs -- otherwise every row would log every
    warning the session has ever produced."""
    detail = {r["id"]: r for r in fixture("discover_trending")["results"]}
    client = RecordingClient({})
    client.get = lambda path, params=None: (
        fixture("discover_trending")
        if path.startswith("/discover")
        else fixture("media_processing")
        if path.startswith("/media")
        else detail[int(path.rsplit("/", 1)[1])]
    )
    service = make_service(client, tmp_path)

    service.warnings.append("left over from an earlier call")
    service.discover_row("trending")
    assert service.warnings == []

    service.warnings.append("left over from an earlier call")
    service.processing_row()
    assert service.warnings == []


def _processing_client(fixture, failing=(), error=None):
    """A client serving media_processing whose detail call fails for chosen tmdb ids."""
    detail = {r["id"]: r for r in fixture("discover_trending")["results"]}
    client = RecordingClient({})

    def get(path, params=None):
        client.calls.append((path, params))
        if path.startswith("/media"):
            return fixture("media_processing")
        tmdb_id = int(path.rsplit("/", 1)[1])
        if tmdb_id in failing:
            raise error or SeerrRequestError(500, "Unable to retrieve movie")
        return detail[tmdb_id]

    client.get = get
    return client


def test_processing_row_skips_an_unresolvable_title(fixture, tmp_path):
    """seerr 500s on ids TMDb no longer serves -- Radarr's announced placeholders. One
    such title must cost one tile, not the whole row."""
    client = _processing_client(fixture, failing={104})
    service = make_service(client, tmp_path)
    specs = service.processing_row()

    assert len(specs) == 2
    assert len(service.warnings) == 1
    assert "104" in service.warnings[0]
    assert "Unable to retrieve movie" in service.warnings[0]


def test_processing_row_raises_when_every_title_fails(fixture, tmp_path):
    """An empty row would misreport a broken TMDb as "nothing is on the way"."""
    client = _processing_client(fixture, failing={103, 104, 105})
    with pytest.raises(SeerrRequestError):
        make_service(client, tmp_path).processing_row()


def test_processing_row_does_not_skip_transport_failures(fixture, tmp_path):
    """Unreachable seerr is a fact about the row, not about one title."""
    client = _processing_client(
        fixture, failing={104}, error=SeerrUnavailable("connection refused")
    )
    with pytest.raises(SeerrUnavailable):
        make_service(client, tmp_path).processing_row()


def test_processing_row_reports_a_thin_item_with_no_tmdb_id(fixture, tmp_path):
    """No tmdbId means no detail call is even possible, so the item cannot be rendered.
    Dropping it silently would be the "returns None to mean failure" shape this project
    bans: it is counted as skipped and named in warnings like any other unresolvable
    title, which also keeps the all-items-failed guard honest."""
    client = RecordingClient({})
    client.get = lambda path, params=None: {
        "results": [{"id": 9, "mediaType": "movie", "status": 3}]
    }
    service = make_service(client, tmp_path)

    with pytest.raises(SeerrRequestError):
        service.processing_row()
    assert len(service.warnings) == 1
    assert "no tmdbId" in service.warnings[0]


def test_processing_row_skips_only_the_item_with_no_tmdb_id(fixture, tmp_path):
    detail = {r["id"]: r for r in fixture("discover_trending")["results"]}
    thin = dict(fixture("media_processing")["results"][0])

    client = RecordingClient({})
    client.get = lambda path, params=None: (
        {"results": [{"id": 9, "mediaType": "movie", "status": 3}, thin]}
        if path.startswith("/media")
        else detail[int(path.rsplit("/", 1)[1])]
    )
    service = make_service(client, tmp_path)

    assert len(service.processing_row()) == 1
    assert len(service.warnings) == 1


def test_blank_language_is_omitted_from_the_detail_call(fixture, tmp_path):
    """The client drops params whose value is None. Sending language="" instead would
    put an empty language on the query string, which TMDb answers in en-US."""
    client = _processing_client(fixture)
    make_service(client, tmp_path, language="").processing_row()

    detail_calls = [c for c in client.calls if not c[0].startswith("/media")]
    assert detail_calls, "no detail call recorded; this guard would pass vacuously"
    assert all(params.get("language") is None for _, params in detail_calls)


def test_processing_row_uses_media_filter_not_request_filter(fixture, tmp_path):
    """Requests would omit titles monitored without a seerr request - the row's whole point."""
    detail = {r["id"]: r for r in fixture("discover_trending")["results"]}

    def get(path, params=None):
        if path.startswith("/media"):
            assert params.get("filter") == "processing"
            return fixture("media_processing")
        return detail[int(path.rsplit("/", 1)[1])]

    client = RecordingClient({})
    client.get = get
    make_service(client, tmp_path).processing_row()


def test_processing_row_fetches_details_concurrently(fixture, tmp_path):
    """Serial hydration makes the row's latency the sum of every detail call. The row is
    the one people watch while something downloads, so it is the one that must feel live."""
    import threading

    seen = []
    barrier = threading.Barrier(3, timeout=5)
    detail = {r["id"]: r for r in fixture("discover_trending")["results"]}

    def get(path, params=None):
        if path.startswith("/media"):
            return fixture("media_processing")
        seen.append(path)
        # Fails with BrokenBarrierError unless three calls are in flight together.
        barrier.wait()
        return detail[int(path.rsplit("/", 1)[1])]

    client = RecordingClient({})
    client.get = get
    specs = make_service(client, tmp_path).processing_row()

    assert len(specs) == 3
    assert len(seen) == 3


def test_concurrent_hydration_keeps_the_payload_order(fixture, tmp_path):
    """The order guarantee, with the completion order deliberately reversed.

    Without skew the workers return in submission order anyway, so the assertion held
    just as well against an as_completed loop -- it could not fail on the property it
    names. Here the first item submitted blocks until the last one has finished, so
    completion order is the exact reverse of submission order, and only consuming the
    futures in submission order still yields the payload's order.

    An Event rather than sleeps: a timing race decided by a sleep length is a test that
    passes on a fast machine and flakes on a loaded one.
    """
    import threading

    ids = [r["tmdbId"] for r in fixture("media_processing")["results"]]
    assert len(ids) > 1, "a single-item row cannot exercise ordering"
    last_finished = threading.Event()
    detail = {r["id"]: r for r in fixture("discover_trending")["results"]}
    completed = []

    client = RecordingClient({})

    def get(path, params=None):
        client.calls.append((path, params))
        if path.startswith("/media"):
            return fixture("media_processing")
        tmdb_id = int(path.rsplit("/", 1)[1])
        if tmdb_id == ids[0]:
            # Submitted first, finishes last. max_workers is 4, so every item is already
            # in flight and this cannot deadlock on a starved pool.
            assert last_finished.wait(timeout=5), "the last item never ran"
        if tmdb_id == ids[-1]:
            last_finished.set()
        completed.append(tmdb_id)
        return detail[tmdb_id]

    client.get = get
    specs = make_service(client, tmp_path).processing_row()

    assert completed[-1] == ids[0], "the skew did not take; ordering is untested"
    assert [s.url.split("tmdb_id=")[1].split("&")[0] for s in specs] == [str(i) for i in ids]


def test_a_single_failure_still_only_costs_its_own_tile(fixture, tmp_path):
    client = _processing_client(fixture, failing={104})
    service = make_service(client, tmp_path)
    specs = service.processing_row()
    assert len(specs) == 2
    assert len(service.warnings) == 1


# --- detail() and its invalidation -------------------------------------------


def _detail_client(fixture):
    """Serves one movie detail and counts how many times it was actually fetched."""
    payload = fixture("discover_trending")["results"][0]
    client = RecordingClient({})

    def get(path, params=None):
        client.calls.append((path, params))
        return payload

    client.get = get
    return client


def test_detail_is_served_from_the_cache_on_the_second_call(fixture, tmp_path):
    """The premise of the invalidation test below: without a cache hit here, the stale
    payload could not survive a request and nothing would need invalidating."""
    client = _detail_client(fixture)
    service = make_service(client, tmp_path)

    service.detail("movie", 101)
    service.detail("movie", 101)

    assert len(client.calls) == 1


def test_invalidate_detail_forces_the_next_call_to_refetch(fixture, tmp_path):
    """After a successful request the cached payload still says "not requested", and it
    says so for fifteen minutes (TTL_DISCOVER). The container refresh that follows a
    request re-reads this key, so an entry that survives it re-offers the request and
    walks straight around send_request's duplicate guard."""
    client = _detail_client(fixture)
    service = make_service(client, tmp_path)

    service.detail("movie", 101)
    service.invalidate_detail("movie", 101)
    service.detail("movie", 101)

    assert len(client.calls) == 2


def test_invalidate_detail_leaves_other_titles_cached(fixture, tmp_path):
    """One title's key, not the whole cache: a request must not cost every other detail
    already fetched."""
    client = _detail_client(fixture)
    service = make_service(client, tmp_path)

    service.detail("movie", 101)
    service.detail("movie", 102)
    service.invalidate_detail("movie", 101)
    service.detail("movie", 102)

    assert len(client.calls) == 2


def test_invalidate_of_an_uncached_key_is_not_an_error(fixture, tmp_path):
    """A request fired from a skin's action property reaches this without a detail view
    ever having run. "Not cached" is the postcondition either way."""
    client = _detail_client(fixture)
    service = make_service(client, tmp_path)

    service.invalidate_detail("movie", 101)

    assert service.detail("movie", 101)[0].tmdb_id == 101
