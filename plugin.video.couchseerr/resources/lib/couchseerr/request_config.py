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
"""Request configuration: four default profile slots, not a named preset.

Pure: the path is a parameter, and nothing here imports Kodi. This replaces the
named-preset model (see docs/private/specs/2026-08-04-couchseerr-v2-design.md,
"Request configuration") - a household thinks "the profile I want for films", not
"a bundle called VF".

Each of the four slots (`SLOTS`) holds at most one server/profile pair. A slot is
either fully configured or entirely absent from the stored file; there is no partial
or default-guessing state below `resolve`.
"""
import json
import os
import tempfile

from .errors import ConfigError

SLOTS = ("movie", "tv", "movie_4k", "tv_4k")
MEDIA_TYPES = ("movie", "tv")


def load_config(path):
    """Return the stored slot configuration, or {} when nothing has been configured yet.

    A missing file is a state, not a failure: a fresh install has no
    request_config.json, and every slot renders as unset. A corrupt file is a
    failure: silently returning {} would let a request go out with seerr's own
    default silently substituted, with nothing telling the user that happened.
    """
    if not os.path.exists(path):
        return {}
    try:
        with open(path) as handle:
            raw = json.load(handle)
    except (IOError, OSError, ValueError) as exc:
        raise ConfigError("could not read {0}: {1}".format(path, exc))
    if not isinstance(raw, dict):
        raise ConfigError("{0} does not contain a configuration object".format(path))
    config = {}
    for slot in SLOTS:
        if slot in raw:
            config[slot] = _slot_from(raw[slot], slot, path)
    return config


def _slot_from(entry, slot, path):
    if not isinstance(entry, dict):
        raise ConfigError("{0} has an invalid entry for slot {1!r}".format(path, slot))
    return {
        "serverId": entry.get("serverId"),
        "profileId": entry.get("profileId"),
        "label": entry.get("label", ""),
    }


def save_config(path, config):
    """Write atomically: a half-written request_config.json is unreadable on the next
    start, and this file is read on every request."""
    directory = os.path.dirname(path) or "."
    fd, temp = tempfile.mkstemp(dir=directory, prefix=".request_config-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as handle:
            json.dump(config, handle, indent=2)
        os.replace(temp, path)
    except (IOError, OSError) as exc:
        try:
            os.remove(temp)
        except OSError:
            pass
        raise ConfigError("could not write {0}: {1}".format(path, exc))


def slot_for(media_type, prefer_4k):
    """The slot an ordinary request of this media type resolves against."""
    if media_type not in MEDIA_TYPES:
        raise ConfigError("unsupported media type {0!r}".format(media_type))
    return media_type + "_4k" if prefer_4k else media_type


def resolve(config, media_type, prefer_4k):
    """Return the chosen slot's settings, or None when that slot is unset.

    None means "this slot has never been configured" - the caller (a request action,
    a context menu label) must render that differently from a configured slot, for
    example by prompting to configure it rather than sending a request. It is never a
    signal to fall back to another slot: resolving a 4K slot never falls back to the
    non-4K one, because a user who asked for 4K and silently got 1080p would not find
    out until the file lands.

    is4k in the result is derived from which slot was chosen, not passed through from
    the caller and not read from the stored entry - the stored entry carries no is4k
    field at all.
    """
    slot = slot_for(media_type, prefer_4k)
    settings = config.get(slot)
    if settings is None:
        return None
    return {
        "serverId": settings.get("serverId"),
        "profileId": settings.get("profileId"),
        "is4k": slot.endswith("_4k"),
    }


def profile_label(server_name, profile_name):
    """The display label mirrored into settings.xml, e.g. 'Radarr - VF Bluray-1080p'."""
    return "{0} - {1}".format(server_name, profile_name)


def request_body(settings, media_type, tmdb_id, seasons="all"):
    """Build seerr's POST /request body from a resolved slot (or an ad-hoc override with
    the same shape: serverId, profileId, is4k).

    serverId and profileId are omitted entirely when unset: seerr applies its own default
    for an absent key and rejects an explicit null.

    `seasons` is "all" (every season, the whole-show request) or a list of season numbers.
    It is ignored for movies, which have none. An empty list is refused rather than sent:
    seerr accepts it, answers as if the request succeeded, and downloads nothing.
    """
    if media_type not in MEDIA_TYPES:
        raise ConfigError("unsupported media type {0!r}".format(media_type))
    body = {
        "mediaType": media_type,
        "mediaId": tmdb_id,
        "is4k": bool(settings.get("is4k")),
    }
    for key in ("serverId", "profileId"):
        if settings.get(key) is not None:
            body[key] = settings[key]
    if media_type == "tv":
        if seasons != "all" and not seasons:
            raise ConfigError("a season request must name at least one season")
        # Without this seerr accepts a request carrying no seasons, which reports success
        # and downloads nothing.
        body["seasons"] = seasons
    return body
