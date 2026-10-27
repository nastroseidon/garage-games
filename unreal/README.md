# Garage Games in Unreal Engine (proof of concept)

The Unreal Engine 5.8 project in `GarageGames/` draws Target Range shots
with Unreal graphics. It is only a renderer. The Python server (`server.py`)
still connects to the VTrack, scores the games and plans every shot; Unreal
plays back the same **shot plans** the browser gets.

```
VTrack ──Open Connect──▶ server.py ──/events (live stream)──┬──▶ browser (scoreboard, control panel)
                                                            └──▶ Unreal editor (garage_bridge.py)
```

What's in the proof of concept: an empty range, one target (Blue, 120 yds),
a ball flying the real shot's path with a tracer, and the broadcast camera
cuts (tee, tower, target, orbit).

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
| `GarageGames/Content/Python/build_range.py` | Builds the Range level and its materials from code |
| `GarageGames/Content/Maps/`, `Content/Garage/` | The level and materials it built (stored in Git LFS) |
| `../tools/unreal_exec.py` | Runs a Python file or command in the open editor |

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
