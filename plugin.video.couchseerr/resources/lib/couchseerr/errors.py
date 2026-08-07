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
"""Typed failures. Callers distinguish these; nothing returns None to mean failure."""


class SeerrError(Exception):
    """Base for every seerr interaction failure."""


class SeerrUnavailable(SeerrError):
    """The instance could not be reached at all: DNS, refused, timeout."""


class SeerrAuthError(SeerrError):
    """401 or 403 - the API key is wrong, or lacks permission for this route."""


class SeerrRequestError(SeerrError):
    """Any other non-2xx response, or a 2xx whose body is not usable JSON."""

    def __init__(self, status_code, message):
        super().__init__("seerr returned {0}: {1}".format(status_code, message))
        self.status_code = status_code
        self.message = message


class ConfigError(SeerrError):
    """The request-configuration file cannot be read, or is not shaped as expected."""


class RequestRefused(SeerrError):
    """The title's own state rules the request out before seerr is contacted.

    Carries the offending `TileState` alongside the message. The message is English and
    exists for the log; a caller that wants to show the reason on screen reads `.state`
    and picks its own wording, because the module that raises this is pure and has no
    way to resolve a localised string.

    `state` is optional: RequestRefused can be raised by a caller that has no tile state
    (a skin driving ?mode=request directly), and such a refusal still has a usable
    English message.
    """

    def __init__(self, message, state=None):
        super().__init__(message)
        self.state = state
