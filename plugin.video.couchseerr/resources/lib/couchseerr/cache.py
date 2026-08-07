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
"""Per-key expiring cache backed by one small file per entry.

One file per key so that writing an entry never rewrites unrelated ones, and expiry is
applied on read rather than trusted to a cleanup that never runs.
"""
import hashlib
import json
import os
import tempfile
import time

TTL_DISCOVER = 900
TTL_PROGRESS = 30


class FileCache(object):
    def __init__(self, root, clock=time.time):
        self.root = root
        self._clock = clock
        os.makedirs(root, exist_ok=True)

    def _path(self, key):
        digest = hashlib.sha1(key.encode("utf-8")).hexdigest()
        return os.path.join(self.root, "{0}.json".format(digest))

    def get(self, key):
        """Return the cached value, or None when absent, expired or unreadable."""
        path = self._path(key)
        entry = _read(path)
        if entry is None:
            return None
        if entry.get("expires", 0) <= self._clock():
            _remove(path)
            return None
        return entry.get("value")

    def set(self, key, value, ttl):
        """Write an entry. A write failure degrades to "not cached"; it never raises."""
        payload = {"expires": self._clock() + ttl, "value": value}
        path = self._path(key)
        temp = None
        try:
            fd, temp = tempfile.mkstemp(dir=self.root, prefix=".tmp-", suffix=".tmp")
            with os.fdopen(fd, "w") as handle:
                json.dump(payload, handle)
            os.replace(temp, path)
        except (IOError, OSError):
            if temp is not None:
                _remove(temp)

    def delete(self, key):
        """Drop one entry. Absent is not an error: the postcondition is "not cached",
        and both an unlinked file and a key that was never written satisfy it."""
        _remove(self._path(key))

    def purge_expired(self):
        removed = 0
        now = self._clock()
        try:
            names = os.listdir(self.root)
        except OSError:
            return 0
        for name in names:
            if not name.endswith(".json"):
                continue
            path = os.path.join(self.root, name)
            entry = _read(path)
            if entry is None or entry.get("expires", 0) <= now:
                _remove(path)
                removed += 1
        return removed


def _read(path):
    try:
        with open(path) as handle:
            entry = json.load(handle)
    except (IOError, OSError, ValueError):
        return None
    return entry if isinstance(entry, dict) else None


def _remove(path):
    try:
        os.remove(path)
    except OSError:
        pass
