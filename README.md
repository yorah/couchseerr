<div align="center">

<img src="plugin.video.couchseerr/icon.png" width="96" alt="Couchseerr">

# Couchseerr

**Your [seerr](https://github.com/seerr-team/seerr) discovery rows on the TV, where every tile shows its status without being focused.**

[![CI](https://github.com/yorah/couchseerr/actions/workflows/ci.yml/badge.svg)](https://github.com/yorah/couchseerr/actions/workflows/ci.yml)
![Kodi 19 to 22](https://img.shields.io/badge/Kodi-19%20to%2022-blue)
![seerr 3.4.1+](https://img.shields.io/badge/seerr-3.4.1%2B-orange)
![License GPL-3.0-or-later](https://img.shields.io/badge/license-GPL--3.0--or--later-green)

</div>

Browse what's trending, see at a glance what you already own or is still downloading, and request
what you don't have. All from the couch.

seerr is the only backend. It already merges Radarr, Sonarr and your media server, so Couchseerr
needs no separate credentials, no TMDb key, and no library scan to know what you own.

## Status at a glance

Every tile carries a marker in its label, so you never have to focus a tile to know where it stands.

| Marker | Meaning |
|---|---|
| `[✓]` | Owned, fully available |
| `[◐]` | Partially available |
| `[62%]` | Downloading, with live percent and time remaining |
| `[⋯]` | Monitored, nothing active right now |
| `[2027-12-25]` | Not yet released, with the date |
| `[⌛]` | Awaiting approval |
| *(none)* | Not requested yet |

> [!IMPORTANT]
> Markers live in the tile **label**, so an art-only view draws none of them. See
> [Pick a view that shows labels](#pick-a-view-that-shows-labels).

## Requirements

- A [seerr](https://github.com/seerr-team/seerr) instance reachable from Kodi, version **3.4.1 or later**
- Its **API key**, from seerr's *Settings → General → API Key*
- **Kodi 19 to 22**

## Install

> [!NOTE]
> Couchseerr has not had its first release yet, so the add-on repository below is not live.
> Until it is, use the from-source path.

<details open>
<summary><b>From source</b> (works today)</summary>

```bash
git clone https://github.com/yorah/couchseerr.git
cd couchseerr
python3 scripts/build_repo.py dist
```

Copy `dist/zips/plugin.video.couchseerr/plugin.video.couchseerr-<version>.zip` to your Kodi device,
then in Kodi: **Settings → Add-ons → Install from zip file** and pick it.

</details>

<details>
<summary><b>From the add-on repository</b> (once released)</summary>

1. **Settings → File manager → Add source** → `https://yorah.github.io/couchseerr/`
2. **Settings → Add-ons → Install from zip file** → that source → `repository.couchseerr-<version>.zip`
3. **Settings → Add-ons → Install from repository → Couchseerr Repository → Video add-ons → Couchseerr**

Kodi then keeps both up to date automatically.

</details>

## Setup

**Settings → Add-ons → My add-ons → Video add-ons → Couchseerr → Configure**

| Setting | Required | What it does |
|---|---|---|
| **Seerr URL** | yes | Base URL including port, e.g. `http://seerr.local:5055` |
| **API key** | yes | From seerr's settings page |
| **Language code** | no | Language of the titles and plots *seerr returns*. Blank follows Kodi's UI language |
| **View mode id** | no | Skin-specific view number. Blank keeps whatever view Kodi remembers |

A wrong URL or key produces a clear on-screen message, never a silently empty row.

## Using it

### Rows

**Trending**, **Upcoming movies**, **Popular series**, and **On the way**: everything seerr is
monitoring, downloading or holding for approval, in one place.

### Requesting

Click any tile to open a detail window for that title: artwork, the plot, its status, and the
actions it actually offers. What you get depends on the title's state: **Request**, **Trailer**,
**Seasons**, or **Play** when Kodi's library already has it. Nothing is requested or played by the
click itself, and every action closes the window before it runs.

Every requestable tile also has two context-menu items:

- **Request** uses the default profile for that title's type
- **Request with...** picks a server and quality profile for this one request, leaving your defaults alone

Kodi adds its own **Play** to that menu, on every tile, and no addon can take it away. Couchseerr
answers it honestly rather than pretending it is not there: on a film your Kodi library already
holds it plays that file, and on anything else it says **Not available to play** and leaves you
where you were. Use the tile itself, not that entry, to open the detail window.

Tiles in a Home-screen widget open the same window on click. They have to take a different route to
get there - a skin hands Kodi's video info dialog to a widget tile that is not a folder, and the
add-on never hears the click - so a widget's tiles are folders, and the folder's directory is never
rendered: it ends immediately and re-enters the add-on as a script, which is the context a window
can open in. Closing the window returns you to Home. Nothing about this is configurable, and
nothing changes for the add-on's own rows.

Requests are refused, with a reason on screen, for titles that are already owned, partial,
downloading, monitored, unreleased or pending. Couchseerr checks the tile's own state before
contacting seerr, because seerr's duplicate guard does not cover every one of those cases.

<details>
<summary><b>Default profiles</b>, so Request is one click</summary>

Under **Configure → Requests**. Not a prerequisite: **Request with...** works on a completely
unconfigured install.

- **Movie profile** and **TV profile**, the Radarr and Sonarr server plus quality profile ordinary requests use
- **Movie profile (4K)** and **TV profile (4K)**, which appear only once Couchseerr has seen a 4K server on your instance. Picking an ordinary profile once is what discovers them
- **Prefer 4K**, sends ordinary requests to the 4K profile instead

Each row asks your live seerr instance for the servers and profiles it currently has, so the
choices always match reality and a bad URL or key fails right there. Root folder and language
profile are not exposed; the server's own defaults apply.

</details>

### Seasons and episodes

A TV title's detail window lists its seasons, each with its own marker. Opening a season swaps the
same list to **Request this season** followed by every episode of that season, and Back steps back
out to the season list.

Every episode is listed, owned or not. Episodes Kodi's library already holds play normally, with
whatever watched state, resume point, artwork and plot your library already knows; episodes Kodi
does not hold render dimmed and do nothing, because seerr's API has no episode-level endpoint, so
Couchseerr cannot offer one. Selecting a playable episode plays it, resuming where you left off.

Requesting is per season, not per episode, for the same reason.

### Search

Search is a plugin route for a skin's own search screen to drive, not a menu entry:

```
plugin://plugin.video.couchseerr/?mode=search&query=<text>
```

It refreshes on every keystroke, so queries under three characters make no API call at all, and
each query is cached for 30 seconds.

<details>
<summary><b>Arctic Fuse 3 recipe</b></summary>

**Stop Kodi first.** It holds this file in memory and rewrites it on shutdown, silently undoing
edits made while it runs.

Append to the flat JSON array at
`userdata/addon_data/script.skinvariables/nodes/skin.arctic.fuse.3/skinvariables-shortcut-searchwidgets.json`:

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

`path` must end at `query=` with nothing after it; the skin appends the typed text. `guid` only has
to be unique within the file.

</details>

## Pick a view that shows labels

Several skins default to an art-only view that draws posters and nothing else, such as Estuary's
"Wall". In those, every tile looks identical and Couchseerr tells you nothing.

Pick **Landscape**, **List**, or any wide variant. seerr's backdrop art is mapped to both `fanart`
and `landscape`, so landscape views render properly instead of showing blanks.

Two places, set independently:

- **Browsing the add-on:** open the view selector and pick a labelled view. Kodi remembers it. Or set **View mode id** in settings to your skin's numeric id
- **A Home-screen widget:** comes from your skin's widget style for that row (Arctic Fuse: widget style → Landscape). Kodi gives add-ons no way to set this

## Troubleshooting

| Symptom | Cause |
|---|---|
| Every tile looks the same | Art-only view. See [Pick a view that shows labels](#pick-a-view-that-shows-labels) |
| A row is empty with a message | Wrong URL or API key, or seerr unreachable. The message says which |
| **Request** reads *Configure default profile* | No default set yet for that type. Selecting it opens the right settings page |
| No 4K rows in settings | Expected until Couchseerr sees a 4K server. Pick an ordinary profile once |
| Some episodes are dimmed and do nothing when selected | Kodi's library does not hold them. seerr has no episode-level request endpoint, so an unowned episode cannot be played or requested from here |
| A widget tile opens Kodi's info dialog instead of Couchseerr | That skin hosts its widgets in a window Couchseerr does not recognise as Home. Browsing the add-on's own rows still opens the window |
| Kodi's own **Play** on a tile says *Not available to play* | That title is not in your Kodi library, or it is a whole show. Open the tile and play an episode from its season list |
| The detail window fails to open | Use the tile's context menu instead: **Request** or **Request with...** still works without the window |
| Interface is English on a non-English Kodi | That language is not translated yet. See [Languages](#languages) |

## Languages

English, French, German and Spanish. Kodi picks the file matching its interface language and falls
back to English for anything missing, so an unsupported language gets an English interface rather
than a broken one.

This is separate from the **Language code** setting, which controls the language of titles and plots
*seerr* returns.

> None of the translations has been proofread on a device yet. Corrections are a one-file change to
> `plugin.video.couchseerr/resources/language/resource.language.<code>/strings.po`, and very welcome.

## For skinners

<details>
<summary><b>Tile property contract</b></summary>

Every tile carries the same properties, in every view, because the add-on builds ListItems in
exactly one place. Read them with `ListItem.Property(seerr.status)` and siblings.

| Property | Holds | Empty when |
|---|---|---|
| `seerr.status` | `owned`, `partial`, `downloading`, `monitored`, `unreleased`, `pending` or `actionable` | Never, always set |
| `seerr.progress` | Download percent as a string, e.g. `"62"` | Not actively downloading |
| `seerr.eta` | seerr's time-remaining string | No download, or no estimate available |
| `seerr.requestable` | `"1"` | The state does not allow a request |
| `seerr.action.request` | A ready-to-run `plugin://` path that starts the request | Same as `seerr.requestable` |

`seerr.action.request` resolves the configured default at the moment it runs and carries no profile
of its own. A skin button can use the property's presence as its visibility condition.

**Why a badge is worth building:** every marker lives in the tile label, so in an art-only view
nothing draws them and the whole premise disappears. A badge reading `seerr.status` (plus
`seerr.progress`) is the only fix for those views. No add-on code can supply it; Kodi gives add-ons
no way to draw into a skin's art-only layout.

</details>

<details>
<summary><b>Naming rule</b>: <code>seerr.</code> versus <code>couchseerr.</code></summary>

`seerr.*` is a fact about the media, derived from your seerr instance: what state a title or season
is in, how far a download has got, whether it can be requested.

`couchseerr.*` is a decision this add-on made about how to draw it: which glyph stands for a state,
what the secondary line says, whether a row is inert.

The practical consequence: **prefer `seerr.*` when you have a choice.** A badge built on
`seerr.status` keeps working if the marker glyphs are retuned, because it is reading the state
rather than our rendering of it.

</details>

<details>
<summary><b>Detail window contract</b> (only if you ship your own copy of it)</summary>

Kodi looks for a window's XML in the current skin **before** the add-on's own copy, so a skin can
theme this window by shipping a file at the same relative path:

```
resources/skins/Default/1080i/couchseerr-detail.xml
```

Everything below is what the add-on fills in. Nothing else is guaranteed.

**Two list controls.** These ids are the only ones the add-on code names, so they must exist and
must be lists:

| Id | Holds |
|---|---|
| `50` | The section list: a show's seasons, or one season's episodes |
| `51` | The action list: Play, Request, Trailer, and so on |

**Window properties**, read with `$INFO[Window.Property(title)]` and siblings:

| Property | Holds | Empty when |
|---|---|---|
| `title` | The title's name | Never |
| `year_status` | Year and status line, already joined, e.g. `2021  ·  Monitored` | Neither is known |
| `plot` | The overview | seerr has none |
| `poster` | Poster URL | seerr has no poster |
| `fanart` | Backdrop URL | seerr has no backdrop |
| `section` | `seasons`, `episodes`, or empty when there is no list to show | A movie, or a show with no season data |
| `section_header` | Heading above the section list | A movie |

`year_status` arrives pre-joined on purpose. Kodi's `$INFO[label,prefix,postfix]` wraps a label's
own value and cannot conditionally join two properties, so composing it in a skin reproduces a bug
this add-on already fixed.

**Row properties**, read with `$INFO[ListItem.Property(couchseerr.marker)]`:

| Property | On | Holds |
|---|---|---|
| `seerr.status` | season rows | Same values as the tile contract above |
| `couchseerr.marker` | season rows | The state's glyph, from the same table the tiles use |
| `couchseerr.detail` | season rows | Localised episode count, e.g. `8 episodes` |
| `couchseerr.inert` | episode rows | `"1"` when the row leads nowhere, empty otherwise |
| `couchseerr.action` | action rows | `play`, `request`, `request_with`, `configure` or `trailer` |

`couchseerr.inert` marks an episode your library does not hold. Those rows are listed deliberately,
so a season reads as a whole, but they carry no action: seerr has no episode-level request endpoint,
so there is nothing they could ever do. Draw them dimmed.

`couchseerr.action` exists so a themed copy can put an icon on each button without hard-coding a
control id per action, which is precisely why Kodi's own video-info dialog cannot carry a Request
button.

The shipped layout draws neither `seerr.status` on a season row nor `couchseerr.action`. Both are
set for a skin override to use, and a test asserts they stay set.

</details>

## Not implemented

- **Episode requesting.** Not merely unbuilt: seerr's API has no episode-level endpoint, so this needs a change on seerr's side
- **Built-in skin support.** The Arctic Fuse recipe above is a config edit you make yourself

## License

GPL-3.0-or-later, see [LICENSE](LICENSE).

Copyright (C) 2026 yorah. This program is free software: you can redistribute it and/or modify it
under the terms of the GNU General Public License as published by the Free Software Foundation,
either version 3 of the License, or (at your option) any later version. It is distributed WITHOUT
ANY WARRANTY; see the license for details.
