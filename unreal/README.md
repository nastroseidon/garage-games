# Garage Games in Unreal Engine (proof of concept)

The Unreal Engine 5.8 project in `GarageGames/` draws Target Range shots
with Unreal graphics. It is only a renderer. The Python server (`server.py`)
still connects to the VTrack, scores the games and plans every shot; Unreal
plays back the same **shot plans** the browser gets.

```
VTrack ──Open Connect──▶ server.py ──/events (live stream)──┬──▶ browser (scoreboard, control panel)
                                                            └──▶ Unreal editor (garage_bridge.py)
```

What's in it: the full range with all seven targets (from `games.py`), mown
stripes, yardage boards, light towers, a tree line and hills; **day and
night lighting** you can switch between; and a ball flying the real shot's
path with a tracer and the broadcast camera cuts (tee, tower, target,
orbit). Everything is built from code with simple shapes, and free **Fab /
Quixel** trees, rocks and grass are used instead when they are on the PC
(see below).

It runs inside the **Unreal editor** (no C++ and no Visual Studio needed).
A standalone Unreal app that runs without the editor would need a small C++
part later; it can read the same live stream.

## Play shots in Unreal

1. **Start the server** as usual: double-click `start.bat`. Unreal can be
   opened before or after the server; it keeps retrying until it connects.
2. **Open the project:** double-click
   `unreal/GarageGames/GarageGames.uproject`.
   - If Windows asks which program to use, or Unreal asks *"Select Unreal
     Engine Version"*, pick **5.8**.
   - The first time, Unreal spends a few minutes compiling shaders. Later
     opens are much faster.
   - The **Range** level opens by itself.
3. **Check it's connected:** *Window → Output Log*. Look for:
   `[Garage Games] server connected (127.0.0.1:8080)`.
4. **Start a game** on the game screen in the browser (Target Range, Called
   Shot or Ladder Climb) and hit a shot (or press **T** for a test shot).
   The Unreal viewport looks through the shot camera and follows the ball.
5. **Bigger picture:** click in the viewport and press **F11** (fills the
   editor window) and **G** (hides editor icons). Press them again to go
   back.

The browser stays the scoreboard and control panel (players, undo, skip).

## Day or night

The range opens at night. To switch, in the Output Log switch the command
box from **Cmd** to **Python** and type:

```
import garage_env; garage_env.set_time_of_day("day")
```

(or `"night"`). The choice is saved with the level. The settings for each
(sun, tower lights, target glow, fog colour, exposure) are in `LIGHTING` at
the bottom of `Content/Python/range_layout.py`.

## Add free Fab / Quixel trees, rocks and grass (optional)

The simple cone trees and round rocks are placeholders. Real ones from Fab
look much better. Fab assets **stay on this PC only**: their licence doesn't
allow them in the public repo, and `.gitignore` keeps them out. Anyone else
who clones the repo repeats these steps (or keeps the simple shapes).

1. In the Unreal editor, open Fab: *Window → Fab*. (Or in the Content
   Browser: *+ Add → Add Fab Content*.)
2. Sign in with your Epic Games account if asked.
3. Search for what you want and filter to **Free**. Good searches:
   *"pine tree"*, *"conifer"*, *"bush"*, *"rock"* or *"boulder"*, and a ground
   surface such as *"grass"* or *"lawn"*. Check each item says it can be
   used in Unreal Engine. Some Megascans are paid now; anything already in
   your Fab library stays usable.
   Megascans' free tier is *"UEFN – Reference only"*, which is for Fortnite
   projects, not this one, so a Megascans item needs a paid licence.
4. Click **Add to Project** (or *Download*, then *Add to Project*). Pick a
   **Medium** quality to keep it fast. Fab imports into `Content/Fab/` or a
   folder named after the pack (e.g. `Content/PSG_LTX/`). Either is fine:
   only our own folders (`Garage`, `Maps`, `Python`) are committed, and the
   build looks in every other folder.
5. Rebuild the range: *Tools → Execute Python Script...* → choose
   `Content/Python/build_range.py`. The Output Log shows what it found, e.g.
   `dressing: 3 tree meshes, 2 rock meshes, grass material: MI_Grass_Lawn`.
   Trees replace the cones and rocks replace the round stones. The grass
   material goes on the mown stripes, the tee and the rough, tiled every
   2 yards and tinted per area (the tiled copies go in `Content/GarageLocal/`,
   also never committed).

Asset names decide where they go: names containing *tree, pine, oak, fir,
spruce, birch, maple, conifer, bush, shrub, hedge* or a tree genus (*abies,
picea, pinus, larix, quercus, betula*) become trees; *rock, boulder, stone,
cliff* become rocks; a material with *grass, lawn, turf, meadow* becomes the
grass.

Before committing `Content/Maps/Range.umap`, build it without Fab content so
a fresh clone opens cleanly. Run this in the editor's Python console (or
`tools/unreal_exec.py -c`) and then build:

```python
import os; os.environ["GG_NO_FAB"] = "1"
```

Set it back to `"0"` and build again to get the Fab look back.

What this PC uses (for credit; none of it is in the repo):

- *PSG – Realistic Abies lasiocarpa* by Studio LTX (Fab Standard License).
- *025_Grass* by NoblesseOblige-No.1, licensed
  [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).

## Golf Cornhole's campsite models (optional)

The campsite is built from simple shapes. Where this PC has these models
(from Fab and elsewhere, imported anywhere under `Content/`; never committed),
they stand in for the shapes the next time a Golf Cornhole game starts:

| Camp item | Model (asset name) |
|---|---|
| Trees (all of them) | `SM_PSG_Abies_lasiocarpa001` to `006` |
| Rocks | `stone`, `river_rock` |
| Campfire stone ring | `forest_stones_campfire` |
| Tents | `camping_tent` |
| Picnic table | `picnic_table_low_poly` |
| Cooler | `cooler_box__BLEND_` |
| Camp chairs | `chair_low_poly` |
| Log seats | `SM_FirewoodBlackCherryPiece01` |
| Woodpile | `SM_FirewoodStackBlackCherry02` |
| One stump, with a lit lantern on it | `woodsman_collection_railroad_lantern` |

`MODELS` in `Content/Python/garage_camp.py` lists them, with how much each
one is turned (some import upside down) and how big it is. To use another
model, add its asset name there. Anything missing stays a shape, and the
bushes, string lights, hooks and flames are always shapes. The firs cast no
shadows and fade out past 40 real metres, which keeps a shot near 80 fps
on an RTX 3080 (about 45 fps otherwise).

## Check it runs smoothly (with the VTrack software running)

After every shot the Output Log prints a line like:

```
[Garage Games] shot finished: {"frames": 910, "avg_fps": 119.4, "worst_ms": 11.1, "p95_ms": 8.9, "slow_frames": 0}
```

- `avg_fps`: average frames per second during the shot. 60 or more is
  smooth.
- `worst_ms`: the slowest single frame. Under about 33 ms won't be noticed.
- `slow_frames`: frames slower than 33 ms (a visible hitch). Should be 0 or
  close to it.

To test with the VTrack: open the VTrack software and connect it to Open
Connect (127.0.0.1, port 921) as usual, hit 3 to 5 real shots, and compare
these lines with the ones you get without it.

## Make sure the Python plugin is on

The project file already turns these on. To check, or if you ever create a
new project:

1. *Edit → Plugins*, search **Python**: **Python Editor Script Plugin** must
   be ticked. (*Editor Scripting Utilities* too.) Restart the editor if you
   change it.
2. *Edit → Project Settings → Plugins → Python*: **Enable Remote
   Execution?** must be ticked. This lets `tools/unreal_exec.py` run Python in
   the open editor (from this PC only).

## Files

| File | What it does |
| --- | --- |
| `GarageGames/GarageGames.uproject` | The project: Unreal 5.8, Python plugins on |
| `GarageGames/Config/` | Engine settings: startup map, Lumen lighting, Python remote execution, no slowdown when the editor isn't the focused window |
| `GarageGames/Content/Python/init_unreal.py` | Runs when the project opens; starts the shot bridge |
| `GarageGames/Content/Python/garage_bridge.py` | The Unreal part: moves the ball and camera every frame |
| `GarageGames/Content/Python/garage_stream.py` | Plain Python (tested in `tests/test_unreal_stream.py`): the live-stream client, shot plan playback, Unreal units |
| `GarageGames/Content/Python/range_layout.py` | Plain Python (tested in `tests/test_range_layout.py`): what the range is made of, and the day/night settings |
| `GarageGames/Content/Python/build_range.py` | Builds the Range level and its materials from the layout |
| `GarageGames/Content/Python/garage_env.py` | Switches day/night; finds Fab / Quixel assets to use |
| `GarageGames/Content/Maps/`, `Content/Garage/` | The level and materials it built (stored in Git LFS) |
| `../tools/unreal_exec.py` | Runs a Python file or command in the open editor |
| `../tools/unreal_snapshot.py` | Saves a screenshot from a chosen camera position (run it with `unreal_exec.py`) |

### Rebuild or change the range

`build_range.py` makes everything (actors named `GG_...`) and can be run
again at any time:

- In Unreal: *Tools → Execute Python Script...* → choose
  `Content/Python/build_range.py`, or
- From a terminal, with the editor open:
  `python tools/unreal_exec.py unreal/GarageGames/Content/Python/build_range.py`

### Handy Python console commands

In the Output Log, switch the command box from **Cmd** to **Python**:

```
import garage_bridge
garage_bridge.status()   # connected? shots played? last shot's smoothness
garage_bridge.stop()     # stop following the server
garage_bridge.start()
```
