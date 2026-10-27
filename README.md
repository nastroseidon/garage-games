# Garage Games

Party games for your golf simulator. Garage Games receives shots from your
launch monitor (VTrack or any other device that supports **Open Connect**,
the same connection GSPro and MuniGolfSim use), then turns them into games on
the projector screen:

### Target Range (3D range view, real balls and clubs)

A down-the-line view of a lit target range with seven target greens from 20
to 225 yards, a live ball tracer, roll-out after landing, and a mini-map.

| Target | Distance | Points |
| --- | --- | --- |
| Red | 20 yds | 1 |
| Yellow | 50 yds | 2 |
| Green | 85 yds | 3 |
| Blue | 120 yds | 4 |
| Purple | 155 yds | 5 |
| White | 190 yds | 6 |
| Gold | 225 yds | 8 |

- Land in the **inner ring** for **double points**, or within 1.5 yds of the
  flag for **triple**.
- A ball that lands in a target stays in it, like the real dish-shaped
  targets. A ball that lands short can **roll in**, which counts for the
  outer-ring points.
- **Juniors get +2** on every target they hit.

| Game | How it works |
| --- | --- |
| 🏟️ **Target Range** | Hit any target. Farther targets and inner rings score more. The final ball counts double. 5, 10 or 20 balls each. |
| 📣 **Called Shot** | Every ball gets a called target. Hit it for double points; any other target scores zero. Juniors are only called to the three nearest targets. |
| 🪜 **Ladder Climb** | Hit the targets in order, nearest first. The first player to reach the top wins. Adults climb 5 rungs (to Purple), juniors 3 (to Green). |

The target layout is in `TARGETS` at the top of the Target Range section in
`web/games.js`. Change the distances, sizes or points to fit your game.

### Broadcast camera

The Target Range games are drawn in real 3D: a night range with light
towers, glowing target rings, a ball tracer, bounces, and the ball dropping
into the cup with a burst of sparks.

Because the game knows how a shot ends (and what it does to the scores)
before the ball finishes flying, it can tell which shots matter and give
them TV-style coverage:

| Camera | When |
| --- | --- |
| **Broadcast** | Tee cam, then a tower cam following the ball against the sky, then a low camera beyond the target as the ball drops in (in slow motion for close calls), then a slow orbit. Letterbox bars, a LIVE score display, captions and a shot-data box run on top. |
| **Quick** | Behind the hitter, a chase camera, then a view of the landing. Used for routine shots so turns keep moving. |

In **Auto broadcast** mode (the default), these shots get broadcast coverage:

- **Pressure shots:** the scores are close with one or two balls left. The
  caption says so during the flight, e.g. "FINAL BALL · 6 behind Dad".
- **Lead changes:** a real overtake in the second half of the game.
- **The winning shot:** with confetti.
- **Close calls:** the flag zone, the inner ring, or a miss by less than
  1.5 yds ("SO CLOSE!").
- **Ladder Climb:** a shot that could win it, or when an opponent is one
  rung from winning.
- **About 1 in 12 routine shots, at random,** so a camera cut never gives
  the result away.

During the flight, captions only show what was known before the shot. The
result is revealed when the ball stops.

**Setup screen options:**
- **Camera:** Auto broadcast / Always broadcast / Quick / Fixed (one
  overview camera).
- **Graphics:** High (glow and shadows) / Low (for slower PCs) / Classic 2D
  (the original flat drawing). If the PC can't run 3D graphics, the game
  falls back to Classic 2D automatically.

### Classic games (top-down view)

| Game | How it works |
| --- | --- |
| 📍 **Closest to the Pin** | A new pin every round. Fewest total yards from the flag wins. |
| 🎯 **Target Darts** | Land in the rings: 50 / 30 / 20 / 10 / 5 points. Most points wins. |
| ⚡ **Hit the Number** | Match a target ball speed. It's all about feel, which makes it good for chips, foam balls and kids. |
| 💪 **Long Drive** | Longest carry wins, but only if it lands in the fairway. |
| ❌ **Tic-Tac-Toe** | Two teams. Land in a square to claim it. Three in a row wins. |

In the classic games, a player marked **Junior** gets targets at half the
distance (and half the speed in Hit the Number). In Long Drive their carry
counts double.

## What you need

- The Windows PC that runs your VTrack software.
- For the 3D graphics, a reasonably modern graphics card. If it stutters,
  pick **Graphics: Low** on the setup screen.
- Python 3.9 or newer, from <https://www.python.org/downloads/>. When you
  install it, tick **"Add python.exe to PATH"**. Nothing else needs to be
  installed.

## Start it

1. **Close GSPro / MuniGolfSim / any other simulator.** Only one program can
   receive Open Connect shots at a time.
2. Double-click **`start.bat`**. You can also open a terminal in this folder
   and run `python server.py`.
   - If Windows Firewall asks, click **Allow**.
3. Your browser opens the game screen at <http://localhost:8080>. Drag it to
   the projector and press **F11** for full screen.
4. In the VTrack software, connect to Open Connect / GSPro the same way you
   do for MuniGolfSim. The address is **127.0.0.1**, port **921**. The dot at
   the top of the game screen turns green when the launch monitor is
   connected and ready.
5. Add players, pick a game, and hit away.

**No launch monitor handy?** Click **🎯 Test shot** (or press **T**) to fake a
shot.

### Keyboard shortcuts

| Key | Action |
| --- | --- |
| T | Fake a test shot |
| U | Undo the last shot (for mis-reads or "that one didn't count!") |
| S | Skip the current player's turn |
| Esc | Back to the menu |

### Options

```
python server.py --help
  --oc-port 921       Open Connect port (change only if your LM software uses another)
  --oc-host 0.0.0.0   Accept shots from another PC on your network
  --web-port 8080     Port for the game screen
  --no-log            Don't save shots to the logs folder
  --no-browser        Don't open the game screen automatically
```

## Trying other balls

The program uses whatever the launch monitor sends, so you can experiment
with anything the VTrack will read: foam balls, plastic practice balls,
tennis balls, small kids' balls. Every message the VTrack sends is saved to
`logs/shots-YYYYMMDD.jsonl`. You can check whether a shot with a new kind of
ball was read at all, and what numbers came through.

Keep in mind:

- **Hit the Number** uses only ball speed, so it works with any ball the
  VTrack reads.
- The other games use a golf-ball flight model to work out where the ball
  "lands." With a different ball the distances are for fun, not physics.

## How it works

```
VTrack software ──Open Connect (TCP 921)──▶ server.py ──live events──▶ browser game screen
                                              │
                                              └─ flight.py turns speed/launch/spin into carry & landing spot
```

- `openconnect.py` acts as the receiving side of the GSPro Open Connect API v1.
  It answers each shot with `{"Code": 200}` like a simulator would.
- `flight.py` is a simple drag-and-lift model tuned to land within about
  5% of PGA Tour average carries. It adds a roll-out after landing (about
  20 yds for a driver, 2 for a wedge). It's good for party games but is
  not a substitute for a real simulator.
- `web/range-gl.js` draws the 3D range with Three.js (WebGL). The library
  is included in `web/vendor/three/` (MIT license), so no internet is needed.
- `web/director.js` decides which shots get broadcast coverage and plans
  each shot's camera cuts, slow motion and ball path.
- `web/range3d.js` is the Classic 2D drawing, also used automatically when
  3D graphics aren't available.
- `web/games.js` holds the game rules. Each game is one small object, so a
  new game means copying one and changing the rules.

## Testing

```
python -m unittest discover -s tests      # Open Connect parsing + flight model
node tests/test_games.js                  # game scoring (needs Node.js)
node tests/test_director.js               # broadcast triggers + camera plans
python tools/fake_launch_monitor.py -n 5  # send 5 fake shots over Open Connect
```

## Unreal Engine files

The Unreal Engine version of the graphics will live in `unreal/GarageGames/`.
Before working on it:

- **Install Git LFS** (<https://git-lfs.com>) and run `git lfs install` once
  on each PC. Unreal assets (`.uasset`, `.umap`, ...) and the source art,
  audio and video inside `unreal/` are stored in Git LFS (see
  `.gitattributes`). Without it, a clone only gets small pointer files instead
  of the real assets. GitHub's free plan has a limited amount of LFS storage
  and download traffic, so keep large source files out when you can.
- **Never commit** these (`.gitignore` blocks them):
  - folders Unreal rebuilds: `Binaries/`, `Intermediate/`, `Saved/`,
    `DerivedDataCache/`, packaged builds, and IDE files
  - Unreal Engine itself, whether from the Epic Games Launcher or built from
    source
  - paid or licensed content: Fab, Marketplace and Quixel assets, and Epic's
    Starter Content. Fab and Quixel Bridge import into `Content/Fab/` and
    `Content/Megascans/` by default; put any other third-party assets in
    `Content/ThirdParty/`. Their licenses don't allow sharing them in a public
    repo, so anyone else who builds the project has to get them themselves.
- `tests/test_repo_rules.py` checks these rules, and fails if a big binary
  file or an Unreal asset gets committed outside Git LFS.

## Safety

Use foam or practice balls in the garage, keep kids well back from the
hitting area, and make sure the ceiling-mounted unit is protected from
high shots.

## License

MIT, see [LICENSE](LICENSE). Three.js, included in `web/vendor/three/`, is
also MIT-licensed. Its own license file is in that folder and must stay with
it.

Garage Games is an independent hobby project. It isn't affiliated with or
endorsed by Laon SwingCraft (makers of VTrack) or GSPro. Those names are used
only to describe what the software works with.
