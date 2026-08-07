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
"""The season-level facts the detail window renders: names, the seerr/Kodi episode join,
and how one episode row reads.

Pure, like detail.py: parsed values and labels in, plain values out. Nothing here imports
Kodi, and nothing here builds a ListItem or a ListItemSpec -- ui/spec.py plus
kodi/adapter.py remain the single construction site. detailview.py is the only caller.

A season is browsed, never actioned by the click that opens it, which is what resolves the
one collision in this feature: a partial season is both browsable and re-requestable, and
separating "open the season" from "request the season" is what keeps a click from meaning
two different things.
"""

#: The label key for a season-scoped request. Read from here rather than spelled inline:
#: the same action reading two different keys is how one renderer came to say "Request
#: this season" while another said "Request".
SEASON_REQUEST_LABEL_KEY = "request_season"


def season_label(season, labels):
    """seerr localises a season's name through TMDb, so prefer it; fall back to the
    addon's own localised format when TMDb has no name for it."""
    return season.name or labels["season"].format(season.number)


class JoinedEpisode(object):
    """One episode row: what seerr knows, plus whether this box actually has it.

    `overview` and `still_path` are seerr's own, carried through untouched so a renderer
    can describe an episode this box does not hold -- an unowned row has no Kodi record
    to take a plot or a thumb from, and dropping them here is what would make
    models.Episode's parsing of them unreachable. `still_path` is already absolute
    (see models.parse_season_episodes), so no image_base is ever prefixed to it.
    """

    __slots__ = ("number", "title", "air_date", "owned", "episode_id", "record",
                 "overview", "still_path")

    def __init__(self, number, title, air_date=None, owned=False, episode_id=None,
                 record=None, overview="", still_path=None):
        self.number = number
        self.title = title
        self.air_date = air_date
        self.owned = owned
        self.episode_id = episode_id
        self.record = record
        self.overview = overview
        self.still_path = still_path


def join_episodes(seerr_episodes, kodi_records, season_number):
    """seerr's episode list, marked with what Kodi holds, ascending by number.

    Matching is exact on (season, episode) and nothing else. TMDb and TVDB disagree about
    the numbering of some shows, so a fuzzy match here would attach a play action to the
    wrong file -- the one failure this join must never produce. When numbering disagrees,
    an owned episode reads as unowned, and any Kodi record that matched nothing is
    appended rather than dropped: the result is more rows than expected, never a playable
    episode that vanished.

    Kodi wins every field it supplies, because it describes the file that will play.

    Two Kodi records for the same (season, episode) -- a second rip of one episode --
    deliberately collapse to the last one seen: the row leads to one playable file, and
    picking between versions is a job for Kodi's own playback path, not for this join.
    """
    by_number = {}
    for record in kodi_records:
        if record.get("season") != season_number:
            continue
        number = record.get("episode")
        if isinstance(number, int) and number > 0:
            by_number[number] = record

    joined = []
    for episode in seerr_episodes:
        record = by_number.pop(episode.number, None)
        joined.append(
            JoinedEpisode(
                number=episode.number,
                title=(record or {}).get("title") or episode.title,
                air_date=episode.air_date,
                owned=record is not None,
                episode_id=(record or {}).get("episodeid"),
                record=record,
                overview=episode.overview,
                still_path=episode.still_path,
            )
        )

    # Whatever Kodi held that seerr never mentioned. Always owned, by definition.
    for number, record in by_number.items():
        joined.append(
            JoinedEpisode(
                number=number,
                title=record.get("title") or "",
                owned=True,
                episode_id=record.get("episodeid"),
                record=record,
            )
        )
    return sorted(joined, key=lambda entry: entry.number)


def episode_label_and_info(number, title, record, air_date=None, overview=""):
    """The label and the info dict for one episode row.

    Lives here rather than inside detailview._episode_row so the label format, the info
    keys and the resume rule stay one rule each: three small rules expressed twice is
    exactly how two rows describing the same episode start disagreeing.

    `air_date` and `overview` are seerr's fallbacks, used only for a row Kodi has no
    record of. An owned row passes neither: Kodi always has the better answer for a file
    it actually holds.
    """
    info = {"title": title, "plot": record.get("plot") or overview or ""}
    aired = record.get("firstaired")
    if not aired and air_date is not None:
        aired = air_date.isoformat()
    if aired:
        info["premiered"] = aired
    if record.get("playcount") is not None:
        info["playcount"] = record["playcount"]
    resume = record.get("resume") or {}
    # A zero position is "never started", not a resume point: passing it would make Kodi
    # offer to resume from the beginning of every unwatched episode.
    if resume.get("position"):
        info["resume"] = (resume["position"], resume.get("total") or 0)

    # Kodi always supplies a number for a scanned episode; the fallback exists only for a
    # malformed record, and "0. Title" would read as a real, wrong episode number rather
    # than as the degradation it is -- so fall back to the bare title instead.
    label = ("{0}. {1}".format(number, title) if number else title).strip()
    return label, info
