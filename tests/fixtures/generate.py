#!/usr/bin/env python3
"""Generate synthetic seerr fixtures.

Shapes match a live seerr 3.4.1 instance; all content is invented. Fixtures are built to
exercise every TileState, multi-server/multi-profile setups, and both populated and empty
downloadStatus.
"""
import json
import pathlib
import shutil

OUT = pathlib.Path(__file__).resolve().parent / "seerr"
if OUT.exists():
    shutil.rmtree(OUT)
OUT.mkdir(parents=True)


def write(name, payload):
    (OUT / f"{name}.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    )


def media_info(
    media_id, tmdb_id, media_type, status, status4k=1, downloading=None, seasons=None
):
    """A mediaInfo block as embedded in discover results and returned by /media."""
    info = {
        "downloadStatus": downloading or [],
        "downloadStatus4k": [],
        "id": media_id,
        "mediaType": media_type,
        "tmdbId": tmdb_id,
        "tvdbId": 90001 if media_type == "tv" else None,
        "imdbId": None,
        "status": status,
        "status4k": status4k,
        "createdAt": "2026-01-05T10:00:00.000Z",
        "updatedAt": "2026-01-06T10:00:00.000Z",
        "lastSeasonChange": "2026-01-05T10:00:00.000Z",
        "mediaAddedAt": "2026-01-05T10:00:00.000Z",
        "serviceId": 0,
        "serviceId4k": None,
        "externalServiceId": 1000 + media_id,
        "externalServiceId4k": None,
        "externalServiceSlug": str(tmdb_id),
        "externalServiceSlug4k": None,
        "ratingKey": None,
        "ratingKey4k": None,
        "jellyfinMediaId": None,
        "jellyfinMediaId4k": None,
        "seasons": seasons or [],
        "serviceUrl": f"http://radarr.example.internal/movie/{tmdb_id}",
    }
    return info


def downloading(size=8_000_000_000, left=3_040_000_000, time_left="00:14:32"):
    return [
        {
            "mediaType": "movie",
            "externalId": 1001,
            "size": size,
            "sizeLeft": left,
            "status": "downloading",
            "timeLeft": time_left,
            "estimatedCompletionTime": "2026-01-06T10:14:32.000Z",
            "title": "Placeholder.Release.2160p",
        }
    ]


def movie(tmdb_id, title, release_date, info=None):
    return {
        "id": tmdb_id,
        "mediaType": "movie",
        "adult": False,
        "genreIds": [878, 12],
        "originalLanguage": "en",
        "originalTitle": title,
        "overview": "Placeholder overview text for fixture purposes.",
        "popularity": 120.5,
        "posterPath": "/fixturePoster.jpg",
        "backdropPath": "/fixtureBackdrop.jpg",
        "releaseDate": release_date,
        "title": title,
        "video": False,
        "voteAverage": 7.1,
        "voteCount": 900,
        **({"mediaInfo": info} if info else {}),
    }


def show(tmdb_id, name, first_air_date, info=None):
    return {
        "id": tmdb_id,
        "mediaType": "tv",
        "genreIds": [18],
        "originalLanguage": "en",
        "originalName": name,
        "overview": "Placeholder overview text for fixture purposes.",
        "popularity": 88.2,
        "posterPath": "/fixturePoster.jpg",
        "backdropPath": "/fixtureBackdrop.jpg",
        "firstAirDate": first_air_date,
        "name": name,
        "voteAverage": 8.0,
        "voteCount": 400,
        **({"mediaInfo": info} if info else {}),
    }


# --- Discover: one item per TileState ---------------------------------------------
# Fixture Two exercises max(status, status4k): status 1 but status4k 3 must read as
# in-flight, not as absent.
TRENDING = [
    movie(101, "Fixture One", "2025-06-01", media_info(1, 101, "movie", 5)),
    movie(102, "Fixture Two", "2025-07-01", media_info(2, 102, "movie", 1, status4k=3)),
    movie(
        103,
        "Fixture Three",
        "2025-08-01",
        media_info(3, 103, "movie", 3, downloading=downloading()),
    ),
    movie(104, "Fixture Four", "2025-09-01", media_info(4, 104, "movie", 3)),
    movie(105, "Fixture Five", "2027-12-25", media_info(5, 105, "movie", 3)),
    movie(106, "Fixture Six", "2025-10-01", media_info(6, 106, "movie", 2)),
    movie(107, "Fixture Seven", "2025-11-01"),
    show(201, "Fixture Series A", "2024-01-01", media_info(7, 201, "tv", 4)),
    show(202, "Fixture Series B", "2024-02-01", media_info(8, 202, "tv", 5)),
    show(203, "Fixture Series C", "2024-03-01"),
]


def service_radarr(count):
    return [
        {
            "id": index,
            "name": "Radarr {0}".format(index + 1),
            "is4k": False,
            "isDefault": index == 0,
            "activeProfileId": 21,
            "activeDirectory": "/data/movies",
        }
        for index in range(count)
    ]


def service_sonarr(count):
    return [
        {
            "id": index,
            "name": "Sonarr {0}".format(index + 1),
            "is4k": False,
            "isDefault": index == 0,
            "activeProfileId": 12,
            "activeLanguageProfileId": 1,
            "activeDirectory": "/data/tv",
        }
        for index in range(count)
    ]


def service_detail():
    return {
        "server": service_radarr(1)[0],
        "profiles": [
            {"id": 21, "name": "VF Bluray-1080p"},
            {"id": 7, "name": "Ultra-HD"},
        ],
        "rootFolders": [{"id": 1, "path": "/data/movies"}],
    }


def search_results():
    return {
        "page": 1,
        "totalPages": 1,
        "totalResults": 3,
        "results": [
            {
                "id": 201, "mediaType": "movie", "title": "Fixture Search Movie",
                "originalTitle": "Fixture Search Movie", "releaseDate": "2024-03-01",
                "overview": "A synthetic search hit.",
                "posterPath": "/fixtureSearchPoster.jpg",
                "backdropPath": "/fixtureSearchBackdrop.jpg",
                "mediaInfo": {"status": 5, "status4k": 1},
            },
            {
                "id": 202, "mediaType": "tv", "name": "Fixture Search Series",
                "originalName": "Fixture Search Series", "firstAirDate": "2023-09-10",
                "overview": "A synthetic series hit.",
                "posterPath": "/fixtureSearchSeriesPoster.jpg",
                "backdropPath": None,
            },
            {
                # seerr returns people in search results; the row must drop them rather
                # than render a person as an unrequestable film.
                "id": 203, "mediaType": "person", "name": "Fixture Person",
                "profilePath": "/fixturePerson.jpg",
            },
        ],
    }


def request_created():
    return {
        "id": 42, "status": 1, "type": "movie",
        "media": {"id": 9, "tmdbId": 693134, "status": 3, "status4k": 1},
    }


def error_body(message):
    return {"message": message}


def page(results, page_no=1, pages=1):
    return {
        "page": page_no,
        "totalPages": pages,
        "totalResults": len(results),
        "results": results,
    }


write("discover_trending", page(TRENDING))
write("discover_movies", page([r for r in TRENDING if r["mediaType"] == "movie"]))
write("discover_tv", page([r for r in TRENDING if r["mediaType"] == "tv"]))
write(
    "discover_movies_upcoming",
    page([movie(108, "Fixture Upcoming", "2027-03-01")]),
)
write("search", page([TRENDING[0], TRENDING[7]]))

# Localized variant: same ids, translated titles, to prove the language param is wired
# through without changing identity.
write(
    "discover_trending_localized",
    page(
        [
            {**TRENDING[0], "title": "Fixture Un"},
            {**TRENDING[1], "title": "Fixture Deux"},
        ]
    ),
)

# --- /media -----------------------------------------------------------------------
# Thin rows: no title, no artwork. Deliberately mixes an actively downloading item with
# ones merely monitored, since that distinction drives three separate tile states.
write(
    "media_processing",
    {
        "pageInfo": {"pages": 1, "pageSize": 20, "results": 3, "page": 1},
        "results": [
            media_info(3, 103, "movie", 3, downloading=downloading()),
            media_info(4, 104, "movie", 3),
            media_info(5, 105, "movie", 3),
        ],
    },
)
write(
    "media_available",
    {
        "pageInfo": {"pages": 1, "pageSize": 20, "results": 1, "page": 1},
        "results": [media_info(1, 101, "movie", 5)],
    },
)

# --- /request ---------------------------------------------------------------------
write(
    "request_all",
    {
        "pageInfo": {"pages": 1, "pageSize": 10, "results": 1, "page": 1},
        "results": [
            {
                "id": 1,
                "status": 2,
                "createdAt": "2026-01-05T10:00:00.000Z",
                "updatedAt": "2026-01-05T10:00:00.000Z",
                "type": "movie",
                "is4k": False,
                "serverId": 0,
                "profileId": 1,
                "profileName": "Standard 1080p",
                "rootFolder": "/movies",
                "languageProfileId": None,
                "tags": [],
                "isAutoRequest": False,
                "canRemove": True,
                "seasons": [],
                "seasonCount": 0,
                "media": media_info(3, 103, "movie", 3, downloading=downloading()),
                "requestedBy": {
                    "id": 1,
                    "email": "user@example.com",
                    "username": "fixture-user",
                    "plexUsername": None,
                    "jellyfinUsername": None,
                    "userType": 1,
                    "permissions": 2,
                    "avatar": "/avatar.png",
                    "warnings": [],
                    "movieQuotaLimit": None,
                    "movieQuotaDays": None,
                    "tvQuotaLimit": None,
                    "tvQuotaDays": None,
                    "createdAt": "2025-01-01T00:00:00.000Z",
                    "updatedAt": "2025-01-01T00:00:00.000Z",
                    "requestCount": 1,
                },
                "modifiedBy": None,
            }
        ],
    },
)

# --- /service ---------------------------------------------------------------------
# Two servers each, so multi-instance profile resolution is covered. A single-server
# install is the degenerate case of this, not a separate shape.
write(
    "service_radarr",
    [
        {
            "id": 0,
            "name": "Movies",
            "is4k": False,
            "isDefault": True,
            "activeDirectory": "/movies",
            "activeProfileId": 1,
        },
        {
            "id": 1,
            "name": "Movies 4K",
            "is4k": True,
            "isDefault": False,
            "activeDirectory": "/movies-4k",
            "activeProfileId": 2,
        },
    ],
)
write(
    "service_sonarr",
    [
        {
            "id": 0,
            "name": "Series",
            "is4k": False,
            "isDefault": True,
            "activeDirectory": "/series",
            "activeProfileId": 10,
            "activeLanguageProfileId": 1,
        },
        {
            "id": 1,
            "name": "Series 4K",
            "is4k": True,
            "isDefault": False,
            "activeDirectory": "/series-4k",
            "activeProfileId": 11,
            "activeLanguageProfileId": 1,
        },
    ],
)
write(
    "service_radarr_0",
    {
        "server": {
            "id": 0,
            "name": "Movies",
            "is4k": False,
            "isDefault": True,
            "activeDirectory": "/movies",
            "activeProfileId": 1,
        },
        "profiles": [
            {"id": 1, "name": "Standard 1080p"},
            {"id": 2, "name": "Ultra HD 2160p"},
        ],
        "rootFolders": [
            {"id": 1, "path": "/movies", "freeSpace": 500_000_000_000},
        ],
        "tags": [{"id": 1, "label": "fixture"}],
    },
)
write(
    "service_sonarr_0",
    {
        "server": {
            "id": 0,
            "name": "Series",
            "is4k": False,
            "isDefault": True,
            "activeDirectory": "/series",
            "activeProfileId": 10,
            "activeLanguageProfileId": 1,
        },
        "profiles": [
            {"id": 10, "name": "Standard 1080p"},
            {"id": 11, "name": "Ultra HD 2160p"},
        ],
        "rootFolders": [
            {"id": 1, "path": "/series", "freeSpace": 500_000_000_000},
        ],
        "languageProfiles": [
            {"id": 1, "name": "Original"},
            {"id": 2, "name": "Dubbed"},
        ],
        "tags": [],
    },
)

# Task 2: service discovery and search fixtures, distinct from the pair above -- these
# exercise servers()/server_detail() against single- and multi-instance responses.
write("service_radarr_one", service_radarr(1))
write("service_radarr_two", service_radarr(2))
write("service_sonarr_one", service_sonarr(1))
write("service_radarr_detail", service_detail())

# --- /search ------------------------------------------------------------------------
write("search_dune", search_results())

# --- /request (create) ---------------------------------------------------------------
write("request_created", request_created())

# --- TV seasons: every season state in one payload ---------------------------------
def season(number, name, episodes, air_date, poster=None):
    return {"id": 3500 + number, "airDate": air_date, "episodeCount": episodes,
            "name": name, "overview": "", "seasonNumber": number, "posterPath": poster}


def tracked_season(number, status, status4k=1):
    return {"id": 30 + number, "seasonNumber": number, "status": status,
            "status4k": status4k, "createdAt": "2026-01-05T10:00:00.000Z",
            "updatedAt": "2026-01-06T10:00:00.000Z"}


TV_SEASONS = {
    "id": 90100,
    "name": "Signal Lost",
    "overview": "A radio station keeps broadcasting after the town leaves.",
    "firstAirDate": "2019-11-12",
    "posterPath": "/signal-lost.jpg",
    "backdropPath": "/signal-lost-wide.jpg",
    "seasons": [
        season(0, "Specials", 3, "2019-10-01", "/sp.jpg"),
        season(1, "Season 1", 8, "2019-11-12", "/s1.jpg"),
        season(2, "Season 2", 8, "2020-10-30"),
        season(3, "Season 3", 8, "2021-11-04"),
        season(4, "Season 4", 8, "2022-12-01"),
        season(5, "Season 5", 8, "2023-12-06"),
        season(6, "Season 6", 8, "2027-01-14"),
        season(7, "Season 7", 0, None),
    ],
    "externalIds": {"tvdbId": 90001, "imdbId": None},
    "relatedVideos": [{"site": "YouTube", "key": "trailer-key", "type": "Trailer"}],
    "mediaInfo": media_info(
        41, 90100, "tv", status=4,
        seasons=[
            tracked_season(1, 5),   # owned
            tracked_season(2, 4),   # partial
            tracked_season(3, 3),   # monitored
            tracked_season(4, 2),   # pending
            tracked_season(6, 3),   # processing but airing in 2027 -> unreleased
            # 5 is absent -> actionable, the ordinary case for an unrequested season
        ],
    ),
}
write("tv_seasons", TV_SEASONS)

TV_SEASONS_UNTRACKED = dict(TV_SEASONS, id=90101, name="Nobody Asked", mediaInfo=None)
write("tv_seasons_untracked", TV_SEASONS_UNTRACKED)

#: Kodi VideoLibrary.GetEpisodes records, not a seerr payload: the season listing joins
#: seerr's seasons against Kodi's own episodes, so the suite needs both shapes.
write("episodes_season_1", {"episodes": [
    {"episodeid": 11, "episode": 1, "season": 1, "title": "Carrier Wave",
     "plot": "The tower stays lit.", "firstaired": "2019-11-12", "playcount": 1,
     "resume": {"position": 0, "total": 0}, "runtime": 2700,
     "art": {"thumb": "image://episode-11/"}},
    {"episodeid": 12, "episode": 2, "season": 1, "title": "Dead Air",
     "plot": "Nobody answers.", "firstaired": "2019-11-19", "playcount": 0,
     "resume": {"position": 420.0, "total": 2700.0}, "runtime": 2700,
     "art": {"thumb": "image://episode-12/"}},
]})

# --- misc -------------------------------------------------------------------------
write(
    "status",
    {
        "version": "3.4.1",
        "commitTag": "0000000000000000000000000000000000000000",
        "updateAvailable": False,
        "commitsBehind": 0,
        "restartRequired": False,
    },
)
write(
    "settings_public",
    {
        "initialized": True,
        "applicationTitle": "Seerr",
        "applicationUrl": "",
        "hideAvailable": False,
        "localLogin": True,
        "mediaServerLogin": True,
        "movie4kEnabled": False,
        "series4kEnabled": False,
        "discoverRegion": "",
        "streamingRegion": "US",
        "originalLanguage": "",
        "mediaServerType": 2,
        "partialRequestsEnabled": True,
    },
)

# Error shapes, so failure handling is testable without provoking a live 4xx.
write("error_401", {"message": "You do not have permission to access this endpoint."})
write("error_403_quota", {"message": "Request quota exceeded."})
write("error_500", {"message": "Internal Server Error"})
write("error_quota", error_body("Request quota exceeded"))
write("error_duplicate", error_body("Request for this media already exists"))

for path in sorted(OUT.glob("*.json")):
    print(f"{path.name:34} {path.stat().st_size:>7} bytes")
