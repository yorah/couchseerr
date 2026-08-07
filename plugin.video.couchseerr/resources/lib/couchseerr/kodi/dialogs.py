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
"""Kodi dialogs used by the request flow: the cross-server profile picker (`choices`,
`pick_profile`), and the small select/notify primitives routes.py builds on.
"""
import xbmcgui

from ..request_config import profile_label


def choose(heading, options):
    """Kodi returns -1 for a cancelled select; translate it to None at the boundary."""
    index = xbmcgui.Dialog().select(heading, options)
    return None if index is None or index < 0 else index


def notify(message):
    xbmcgui.Dialog().notification("Couchseerr", message)


def choices(client, media_type):
    """Every (server, profile) pair for this media type, one entry per pair.

    Fetches `client.servers(media_type)` once, then `client.server_detail` per server --
    the picker's whole cost, paid only when the picker opens (never while a discovery
    row renders). `is4k` comes from the server's own flag, not the profile: a 4K server
    reports is4k regardless of which of its profiles gets picked.
    """
    entries = []
    for server in client.servers(media_type):
        server_id = server.get("id")
        server_name = server.get("name") or str(server_id)
        is4k = bool(server.get("is4k"))
        detail = client.server_detail(media_type, server_id)
        for profile in detail.get("profiles") or []:
            entries.append({
                "serverId": server_id,
                "profileId": profile.get("id"),
                "is4k": is4k,
                "label": profile_label(server_name, profile.get("name", "")),
            })
    return entries


def pick_profile(entries, labels):
    """Select dialog over every (server, profile) choice `choices()` returned. Each
    entry is already labelled `<server> - <profile>`, so a 4K server is unambiguous
    even though this list carries no separate server-picker step. None on cancel."""
    index = choose(labels["pick_profile"], [entry["label"] for entry in entries])
    return None if index is None else entries[index]
