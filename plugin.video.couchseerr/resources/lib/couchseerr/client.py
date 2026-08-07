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
import json
import urllib.error
import urllib.parse
import urllib.request

from .errors import SeerrAuthError, SeerrError, SeerrRequestError, SeerrUnavailable

API_PREFIX = "/api/v1"


def urllib_transport(url, headers, timeout, data=None):
    """Real transport. Returns (status_code, body_bytes) and raises only on network failure."""
    request = urllib.request.Request(url, headers=headers, data=data)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.getcode(), response.read()
    except urllib.error.HTTPError as exc:
        # An HTTP error is a *response*, not a transport failure - hand back its body so
        # the caller can surface seerr's own message.
        return exc.code, exc.read()


class SeerrClient:
    def __init__(self, base_url, api_key, transport=urllib_transport, timeout=15):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self._transport = transport

    def _url(self, path, params):
        url = "{0}{1}{2}".format(self.base_url, API_PREFIX, path)
        if params:
            usable = {k: v for k, v in params.items() if v is not None and v != ""}
            if usable:
                url = "{0}?{1}".format(url, urllib.parse.urlencode(usable))
        return url

    def get(self, path, params=None):
        return self._call("GET", self._url(path, params), None)

    def post(self, path, body):
        """POST JSON. Same contract as get(): a result, or a typed error - never None.

        The failure being avoided is the one common in this space: catching the HTTP
        error, returning None, and letting the UI report "Request sent" over a quota
        rejection the user never sees.
        """
        return self._call(
            "POST", self._url(path, None), json.dumps(body).encode("utf-8")
        )

    def _call(self, method, url, data):
        headers = {"X-Api-Key": self.api_key, "Accept": "application/json"}
        if data is not None:
            headers["Content-Type"] = "application/json"
        try:
            status, body = self._transport(url, headers, self.timeout, data)
        except SeerrError:
            raise
        except Exception as exc:
            raise SeerrUnavailable(
                "could not reach seerr at {0}: {1}".format(url, exc)
            )

        if status in (401, 403):
            raise SeerrAuthError(_message_from(body, "authentication failed"))
        if not 200 <= status < 300:
            raise SeerrRequestError(status, _message_from(body, "request failed"))

        try:
            parsed = json.loads(body.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            raise SeerrRequestError(status, "response was not valid JSON: {0}".format(exc))

        if not isinstance(parsed, (dict, list)):
            raise SeerrRequestError(
                status, "response body was not a JSON object or array: {0!r}".format(parsed)
            )
        return parsed

    def servers(self, media_type):
        """Both endpoints return an *array*: two Radarr instances are a supported setup."""
        return self.get("/service/{0}".format(_service_for(media_type)))

    def server_detail(self, media_type, server_id):
        return self.get(
            "/service/{0}/{1}".format(_service_for(media_type), server_id)
        )

    def search(self, query, language=None, page=1):
        return self.get(
            "/search", {"query": query, "language": language, "page": page}
        )

    def season(self, tmdb_id, season_number, language=None):
        """One season's episodes. Thin: parsing belongs to models.parse_season_episodes."""
        return self.get(
            "/tv/{0}/season/{1}".format(tmdb_id, season_number), {"language": language}
        )


def _service_for(media_type):
    if media_type == "movie":
        return "radarr"
    if media_type == "tv":
        return "sonarr"
    raise SeerrRequestError(0, "no *arr service for media type {0!r}".format(media_type))


def _message_from(body, default):
    """seerr puts a human-readable reason in {"message": ...}; fall back when it does not."""
    try:
        parsed = json.loads(body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError, AttributeError):
        return default
    if isinstance(parsed, dict) and parsed.get("message"):
        return parsed["message"]
    return default
