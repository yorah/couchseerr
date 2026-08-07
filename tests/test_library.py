from couchseerr.library import external_ids, match_library_id

# Measured on the target box, 2026-08-04: 559 of 560 movies carry imdb and none carry
# tmdb; 108 of 109 shows carry tvdb and none carry tmdb.
MOVIES = [
    {"movieid": 1, "label": "2 Guns", "year": 2013, "uniqueid": {"imdb": "tt1272878"}},
    {"movieid": 2, "label": "Dune", "year": 2021, "uniqueid": {"imdb": "tt1160419"}},
    {"movieid": 3, "label": "Sans identifiant", "year": 1999, "uniqueid": {}},
]
SHOWS = [
    {"tvshowid": 7, "label": "Game of Thrones", "year": 2011, "uniqueid": {"tvdb": "121361"}},
]


def test_external_ids_reads_a_movie_detail():
    detail = {"id": 693134, "imdbId": "tt15239678",
              "externalIds": {"imdbId": "tt15239678"}}
    assert external_ids(detail) == {"imdb": "tt15239678", "tvdb": None}


def test_external_ids_reads_a_tv_detail():
    detail = {"id": 1399, "externalIds": {"imdbId": "tt0944947", "tvdbId": 121361}}
    assert external_ids(detail) == {"imdb": "tt0944947", "tvdb": "121361"}


def test_external_ids_of_a_detail_with_none():
    assert external_ids({"id": 5}) == {"imdb": None, "tvdb": None}


def test_external_ids_with_none_external_ids():
    assert external_ids({"id": 5, "externalIds": None}) == {"imdb": None, "tvdb": None}


def test_matches_a_movie_on_its_imdb_id():
    assert match_library_id(MOVIES, "movieid", "imdb", "tt1160419", "Dune", 2021) == 2


def test_matches_a_show_on_its_tvdb_id():
    assert match_library_id(SHOWS, "tvshowid", "tvdb", "121361", "Game of Thrones", 2011) == 7


def test_id_match_wins_over_a_conflicting_title():
    """Titles are localised and duplicated across years; the id is the trustworthy key."""
    assert match_library_id(MOVIES, "movieid", "imdb", "tt1272878", "Dune", 2021) == 1


def test_namespace_is_respected_numeric_id_collision():
    """A numeric id under the wrong key must not match: false positives play the wrong film."""
    records = [
        {"movieid": 1, "label": "Title A", "year": 2020, "uniqueid": {"imdb": "tt1234567"}},
        {"movieid": 2, "label": "Title B", "year": 2021, "uniqueid": {"tmdb": "121361", "imdb": "tt7654321"}},
    ]
    assert match_library_id(records, "movieid", "imdb", "121361", None, None) is None


def test_falls_back_to_exact_title_and_year_when_there_is_no_id():
    assert match_library_id(MOVIES, "movieid", "imdb", None, "Sans identifiant", 1999) == 3


def test_the_title_fallback_requires_the_year_to_match():
    """A near miss here plays the wrong film, which is worse than playing nothing."""
    assert match_library_id(MOVIES, "movieid", "imdb", None, "Sans identifiant", 2003) is None


def test_the_title_fallback_is_case_insensitive_but_not_fuzzy():
    assert match_library_id(MOVIES, "movieid", "imdb", None, "sans identifiant", 1999) == 3
    assert match_library_id(MOVIES, "movieid", "imdb", None, "Sans identifian", 1999) is None


def test_record_with_title_field_instead_of_label():
    records = [
        {"movieid": 1, "title": "Movie Title", "year": 2020, "uniqueid": {"imdb": "tt1234567"}},
    ]
    assert match_library_id(records, "movieid", "imdb", None, "Movie Title", 2020) == 1


def test_no_match_returns_none_rather_than_guessing():
    assert match_library_id(MOVIES, "movieid", "imdb", "tt0000000", "Nowhere", 1970) is None


def test_a_record_without_the_id_field_is_skipped_not_crashed():
    records = [{"label": "Broken", "year": 2000, "uniqueid": {"imdb": "tt1"}}]
    assert match_library_id(records, "movieid", "imdb", "tt1", "Broken", 2000) is None
