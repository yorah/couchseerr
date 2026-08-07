# Couchseerr

A Kodi addon that shows your [seerr](https://github.com/seerr-team/seerr) discovery rows on
the TV. Every tile makes clear, at a glance, whether a title is already owned, currently
downloading, monitored and waiting, or not yet requested - without needing to focus it.

seerr is the only backend Couchseerr talks to. Since seerr already merges Radarr, Sonarr and
your media server, the addon needs no separate Radarr/Sonarr credentials and no local library
scan to know what you own.

## Requirements

- A running [seerr](https://github.com/seerr-team/seerr) instance reachable from your Kodi
  device (tested against seerr **3.4.1**).
- A seerr **API key** for that instance (seerr's own settings page: Settings → General → API
  Key).
- Kodi **19 through 22**.

## Installation

1. In Kodi, add the Couchseerr repository as a file source:
   **Settings → File manager → Add source** → enter
   `https://yorah.github.io/couchseerr/` → give it a name (e.g. "Couchseerr repo").
2. Install the repository add-on:
   **Settings → Add-ons → Install from zip file** → the source you just added →
   `repository.couchseerr-<version>.zip`.
3. Install Couchseerr itself:
   **Settings → Add-ons → Install from repository → Couchseerr Repository → Video add-ons →
   Couchseerr**.

Kodi will offer updates to both the repository and the addon automatically from then on.

## First-run setup

Open the addon's settings (**Settings → Add-ons → My add-ons → Video add-ons → Couchseerr →
Configure**) before browsing:

- **Connection → Seerr URL**: the base URL of your seerr instance, e.g. `http://seerr.local:5055`.
- **Connection → API key**: the API key from seerr's settings page.
- **Display → Language code**: optional. Leave blank to use Kodi's own UI language; set an
  explicit code (e.g. `fr`, `en`) to override it for seerr's localized titles.
- **Display → View mode id**: optional, and only worth setting after reading
  [Choosing a view](#choosing-a-view) below. Leave blank to keep whatever view Kodi already
  uses.

If the URL or key is wrong, Couchseerr shows a clear on-screen notification (never a silent
empty row) telling you what to check.

## What each row shows

- **Trending** - seerr's trending titles.
- **Upcoming movies** - movies not yet released.
- **Popular series** - popular TV shows.
- **On the way** - everything seerr is currently monitoring, downloading or pending, in one
  place.

Every tile carries a short marker so status is visible without focusing it:

| Marker | Meaning |
|---|---|
| `[✓]` | Owned - fully available |
| `[◐]` | Partially available |
| `[62%]` | Downloading, with live percent (and time remaining, when seerr reports one) |
| `[⋯]` | Monitored - seerr is tracking it, nothing active right now |
| `[2027-12-25]` | Unreleased, with the release date |
| `[⌛]` | Pending approval |
| *(no marker)* | Not yet requested |

## Choosing a view

Those markers are part of each tile's **label**, so they only appear in a view that draws
labels. Several skins default to an art-only view - "Wall" in Estuary, "Tableau" in Arctic
Fuse - which shows posters and nothing else until you focus a tile. In such a view every
tile looks identical and the addon tells you nothing.

Pick a view that shows titles: **Landscape** / **Paysage**, **List**, or any of the wide
variants. Couchseerr maps seerr's backdrop art to both `fanart` and `landscape`, so
landscape views render properly rather than showing blank tiles.

Two places to set this, and they are independent:

- **Browsing into the addon**: open the view selector (left sidebar in most skins) and pick
  a labelled view. Kodi remembers it for this addon from then on. Alternatively, set
  **Display → View mode id** in the addon settings to your skin's numeric id for that view;
  ids are skin-specific, so there is no sensible default and the setting ships blank.
- **A Home-screen widget row**: the layout comes from your skin's own widget style setting
  for that widget (Arctic Fuse: widget style → Paysage). Kodi gives an addon no way to
  choose this, so it has to be set skin-side, exactly as for the skin's built-in rows.

## Requesting

Configuring default profiles is what makes a one-click **Request** work: **Settings →
Add-ons → My add-ons → Video add-ons → Couchseerr → Configure → Requests**. It is not a
prerequisite for requesting at all - **Request with...** (below) picks a server and profile
per request and works on a completely unconfigured install. There are up to four rows:

- **Movie profile** - the Radarr server and quality profile ordinary film requests use.
- **TV profile** - the Sonarr server and quality profile ordinary series requests use.
- **Movie profile (4K)** / **TV profile (4K)** - only shown once Couchseerr has seen a 4K
  Radarr or Sonarr server on your seerr instance. On a fresh install these stay hidden;
  picking the ordinary movie or TV profile once is what discovers them, so they appear
  automatically from then on without any extra step.
- **Prefer 4K** - a toggle, shown alongside whichever 4K row(s) are visible, that sends
  ordinary requests to the 4K profile instead of the standard one.

Each row is a button, not a static list: selecting it asks your live seerr instance for
every server and quality profile combination it currently has and shows them in a picker,
so a wrong URL or API key fails right there rather than later, and the choices always match
what seerr actually offers. Picking one saves it as that slot's default; cancelling changes
nothing.

Root folder and language-profile selection are not exposed - the server's own defaults
apply, as in v1.

Clicking a tile opens a detail listing whose entries are the actions available for that
title, given its current state, rather than the "Unknown mode" notice from v1. For a title
that can still be requested you get **Request**, which fires immediately using the profile
configured for its slot, unless nothing is configured yet, in which case the entry reads
**Configure default profile** and takes you straight to the settings above. A title seerr
already has a trailer for also gets a **Trailer** entry, regardless of state.

Every requestable tile - in a discovery row, in search results, and every matching entry of
the detail listing - also carries two context-menu items: **Request**, which uses the
profile configured for that title's slot, and **Request with...**, which opens a picker
listing every profile on every configured server (each entry labelled `<server> -
<profile>` so a 4K server is unambiguous) and lets you send this one request through a
different profile without touching your defaults.

A request is refused, with an on-screen reason, when the title is already owned, partially
available, downloading, monitored, awaiting its release, or already pending approval.
Couchseerr checks the tile's own state before it ever contacts seerr: seerr's own
duplicate-request guard does not cover every one of those states, so relying on it alone
would let some duplicates through, to surface only later, downstream in Radarr or Sonarr.

## Seasons and episodes

Opening a TV title's detail listing shows one folder entry per season, each carrying the
same marker table as [What each row shows](#what-each-row-shows) (except the downloading
percentage, which seerr only reports per title, not per season). Opening a season shows
its actions: **Request this season** when the season's own state allows a request, followed
by the episodes Kodi's library already holds for it.

Episodes are listed only when Kodi's own library has scanned them - they come from Kodi,
never from seerr, so watched state, resume point, thumbnail and plot are exactly what your
library already knows. Selecting an episode plays it directly. A season Kodi has not
scanned, or a show with no Kodi library entry at all, shows one explanatory line instead of
an empty listing.

Requesting is per season, not per episode: seerr's own request API has no way to ask for a
single episode, only whole seasons or a whole show, so Couchseerr cannot offer one either.

## Search

Couchseerr exposes search directly as a route in its plugin path:

```
plugin://plugin.video.couchseerr/?mode=search&query=<text>
```

There's no search entry in Couchseerr's own menu - this route exists for a skin to drive,
not to browse to by hand. A skin whose search screen builds its container's path out of a
text box, appending what's typed so far, can drive this route live, refreshing on every
keystroke. Arctic Fuse 3's search screen works exactly this way.

The Arctic Fuse 3 recipe: stop Kodi first - it holds this file's data in memory and rewrites
it on shutdown, so an edit made while Kodi is running is silently undone. The file is a flat
JSON array at
`userdata/addon_data/script.skinvariables/nodes/skin.arctic.fuse.3/skinvariables-shortcut-searchwidgets.json`.
Append an object shaped like its existing entries:

```json
{
  "label": "Couchseerr",
  "icon": "",
  "path": "plugin://plugin.video.couchseerr/?mode=search&query=",
  "target": "videos",
  "widget_style": "Poster",
  "guid": "couchseerr-search"
}
```

`path` must end in `query=` with nothing after it - the skin appends the typed text itself.
`target` is `videos`, matching the content type Couchseerr's own search route sets.
`widget_style` is any skin view name (`Poster` above; use `Landscape` / `Paysage` if you'd
rather have search results carry the same markers-in-label view as
[Choosing a view](#choosing-a-view) recommends for browsing). `guid` only has to be unique
within the file - it's how the skin tells this row apart from the others, not a value
Couchseerr reads or cares about.

Two things exist here because the container reloads on every keystroke, not once per
finished search:

- **A three-character minimum.** Below that, the route returns an empty listing without
  calling seerr at all - otherwise every keystroke on the way to a real query would be its
  own API call for a result nobody is going to read.
- **Per-query caching**, for 30 seconds. Backspacing back to something you already typed
  replays the cached answer instead of re-querying seerr.

## For skinners

Every tile Couchseerr builds - in a discovery row or in search results alike - carries the
same set of custom properties, because there is exactly one place in the addon that builds a
ListItem. A skin can read them with `ListItem.Property(seerr.status)` and its siblings, in
any view:

| Property | Holds | Empty when |
|---|---|---|
| `seerr.status` | One of `owned`, `partial`, `downloading`, `monitored`, `unreleased`, `pending`, `actionable` | Never - always set |
| `seerr.progress` | Download percent, as a string integer (e.g. `"62"`) | The title isn't actively downloading |
| `seerr.eta` | seerr's own time-remaining string for the download | No download in progress, or seerr reports no estimate |
| `seerr.requestable` | `"1"` | The state doesn't allow a request (owned, partial, downloading, monitored, unreleased, or pending) |
| `seerr.action.request` | A ready-to-run `plugin://` path that starts a request for this title | Same cases as `seerr.requestable` above |

Running `seerr.action.request` always uses the profile configured for that title's slot in
settings - it carries no profile choice of its own (it can't; building the tile is pure and
has no access to the settings file), so the addon resolves the default at the moment the
request runs. A skin button can treat the property's presence as its visibility condition:
empty means the title can't be requested right now.

This matters because every marker in [What each row shows](#what-each-row-shows) lives in
the tile's **label**. In an art-only view - "Tableau" in Arctic Fuse, "Wall" in Estuary -
nothing draws the label, so nothing draws the marker either, and the addon's whole premise,
a title's status visible without focusing it, disappears completely. A skin badge that reads
`seerr.status` (and `seerr.progress` for the downloading case) is the only fix for that kind
of view. No code in this addon can supply one - Kodi gives an addon no way to draw into a
skin's own art-only layout, only the label it already renders.

## Not yet implemented in this release

Couchseerr v1 was read-only; this release adds requesting, playback of titles you already
own, search, and per-season browsing - see the sections above. Still not available, and not
planned for this release unless noted otherwise:

- **Episode requesting.** Not merely unbuilt: seerr's request API has no episode-level
  endpoint, only whole seasons or a whole show, so there is no way to add this without a
  change on seerr's side.
- **A purpose-built detail screen.** Clicking a tile opens a plain Kodi listing of the
  actions available for it, not a custom window.
- **Built-in skin support.** The Arctic Fuse recipe above is a config edit you make
  yourself; no skin ships with Couchseerr integration, and none is bundled with this
  release.

## License

GPL-3.0-or-later - see [LICENSE](LICENSE).

Copyright (C) 2026 yorah. This program is free software: you can redistribute it and/or modify it
under the terms of the GNU General Public License as published by the Free Software Foundation,
either version 3 of the License, or (at your option) any later version. It is distributed WITHOUT
ANY WARRANTY; see the license for details.
