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
"""The detail window. Renders a DetailView and decides only where pixels go.

Nothing here knows what is playable, requestable or visible: detailview.build_view and
build_season_view answered all of that before this module was handed anything, and the
rows it renders are ListItemSpecs from ui/spec.py turned into ListItems by the one
adapter. There is no xbmcgui.ListItem(...) in this file, and there must never be.

Two control ids, 50 and 51, both in Kodi's documented 50-59 list range. Every other piece
of text is a window property the XML reads through $INFO[Window.Property(...)], so a
renamed label cannot crash the window -- there is no label control id to get wrong. That
is the point: hardcoded control ids are precisely why Kodi's own video-info dialog can
never carry a Request button.
"""
import traceback

import xbmc
import xbmcaddon
import xbmcgui
import xbmcvfs

from . import dialogs
from .adapter import to_list_item
from ..detailview import Action, SeasonRow, action_spec, episode_spec, season_spec
from ..errors import SeerrError

ADDON_ID = "plugin.video.couchseerr"
XML_FILE = "couchseerr-detail.xml"
#: Must match the directory the XML actually ships in:
#: resources/skins/<SKIN>/<RES>/couchseerr-detail.xml. Capitalised exactly as Kodi's own
#: default, because CoreELEC's filesystem is case sensitive.
SKIN = "Default"
RES = "1080i"

#: 50 is the section list (seasons, or one season's episodes); 51 the action list.
SECTION_ID = 50
ACTIONS_ID = 51

#: Back, and the remote's Menu key, which every Kodi window treats as the same gesture.
_BACK_ACTIONS = (xbmcgui.ACTION_NAV_BACK, xbmcgui.ACTION_PREVIOUS_MENU)


def _run_plugin(url):
    xbmc.executebuiltin("RunPlugin({0})".format(url))


def _year_status_line(year, status_line):
    """The single "year  ·  status" line the header shows, composed once as a plain
    string rather than left for the XML to glue together.

    Kodi's $INFO[label,prefix,postfix] form *wraps* one label's own value in a prefix and
    a postfix; it cannot conditionally join two different properties, because the
    prefix/postfix are only ever emitted alongside that one label's own value, never in
    its place. Nesting a second $INFO inside the prefix does not fix this -- it still
    renders as value-plus-prefix, which is how a title with both a year and a status once
    rendered as "2021  ·  2021Monitored". Composing the join here, where it is
    testable, is the fix.
    """
    year_text = str(year) if year else ""
    status_text = status_line or ""
    if year_text and status_text:
        return "{0}  ·  {1}".format(year_text, status_text)
    return year_text or status_text


class DetailWindow(xbmcgui.WindowXML):
    """Built, then bound, then shown.

    bind() rather than constructor arguments on purpose: xbmcgui.WindowXML consumes its
    own positional arguments in __new__, and threading extra ones through that is the
    classic way an addon window fails to construct at all.
    """

    def bind(self, view, load_season, labels, run=_run_plugin, has_seasons=False):
        self._view = view
        self._load_season = load_season
        self._labels = labels
        self._run = run
        self._has_seasons = has_seasons
        self._season = None
        # Kodi destroys the ListItems a reset() drops. The window keeps its own
        # references so nothing it added can be collected out from under the control --
        # the documented way to crash a WindowXML that refills a list.
        self._items = {}
        self._rows = {}
        # The season list's selected position, captured the moment a season is opened --
        # see _open_season and the restore_position argument to _show_title -- so Back
        # can put the remote where it was rather than snapping to row 0.
        self._section_position = None

    def onInit(self):
        """Kodi calls this through its own callback dispatcher, not through open_detail's
        try/doModal/finally -- an exception here (a missing control id, a bad labels key)
        would otherwise be swallowed by Kodi's own logging, leaving doModal() blocking on
        a window that drew nothing and told nobody. This is the one place that failure
        must be caught, logged and turned into a notification and a close, or the window
        both "opens blank" and "closes silently" at once, the two things the spec says it
        must never do.
        """
        try:
            self._show_title()
        except Exception:
            xbmc.log(
                "[couchseerr] detail window failed to draw:\n{0}".format(
                    traceback.format_exc()
                ),
                xbmc.LOGERROR,
            )
            dialogs.notify(self._labels["unexpected_error"])
            self.close()

    # -- rendering ---------------------------------------------------------------

    def _show_title(self, restore_position=None):
        """The title view. `self._has_seasons` says whether this title is one that
        *should* have seasons -- a tv show -- so a show whose season list came back empty
        gets the "no season information" heading rather than a blank right-hand column,
        which on a TV is indistinguishable from a broken addon.

        `restore_position` is the season list's selection to return to, set only when
        this is Back unwinding out of a season (see onAction) -- the initial onInit call
        passes none, so the first paint still uses _focus_something's default.
        """
        view = self._view
        self._season = None
        self.setProperty("title", view.title or "")
        self.setProperty("year_status", _year_status_line(view.year, view.status_line))
        self.setProperty("plot", view.plot or "")
        self.setProperty("poster", view.art.get("poster", ""))
        self.setProperty("fanart", view.art.get("fanart", ""))

        self._fill(ACTIONS_ID, view.actions, action_spec)
        if view.seasons:
            self.setProperty("section", "seasons")
            self.setProperty("section_header", self._labels["seasons"])
            self._fill(SECTION_ID, view.seasons,
                       lambda row: season_spec(row, self._labels))
        else:
            self.setProperty("section", "")
            self.setProperty(
                "section_header",
                self._labels["no_seasons"] if self._has_seasons else "",
            )
            self._fill(SECTION_ID, [], action_spec)
        if restore_position is not None and self._restore_section_position(restore_position):
            return
        self._focus_something()

    def _show_season(self, number, season_view):
        self._season = number
        self.setProperty("section", "episodes")
        self.setProperty("section_header", season_view.season_name or "")
        self._fill(ACTIONS_ID, season_view.actions, action_spec)
        self._fill(SECTION_ID, season_view.episodes, episode_spec)
        self._focus_something()

    def _fill(self, control_id, rows, to_spec):
        control = self.getControl(control_id)
        control.reset()
        items = [to_list_item(to_spec(row)) for row in rows]
        self._rows[control_id] = list(rows)
        self._items[control_id] = items
        if items:
            control.addItems(items)

    def _focus_something(self):
        """Focus the first list that has anything in it. A title with neither an action
        nor a section -- an owned movie Kodi cannot resolve -- is left unfocused, and Back
        still closes the window because onAction runs regardless of focus.
        """
        for control_id in (ACTIONS_ID, SECTION_ID):
            if self._rows.get(control_id):
                self.setFocusId(control_id)
                return

    def _restore_section_position(self, position):
        """Put the season list's selection back where Back into it left off, and focus
        the list itself rather than the actions row _focus_something would otherwise
        pick. Returns whether it could: a position from a season list of a different
        size (the season count cannot change between opening and closing one season, but
        an empty season list is still possible in principle) falls back to the caller's
        default focus instead of selecting out of range.
        """
        rows = self._rows.get(SECTION_ID) or []
        if not rows or position < 0 or position >= len(rows):
            return False
        self.getControl(SECTION_ID).selectItem(position)
        self.setFocusId(SECTION_ID)
        return True

    # -- input -------------------------------------------------------------------

    def _row_at(self, control_id):
        rows = self._rows.get(control_id) or []
        position = self.getControl(control_id).getSelectedPosition()
        if position is None or position < 0 or position >= len(rows):
            return None
        return rows[position]

    def onClick(self, control_id):
        row = self._row_at(control_id)
        if row is None:
            return
        if isinstance(row, SeasonRow):
            self._open_season(row.number)
        elif isinstance(row, Action):
            self._fire(row.url)
        elif row.url:
            # An EpisodeRow. An empty url is an unowned episode: seerr has no
            # episode-level request, so there is genuinely nothing behind it.
            self._fire(row.url)

    def _fire(self, url):
        """Run a plugin route, then close.

        Every action closes, with no table of exceptions. Play and the trailer take over
        the screen anyway; a request, once fired, makes this window's own Request button a
        lie, and RunPlugin is asynchronous so the window can never learn when to correct
        itself. Closing returns the user to the row, which mode=request already refreshes.
        """
        self._run(url)
        self.close()

    def _open_season(self, number):
        # Captured before the swap, while SECTION_ID still holds the season list: this is
        # the row Back must return the remote to, not row 0.
        self._section_position = self.getControl(SECTION_ID).getSelectedPosition()
        try:
            season_view = self._load_season(number)
        except SeerrError as exc:
            # seerr's own words about its own failure -- an unretrievable season is an
            # HTTP 500 carrying a message, not an empty payload. Rewording it would hide
            # what the server actually said.
            xbmc.log("[couchseerr] season {0}: {1}".format(number, exc), xbmc.LOGERROR)
            dialogs.notify(str(exc))
            return
        except Exception:
            xbmc.log(
                "[couchseerr] could not open season {0}:\n{1}".format(
                    number, traceback.format_exc()
                ),
                xbmc.LOGERROR,
            )
            dialogs.notify(self._labels["unexpected_error"])
            return
        self._show_season(number, season_view)

    def onAction(self, action):
        """Back steps out one level, then closes.

        The base class is deliberately not called: xbmcgui.Window's own onAction is
        documented to close the window on these same two actions in at least some Kodi
        versions, and if that holds here too, delegating to it would close the window
        from under the episode view. Skipping it is safe either way -- this method
        already handles both actions itself, so nothing depends on the base
        implementation running. Navigation actions are handled by Kodi's GUI engine and
        never reach here as something this window has to forward.
        """
        if action.getId() in _BACK_ACTIONS:
            if self._season is not None:
                self._show_title(restore_position=self._section_position)
                return
            self.close()


def open_detail(view, load_season, labels, run=_run_plugin, has_seasons_source=False):
    """Build, bind, show, and tear down.

    Fails loudly by contract (see the spec's "Failure behaviour"): there is no fallback
    listing any more, so a window that could not be built must say so rather than leave
    the user on a screen that did nothing. The caller (routes.dispatch) logs and notifies;
    nothing is caught here, because catching it here is what would make it silent.
    """
    path = xbmcvfs.translatePath(xbmcaddon.Addon(ADDON_ID).getAddonInfo("path"))
    win = DetailWindow(XML_FILE, path, SKIN, RES)
    try:
        win.bind(view, load_season, labels, run, has_seasons=has_seasons_source)
        win.doModal()
    finally:
        # Kodi keeps the window alive until the Python reference goes; without this the
        # next open finds a stale instance still holding the previous title's ListItems.
        del win
