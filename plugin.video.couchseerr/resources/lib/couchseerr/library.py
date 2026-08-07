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
"""Match a seerr title against Kodi's video library. Pure: records come from the caller.

The v1 design assumed Kodi stores a tmdb uniqueid. Measured on the target library it does
not: 559 of 560 movies carry imdb only, 108 of 109 shows carry tvdb only, and none carry
tmdb. seerr's detail payload supplies both, so the join goes through imdb or tvdb, with
exact title-and-year as the only fallback.
"""


def external_ids(detail):
    """Pull the ids Kodi actually stores out of a seerr detail payload."""
    external = detail.get("externalIds") or {}
    imdb = detail.get("imdbId") or external.get("imdbId") or None
    tvdb = external.get("tvdbId")
    return {
        "imdb": str(imdb) if imdb else None,
        "tvdb": str(tvdb) if tvdb else None,
    }


def match_library_id(records, id_key, uniqueid_key, external_id, title, year):
    """Return the Kodi library id for this title, or None.

    Order matters: an id match beats a title match, because titles are localised,
    duplicated across remakes, and routinely disagree between TMDb and a local scraper.
    The fallback demands an exact, case-insensitive title *and* the same year: a fuzzy
    match here plays the wrong film, which is worse than playing nothing.

    On a box whose language setting is not English, the title fallback is close to dead
    and is meant to be: the caller's title came from a payload fetched with that language
    ("Dune, deuxieme partie"), while Kodi's library holds whatever its own scraper wrote,
    normally English ("Dune: Part Two"). Exact matching then fails and playback reports
    "not in your library" for the handful of titles carrying no imdb/tvdb id at all.
    That is the intended trade: loosening the match to rescue those few is how the wrong
    film gets played, so do not "fix" this by fuzzy-matching or dropping the year.

    Args:
        records: List of library records from Kodi's GetMovies/GetTVShows.
        id_key: The key name for the library id ("movieid" or "tvshowid").
        uniqueid_key: The key to use in the uniqueid dict ("imdb" or "tvdb").
        external_id: The id from seerr, or None for title-based matching.
        title: The title from seerr, or None if only id-based matching.
        year: The year from seerr.
    """
    if external_id:
        wanted = str(external_id)
        for record in records:
            if id_key not in record:
                continue
            uniqueid = (record.get("uniqueid") or {}).get(uniqueid_key)
            if uniqueid is not None and str(uniqueid) == wanted:
                return record[id_key]

    if title and year:
        wanted_title = title.strip().lower()
        for record in records:
            if id_key not in record:
                continue
            label = (record.get("title") or record.get("label") or "").strip().lower()
            if label == wanted_title and record.get("year") == year:
                return record[id_key]
    return None
