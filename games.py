"""Game rules and scoring, shared by every screen (browser and Unreal).

A Python port of the rules that used to live in web/games.js. Each game
turns a shot into points. Distances are in yards; "offline" is positive to
the right of the target line.

Adding a game: copy one of these classes, give it a new id, and add it to
GAMES at the bottom.

Text and numbers are formatted the way the JavaScript version did it, so
the browser shows exactly the same captions (see js_round / to_fixed).
"""

import math
import random
from decimal import ROUND_HALF_UP, Decimal

import cornhole
import flight

JUNIOR = 0.5  # juniors' targets are this fraction of the adult distance


# ---------------- JavaScript-compatible number formatting ----------------

def js_round(x):
    """Math.round: halves round up (toward +infinity)."""
    return int(math.floor(x + 0.5))


def to_fixed(x, digits=1):
    """Number.prototype.toFixed: halves round away from zero."""
    if x == 0:
        x = 0.0  # JS prints -0 as "0.0" (but -0.04 as "-0.0")
    q = Decimal(1).scaleb(-digits)
    return str(Decimal(x).quantize(q, rounding=ROUND_HALF_UP))


def num(x):
    """String(x) for a JS number: 10.0 -> "10", 2.5 -> "2.5"."""
    if isinstance(x, float) and x.is_integer():
        return str(int(x))
    return str(x)


def rand_step(lo, hi, step, rng=random):
    n = (hi - lo) // step + 1
    return lo + step * rng.randrange(n)


def dist(shot, d, l):
    f = shot["flight"]
    return math.hypot(f["carry_yd"] - d, f["offline_yd"] - l)


def fmt_yards(yd):
    if yd < 10:
        return "%d ft" % js_round(yd * 3)
    return to_fixed(yd) + " yds"


def kind_for(distance):
    if distance < 45:
        return "chip"
    if distance < 100:
        return "wedge"
    if distance < 170:
        return "iron"
    return "driver"


def scaled(base, player, keys):
    t = dict(base)
    if player.get("junior"):
        for k in keys:
            t[k] = js_round(base[k] * JUNIOR)
    return t


class Game:
    """Defaults shared by every game. ctx is the running GameSession."""

    id = ""
    name = ""
    emoji = ""
    blurb = ""
    view = "range"
    lower_is_better = False
    combine = "sum"
    miss_points = 0
    min_players = 1
    uses_rounds = True
    round_choices = None
    default_rounds = None
    pressure_gap = 10
    stateful = False  # True when score() changes ctx, so undo replays the shots

    def __init__(self, rng=None):
        self.rng = rng or random

    def format_score(self, v):
        return num(v)

    def reset(self, ctx):
        pass

    def player_for_turn(self, ctx, turn):
        return turn % len(ctx.players)

    def make_target(self, round_):
        return {}

    def player_target(self, base, player):
        return base

    def task(self, t, player, ctx, idx):
        return ""

    def test_kind(self, t, ctx, idx):
        return None

    def highlight(self, t, ctx, idx):
        return -1

    def is_over(self, ctx):
        return ctx.turn >= ctx.rounds * len(ctx.players)

    def score(self, shot, t, player, ctx, idx):
        raise NotImplementedError

    # Tic-Tac-Toe replaces the per-player scoreboard with a per-team one.
    scoreboard = None
    winner_text = None
    # Extra setup choices: [{key, label, choices, default, unit}] (Golf Cornhole's board distance).
    options = None

    def check_options(self, given):
        """The chosen options, each one of its choices (or the default)."""
        out = {}
        for o in self.options or []:
            v = (given or {}).get(o["key"], o["default"])
            try:
                v = type(o["default"])(v)
            except (TypeError, ValueError):
                raise ValueError("bad %s: %r" % (o["label"].lower(), v))
            if v not in o["choices"]:
                raise ValueError("%s must be one of %s" % (o["label"], ", ".join(map(str, o["choices"]))))
            out[o["key"]] = v
        return out

    def on_skip(self, ctx):
        """A skipped turn (stateful games count it too)."""

    def round_info(self, ctx):
        return None

    def player_totals(self, ctx):
        """Per-player scores when they aren't the sum of shot points (None: they are)."""
        return None

    def extra(self, ctx):
        """Game-specific state for the screens (None: nothing)."""
        return None

    def headline(self, ctx):
        """A head-to-head game score shown above the scoreboard (None: no headline)."""
        return None

    def test_shot(self, t, ctx, idx):
        """Launch numbers for a test shot ({} lets the server pick by test_kind)."""
        return {}

    def info(self):
        """What a menu needs to list the game."""
        return {"id": self.id, "name": self.name, "emoji": self.emoji,
                "blurb": self.blurb, "view": self.view,
                "min_players": self.min_players, "uses_rounds": self.uses_rounds,
                "round_choices": self.round_choices,
                "default_rounds": self.default_rounds,
                "options": self.options}


# ---------------- Closest to the Pin ----------------

class Closest(Game):
    id = "closest"
    name = "Closest to the Pin"
    emoji = "📍"
    blurb = "A new pin every round. Fewest total yards from the flag wins."
    lower_is_better = True
    cap = 50
    miss_points = 50

    def format_score(self, v):
        return to_fixed(v) + " yds"

    def make_target(self, round_):
        return {"pin": rand_step(50, 150, 5, self.rng)}

    def player_target(self, base, p):
        return scaled(base, p, ["pin"])

    def task(self, t, p, ctx, idx):
        return "Pin: %s yds" % num(t["pin"])

    def test_kind(self, t, ctx, idx):
        return kind_for(t["pin"])

    def score(self, shot, t, p, ctx, idx):
        miss = dist(shot, t["pin"], 0)
        return {
            "points": min(self.cap, miss),
            "what": fmt_yards(miss),
            "detail": "Tap-in range!" if miss <= 3 else "Great shot" if miss <= 8 else "from the pin",
            "great": miss <= 5,
            "mark": [t["pin"], 0],
        }


# ---------------- Target Darts ----------------

RINGS = [[3, 50], [7, 30], [12, 20], [18, 10], [25, 5]]


class Darts(Game):
    id = "darts"
    name = "Target Darts"
    emoji = "🎯"
    blurb = "Land it in the rings. Bullseye is 50. Most points wins."

    def format_score(self, v):
        return num(v) + " pts"

    def make_target(self, round_):
        return {"d": rand_step(60, 140, 10, self.rng)}

    def player_target(self, base, p):
        return scaled(base, p, ["d"])

    def task(self, t, p, ctx, idx):
        return "Bullseye at %s yds" % num(t["d"])

    def test_kind(self, t, ctx, idx):
        return kind_for(t["d"])

    def score(self, shot, t, p, ctx, idx):
        miss = dist(shot, t["d"], 0)
        pts = 0
        for radius, value in RINGS:
            if miss <= radius:
                pts = value
                break
        return {
            "points": pts,
            "what": "BULLSEYE!" if pts == 50 else "%d points" % pts if pts else "Missed",
            "detail": fmt_yards(miss) + " from center",
            "great": pts >= 30,
            "mark": [t["d"], 0],
        }


# ---------------- Hit the Number (ball speed) ----------------

class Speed(Game):
    id = "speed"
    name = "Hit the Number"
    emoji = "⚡"
    blurb = "Match the target ball speed. Pure feel - great for chips and kids."
    view = "speed"
    lower_is_better = True
    cap = 30
    miss_points = 30

    def format_score(self, v):
        return to_fixed(v) + " mph off"

    def make_target(self, round_):
        return {"mph": rand_step(30, 100, 5, self.rng)}

    def player_target(self, base, p):
        if p.get("junior"):
            return {"mph": max(15, js_round(base["mph"] * JUNIOR / 5) * 5)}
        return base

    def task(self, t, p, ctx, idx):
        return "Hit it %s mph" % num(t["mph"])

    def test_kind(self, t, ctx, idx):
        return "chip" if t["mph"] < 50 else "wedge" if t["mph"] < 90 else "iron"

    def score(self, shot, t, p, ctx, idx):
        speed = shot["speed_mph"]
        off = abs(speed - t["mph"])
        return {
            "points": min(self.cap, off),
            "what": "BULLSEYE!" if off <= 1 else to_fixed(speed) + " mph",
            "detail": "Within 1 mph!" if off <= 1 else to_fixed(off) + " mph " +
                      ("too hot" if speed > t["mph"] else "too soft"),
            "great": off <= 3,
        }


# ---------------- Long Drive (stay in the fairway) ----------------

FAIRWAY = 15


class LongDrive(Game):
    id = "longdrive"
    name = "Long Drive"
    emoji = "💪"
    blurb = "Longest carry wins - but only if it lands in the fairway. Juniors count double."
    combine = "max"

    def format_score(self, v):
        return to_fixed(v) + " yds"

    def player_target(self, base, p):
        return {"junior": bool(p.get("junior"))}

    def task(self, t, p, ctx, idx):
        return "Stay within %d yds of center%s" % (FAIRWAY, " (x2 bonus)" if t["junior"] else "")

    def test_kind(self, t, ctx, idx):
        return "iron" if t["junior"] else "driver"

    def score(self, shot, t, p, ctx, idx):
        f = shot["flight"]
        carry = f["carry_yd"]
        in_fairway = abs(f["offline_yd"]) <= FAIRWAY
        counted = carry * (2 if t["junior"] else 1) if in_fairway else 0
        if in_fairway:
            detail = "Junior x2 = %s yds" % to_fixed(counted) if t["junior"] else "Carry"
        else:
            detail = "%s yds, %s yds %s" % (to_fixed(carry), to_fixed(abs(f["offline_yd"])),
                                            "right" if f["offline_yd"] > 0 else "left")
        return {
            "points": js_round(counted * 10) / 10,
            "what": to_fixed(carry) + " yds" if in_fairway else "In the rough!",
            "detail": detail,
            "great": in_fairway and carry >= 200,
        }


# ---------------- Tic-Tac-Toe ----------------

COLS = [-24, -8, 8, 24]      # lateral edges, yards
ROWS = [40, 70, 100, 130]    # downrange edges, yards
LINES = [[0, 1, 2], [3, 4, 5], [6, 7, 8], [0, 3, 6], [1, 4, 7], [2, 5, 8], [0, 4, 8], [2, 4, 6]]
TEAMS = [{"name": "Team X", "mark": "X", "color": "#ff8c42"},
         {"name": "Team O", "mark": "O", "color": "#4ea8ff"}]


def team_of(ctx, player_idx):
    return player_idx % 2


def cell_for(shot, t):
    d, l = shot["flight"]["carry_yd"], shot["flight"]["offline_yd"]
    row = col = -1
    for r in range(3):
        if t["rows"][r] <= d < t["rows"][r + 1]:
            row = r
    for c in range(3):
        if t["cols"][c] <= l < t["cols"][c + 1]:
            col = c
    if row < 0 or col < 0:
        return -1
    return (2 - row) * 3 + col  # top row of the board = farthest


class TicTacToe(Game):
    id = "tictactoe"
    name = "Tic-Tac-Toe"
    emoji = "❌"
    blurb = "Two teams. Land in a square to claim it. Three in a row wins!"
    min_players = 2
    uses_rounds = False
    stateful = True

    def reset(self, ctx):
        ctx.board = [None] * 9
        ctx.ttt_winner = None
        ctx.boards = 1

    def player_for_turn(self, ctx, turn):
        # Alternate teams every shot, rotating through each team's players.
        team = turn % 2
        members = [i for i in range(len(ctx.players)) if team_of(ctx, i) == team]
        return members[(turn // 2) % len(members)]

    def make_target(self, round_):
        return {"cols": list(COLS), "rows": list(ROWS)}

    def player_target(self, base, p):
        if not p.get("junior"):
            return base
        return {"cols": [js_round(v * JUNIOR) for v in base["cols"]],
                "rows": [js_round(v * JUNIOR) for v in base["rows"]]}

    def task(self, t, p, ctx, idx):
        return TEAMS[team_of(ctx, idx)]["name"] + " - claim a square!"

    def test_kind(self, t, ctx, idx):
        return kind_for(t["rows"][1])

    def score(self, shot, t, p, ctx, idx):
        team = team_of(ctx, idx)
        cell = cell_for(shot, t)
        if cell < 0:
            return {"points": 0, "what": "Off the board", "detail": "No square claimed", "great": False}
        if ctx.board[cell] is not None:
            return {"points": 0, "what": "Already taken!",
                    "detail": "That square belongs to " + TEAMS[ctx.board[cell]]["name"], "great": False}
        ctx.board[cell] = team
        res = {"points": 1, "what": "Square claimed!", "detail": TEAMS[team]["name"] + " takes it", "great": True}
        for line in LINES:
            if all(ctx.board[c] == team for c in line):
                ctx.ttt_winner = team
                res["what"] = "THREE IN A ROW!"
                res["detail"] = TEAMS[team]["name"] + " wins!"
        if ctx.ttt_winner is None and all(c is not None for c in ctx.board):
            ctx.board = [None] * 9
            ctx.boards += 1
            res["detail"] = "Cat's game - new board!"
        return res

    def is_over(self, ctx):
        return ctx.ttt_winner is not None

    def scoreboard(self, ctx, current):
        rows = []
        for ti, team in enumerate(TEAMS):
            owned = sum(1 for c in ctx.board if c == ti)
            names = ", ".join(p["name"] for i, p in enumerate(ctx.players) if team_of(ctx, i) == ti)
            rows.append({"name": "%s (%s)" % (team["name"], team["mark"]), "sub": names,
                         "color": team["color"],
                         "value": "%d %s" % (owned, "square" if owned == 1 else "squares"),
                         "current": current >= 0 and team_of(ctx, current) == ti})
        return rows

    def winner_text(self, ctx):
        return TEAMS[ctx.ttt_winner]["name"] + " wins!"


# ================= Target Range (3D view, real balls) =================
# Seven target greens. A ball that lands in a target stays there (they are
# dish-shaped), and a ball that lands short can roll into one.

TARGETS = [
    {"name": "Red", "color": "#ff4d4d", "d": 20, "l": -4, "r": 5, "pts": 1},
    {"name": "Yellow", "color": "#ffd23f", "d": 50, "l": 7, "r": 7, "pts": 2},
    {"name": "Green", "color": "#3ddc84", "d": 85, "l": -9, "r": 9, "pts": 3},
    {"name": "Blue", "color": "#4ea8ff", "d": 120, "l": 8, "r": 11, "pts": 4},
    {"name": "Purple", "color": "#c77dff", "d": 155, "l": -12, "r": 13, "pts": 5},
    {"name": "White", "color": "#f2f2f2", "d": 190, "l": 12, "r": 15, "pts": 6},
    {"name": "Gold", "color": "#ffa630", "d": 225, "l": -4, "r": 17, "pts": 8},
]
INNER = 0.4          # inner ring = 40% of the radius: double points
CENTER = 1.5         # within 1.5 yds of the flag: triple points
ZONE_MULT = {"center": 3, "inner": 2, "outer": 1}
ZONE_TEXT = {"center": "Flag zone x3", "inner": "Inner ring x2", "outer": ""}
JUNIOR_BONUS = 2     # juniors get +2 on every target hit
LADDER = {"adult": 5, "junior": 3}


def target_at(p):
    for i, T in enumerate(TARGETS):
        dd = math.hypot(p[0] - T["d"], p[1] - T["l"])
        if dd <= T["r"]:
            return i, dd
    return None


def rest_of(flight):
    return flight.get("rest") or [flight["carry_yd"], flight["offline_yd"]]


def range_hit(shot):
    """Where the ball ends up: {target (index or -1), zone, stop [d, l], rolledIn}."""
    f = shot["flight"]
    land = [f["carry_yd"], f["offline_yd"]]
    rest = rest_of(f)
    hit = target_at(land)
    if hit:
        i, dd = hit
        zone = "center" if dd <= CENTER else "inner" if dd <= TARGETS[i]["r"] * INNER else "outer"
        return {"target": i, "zone": zone, "stop": land, "rolledIn": False}
    length = math.hypot(rest[0] - land[0], rest[1] - land[1])
    steps = int(math.ceil(length / 0.5))
    for s in range(1, steps + 1):
        p = [land[0] + (rest[0] - land[0]) * s / steps, land[1] + (rest[1] - land[1]) * s / steps]
        hit = target_at(p)
        if hit:
            return {"target": hit[0], "zone": "outer", "stop": p, "rolledIn": True}
    return {"target": -1, "zone": None, "stop": rest, "rolledIn": False}


def near_miss(shot):
    """How far (yds) a miss finished from the nearest target edge, or None on a hit."""
    f = shot["flight"]
    if range_hit(shot)["target"] >= 0:
        return None
    pts = [[f["carry_yd"], f["offline_yd"]], rest_of(f)]
    best = min(math.hypot(p[0] - T["d"], p[1] - T["l"]) - T["r"] for T in TARGETS for p in pts)
    return max(0, best)


def range_timing(shot, stop=None):
    """Animation timing for the Classic 2D range view."""
    f = shot["flight"]
    flight_ms = min(5500, max(1200, f["flight_time_s"] * 800))
    land = [f["carry_yd"], f["offline_yd"]]
    end = stop or rest_of(f)
    roll = math.hypot(end[0] - land[0], end[1] - land[1])
    roll_ms = 400 + min(1400, roll * 50) if roll > 0.3 else 0
    return {"flightMs": flight_ms, "rollMs": roll_ms, "totalMs": flight_ms + roll_ms}


def fnv_hash(text):
    """32-bit FNV-1a over UTF-16 code units, matching the JS hash()."""
    h = 2166136261
    data = text.encode("utf-16-le")
    for i in range(0, len(data), 2):
        h ^= data[i] | (data[i + 1] << 8)
        h = (h * 16777619) & 0xFFFFFFFF
    return h


def hit_text(hit, pts):
    T = TARGETS[hit["target"]]
    bits = []
    if ZONE_TEXT[hit["zone"]]:
        bits.append(ZONE_TEXT[hit["zone"]])
    if hit["rolledIn"]:
        bits.append("rolled in!")
    return {"what": "%s  +%s" % (T["name"].upper(), num(pts)),
            "detail": " · ".join(bits) or T["name"] + " target", "color": T["color"]}


def yds(v):
    n = js_round(v)
    return "%d %s" % (n, "yd" if n == 1 else "yds")


def miss_text(shot):
    f = shot["flight"]
    rest = rest_of(f)
    return {"what": "No target",
            "detail": "%s yds, %s %s" % (to_fixed(f["total_yd"], 0), yds(abs(rest[1])),
                                         "right" if rest[1] >= 0 else "left")}


def ladder_step(ctx, idx):
    return sum(1 for r in ctx.history if r["idx"] == idx and r["result"]["points"] > 0)


def ladder_length(p):
    return LADDER["junior"] if p.get("junior") else LADDER["adult"]


class RangeGame(Game):
    view = "range3d"
    round_choices = [5, 10, 20]
    default_rounds = 10

    def format_score(self, v):
        return num(v) + " pts"

    def test_kind(self, t, ctx, idx):
        return self.rng.choice(["chip", "wedge", "iron", "iron", "driver"])


class TargetRange(RangeGame):
    id = "targetrange"
    name = "Target Range"
    pressure_gap = 10  # "one good shot" - scores this close late in the game are pressure shots
    emoji = "🏟️"
    blurb = "Hit any target. Farther targets and inner rings score more. Final ball counts double!"

    def make_target(self, round_):
        return {"round": round_}

    def player_target(self, base, p):
        return {"round": base["round"], "junior": bool(p.get("junior"))}

    def task(self, t, p, ctx, idx):
        return "FINAL BALL - double points!" if t["round"] == ctx.rounds - 1 else "Hit any target"

    def score(self, shot, t, p, ctx, idx):
        hit = range_hit(shot)
        if hit["target"] < 0:
            return dict({"points": 0, "great": False, "stop": hit["stop"]}, **miss_text(shot))
        last = t["round"] == ctx.rounds - 1
        pts = ((TARGETS[hit["target"]]["pts"] + (JUNIOR_BONUS if t["junior"] else 0))
               * ZONE_MULT[hit["zone"]] * (2 if last else 1))
        txt = hit_text(hit, pts)
        if last:
            txt["detail"] = (txt["detail"] + " · " if txt["detail"] else "") + "final ball x2"
        return dict({"points": pts, "great": True, "stop": hit["stop"], "hitTarget": hit["target"]}, **txt)


class CalledShot(RangeGame):
    id = "calledshot"
    name = "Called Shot"
    pressure_gap = 14
    emoji = "📣"
    blurb = "Every ball gets a called target. Hit it for double points - any other target scores zero."
    round_choices = [5, 10]
    default_rounds = 5

    def make_target(self, round_):
        return {"seed": self.rng.randrange(10 ** 9)}

    def player_target(self, base, p):
        choices = 3 if p.get("junior") else len(TARGETS)
        return {"called": fnv_hash("%d:%s" % (base["seed"], p["name"])) % choices,
                "junior": bool(p.get("junior"))}

    def task(self, t, p, ctx, idx):
        T = TARGETS[t["called"]]
        return "Called: %s (%d yds)" % (T["name"].upper(), T["d"])

    def highlight(self, t, ctx, idx):
        return t["called"]

    def test_kind(self, t, ctx, idx):
        return kind_for(TARGETS[t["called"]]["d"])

    def score(self, shot, t, p, ctx, idx):
        hit = range_hit(shot)
        if hit["target"] < 0:
            return dict({"points": 0, "great": False, "stop": hit["stop"]}, **miss_text(shot))
        if hit["target"] != t["called"]:
            return {"points": 0, "great": False, "stop": hit["stop"], "what": "Wrong target!",
                    "detail": "That was %s - needed %s" % (TARGETS[hit["target"]]["name"],
                                                           TARGETS[t["called"]]["name"])}
        pts = ((TARGETS[hit["target"]]["pts"] + (JUNIOR_BONUS if t["junior"] else 0))
               * ZONE_MULT[hit["zone"]] * 2)
        txt = hit_text(hit, pts)
        txt["what"] = "CALLED IT!  +%s" % num(pts)
        return dict({"points": pts, "great": True, "stop": hit["stop"], "hitTarget": hit["target"]}, **txt)


class Ladder(RangeGame):
    id = "ladder"
    name = "Ladder Climb"
    emoji = "🪜"
    blurb = "Hit the targets in order, nearest first. First to the top wins. Juniors climb 3, adults 5."
    round_choices = [10, 20]
    default_rounds = 10

    def format_score(self, v):
        return "Step " + num(v)

    def player_target(self, base, p):
        return {"junior": bool(p.get("junior"))}

    def _rung(self, ctx, idx):
        return min(ladder_step(ctx, idx), len(TARGETS) - 1)

    def task(self, t, p, ctx, idx):
        step = ladder_step(ctx, idx)
        T = TARGETS[min(step, len(TARGETS) - 1)]
        return "Climb to %s (%d yds) - step %d of %d" % (T["name"].upper(), T["d"], step + 1, ladder_length(p))

    def highlight(self, t, ctx, idx):
        return self._rung(ctx, idx)

    def test_kind(self, t, ctx, idx):
        return kind_for(TARGETS[self._rung(ctx, idx)]["d"])

    def score(self, shot, t, p, ctx, idx):
        step = ladder_step(ctx, idx)
        hit = range_hit(shot)
        if hit["target"] == step:
            done = step + 1 >= ladder_length(p)
            return {"points": 1, "great": True, "stop": hit["stop"], "hitTarget": hit["target"],
                    "color": TARGETS[step]["color"],
                    "what": "TOP OF THE LADDER!" if done else TARGETS[step]["name"].upper() + " ✓",
                    "detail": p["name"] + " wins!" if done else "Next up: " + TARGETS[step + 1]["name"]}
        if hit["target"] >= 0:
            return {"points": 0, "great": False, "stop": hit["stop"], "what": "Wrong rung!",
                    "detail": "Hit %s - need %s" % (TARGETS[hit["target"]]["name"], TARGETS[step]["name"])}
        return dict({"points": 0, "great": False, "stop": hit["stop"]}, **miss_text(shot))

    def is_over(self, ctx):
        if any(ladder_step(ctx, i) >= ladder_length(p) for i, p in enumerate(ctx.players)):
            return True
        return ctx.turn >= ctx.rounds * len(ctx.players)


# ================= Golf Cornhole =================
# The physics (bag flight, the board, collisions) is in cornhole.py. These are
# the official (ACL) rules: two sides, 4 bags each per inning, alternating;
# in the hole 3, on the board 1; only the difference scores (cancellation);
# first to 21 at the end of an inning wins; whoever scored last throws first.

BAGS_PER_SIDE = 4
MISS_TEXT = {"short": "Short of the board", "long": "Over the board", "wide": "Wide of the board",
             "face": "Hit the front of the board", "off_front": "Slid off the front",
             "off_back": "Slid off the back", "off_side": "Slid off the side"}


class Cornhole(Game):
    id = "cornhole"
    name = "Golf Cornhole"
    emoji = "🌽"
    blurb = "Your shot becomes a bean bag on a giant board. Hole 3, board 1, cancellation scoring."
    view = "cornhole"
    min_players = 2
    uses_rounds = False
    stateful = True
    options = [{"key": "distance", "label": "Hole distance", "choices": [30, 50, 75, 100, 150, 200, 250],
                "default": 100, "unit": "yds"},
               {"key": "to", "label": "Play to", "choices": [21, 11], "default": 21, "unit": ""}]

    def reset(self, ctx):
        opts = ctx.options or self.check_options({})
        ctx.cornhole = {"board": cornhole.Board(opts["distance"]), "to": opts["to"], "scores": [0, 0],
                        "inning": 1, "first": 0, "thrown": 0, "bags": [], "clear": False,
                        "innings": [], "winner": None, "last": None}

    # ---- sides ----
    def side_of(self, idx):
        return idx % 2

    def members(self, ctx, side):
        return [i for i in range(len(ctx.players)) if i % 2 == side]

    def sides(self, ctx):
        out = []
        for s in (0, 1):
            ps = [ctx.players[i] for i in self.members(ctx, s)]
            out.append({"name": " & ".join(p["name"] for p in ps), "color": ps[0]["color"],
                        "players": [p["name"] for p in ps]})
        return out

    def side_up(self, ctx):
        st = ctx.cornhole
        return st["first"] if st["thrown"] % 2 == 0 else 1 - st["first"]

    def player_for_turn(self, ctx, turn):
        side = self.side_up(ctx)
        team = self.members(ctx, side)
        return team[(ctx.cornhole["inning"] - 1) % len(team)]

    def make_target(self, round_):
        return {}

    def player_target(self, base, p):
        return base

    def bag_number(self, ctx):
        return ctx.cornhole["thrown"] // 2 + 1

    def task(self, t, p, ctx, idx):
        st = ctx.cornhole
        return "Bag %d of %d · hole at %s yds" % (self.bag_number(ctx), BAGS_PER_SIDE,
                                                  num(st["board"].distance_yd))

    def test_kind(self, t, ctx, idx):
        return kind_for(ctx.cornhole["board"].distance_yd)

    def test_shot(self, t, ctx, idx):
        """A shot aimed at the hole, with a golfer's usual misses."""
        d = ctx.cornhole["board"].distance_yd
        vla, spin = {"chip": (28, 4500), "wedge": (28, 8500), "iron": (18, 6500), "driver": (12, 3000)}[kind_for(d)]
        rng = self.rng
        # some stingers (low and hot) and some high, floaty shots, so the bags' flights vary
        style = rng.random()
        if style < 0.2:
            vla, spin = vla * 0.45, spin * 0.55
        elif style < 0.4:
            vla, spin = vla * 1.5, spin * 1.1
        vla += rng.uniform(-2, 2)
        spin *= rng.uniform(0.9, 1.1)
        # one in four is a big draw or fade, started out the other way so it curves back
        axis = rng.choice((-1, 1)) * rng.uniform(12, 20) if rng.random() < 0.25 else rng.uniform(-6, 6)
        lo, hi = 5.0, 200.0
        for _ in range(30):
            mid = (lo + hi) / 2
            if flight.simulate(mid, vla, 0, spin, axis)["carry_yd"] < d:
                lo = mid
            else:
                hi = mid
        curve = flight.simulate(lo, vla, 0, spin, axis)["offline_yd"]
        aim = -math.degrees(math.atan2(curve, d))
        # about one swing in five is pushed or pulled far enough to miss the board to the side
        hla = rng.choice((-1, 1)) * rng.uniform(8, 12) if rng.random() < 0.2 else aim + rng.uniform(-3, 3)
        return {"speed_mph": lo * rng.uniform(0.95, 1.04), "vla_deg": vla, "hla_deg": hla,
                "spin_rpm": spin, "spin_axis_deg": axis}

    # ---- a throw ----
    def score(self, shot, t, p, ctx, idx):
        st = ctx.cornhole
        if st["clear"]:
            st["bags"], st["clear"] = [], False
        side = self.side_of(idx)
        # undo replays the earlier throws; they don't need animation frames
        sim = cornhole.throw(st["board"], st["bags"], shot, side, idx, seed=shot.get("id") or 0,
                             frames=not getattr(ctx, "replaying", False))
        st["bags"], st["last"] = sim["bags"], sim
        st["thrown"] += 1
        bag = sim["thrown"]
        names = self.sides(ctx)
        if bag.state == "hole":
            what = "AIRMAIL!  +3" if bag.how == "airmail" else "IN THE HOLE!  +3"
        elif bag.state == "board":
            what = "On the board  +1"
        else:
            what = MISS_TEXT.get(bag.how, "Off the board")
        effects = []
        for b, was in zip(sim["bags"], sim["before"]):
            if was == "board" and b.state == "hole":
                effects.append("knocked %s bag in" % ("their own" if b.side == side else names[b.side]["name"] + "'s"))
            elif was == "board" and b.state != "board":
                effects.append("knocked %s bag off" % ("their own" if b.side == side else names[b.side]["name"] + "'s"))
        detail = (", ".join(effects).capitalize()) if effects else ""
        res = {"points": 0, "what": what, "detail": detail, "great": bag.state == "hole",
               "color": names[side]["color"]}
        summary = self._advance(ctx)
        if summary:
            res["detail"] = (detail + " · " if detail else "") + summary
            res["inning_over"] = True
        return res

    def on_skip(self, ctx):
        st = ctx.cornhole
        if st["clear"]:
            st["bags"], st["clear"] = [], False
        st["thrown"] += 1
        st["last"] = None
        self._advance(ctx)

    def _advance(self, ctx):
        """End the inning after the 8th bag: cancellation scoring. Returns the inning's summary."""
        st = ctx.cornhole
        if st["thrown"] < 2 * BAGS_PER_SIDE:
            return None
        pts = [0, 0]
        for b in st["bags"]:
            pts[b.side] += b.points
        diff = abs(pts[0] - pts[1])
        scorer = None if diff == 0 else 0 if pts[0] > pts[1] else 1
        if scorer is not None:
            st["scores"][scorer] += diff
        st["innings"].append({"inning": st["inning"], "points": pts, "scorer": scorer, "diff": diff})
        names = self.sides(ctx)
        text = "Inning %d: %d-%d, " % (st["inning"], pts[0], pts[1])
        text += "cancels out" if scorer is None else "%s +%d" % (names[scorer]["name"], diff)
        if scorer is not None and st["scores"][scorer] >= st["to"]:
            st["winner"] = scorer
        else:
            st["inning"] += 1
            st["thrown"] = 0
            st["clear"] = True
            if scorer is not None:
                st["first"] = scorer
        return text

    def is_over(self, ctx):
        return ctx.cornhole["winner"] is not None

    # ---- screens ----
    def round_info(self, ctx):
        st = ctx.cornhole
        return "INNING %d · TO %d" % (st["inning"], st["to"])

    def player_totals(self, ctx):
        st = ctx.cornhole
        return [st["scores"][self.side_of(i)] for i in range(len(ctx.players))]

    def scoreboard(self, ctx, current):
        st = ctx.cornhole
        rows = []
        thrown = [0, 0] if st["clear"] else [sum(1 for b in st["bags"] if b.side == s) for s in (0, 1)]
        for s, side in enumerate(self.sides(ctx)):
            left = BAGS_PER_SIDE - thrown[s] if not st["clear"] else BAGS_PER_SIDE
            on = sum(b.points for b in st["bags"] if b.side == s) if not st["clear"] else 0
            # the row shows this inning's points; the game score is the headline above
            rows.append({"name": side["name"], "color": side["color"],
                         "sub": "%d bag%s left" % (left, "" if left == 1 else "s"),
                         "value": str(on),
                         "current": current >= 0 and self.side_of(current) == s})
        return rows

    def headline(self, ctx):
        st = ctx.cornhole
        return {"label": "GAME · TO %d" % st["to"], "board_title": "Inning %d" % st["inning"],
                "sides": [{"name": side["name"], "color": side["color"], "value": st["scores"][s]}
                          for s, side in enumerate(self.sides(ctx))]}

    def winner_text(self, ctx):
        st = ctx.cornhole
        w = st["winner"]
        side = self.sides(ctx)[w]
        verb = "win" if len(side["players"]) > 1 else "wins"
        return "%s %s %d-%d!" % (side["name"], verb, st["scores"][w], st["scores"][1 - w])

    def extra(self, ctx):
        st = ctx.cornhole
        board = st["board"]
        sides = self.sides(ctx)
        bags = [] if st["clear"] else st["bags"]
        return {"board": board.info(), "idle_camera": cornhole.idle_camera(board),
                "bags": [{"side": b.side, "player": b.player, "color": sides[b.side]["color"],
                          "state": b.state, "pose": b.pose(board)} for b in bags],
                "scores": st["scores"], "inning": st["inning"], "thrown": st["thrown"], "to": st["to"],
                "sides": sides, "innings": st["innings"]}

    def plan(self, ctx, shot, result, player, style):
        """The shot plan for the throw score() just played."""
        st = ctx.cornhole
        sim = st["last"]
        great = result.get("great") or result.get("inning_over") or st["winner"] is not None
        mode = ("static" if style == "static" else "quick" if style == "quick" else
                "broadcast" if style == "broadcast" or great else "quick")
        return cornhole.message(st["board"], sim, shot, result, player,
                                [s["color"] for s in self.sides(ctx)], mode)


GAME_CLASSES = [TargetRange, CalledShot, Ladder, Closest, Darts, Speed, LongDrive, TicTacToe, Cornhole]


def make_games(rng=None):
    """Fresh game objects (pass a seeded random.Random for repeatable tests)."""
    return [cls(rng) for cls in GAME_CLASSES]


GAMES = make_games()


def game_by_id(game_id, games=None):
    for g in games or GAMES:
        if g.id == game_id:
            return g
    return None
