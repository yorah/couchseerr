from urllib.parse import parse_qsl, urlparse

import pytest

from couchseerr.cache import FileCache
from couchseerr.rows import MIN_QUERY, RowService

TODAY = __import__("datetime").date(2026, 1, 6)
LABELS = {"request": "Request", "request_with": "Request with..."}


class RecordingClient(object):
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def get(self, path, params=None):
        self.calls.append((path, params))
        return self.payload

    def search(self, query, language=None, page=1):
        self.calls.append(("/search", {"query": query, "language": language}))
        return self.payload


def _service(client, tmp_path, language="fr"):
    return RowService(client=client, cache=FileCache(str(tmp_path)),
                      base_url="plugin://plugin.video.couchseerr/",
                      image_base="https://image.tmdb.org/t/p/w780",
                      language=language, today_provider=lambda: TODAY,
                      labels=LABELS)


def _tmdb_id(spec):
    return dict(parse_qsl(urlparse(spec.url).query))["tmdb_id"]


def test_a_short_query_returns_nothing_without_calling_seerr(fixture, tmp_path):
    """The skin reloads this container on every keystroke. Querying on one letter is one
    API call per letter typed, for results nobody reads."""
    client = RecordingClient(fixture("search_dune"))
    for query in ("", "d", "du"):
        assert _service(client, tmp_path).search_row(query) == []
    assert client.calls == []


def test_a_long_enough_query_searches(fixture, tmp_path):
    client = RecordingClient(fixture("search_dune"))
    specs = _service(client, tmp_path).search_row("dune")

    assert client.calls[0][0] == "/search"
    assert client.calls[0][1]["query"] == "dune"
    assert len(specs) == 2  # the person result is dropped


def test_people_are_dropped_from_results(fixture, tmp_path):
    """seerr returns people; a person rendered as a tile is unplayable, unrequestable,
    and indistinguishable from a broken film.

    The fixture's person entry carries "name", not "title"/"originalTitle", so
    parse_discover_item() gives it an empty title with or without the mediaType
    filter -- asserting on the label would pass even with the filter deleted. Assert
    on identity instead: the surviving tmdb ids must be exactly the movie and tv
    entries' ids (201, 202), with the person's id (203) absent.
    """
    specs = _service(RecordingClient(fixture("search_dune")), tmp_path).search_row("dune")
    assert {_tmdb_id(s) for s in specs} == {"201", "202"}


def test_results_are_cached_per_query(fixture, tmp_path):
    """Backspacing and retyping is normal; it must not re-query."""
    client = RecordingClient(fixture("search_dune"))
    service = _service(client, tmp_path)
    service.search_row("dune")
    service.search_row("dune")
    assert len(client.calls) == 1


def test_the_query_is_normalised_for_the_cache_key(fixture, tmp_path):
    client = RecordingClient(fixture("search_dune"))
    service = _service(client, tmp_path)
    service.search_row("Dune")
    service.search_row(" dune ")
    assert len(client.calls) == 1


def test_the_language_is_passed_through(fixture, tmp_path):
    client = RecordingClient(fixture("search_dune"))
    _service(client, tmp_path, language="fr").search_row("dune")
    assert client.calls[0][1]["language"] == "fr"


def test_different_languages_do_not_share_a_cached_result(fixture, tmp_path):
    """The cache key folds in language; two services sharing a cache directory but
    configured for different languages must each hit seerr rather than one serving
    the other's cached (and differently-translated) payload."""
    client = RecordingClient(fixture("search_dune"))
    _service(client, tmp_path, language="fr").search_row("dune")
    _service(client, tmp_path, language="en").search_row("dune")
    assert len(client.calls) == 2
