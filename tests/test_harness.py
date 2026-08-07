def test_fixture_loader_reads_synthetic_discover(fixture):
    data = fixture("discover_trending")
    assert data["results"][0]["title"] == "Fixture One"


def test_couchseerr_package_importable():
    import couchseerr

    assert couchseerr.__name__ == "couchseerr"


def test_kodi_stubs_importable():
    import xbmc
    import xbmcgui
    import xbmcplugin

    assert xbmcgui.ListItem is not None
