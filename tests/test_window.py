"""The detail window's dispatch, against a stubbed xbmcgui.

What this file can and cannot see: it drives the same onClick/onAction entry points Kodi
drives, so the state machine (which row does what, what Back means at each level) is
covered. It says nothing about layout, focus or rendering -- the stub is not Kodi, and a
stub that answered those questions would be inventing them. See CONTEXT.md: "a stub that
ignores the argument under test cannot test it".
"""
import pytest

import xbmc
import xbmcgui
from couchseerr import detailview
from couchseerr.kodi import window
from couchseerr.state import TileState


@pytest.fixture(autouse=True)
def _clean():
    del xbmc._builtins[:]
    del xbmcgui._notifications[:]
    yield


LABELS = {"seasons": "Seasons", "no_seasons": "No season information",
          "episode_count": "{0} episodes", "unexpected_error": "Unexpected error - see log"}


def _action(key="play", label="Play", url="plugin://x?mode=play"):
    return detailview.Action(key, label, url)


def _season_row(number=1):
    return detailview.SeasonRow(number=number, label="Season {0}".format(number),
                                marker="[✓]", state=TileState.OWNED, episode_count=10)


def _episode_row(number=1, url="plugin://x?mode=play&episode_id=7"):
    return detailview.EpisodeRow(
        number=number, title="Chapter {0}".format(number), air_date=None, owned=bool(url),
        label="{0}. Chapter {0}".format(number), url=url, art={}, info={"title": "c"},
    )


def _view(actions=None, seasons=None):
    return detailview.DetailView(
        title="Lupin", year=2021, plot="A thief.", status_line="", art={},
        actions=actions if actions is not None else [_action()],
        seasons=seasons or [],
    )


def _season_view(actions=None, episodes=None):
    return detailview.SeasonView(
        title="Lupin", season_name="Season 1", art={},
        actions=actions or [], episodes=episodes if episodes is not None else [_episode_row()],
    )


def _open(view, load_season=None, run=None):
    """Build the window and run onInit, without doModal (which would block)."""
    win = window.DetailWindow("couchseerr-detail.xml", "/addon", "Default", "1080i")
    win.bind(view, load_season or (lambda number: _season_view()), LABELS, run or (lambda url: None))
    win.onInit()
    return win


# --- the composed year/status line -------------------------------------------------
#
# Kodi's $INFO[label,prefix,postfix] form wraps one label's own value; it cannot
# conditionally join two different properties, so kodi/window._year_status_line does the
# join in Python instead, where all four emptiness combinations are directly testable.


def test_year_status_line_joins_both_when_present():
    assert window._year_status_line(2021, "Monitored") == "2021  ·  Monitored"


def test_year_status_line_is_bare_year_alone():
    assert window._year_status_line(2021, "") == "2021"


def test_year_status_line_is_bare_status_alone():
    assert window._year_status_line(None, "Monitored") == "Monitored"


def test_year_status_line_is_empty_when_neither_is_present():
    assert window._year_status_line(None, "") == ""


def test_the_title_view_fills_both_lists():
    win = _open(_view(seasons=[_season_row(1), _season_row(2)]))
    assert win.getProperty("title") == "Lupin"
    # _view's default carries a year and no status, so the composed property is bare.
    assert win.getProperty("year_status") == "2021"
    assert win.getProperty("section") == "seasons"
    assert win.getProperty("section_header") == "Seasons"
    assert win.getControl(window.ACTIONS_ID).size() == 1
    assert win.getControl(window.SECTION_ID).size() == 2
    # Play (or whatever the single action is) beats the season list for the remote's
    # first OK press -- landing on the section list instead is a real regression.
    assert win._focus_id == window.ACTIONS_ID


def test_focus_falls_back_to_the_section_with_no_actions():
    """A title with no actions at all (an owned movie Kodi cannot resolve) still has
    somewhere for the remote to land: the section list, not nothing."""
    win = _open(_view(actions=[], seasons=[_season_row(1)]))
    assert win.getControl(window.ACTIONS_ID).size() == 0
    assert win._focus_id == window.SECTION_ID


def test_a_movie_shows_no_section():
    win = _open(_view())
    assert win.getProperty("section") == ""
    assert win.getProperty("section_header") == ""
    assert win.getControl(window.SECTION_ID).size() == 0


def test_a_show_with_no_seasons_says_so():
    """An empty list under a heading beats an empty screen, which on a TV is
    indistinguishable from a broken addon."""
    win = window.DetailWindow("couchseerr-detail.xml", "/addon", "Default", "1080i")
    win.bind(_view(seasons=[]), lambda n: _season_view(), LABELS, has_seasons=True)
    win.onInit()
    assert win.getProperty("section_header") == "No season information"


def test_clicking_an_action_runs_it_and_closes():
    fired = []
    win = _open(_view(), run=fired.append)
    win.getControl(window.ACTIONS_ID).selectItem(0)
    win.onClick(window.ACTIONS_ID)
    assert fired == ["plugin://x?mode=play"]
    assert win._closed is True


def test_clicking_a_season_swaps_to_its_episodes():
    asked = []

    def load(number):
        asked.append(number)
        return _season_view(episodes=[_episode_row(1), _episode_row(2)])

    win = _open(_view(seasons=[_season_row(1), _season_row(2)]), load_season=load)
    win.getControl(window.SECTION_ID).selectItem(1)
    win.onClick(window.SECTION_ID)
    assert asked == [2]
    assert win.getProperty("section") == "episodes"
    assert win.getProperty("section_header") == "Season 1"
    assert win.getControl(window.SECTION_ID).size() == 2
    assert win._closed is False
    # The loaded season carries no actions, so opening it must land the remote on the
    # episode list, not silently stay wherever the title view left it.
    assert win._focus_id == window.SECTION_ID


def test_clicking_an_owned_episode_plays_and_closes():
    fired = []
    win = _open(_view(seasons=[_season_row(1)]), run=fired.append)
    win.getControl(window.SECTION_ID).selectItem(0)
    win.onClick(window.SECTION_ID)
    win.getControl(window.SECTION_ID).selectItem(0)
    win.onClick(window.SECTION_ID)
    assert fired == ["plugin://x?mode=play&episode_id=7"]
    assert win._closed is True


def test_clicking_an_unowned_episode_does_nothing():
    fired = []
    win = _open(
        _view(seasons=[_season_row(1)]),
        load_season=lambda n: _season_view(episodes=[_episode_row(4, url="")]),
        run=fired.append,
    )
    win.getControl(window.SECTION_ID).selectItem(0)
    win.onClick(window.SECTION_ID)
    win.getControl(window.SECTION_ID).selectItem(0)
    win.onClick(window.SECTION_ID)
    assert fired == []
    assert win._closed is False


def test_back_from_episodes_returns_to_the_title():
    win = _open(_view(seasons=[_season_row(1)]))
    win.getControl(window.SECTION_ID).selectItem(0)
    win.onClick(window.SECTION_ID)
    win.onAction(xbmcgui.Action(xbmcgui.ACTION_NAV_BACK))
    assert win.getProperty("section") == "seasons"
    assert win._closed is False


def test_back_from_a_season_restores_its_position():
    """Backing out of season 3 of 3 must not snap the remote back to row 0 and the
    actions list -- see IMPORTANT 4. mode=season was a directory and Kodi restored
    selection on Back for free; the window has to do it itself now."""
    win = _open(_view(seasons=[_season_row(1), _season_row(2), _season_row(3)]))
    win.getControl(window.SECTION_ID).selectItem(2)
    win.onClick(window.SECTION_ID)
    win.onAction(xbmcgui.Action(xbmcgui.ACTION_NAV_BACK))
    assert win.getControl(window.SECTION_ID).getSelectedPosition() == 2
    assert win._focus_id == window.SECTION_ID


def test_back_from_the_title_closes():
    win = _open(_view())
    win.onAction(xbmcgui.Action(xbmcgui.ACTION_NAV_BACK))
    assert win._closed is True


def test_previous_menu_behaves_like_back():
    win = _open(_view())
    win.onAction(xbmcgui.Action(xbmcgui.ACTION_PREVIOUS_MENU))
    assert win._closed is True


def test_a_failing_season_notifies_and_stays_open():
    from couchseerr.errors import SeerrRequestError

    def load(number):
        raise SeerrRequestError(500, "Unable to retrieve season.")

    win = _open(_view(seasons=[_season_row(1)]), load_season=load)
    win.getControl(window.SECTION_ID).selectItem(0)
    win.onClick(window.SECTION_ID)
    assert win._closed is False
    assert win.getProperty("section") == "seasons"
    assert xbmcgui._notifications[-1][1] == "seerr returned 500: Unable to retrieve season."


def test_an_unexpected_season_failure_is_logged_loudly():
    def load(number):
        raise KeyError("airDate")

    win = _open(_view(seasons=[_season_row(1)]), load_season=load)
    win.getControl(window.SECTION_ID).selectItem(0)
    win.onClick(window.SECTION_ID)
    assert win._closed is False
    assert xbmcgui._notifications[-1][1] == LABELS["unexpected_error"]
    assert any("Traceback" in message for message, _level in xbmc._log_calls)


def test_a_failing_onInit_notifies_and_closes():
    """onInit runs through Kodi's own callback dispatcher, not open_detail's try/finally
    -- see IMPORTANT 3. A blank, unfocused window that doModal() blocks on forever, with
    nothing logged and nothing said, is exactly what the spec forbids."""
    bad_labels = dict(LABELS)
    del bad_labels["seasons"]
    win = window.DetailWindow("couchseerr-detail.xml", "/addon", "Default", "1080i")
    win.bind(_view(seasons=[_season_row(1)]), lambda n: _season_view(), bad_labels)
    win.onInit()
    assert win._closed is True
    assert xbmcgui._notifications[-1][1] == LABELS["unexpected_error"]
    assert any("Traceback" in message for message, _level in xbmc._log_calls)


def test_a_season_request_button_stays_on_the_season():
    """A season-scoped request is fired from the episode view, and like every other action
    it closes the window rather than leaving a stale Request button behind it."""
    fired = []
    win = _open(
        _view(seasons=[_season_row(1)]),
        load_season=lambda n: _season_view(
            actions=[_action("request", "Request this season", "plugin://x?mode=request&season=1")]
        ),
        run=fired.append,
    )
    win.getControl(window.SECTION_ID).selectItem(0)
    win.onClick(window.SECTION_ID)
    win.getControl(window.ACTIONS_ID).selectItem(0)
    win.onClick(window.ACTIONS_ID)
    assert fired == ["plugin://x?mode=request&season=1"]
    assert win._closed is True
