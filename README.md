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

The target layout is in `TARGETS` in the Target Range section of `games.py`.
Change the distances, sizes or points to fit your game. (For now, also make
the same change in `web/games.js`; `tests/test_parity.py` fails until the two
match.)

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

### Golf Cornhole (3D)

Your shot becomes a cornhole bag. It flies your ball's real flight and lands
where the ball would have landed on a driving range, on a giant cornhole board
standing on the range.

- **Pick the hole distance** (30 to 250 yds) before the game. The whole set
  scales with it: the hole's radius is 3% of the distance (3 yds at 100 yds,
  7.5 yds at 250). The board, bags and slope keep official proportions around
  it: a 2 × 4 board, 6 in hole 9 in from the back, front 3 in and back 12 in
  high. At 100 yds the board covers about 61 to 109 yds downrange and 12 yds
  either side of the line. A 120-yard carry goes over it; a shot 15 yds
  wide misses.
- **After landing,** the bag slides as far (in board terms) as the ball would
  have rolled, up the slope. It can bump other bags, knock them into the hole
  or off the board, drop in the hole, or slide off an edge. A bag that lands
  on the grass first scores nothing (a foul bag).
- **Official (ACL) scoring.** Two sides (1v1, or teams: players 1 & 3 against
  2 & 4) throw 4 bags each per inning, alternating. In the hole is 3, on the
  board 1. Only the difference scores (cancellation). The first side to 21 (or
  11) at the end of an inning wins, and whoever scored last inning throws
  first. Teammates take turns, one inning each.
- **Life-size view.** The golfer's camera matches a 12 × 9 ft screen seen from
  10 ft, so the board looks as big as a real board at the same distance. The
  numbers are at the top of `cornhole.py` (`SCREEN_W_FT`, `SCREEN_H_FT`,
  `HITTER_FT`) if your screen differs. The camera looks down at the board at
  the same angle a 6 ft thrower at the foul line would (about 10 degrees), so
  you see the top of the board before each throw (`THROWER_EYE`).
- **Skip** counts as a thrown bag that scored nothing. **Undo** puts the board
  back exactly as it was.

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

## Unreal Engine files

The Unreal Engine version of the graphics lives in `unreal/GarageGames/`
(a proof of concept). **How to open it and play shots in Unreal:** see
[unreal/README.md](unreal/README.md). Before working on it:

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

## How it works

```
VTrack software ──Open Connect (TCP 921)──▶ server.py ──live events──▶ every game screen
                                              │                         (projector, tablet, ...)
                                              ├─ flight.py   speed/launch/spin → carry & landing spot
                                              ├─ session.py  the running game: turns, undo, skip, winner
                                              ├─ games.py    game rules and scoring
                                              └─ director.py broadcast decisions + the shot plan
```

The server is the brain. The game screens only draw what it sends, so
every screen shows the same game, and a future Unreal renderer can play
the same shot plans as the browser.

- `openconnect.py` acts as the receiving side of the GSPro Open Connect API v1.
  It answers each shot with `{"Code": 200}` like a simulator would.
- `flight.py` is a simple drag-and-lift model tuned to land within about
  5% of PGA Tour average carries. It adds a roll-out after landing (about
  20 yds for a driver, 2 for a wedge). It's good for party games but is
  not a substitute for a real simulator.
- `games.py` holds the game rules. Each game is one small class, so a new
  game means copying one and changing the rules.
- `director.py` decides which shots get broadcast coverage and plans each
  shot's camera cuts, slow motion, ball path and captions. It sends the plan
  as a **shot plan**: the ball and camera sampled 60 times a second (with
  the camera smoothing already done), the cuts, and timed captions. Units
  are yards: x downrange, y to the right, z up.
- `session.py` runs the current game: whose turn it is, the scores, undo,
  skip and the winner.
- `web/app.js` is the setup screen and scoreboard. `web/shotplan.js` plays
  back a shot plan, and `web/range-gl.js` draws the 3D range with Three.js
  (WebGL). The library is included in `web/vendor/three/` (MIT license), so
  no internet is needed.
- `web/range3d.js` is the Classic 2D drawing, also used automatically when
  3D graphics aren't available.
- `web/games.js` and `web/director.js` are the original JavaScript versions
  of the rules and the director. The page still uses `web/games.js` for the
  Classic 2D drawings. Both are kept for now so `tests/test_parity.py` can
  check the Python versions give exactly the same results.

### Control API

Any screen can run the game (for example a tablet as the control panel).
All requests are JSON `POST`s to `http://localhost:8080` unless marked GET:

| Request | Does |
| --- | --- |
| `GET /api/games` | The games, the target layout and the idle camera |
| `GET /api/state` | The current game: players, scoreboard, whose turn |
| `/api/game/start` | `{"game": "targetrange", "players": [{"name": "Dad", "junior": false, "color": "#ffd23f"}], "rounds": 10, "camera": "auto"}` |
| `/api/game/undo`, `/api/game/skip`, `/api/game/end` | Undo the last shot, skip a turn, end the game |
| `/api/settings` | `{"camera": "auto" \| "broadcast" \| "quick" \| "static"}` |
| `/api/test-shot` | Fake a shot that suits whoever is up |

`GET /events` streams `status` (launch monitor), `state` (after any change)
and `shot` (the scored shot, the new state and, for the Target Range games,
the shot plan) as Server-Sent Events.

## Testing

```
python -m unittest discover -s tests      # everything in Python: Open Connect, flight model,
                                          # game rules, director, shot plans, game session, API
node tests/test_games.js                  # the original JavaScript game rules (needs Node.js)
node tests/test_director.js               # the original JavaScript director
python tools/fake_launch_monitor.py -n 5  # send 5 fake shots over Open Connect
```

`tests/test_parity.py` runs the JavaScript and Python versions side by side
on hundreds of shots and checks they agree. It needs Node.js and is skipped
without it.

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
