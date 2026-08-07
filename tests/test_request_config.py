import pytest

from couchseerr.errors import ConfigError
from couchseerr.request_config import (
    SLOTS, load_config, profile_label, request_body, resolve, save_config, slot_for,
)


def _slot(server_id=0, profile_id=21, label="Radarr - HD-1080p"):
    return {"serverId": server_id, "profileId": profile_id, "label": label}


def test_load_returns_empty_dict_when_file_absent(tmp_path):
    """A fresh install has no request_config.json. That is not an error; every slot
    just renders as unset."""
    assert load_config(str(tmp_path / "request_config.json")) == {}


def test_load_raises_on_a_corrupt_file(tmp_path):
    """Silently returning {} would send a request out with the wrong profile, or with
    seerr's own default silently substituted, and no explanation to the user."""
    path = tmp_path / "request_config.json"
    path.write_text("{not json")
    with pytest.raises(ConfigError):
        load_config(str(path))


def test_load_raises_when_file_is_not_an_object(tmp_path):
    path = tmp_path / "request_config.json"
    path.write_text("[1, 2, 3]")
    with pytest.raises(ConfigError):
        load_config(str(path))


def test_roundtrip_preserves_every_slot(tmp_path):
    path = str(tmp_path / "request_config.json")
    original = {
        "movie": _slot(profile_id=21, label="Radarr - HD-1080p"),
        "tv": _slot(profile_id=12, label="Sonarr - HD-1080p"),
        "movie_4k": _slot(profile_id=7, label="Radarr 4K - UHD"),
    }
    save_config(path, original)
    loaded = load_config(path)

    assert loaded["movie"] == original["movie"]
    assert loaded["tv"] == original["tv"]
    assert loaded["movie_4k"] == original["movie_4k"]
    assert "tv_4k" not in loaded


def test_save_is_atomic_no_partial_file_left_behind(tmp_path):
    """Same reasoning as the old save_presets: a crash mid-write must not leave a
    half-written file that fails to parse on the next start."""
    path = tmp_path / "request_config.json"
    save_config(str(path), {"movie": _slot()})
    leftovers = list(tmp_path.glob(".request_config-*"))
    assert leftovers == []


def test_slots_are_the_four_default_profile_slots():
    assert SLOTS == ("movie", "tv", "movie_4k", "tv_4k")


def test_slot_for_movie_without_4k_preference():
    assert slot_for("movie", prefer_4k=False) == "movie"


def test_slot_for_tv_without_4k_preference():
    assert slot_for("tv", prefer_4k=False) == "tv"


def test_slot_for_returns_the_4k_slot_only_when_preferred():
    assert slot_for("movie", prefer_4k=True) == "movie_4k"
    assert slot_for("tv", prefer_4k=True) == "tv_4k"


def test_slot_for_rejects_an_unknown_media_type():
    with pytest.raises(ConfigError):
        slot_for("person", prefer_4k=False)


def test_resolve_returns_none_when_the_slot_is_unset():
    assert resolve({}, "movie", prefer_4k=False) is None


def test_resolve_does_not_fall_back_from_4k_to_the_plain_slot():
    """A user who asked for 4K and silently got 1080p would not find out until the
    file lands - the whole reason this slot exists separately."""
    config = {"movie": _slot(profile_id=21)}
    assert resolve(config, "movie", prefer_4k=True) is None


def test_resolve_returns_the_configured_slot_settings():
    config = {"movie": _slot(server_id=3, profile_id=21)}
    assert resolve(config, "movie", prefer_4k=False) == {
        "serverId": 3, "profileId": 21, "is4k": False,
    }


def test_resolve_distinguishes_unset_from_default_profile():
    """These are different states with opposite consequences: an entirely absent slot
    means do not request at all and tell the user to configure a profile; a slot that
    exists with profileId None means request, letting Radarr or Sonarr apply their own
    default. Both look like a falsy profile id, so the difference must be pinned
    explicitly - a refactor that collapses them would fail silently otherwise."""
    unset = resolve({}, "movie", prefer_4k=False)
    assert unset is None

    server_default = resolve(
        {"movie": {"serverId": 3, "profileId": None, "label": "Radarr"}},
        "movie", prefer_4k=False,
    )
    assert server_default == {"serverId": 3, "profileId": None, "is4k": False}
    assert server_default is not None


def test_request_body_from_server_default_slot_omits_profile_id():
    """The full path from stored config to seerr payload: a slot with profileId None
    must reach seerr without a profileId key at all, while its serverId survives."""
    settings = resolve(
        {"movie": {"serverId": 3, "profileId": None, "label": "Radarr"}},
        "movie", prefer_4k=False,
    )
    body = request_body(settings, "movie", 693134)
    assert body == {
        "mediaType": "movie", "mediaId": 693134, "is4k": False, "serverId": 3,
    }
    assert "profileId" not in body


def test_load_raises_on_a_slot_that_is_not_an_object(tmp_path):
    """A hand-edited file with {"movie": "oops"} must not be silently treated as
    unset - that would hide a hand-edit the user thinks took effect. Consistent with
    the corrupt-file rule: fail loudly rather than guess."""
    path = tmp_path / "request_config.json"
    path.write_text('{"movie": "oops"}')
    with pytest.raises(ConfigError):
        load_config(str(path))


def test_load_ignores_unknown_top_level_keys(tmp_path):
    """A stray or future-version key at the top level is dropped, not an error - only
    the four known slots are read back out."""
    path = tmp_path / "request_config.json"
    path.write_text(
        '{"movie": {"serverId": 0, "profileId": 21, "label": "Radarr"}, '
        '"future_slot": {"serverId": 9}, "some_other_key": true}'
    )
    loaded = load_config(str(path))
    assert set(loaded.keys()) == {"movie"}


def test_resolve_sets_is4k_from_the_slot_not_the_caller():
    """The stored slot entry carries no is4k field at all - it is implied entirely by
    which of the four slots was chosen."""
    config = {"movie_4k": _slot(server_id=9, profile_id=99)}
    resolved = resolve(config, "movie", prefer_4k=True)
    assert resolved["is4k"] is True

    config = {"movie": _slot(server_id=9, profile_id=99)}
    resolved = resolve(config, "movie", prefer_4k=False)
    assert resolved["is4k"] is False


def test_profile_label_combines_server_and_profile_names():
    assert profile_label("Radarr", "VF Bluray-1080p") == "Radarr - VF Bluray-1080p"


def test_request_body_for_a_movie():
    settings = {"serverId": 0, "profileId": 21, "is4k": False}
    assert request_body(settings, "movie", 693134) == {
        "mediaType": "movie",
        "mediaId": 693134,
        "is4k": False,
        "serverId": 0,
        "profileId": 21,
    }


def test_request_body_for_tv_requests_the_whole_series():
    """v2 is whole-show only. Omitting seasons makes seerr create a request with no
    seasons at all, which looks accepted and downloads nothing."""
    settings = {"serverId": 0, "profileId": 12, "is4k": False}
    body = request_body(settings, "tv", 1399)
    assert body["seasons"] == "all"
    assert body["mediaId"] == 1399


def test_request_body_omits_unset_server_and_profile():
    """'Server default' is a real choice: seerr applies its own default when the keys
    are absent, but rejects an explicit null."""
    settings = {"serverId": None, "profileId": None, "is4k": False}
    assert request_body(settings, "movie", 1) == {
        "mediaType": "movie", "mediaId": 1, "is4k": False,
    }


def test_request_body_carries_is4k_through():
    settings = {"serverId": 5, "profileId": 7, "is4k": True}
    body = request_body(settings, "movie", 42)
    assert body["is4k"] is True


def test_request_body_rejects_an_unknown_media_type():
    with pytest.raises(ConfigError):
        request_body({"serverId": None, "profileId": None, "is4k": False}, "person", 5)


def test_request_body_defaults_to_the_whole_show():
    body = request_body({"serverId": 0, "profileId": 3}, "tv", 82856)
    assert body["seasons"] == "all"


def test_request_body_carries_one_season():
    body = request_body({"serverId": 0, "profileId": 3}, "tv", 82856, seasons=[4])
    assert body["seasons"] == [4]
    assert body["mediaId"] == 82856


def test_request_body_ignores_seasons_for_a_movie():
    """Radarr has no seasons; sending the key would be a body seerr has to ignore."""
    body = request_body({"serverId": 0, "profileId": 3}, "movie", 693134, seasons=[1])
    assert "seasons" not in body


def test_request_body_refuses_an_empty_season_list():
    """seerr accepts seasons: [] and answers as if the request succeeded, then downloads
    nothing -- the exact silent success this project exists to avoid."""
    with pytest.raises(ConfigError):
        request_body({"serverId": 0, "profileId": 3}, "tv", 82856, seasons=[])
