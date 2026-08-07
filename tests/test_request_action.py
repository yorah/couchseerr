import pytest

from couchseerr.actions.request import send_request
from couchseerr.errors import RequestRefused, SeerrRequestError
from couchseerr.state import TileState


class FakeClient(object):
    def __init__(self, response=None, error=None):
        self.response = response or {"id": 42}
        self.error = error
        self.calls = []

    def post(self, path, body):
        self.calls.append((path, body))
        if self.error is not None:
            raise self.error
        return self.response


def _settings():
    return {"serverId": 0, "profileId": 21, "is4k": False}


def test_sends_the_settings_body_to_the_request_endpoint():
    client = FakeClient()
    result = send_request(client, _settings(), "movie", 693134, TileState.ACTIONABLE)

    assert result["id"] == 42
    assert client.calls == [
        ("/request", {"mediaType": "movie", "mediaId": 693134, "is4k": False,
                      "serverId": 0, "profileId": 21}),
    ]


def test_refuses_before_calling_seerr_for_in_flight_titles():
    """The tile already carries the state, so this costs no API call. seerr's own guard
    only blocks some states, so without this a second request is created silently and is
    discovered much later, in Radarr. Derives from TileState, so a new enum member
    automatically joins the test without code change."""
    for state in TileState:
        if state == TileState.ACTIONABLE:
            # ACTIONABLE is the only permitted state; test it separately below.
            continue
        client = FakeClient()
        with pytest.raises(RequestRefused):
            send_request(client, _settings(), "movie", 1, state)
        assert client.calls == [], state

    # ACTIONABLE is the only state that should send.
    client = FakeClient()
    send_request(client, _settings(), "movie", 1, TileState.ACTIONABLE)
    assert len(client.calls) == 1


def test_refusal_names_the_state_for_notification():
    client = FakeClient()
    with pytest.raises(RequestRefused) as excinfo:
        send_request(client, _settings(), "movie", 1, TileState.DOWNLOADING)
    assert "downloading" in str(excinfo.value)


def test_a_seerr_rejection_propagates_untouched():
    """Reporting success over a quota rejection is the failure this project exists to
    avoid; the caller must see the typed error and seerr's own message."""
    client = FakeClient(error=SeerrRequestError(409, "Request already exists"))
    with pytest.raises(SeerrRequestError):
        send_request(client, _settings(), "movie", 1, TileState.ACTIONABLE)


def test_state_none_skips_the_local_refusal():
    """A skin invoking ?mode=request directly has no tile state to pass."""
    client = FakeClient()
    send_request(client, {"serverId": 0, "profileId": 12, "is4k": False}, "tv", 1399, None)
    assert client.calls[0][1]["seasons"] == "all"


def test_a_partial_season_may_be_requested():
    """A season with missing episodes is one a fresh request tells Sonarr to search for.
    The title-level guard would refuse this, which is why the season path has its own
    tuple."""
    client = FakeClient()
    send_request(client, _settings(), "tv", 82856, TileState.PARTIAL, seasons=[3])
    assert client.calls[0][1]["seasons"] == [3]


def test_an_owned_season_is_refused():
    client = FakeClient()
    with pytest.raises(RequestRefused):
        send_request(client, _settings(), "tv", 82856, TileState.OWNED, seasons=[1])
    assert client.calls == []


def test_a_partial_title_is_still_refused_without_seasons():
    """The title-level rule is unchanged: a whole-show request on a partial title would
    duplicate what is already requested."""
    client = FakeClient()
    with pytest.raises(RequestRefused):
        send_request(client, _settings(), "tv", 82856, TileState.PARTIAL)
    assert client.calls == []
