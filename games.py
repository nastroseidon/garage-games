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

    def info(self):
        """What a menu needs to list the game."""
        return {"id": self.id, "name": self.name, "emoji": self.emoji,
                "blurb": self.blurb, "view": self.view,
                "min_players": self.min_players, "uses_rounds": self.uses_rounds,
                "round_choices": self.round_choices,
                "default_rounds": self.default_rounds}


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


GAME_CLASSES = [TargetRange, CalledShot, Ladder, Closest, Darts, Speed, LongDrive, TicTacToe]


def make_games(rng=None):
    """Fresh game objects (pass a seeded random.Random for repeatable tests)."""
    return [cls(rng) for cls in GAME_CLASSES]


GAMES = make_games()


def game_by_id(game_id, games=None):
    for g in games or GAMES:
        if g.id == game_id:
            return g
    return None
