import xbmcgui

from couchseerr.kodi import dialogs

LABELS = {"pick_profile": "Choisir un profil"}


def setup_function():
    del xbmcgui._select_answers[:]
    del xbmcgui._input_answers[:]
    del xbmcgui._selects_seen[:]
    del xbmcgui._notifications[:]


def test_choose_returns_none_on_a_cancelled_select():
    xbmcgui._select_answers.append(-1)
    assert dialogs.choose("Heading", ["a", "b"]) is None


def test_choose_returns_the_chosen_index():
    xbmcgui._select_answers.append(1)
    assert dialogs.choose("Heading", ["a", "b"]) == 1


def test_notify_shows_a_notification_with_the_addon_name():
    dialogs.notify("Requested: Dune")
    assert xbmcgui._notifications[-1] == ("Couchseerr", "Requested: Dune")


# --- choices() / pick_profile() -- the cross-server profile picker ------------


class _MultiServerClient(object):
    """Distinct server_detail() per (media_type, server_id), so a test can tell a real
    4K server's profiles apart from an ordinary one's."""

    def __init__(self, servers, details):
        self._servers = servers
        self._details = details
        self.calls = []

    def servers(self, media_type):
        self.calls.append(("servers", media_type))
        return self._servers.get(media_type, [])

    def server_detail(self, media_type, server_id):
        self.calls.append(("detail", media_type, server_id))
        return self._details[(media_type, server_id)]


def test_choices_lists_every_server_every_profile():
    client = _MultiServerClient(
        {"movie": [{"id": 0, "name": "Radarr"}, {"id": 1, "name": "Radarr 4K", "is4k": True}]},
        {
            ("movie", 0): {"profiles": [{"id": 21, "name": "HD-1080p"}]},
            ("movie", 1): {"profiles": [{"id": 7, "name": "Ultra-HD"}, {"id": 8, "name": "Remux"}]},
        },
    )

    result = dialogs.choices(client, "movie")

    assert len(result) == 3
    assert result[0] == {
        "serverId": 0, "profileId": 21, "is4k": False, "label": "Radarr - HD-1080p",
    }
    assert result[1] == {
        "serverId": 1, "profileId": 7, "is4k": True, "label": "Radarr 4K - Ultra-HD",
    }
    assert result[2] == {
        "serverId": 1, "profileId": 8, "is4k": True, "label": "Radarr 4K - Remux",
    }


def test_choices_is4k_comes_from_the_server_not_the_profile():
    client = _MultiServerClient(
        {"movie": [{"id": 5, "name": "4K Radarr", "is4k": True}]},
        {("movie", 5): {"profiles": [{"id": 1, "name": "Any"}]}},
    )
    result = dialogs.choices(client, "movie")
    assert result[0]["is4k"] is True


def test_choices_defaults_is4k_false_without_the_flag():
    client = _MultiServerClient(
        {"tv": [{"id": 0, "name": "Sonarr"}]},
        {("tv", 0): {"profiles": [{"id": 1, "name": "Any"}]}},
    )
    result = dialogs.choices(client, "tv")
    assert result[0]["is4k"] is False


def test_choices_empty_when_media_type_has_no_servers():
    """seerr has no Radarr/Sonarr configured for this media type -- the caller (the
    route) is the one that turns this into a user-facing notification; choices() itself
    just reports the empty fact."""
    client = _MultiServerClient({"movie": []}, {})
    assert dialogs.choices(client, "movie") == []


def test_choices_fetches_detail_once_per_server():
    """Confirms the design rule that the list is fetched only when the picker opens: one
    servers() call, then exactly one server_detail() call per server -- no repeats, no
    calls for a media type that was not asked about."""
    client = _MultiServerClient(
        {"movie": [{"id": 0, "name": "A"}, {"id": 1, "name": "B"}]},
        {("movie", 0): {"profiles": []}, ("movie", 1): {"profiles": []}},
    )
    dialogs.choices(client, "movie")
    assert client.calls == [
        ("servers", "movie"), ("detail", "movie", 0), ("detail", "movie", 1),
    ]


def test_pick_profile_returns_the_chosen_entry():
    entries = [
        {"serverId": 0, "profileId": 21, "is4k": False, "label": "Radarr - HD-1080p"},
        {"serverId": 1, "profileId": 7, "is4k": True, "label": "Radarr 4K - Ultra-HD"},
    ]
    xbmcgui._select_answers.append(1)
    assert dialogs.pick_profile(entries, LABELS) == entries[1]


def test_pick_profile_returns_none_when_cancelled():
    entries = [{"serverId": 0, "profileId": 21, "is4k": False, "label": "Radarr - HD-1080p"}]
    xbmcgui._select_answers.append(-1)
    assert dialogs.pick_profile(entries, LABELS) is None


def test_pick_profile_shows_every_entrys_label_as_the_options():
    entries = [
        {"serverId": 0, "profileId": 21, "is4k": False, "label": "Radarr - HD-1080p"},
        {"serverId": 1, "profileId": 7, "is4k": True, "label": "Radarr 4K - Ultra-HD"},
    ]
    xbmcgui._select_answers.append(0)
    dialogs.pick_profile(entries, LABELS)
    heading, options = xbmcgui._selects_seen[-1]
    assert heading == LABELS["pick_profile"]
    assert options == ["Radarr - HD-1080p", "Radarr 4K - Ultra-HD"]
