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
"""What a title offers, and what the row describing it says.

Kodi's CGUIMediaWindow::OnClick branches three ways on a plugin item, and this is the
only place that mechanic is written down -- detailview.action_spec points here:

  folder                                -> navigate into the path; the addon is called as
                                           a directory and must render a listing
  non-folder, isplayable not set        -> run the addon as a script, handle -1, exactly
                                           what the RunPlugin builtin does
  non-folder, isplayable true           -> play it; the addon must answer setResolvedUrl

mode=request, mode=play, mode=settings and mode=trailer render no listing: they act and
end with a notification (mode=settings opens the addon's own settings dialog instead).
That is the middle branch, so every action row must be a non-folder and must *not* claim
isplayable -- claiming it would make Kodi try to play the plugin URL and raise a
failed-playback dialog. This is why the addon writes no explicit RunPlugin anywhere: the
builtin is the setting-level spelling of the same behaviour (see resources/settings.xml),
and a row gets it from the item flags instead.

The two functions here are pure and build nothing: available_actions answers "what can the
user do with this title right now" and status_line answers "what does its state say". The
detail window (detailview.py) is their only caller, and it renders their answers.
"""
from .state import REQUESTABLE_STATES, TileState

#: The status line's wording per state, keyed into LABEL_IDS. DOWNLOADING and UNRELEASED
#: are absent on purpose: both take an argument (percent, release date) and are handled
#: explicitly in status_line, where the argument is available.
STATUS_LABEL_KEYS = {
    TileState.MONITORED: "monitored",
    TileState.PENDING: "pending",
    TileState.PARTIAL: "partial",
}


def status_line(state, item, labels):
    """The non-actionable line the detail window shows for a title in flight.

    It carries "progress or the release date" (design), localised. It cannot share the
    text with markers.marker_for: that table is pure core, so it has no access to
    getLocalizedString, and it deliberately emits compact glyphs ("[⋯]", "[◐]") sized for
    a poster label rather than prose for a full-width listing row. What the two do share
    is the question they answer, and that lives in TileState, not in either table.

    Percent is truncated, not rounded, matching marker_for: 99.6% reads as 99, because
    "100" is reserved for a download that is actually finished.

    Returns "" for a state that carries no line -- OWNED and ACTIONABLE, and the two
    shapes tile_state cannot produce (DOWNLOADING with no download record, UNRELEASED
    with no release date). "" is not a failure signal: detailview.build_view renders no
    status line for a blank one.
    """
    download = item.media.best_download if item.media else None
    if state is TileState.DOWNLOADING and download is not None:
        return labels["downloading"].format(int(download.percent))
    if state is TileState.UNRELEASED and item.release_date is not None:
        return labels["unreleased"].format(item.release_date.isoformat())
    key = STATUS_LABEL_KEYS.get(state)
    return labels[key] if key else ""


def can_play_from_library(state, media_type):
    """Whether this title could ever be played from Kodi's library, before asking Kodi
    whether it actually holds it.

    Split out because two callers need the same answer at different moments.
    available_actions asks it knowing `in_library`; routes._open_detail asks it to decide
    whether resolving a Kodi library id is worth a JSON-RPC round trip at all, which is a
    question it must answer *before* it has that flag. Spelling the condition in both
    places is how the listing and the window came to disagree about a title in the first
    place, so it is spelled here.

    No whole-show Play: Player.Open has no tvshowid parameter (verified against
    JSONRPC.Introspect on the target device), so this never worked for a tv title.
    Seasons is the way into an owned show, and reaches an episode that genuinely plays.
    """
    return state is TileState.OWNED and media_type != "tv"


def available_actions(state, media_type, resolved, in_library, trailer_key):
    """The actions this title offers right now, as label keys in display order -- a
    subset of ("play", "request", "configure", "seasons", "trailer").

    This is the one place that decides "what can the user do with this title". Any
    renderer for the same title calls this instead of re-deriving the rule, so two of
    them can never answer differently. The status line and the "not in the Kodi library"
    explanation are deliberately not represented here: they are text the user reads, not
    an action, and carry no key of their own.
    """
    actions = []

    if state is TileState.OWNED:
        # Through can_play_from_library, never re-derived here: routes._open_detail gates
        # its library lookup on the same predicate, and the two must not drift.
        if can_play_from_library(state, media_type) and in_library:
            actions.append("play")
    elif state in REQUESTABLE_STATES:
        if resolved is None:
            # No default profile configured for this media type: offering "Demander"
            # here would resolve to nothing and send seerr an empty body. Send the user
            # to fix it instead -- the context menu's "Demander avec..." still works
            # without a default, since it always fetches its own choice.
            actions.append("configure")
        else:
            actions.append("request")

    if media_type == "tv":
        # Whole-show requesting stays above it, unchanged; this is the way to a single
        # season, and the only way a partial show reaches its missing seasons at all.
        # The window renders its season list inline rather than as a button, so it drops
        # this key -- but the decision that a show *offers* seasons stays here.
        actions.append("seasons")

    if trailer_key:
        actions.append("trailer")

    return actions
