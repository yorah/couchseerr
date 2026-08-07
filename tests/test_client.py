import json

import pytest

from couchseerr.client import SeerrClient
from couchseerr.errors import SeerrAuthError, SeerrRequestError, SeerrUnavailable


def make_transport(status, payload, recorder=None):
    def _transport(url, headers, timeout, data=None):
        if recorder is not None:
            recorder.append((url, headers, timeout))
        body = json.dumps(payload).encode() if payload is not None else b""
        return status, body

    return _transport


def test_get_returns_parsed_json(fixture):
    client = SeerrClient(
        "http://seerr.test:5055", "k", transport=make_transport(200, fixture("status"))
    )
    assert client.get("/status")["version"] == "3.4.1"


def test_get_builds_url_with_api_prefix_and_params():
    calls = []
    client = SeerrClient(
        "http://seerr.test:5055", "k", transport=make_transport(200, {}, calls)
    )
    client.get("/discover/trending", {"language": "fr", "page": 1})
    url, headers, _ = calls[0]
    assert url.startswith("http://seerr.test:5055/api/v1/discover/trending?")
    assert "language=fr" in url and "page=1" in url
    assert headers["X-Api-Key"] == "k"


def test_trailing_slash_in_base_url_does_not_double_up():
    calls = []
    client = SeerrClient(
        "http://seerr.test:5055/", "k", transport=make_transport(200, {}, calls)
    )
    client.get("/status")
    assert calls[0][0] == "http://seerr.test:5055/api/v1/status"


def test_none_params_are_omitted():
    calls = []
    client = SeerrClient(
        "http://seerr.test:5055", "k", transport=make_transport(200, {}, calls)
    )
    client.get("/discover/trending", {"language": None, "page": 2})
    assert "language" not in calls[0][0]
    assert "page=2" in calls[0][0]


@pytest.mark.parametrize("status", [401, 403])
def test_auth_failures_raise_auth_error(status, fixture):
    client = SeerrClient(
        "http://seerr.test:5055",
        "k",
        transport=make_transport(status, fixture("error_401")),
    )
    with pytest.raises(SeerrAuthError):
        client.get("/status")


def test_server_error_carries_status_and_message(fixture):
    client = SeerrClient(
        "http://seerr.test:5055", "k", transport=make_transport(500, fixture("error_500"))
    )
    with pytest.raises(SeerrRequestError) as excinfo:
        client.get("/status")
    assert excinfo.value.status_code == 500
    assert "Internal Server Error" in excinfo.value.message


def test_transport_failure_raises_unavailable():
    def boom(url, headers, timeout, data=None):
        raise OSError("connection refused")

    client = SeerrClient("http://seerr.test:5055", "k", transport=boom)
    with pytest.raises(SeerrUnavailable):
        client.get("/status")


def test_malformed_json_raises_request_error():
    def bad_json(url, headers, timeout, data=None):
        return 200, b"<html>not json</html>"

    client = SeerrClient("http://seerr.test:5055", "k", transport=bad_json)
    with pytest.raises(SeerrRequestError):
        client.get("/status")


def test_client_never_returns_none_on_failure():
    """Regression guard: the failure mode this codebase exists to avoid is a client
    that reports success by returning None."""
    def boom(url, headers, timeout, data=None):
        raise OSError("down")

    client = SeerrClient("http://seerr.test:5055", "k", transport=boom)
    try:
        result = client.get("/status")
    except SeerrUnavailable:
        return
    pytest.fail(f"expected SeerrUnavailable, got {result!r}")


def test_null_json_body_raises_request_error():
    """A 2xx response whose body is the literal JSON `null` parses to None in Python --
    get() must not hand that back, since a None return is exactly the "None means
    failure" ambiguity this task exists to eliminate."""
    def null_body(url, headers, timeout, data=None):
        return 200, b"null"

    client = SeerrClient("http://seerr.test:5055", "k", transport=null_body)
    with pytest.raises(SeerrRequestError):
        client.get("/status")


def test_post_sends_json_and_returns_the_parsed_body(fixture):
    sent = {}

    def transport(url, headers, timeout, data=None):
        sent["url"] = url
        sent["headers"] = headers
        sent["data"] = data
        return 201, json.dumps(fixture("request_created")).encode()

    client = SeerrClient("http://seerr:5055", "key", transport=transport)
    result = client.post("/request", {"mediaType": "movie", "mediaId": 693134})

    assert result["id"] == 42
    assert sent["url"] == "http://seerr:5055/api/v1/request"
    assert sent["headers"]["Content-Type"] == "application/json"
    assert json.loads(sent["data"].decode()) == {"mediaType": "movie", "mediaId": 693134}


def test_post_surfaces_a_quota_rejection_as_a_typed_error(fixture):
    def transport(url, headers, timeout, data=None):
        return 403, json.dumps(fixture("error_quota")).encode()

    client = SeerrClient("http://seerr:5055", "key", transport=transport)
    with pytest.raises(SeerrAuthError) as excinfo:
        client.post("/request", {})
    assert "quota" in str(excinfo.value).lower()


def test_post_surfaces_a_duplicate_rejection_with_seerr_message(fixture):
    def transport(url, headers, timeout, data=None):
        return 409, json.dumps(fixture("error_duplicate")).encode()

    client = SeerrClient("http://seerr:5055", "key", transport=transport)
    with pytest.raises(SeerrRequestError) as excinfo:
        client.post("/request", {})
    assert "already exists" in str(excinfo.value)


def test_servers_uses_the_radarr_endpoint_for_movies(fixture):
    calls = []

    def transport(url, headers, timeout, data=None):
        calls.append(url)
        return 200, json.dumps(fixture("service_radarr_two")).encode()

    client = SeerrClient("http://seerr:5055", "key", transport=transport)
    servers = client.servers("movie")

    assert calls == ["http://seerr:5055/api/v1/service/radarr"]
    assert [s["id"] for s in servers] == [0, 1]


def test_servers_uses_the_sonarr_endpoint_for_tv(fixture):
    calls = []

    def transport(url, headers, timeout, data=None):
        calls.append(url)
        return 200, json.dumps(fixture("service_sonarr_one")).encode()

    SeerrClient("http://seerr:5055", "key", transport=transport).servers("tv")
    assert calls == ["http://seerr:5055/api/v1/service/sonarr"]


def test_server_detail_returns_profiles(fixture):
    def transport(url, headers, timeout, data=None):
        assert url.endswith("/service/radarr/0")
        return 200, json.dumps(fixture("service_radarr_detail")).encode()

    detail = SeerrClient("http://s:5055", "k", transport=transport).server_detail("movie", 0)
    assert [p["name"] for p in detail["profiles"]] == ["VF Bluray-1080p", "Ultra-HD"]


def test_search_passes_query_and_language(fixture):
    seen = {}

    def transport(url, headers, timeout, data=None):
        seen["url"] = url
        return 200, json.dumps(fixture("search_dune")).encode()

    SeerrClient("http://s:5055", "k", transport=transport).search("dune", language="fr")
    assert "query=dune" in seen["url"]
    assert "language=fr" in seen["url"]


def test_search_omits_a_blank_language(fixture):
    seen = {}

    def transport(url, headers, timeout, data=None):
        seen["url"] = url
        return 200, json.dumps(fixture("search_dune")).encode()

    SeerrClient("http://s:5055", "k", transport=transport).search("dune", language="")
    assert "language" not in seen["url"]
