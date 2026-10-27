"""Golf Cornhole: the board, the bags, their physics and the shot plan.

The golfer hits a real ball; a cornhole bag flies the ball's flight instead
and lands where the ball would land on a driving range. The cornhole set is
scaled to the hole distance the players pick: the hole's radius is 3% of that
distance (3 yds at 100 yds, 7.5 yds at 250), and the board, the bags and the
slope keep official proportions around it (2 x 4 ft board, 6 in hole 9 in from
the back, front edge 3 in and back edge 12 in high, 6 in bags). So a shot
that would go wide or long on the range misses the board, by as much as it
missed on the range.

After landing, the bag slides as far (in board terms) as the ball would have
rolled, up the sloped board; it can bump other bags (into the hole or off
the board), drop in the hole, or slide off an edge. A bag that lands on the
grass first is a foul bag and scores nothing.

The physics runs on a real-size board, in metres, with the hole at x = 0
("board space"); positions for the screens are scaled up around the real
hole, in yards (x downrange, y right, z up).

The rules (innings, cancellation scoring) live in games.py (Cornhole).
"""

import functools
import math

IN = 0.0254
YD = 0.9144
FT = 0.3048
G = 9.81

# ---- an official board and bag ----
BOARD_L = 48 * IN
BOARD_W = 24 * IN
HOLE_R = 3 * IN
HOLE_FROM_BACK = 9 * IN
FRONT_H = 3 * IN
BACK_H = 12 * IN
FRAME_H = 3.5 * IN          # the 2x4 frame under the top
BAG = 6 * IN
BAG_T = 1.5 * IN            # a bag lying flat
SLOPE = math.asin((BACK_H - FRONT_H) / BOARD_L)

HOLE_PCT = 0.03             # hole radius as a fraction of the hole distance

# ---- the screen in the garage: the tee camera shows the world life-size ----
SCREEN_W_FT = 12.0
SCREEN_H_FT = 9.0
HITTER_FT = 10.0            # golfer to screen (9-11 ft)
TEE_FOV = math.degrees(2 * math.atan(SCREEN_H_FT / 2 / HITTER_FT))   # vertical, ~48.5 degrees
# A real thrower's eyes are 6 ft up at the foul line, 27 ft from the far board's front edge.
# The tee camera looks down at the hole at that same angle, so the scaled-up board reads like
# a real one seen from the line instead of from ground level.
THROWER_EYE = 6 * FT
THROW_LINE = 27 * FT

# ---- contact (on the real-size board) ----
MU_BOARD = 0.4              # sliding friction, bag on board
MU_GRASS = 1.0
SLIDE_PER_ROLL = 1.5        # board slide = the ball's roll on the range x this
BAG_BOUNCE = 0.2            # bag-on-bag restitution
STOP = 0.02                 # m/s: slower than this counts as stopped
SPIN_DRAG = 12.0            # rad/s^2 a sliding bag's spin slows by
BAG_SPIN_PER_RPM = 4 * math.pi / 1000   # 1000 rpm of side spin on the ball: the bag turns twice a second
BAG_SPIN_MAX = 8 * math.pi              # four turns a second at most
HOLE_DROP_S = 0.3           # how long the drop through the hole takes on screen

DT_SLIDE = 1.0 / 600
FPS = 60
MAX_SETTLE_S = 8.0

POINTS = {"hole": 3, "board": 1}


class Board:
    """The board for one game: its hole distance_yd straight down the target line."""

    def __init__(self, distance_yd):
        self.distance_yd = float(distance_yd)
        self.s = HOLE_PCT * self.distance_yd * YD / HOLE_R     # screen metres per board-space metre
        self.L, self.W, self.hole_r = BOARD_L, BOARD_W, HOLE_R
        self.hole_a = BOARD_L - HOLE_FROM_BACK                  # up the slope from the front edge
        self.cos, self.sin = math.cos(SLOPE), math.sin(SLOPE)
        self.x0 = -self.hole_a * self.cos                       # front edge, board space (hole at x = 0)
        self.x1 = self.x0 + self.L * self.cos
        self.bag_r = BAG * 0.55                                 # a square bag, as a disc

    # ---- board space (real size, metres) ----
    def surface(self, x):
        return FRONT_H + (x - self.x0) * self.sin / self.cos

    def over(self, x, y):
        return self.x0 <= x <= self.x1 and abs(y) <= self.W / 2

    def on_top(self, a, c, lift=0.0):
        """A point on the board (a up the slope from the front edge, c right) -> board space."""
        return [self.x0 + a * self.cos - lift * self.sin, c, FRONT_H + a * self.sin + lift * self.cos]

    # ---- board space <-> the range (yards) ----
    def to_range(self, p):
        k = self.s / YD
        return [round(self.distance_yd + p[0] * k, 4), round(p[1] * k, 4), round(p[2] * k, 4)]

    def from_range(self, d, l, h=0.0):
        k = YD / self.s
        return [(d - self.distance_yd) * k, l * k, h * k]

    def surface_yd(self, d):
        return self.surface(self.from_range(d, 0)[0]) * self.s / YD

    def over_yd(self, d, l):
        p = self.from_range(d, l)
        return self.over(p[0], p[1])

    def info(self):
        """The board for the screens, in yards."""
        k = self.s / YD
        return {"distance": self.distance_yd, "scale": round(self.s, 3),
                "center": self.to_range(self.on_top(self.L / 2, 0)),
                "hole": self.to_range(self.on_top(self.hole_a, 0)),
                "length": round(self.L * k, 4), "width": round(self.W * k, 4),
                "hole_r": round(self.hole_r * k, 4), "slope_deg": round(math.degrees(SLOPE), 3),
                "front": self.to_range([self.x0, 0, FRONT_H]),
                "back": self.to_range([self.x1, 0, BACK_H]),
                "frame": round(FRAME_H * k, 4), "bag": round(BAG * k, 4), "bag_t": round(BAG_T * k, 4),
                "sign": yardage_sign(self), "camp": _camp_at(self.distance_yd)}


# ---- the yardage sign: a crooked, hand-painted plank on a post, off to the left ----
# Brush strokes for the digits, in a box 0.6 wide and 1 tall (x right, y up).
GLYPHS = {
    "0": [[(0.3, 1.0), (0.12, 0.92), (0.03, 0.7), (0.02, 0.4), (0.08, 0.14), (0.25, 0.0), (0.42, 0.04),
           (0.55, 0.25), (0.58, 0.55), (0.52, 0.85), (0.38, 0.99), (0.24, 0.96)]],
    "1": [[(0.12, 0.8), (0.32, 1.0), (0.33, 0.0)]],
    "2": [[(0.04, 0.76), (0.14, 0.95), (0.34, 1.0), (0.52, 0.9), (0.55, 0.7), (0.44, 0.48), (0.06, 0.02),
           (0.6, 0.0)]],
    "3": [[(0.04, 0.9), (0.28, 1.0), (0.5, 0.92), (0.52, 0.72), (0.28, 0.56)],
          [(0.26, 0.56), (0.52, 0.44), (0.56, 0.18), (0.36, 0.0), (0.04, 0.08)]],
    "5": [[(0.56, 1.0), (0.1, 0.99), (0.07, 0.58), (0.3, 0.63), (0.52, 0.5), (0.56, 0.24), (0.4, 0.03),
           (0.2, 0.0), (0.02, 0.1)]],
    "7": [[(0.02, 0.99), (0.6, 1.0), (0.22, 0.0)]],
}
for _d in "4689":
    GLYPHS.setdefault(_d, GLYPHS["0"])


def yardage_sign(board):
    """The sign's size, where it stands and its brush strokes, in yards on the range.
    base is the foot of the post; u, v, n are the plank's right, up and out-of-the-face
    directions (n faces the tee, the whole thing leans a little). Strokes are [a, b] points
    across (a) and up (b) the plank's face from its centre."""
    import random
    rnd = random.Random(int(board.distance_yd))
    ln = board.L * board.s / YD                     # the board's length in yards
    hole = board.to_range(board.on_top(board.hole_a, 0))
    hx, hz = hole[0], hole[2]
    hw = board.W * board.s / YD / 2
    w, h, post_h = 0.34 * ln, 0.13 * ln, 0.16 * ln
    # placed on the tee view: the plank's centre level with the hole on screen, halfway between
    # the board's left edge and the screen's left edge. The hole is in the middle of the view.
    cz = hz + hx * tee_drop()
    dist = math.hypot(hx, cz - hz)
    f = [hx / dist, 0.0, (hz - cz) / dist]              # straight at the hole; right is +y
    tan_w = SCREEN_W_FT / 2 / HITTER_FT                 # half the screen's width over the distance
    sx = (-hw / dist / tan_w - 1) / 2                   # -1 is the screen's left edge
    ray = [f[0], sx * tan_w, f[2]]
    turn = math.radians(rnd.uniform(4, 9))
    lean = math.radians(rnd.choice((-1, 1)) * rnd.uniform(4, 7))
    up = post_h + h / 2                             # foot of the post to the plank's centre
    t = (up * math.cos(lean) - cz) / ray[2]         # down the ray to the plank's centre height
    mid = [t * ray[0], t * ray[1]]
    heading = math.atan2(-mid[1], -mid[0]) + turn   # turned toward the tee
    nvec = [math.cos(heading), math.sin(heading), 0.0]
    r = [nvec[1], -nvec[0], 0.0]                    # the viewer's right
    u = [r[0] * math.cos(lean), r[1] * math.cos(lean), -math.sin(lean)]
    v = [r[0] * math.sin(lean), r[1] * math.sin(lean), math.cos(lean)]
    # the lean carries the plank sideways, so the post's foot goes the other way
    base = [round(mid[0] - v[0] * up, 3), round(mid[1] - v[1] * up, 3), 0.0]
    text = str(int(board.distance_yd))
    th = 0.66 * h                                   # letter height
    gap = 0.16 * th
    width = len(text) * 0.6 * th + (len(text) - 1) * gap
    strokes, x = [], -width / 2
    for ch in text:
        tilt = math.radians(rnd.uniform(-5, 5))
        lift = rnd.uniform(-0.05, 0.05) * th
        for line in GLYPHS[ch]:
            pts = []
            for gx, gy in line:
                px = (gx - 0.3) * th + rnd.uniform(-0.025, 0.025) * th
                py = (gy - 0.5) * th + rnd.uniform(-0.025, 0.025) * th
                pts.append([round(x + 0.3 * th + px * math.cos(tilt) - py * math.sin(tilt), 4),
                            round(lift + px * math.sin(tilt) + py * math.cos(tilt), 4)])
            strokes.append({"pts": pts, "w": round(th * rnd.uniform(0.15, 0.18), 4)})
        x += 0.6 * th + gap
    return {"text": text, "base": base, "u": [round(c, 5) for c in u], "v": [round(c, 5) for c in v],
            "n": [round(c, 5) for c in nvec], "w": round(w, 4), "h": round(h, 4), "t": round(0.02 * ln, 4),
            "post_h": round(post_h, 4), "post_w": round(0.035 * ln, 4), "strokes": strokes}


# ---- the campsite around the board ----
# Laid out at real size in board space (metres, hole at x = 0, x away from the thrower, y right),
# then scaled up with the board, so the grass, the fire and the trees all match the board.
# It is the same camp at every hole distance. The thrower stands about 2.5 m short of the hole.
CAMP_CENTER = (4.0, 0.0)        # the middle of the clearing
CAMP_CLEARING_R = 9.0
CAMP_FIRE = (3.6, 2.2)
CAMP_LANE = (-3.6, 1.6, 1.5)    # x from, x to, half width: where the bags fly; nothing stands in it


@functools.lru_cache(maxsize=8)
def _camp_at(distance_yd):
    """The campsite for a hole distance, built once (the screens ask for the board often)."""
    return campsite(Board(distance_yd))


def campsite(board):
    """The campsite in yards on the range, sizes in yards. "k" is yards per real metre."""
    import random
    rnd = random.Random(7)
    k = board.s / YD

    def at(x, y, z=0.0):
        return [round(c, 3) for c in board.to_range([x, y, z])]

    def m(v):
        return round(v * k, 4)

    def facing(x, y, tx, ty):
        """The yaw (degrees, clockwise from downrange seen from above) that faces (tx, ty)."""
        return round(math.degrees(math.atan2(ty - y, tx - x)), 1)

    taken = []    # (x, y, r): things that stand on the ground, so nothing else lands on them

    def free(x, y, r):
        lx0, lx1, lw = CAMP_LANE
        if lx0 - r < x < lx1 + r and abs(y) < lw + r:
            return False
        return all(math.hypot(x - a, y - b) >= r + c for a, b, c in taken)

    def claim(x, y, r):
        taken.append((x, y, r))

    fx, fy = CAMP_FIRE
    claim(fx, fy, 0.9)
    claim(-0.07, -0.9, 0.35)                              # the yardage sign

    logs = []
    for ang in (40, 150, 260):
        a = math.radians(ang)
        x, y = fx + 1.45 * math.cos(a), fy + 1.45 * math.sin(a)
        # yaw turns the log's length (its local right) to run around the fire
        logs.append({"p": at(x, y), "len": m(1.3), "r": m(0.16), "yaw": float(ang)})
        claim(x, y, 0.7)
    chairs = []
    for ang, color in ((95, "#2f4f7f"), (320, "#3f6b3a")):
        a = math.radians(ang)
        x, y = fx + 1.55 * math.cos(a), fy + 1.55 * math.sin(a)
        chairs.append({"p": at(x, y), "yaw": facing(x, y, fx, fy), "size": m(0.55), "color": color})
        claim(x, y, 0.45)

    tents = [
        {"kind": "aframe", "p": at(8.8, -3.2), "yaw": facing(8.8, -3.2, fx, fy), "l": m(2.2), "w": m(1.6),
         "h": m(1.25), "color": "#d9772b", "glow": 0.0},
        {"kind": "dome", "p": at(9.6, 5.2), "yaw": facing(9.6, 5.2, fx, fy), "l": m(2.4), "w": m(2.2),
         "h": m(1.3), "color": "#4f8a3c", "glow": 0.6},
    ]
    claim(8.8, -3.2, 1.5)
    claim(9.6, 5.2, 1.6)
    table = {"p": at(6.2, -2.4), "yaw": 15.0, "l": m(1.8), "w": m(0.75), "h": m(0.75), "bench": m(0.45)}
    claim(6.2, -2.4, 1.3)
    cooler = {"p": at(5.0, -0.9), "yaw": 20.0, "size": [m(0.6), m(0.4), m(0.42)]}
    claim(5.0, -0.9, 0.45)
    woodpile = {"p": at(5.7, 4.6), "yaw": 30.0, "len": m(0.45), "r": m(0.07)}
    claim(5.7, 4.6, 0.7)
    stumps = [{"p": at(6.9, 2.9), "r": m(0.24), "h": m(0.4)}, {"p": at(-1.6, 4.6), "r": m(0.2), "h": m(0.3)}]
    for s_ in ((6.9, 2.9), (-1.6, 4.6)):
        claim(s_[0], s_[1], 0.4)
    # a lantern on a shepherd's hook, just off the left of the starting view: it lights the board
    hook = {"p": at(-0.4, -1.75), "h": m(1.7), "arm": m(0.3)}
    claim(-0.4, -1.75, 0.3)

    trees = []

    def tree(x, y, kind, h, r):
        trees.append({"p": at(x, y), "kind": kind, "h": m(h), "r": m(r), "yaw": round(rnd.uniform(0, 360), 1),
                      "tint": round(rnd.uniform(0.75, 1.15), 3)})
        claim(x, y, max(0.6, r * 0.45))

    # the two trees the string lights hang between, and a few that frame the clearing
    a_, b_ = (10.5, -6.5), (12.5, 7.5)
    tree(a_[0], a_[1], "pine", 15.0, 3.0)
    tree(b_[0], b_[1], "pine", 16.0, 3.2)
    for x, y, kind, h, r in ((14.5, 0.8, "pine", 18.0, 3.6), (2.5, -9.5, "oak", 11.0, 3.4),
                             (1.2, 9.6, "pine", 14.0, 2.8), (-4.0, -8.0, "pine", 13.0, 2.6),
                             (-5.0, 8.5, "oak", 10.0, 3.0)):
        tree(x, y, kind, h, r)
    cx, cy = CAMP_CENTER
    tries = 0
    while len(trees) < 320 and tries < 20000:
        tries += 1
        ang = rnd.uniform(0, 2 * math.pi)
        dist = CAMP_CLEARING_R + 2 + (rnd.random() ** 1.3) * 52
        x, y = cx + dist * math.cos(ang), cy + dist * math.sin(ang)
        kind = "pine" if rnd.random() < 0.72 else "oak"
        h = rnd.uniform(10, 19) if kind == "pine" else rnd.uniform(7, 12)
        r = h * rnd.uniform(0.17, 0.22) if kind == "pine" else rnd.uniform(2.4, 3.8)
        if free(x, y, 1.6):
            tree(x, y, kind, h, r)

    # string lights: a sagging line of bulbs between the two trees, in front of their trunks
    lights = []
    ax, ay = a_[0] - 0.4, a_[1] + 0.35
    bx, by = b_[0] - 0.4, b_[1] - 0.35
    span = math.hypot(bx - ax, by - ay)
    n = int(span / 0.45)
    for i in range(n + 1):
        u = i / n
        z = 2.7 - 0.7 * 4 * u * (1 - u)
        lights.append(at(ax + (bx - ax) * u, ay + (by - ay) * u, z))

    rocks, bushes = [], []
    while len(rocks) < 26:
        ang, dist = rnd.uniform(0, 2 * math.pi), rnd.uniform(5.5, CAMP_CLEARING_R + 3)
        x, y = cx + dist * math.cos(ang), cy + dist * math.sin(ang)
        r = rnd.uniform(0.12, 0.45)
        if free(x, y, r):
            rocks.append({"p": at(x, y), "r": m(r), "yaw": round(rnd.uniform(0, 360), 1)})
            claim(x, y, r)
    while len(bushes) < 48:
        ang, dist = rnd.uniform(0, 2 * math.pi), rnd.uniform(CAMP_CLEARING_R - 1, CAMP_CLEARING_R + 4)
        x, y = cx + dist * math.cos(ang), cy + dist * math.sin(ang)
        r = rnd.uniform(0.4, 1.1)
        if free(x, y, r * 0.8):
            bushes.append({"p": at(x, y), "r": m(r), "tint": round(rnd.uniform(0.7, 1.2), 3)})
            claim(x, y, r * 0.8)

    return {"k": round(k, 4), "center": at(cx, cy), "clearing_r": m(CAMP_CLEARING_R), "ground_r": m(140),
            "fire": {"p": at(fx, fy), "r": m(0.55)}, "logs": logs, "chairs": chairs, "tents": tents,
            "table": table, "cooler": cooler, "woodpile": woodpile, "stumps": stumps, "hook": hook,
            "trees": trees, "lights": lights, "rocks": rocks, "bushes": bushes}


class Bag:
    """state: air, board, falling, ground or hole.
    On the board p = [a, c] and v = [va, vc]; otherwise board-space [x, y, z]."""

    def __init__(self, side, player, number, yaw=0.0):
        self.side, self.player, self.number = side, player, number
        self.state = "air"
        self.p, self.v = [0.0, 0.0, 0.0], [0.0, 0.0, 0.0]
        self.yaw, self.spin = yaw, 0.0
        self.hole_t = None
        self.air = None      # [x, y, z] in yards while flying
        self.how = None      # airmail, slid, knocked, short, long, wide, off_front, off_back, off_side

    def copy(self):
        b = Bag(self.side, self.player, self.number, self.yaw)
        b.state, b.p, b.v, b.spin, b.how = self.state, list(self.p), list(self.v), self.spin, self.how
        return b

    @property
    def points(self):
        return POINTS.get(self.state, 0)

    def speed(self):
        return math.sqrt(sum(c * c for c in self.v))

    def moving(self, t):
        if self.state in ("air", "falling"):
            return True
        if self.state == "hole":
            return self.hole_t is not None and t - self.hole_t < HOLE_DROP_S
        return self.speed() > 0

    def pose(self, board, t=None):
        """[x, y, z, yaw, pitch, visible, size] in yards / degrees: the bag's centre, how it lies,
        and its size as a fraction of the board's bags. In the air the bag grows with its distance
        from the tee, so on screen it always looks like a real bag (it is board-sized on landing)."""
        yaw = round(math.degrees(self.yaw) % 360, 1)
        if self.state == "air":
            far = math.sqrt(sum(c * c for c in self.air)) / board.distance_yd
            return [self.air[0], self.air[1], self.air[2], yaw, 0.0, 1, round(min(1.0, max(1.0 / board.s, far)), 4)]
        if self.state == "board":
            p, pitch, vis = board.on_top(self.p[0], self.p[1], BAG_T / 2), math.degrees(SLOPE), 1
        elif self.state == "hole":
            done = 1.0 if t is None or self.hole_t is None else min(1.0, (t - self.hole_t) / HOLE_DROP_S)
            p = board.on_top(board.hole_a, 0, BAG_T / 2 - done * (BAG + BAG_T))
            pitch, vis = math.degrees(SLOPE) * (1 - done) + 70 * done, 0 if done >= 1 else 1
        else:
            p, pitch, vis = [self.p[0], self.p[1], max(self.p[2], BAG_T / 2)], 0.0, 1
        return board.to_range(p) + [yaw, round(pitch, 1), vis, 1]


# ---------------- one throw ----------------

def _flight_frames(board, flight, lands_on_board):
    """The ball's flight in yards, one point per frame, ending on the board (or the grass).
    It never cuts through the board: over the board it skims the top."""
    pts = [[q[0], q[1], q[2] / 3.0] for q in flight["points"]]
    land = [flight["carry_yd"], flight["offline_yd"]]
    if len(pts) < 2:
        pts = [[0, 0, 0], land + [0]]
    pts[-1] = land + [0]
    end_h = board.surface_yd(land[0]) + BAG_T / 2 * board.s / YD if lands_on_board else BAG_T / 2 * board.s / YD
    t_total = max(0.3, flight["flight_time_s"])
    n = max(2, int(math.ceil(t_total * FPS)))
    out = []
    for k in range(n):
        u = k / (n - 1)
        x = u * (len(pts) - 1)
        i = min(int(x), len(pts) - 2)
        f = x - i
        p = [pts[i][j] + (pts[i + 1][j] - pts[i][j]) * f for j in range(3)]
        # lift the flight onto the (raised) board evenly, so the bag comes down at close to the
        # ball's own angle: a stinger stays low and flat, a high shot drops in steeply
        p[2] += end_h * u
        if board.over_yd(p[0], p[1]):
            p[2] = max(p[2], board.surface_yd(p[0]) + BAG_T / 2 * board.s / YD)
        out.append([round(p[0], 4), round(p[1], 4), round(p[2], 4)])
    return out, t_total


def _slide_speed(dist, decel):
    return math.sqrt(2 * decel * max(0.0, dist))


def _land(board, bag, flight):
    """Put the bag down where the ball landed, moving the way the ball would roll."""
    land = [flight["carry_yd"], flight["offline_yd"]]
    rest = flight.get("rest") or land
    p = board.from_range(land[0], land[1])
    heading = math.atan2(rest[1] - land[1], rest[0] - land[0]) if rest != land else 0.0
    roll = math.hypot(rest[0] - land[0], rest[1] - land[1]) * YD / board.s
    if board.over(p[0], p[1]):
        a, c = (p[0] - board.x0) / board.cos, p[1]
        uphill = max(0.0, math.cos(heading))
        v0 = _slide_speed(roll * SLIDE_PER_ROLL, MU_BOARD * G * board.cos + G * board.sin * uphill)
        bag.state, bag.p, bag.v = "board", [a, c], [v0 * math.cos(heading), v0 * math.sin(heading)]
        bag.how = "landed"
        bag.spin *= 0.5
        if math.hypot(a - board.hole_a, c) < board.hole_r:
            bag.state, bag.how, bag.v = "hole", "airmail", [0.0, 0.0]
        return
    v0 = _slide_speed(roll, MU_GRASS * G)
    bag.state, bag.p = "ground", [p[0], p[1], BAG_T / 2]
    bag.v = [v0 * math.cos(heading), v0 * math.sin(heading), 0.0]
    bag.how = "short" if p[0] < board.x0 else "long" if p[0] > board.x1 else "wide"


def _step(board, b, t, dt):
    if b.state == "board":
        va, vc = b.v
        if va or vc:
            va -= G * board.sin * dt
            sp = math.hypot(va, vc)
            dec = MU_BOARD * G * board.cos * dt
            if sp <= dec or sp < STOP:
                va = vc = 0.0       # static friction (0.4) beats the 10.8 degree slope
            else:
                va -= va / sp * dec
                vc -= vc / sp * dec
            b.v = [va, vc]
            b.p = [b.p[0] + va * dt, b.p[1] + vc * dt]
            b.yaw += b.spin * dt
            b.spin = math.copysign(max(0.0, abs(b.spin) - SPIN_DRAG * dt), b.spin)
            if not (va or vc):
                b.spin = 0.0
            d = math.hypot(b.p[0] - board.hole_a, b.p[1])
            if d < board.hole_r * (0.85 if math.hypot(va, vc) < 2.5 else 0.45):
                b.state, b.hole_t, b.v = "hole", t, [0.0, 0.0]
                if b.how != "knocked":
                    b.how = "slid"
                return
            a, c = b.p
            edge = "off_front" if a < 0 else "off_back" if a > board.L else "off_side" if abs(c) > board.W / 2 else None
            if edge:
                b.state, b.how = "falling", edge
                b.p = board.on_top(min(max(a, 0.0), board.L), c, BAG_T / 2)
                # it falls from just past the edge (from inside it, the frame would stop it dead underneath)
                if edge == "off_back":
                    b.p[0] = max(b.p[0], board.x1 + BAG / 2)
                elif edge == "off_front":
                    b.p[0] = min(b.p[0], board.x0 - BAG / 2)
                else:
                    b.p[1] = math.copysign(board.W / 2 + BAG / 2, c)
                b.v = [va * board.cos, vc, va * board.sin]
    elif b.state == "falling":
        b.v[2] -= G * dt
        n = [b.p[0] + b.v[0] * dt, b.p[1] + b.v[1] * dt, b.p[2] + b.v[2] * dt]
        if board.over(n[0], n[1]):
            n[0], n[1] = b.p[0], b.p[1]  # it slides down the frame, not through it
            b.v[0] = b.v[1] = 0.0
        if n[2] <= BAG_T / 2:
            b.state, b.p = "ground", [n[0], n[1], BAG_T / 2]
            sp = math.hypot(b.v[0], b.v[1])
            keep = max(0.0, sp - MU_GRASS * abs(b.v[2])) / sp if sp > 1e-9 else 0.0
            b.v = [b.v[0] * keep, b.v[1] * keep, 0.0]
            return
        b.p = n
        b.yaw += b.spin * dt
    elif b.state == "ground":
        vx, vy = b.v[0], b.v[1]
        sp = math.hypot(vx, vy)
        if sp:
            dec = MU_GRASS * G * dt
            if sp <= dec or sp < STOP:
                b.v = [0.0, 0.0, 0.0]
                b.spin = 0.0
            else:
                b.v = [vx - vx / sp * dec, vy - vy / sp * dec, 0.0]
                n = [b.p[0] + b.v[0] * dt, b.p[1] + b.v[1] * dt]
                if board.over(n[0], n[1]):
                    b.v = [0.0, 0.0, 0.0]       # stopped by the board's frame (a foul bag stays off it)
                else:
                    b.p = [n[0], n[1], b.p[2]]
                b.yaw += b.spin * dt
                b.spin = math.copysign(max(0.0, abs(b.spin) - 3 * SPIN_DRAG * dt), b.spin)


def _collide(board, bags):
    on = [b for b in bags if b.state == "board"]
    reach = 2 * board.bag_r
    for i in range(len(on)):
        for j in range(i + 1, len(on)):
            a, b = on[i], on[j]
            dx, dc = b.p[0] - a.p[0], b.p[1] - a.p[1]
            d = math.hypot(dx, dc)
            if d >= reach:
                continue
            nx, nc = (dx / d, dc / d) if d > 1e-9 else (1.0, 0.0)
            rel = (a.v[0] - b.v[0]) * nx + (a.v[1] - b.v[1]) * nc
            if rel > 0:
                imp = (1 + BAG_BOUNCE) / 2 * rel
                a.v = [a.v[0] - imp * nx, a.v[1] - imp * nc]
                b.v = [b.v[0] + imp * nx, b.v[1] + imp * nc]
                # a glancing hit sets both spinning
                tang = (a.v[0] - b.v[0]) * -nc + (a.v[1] - b.v[1]) * nx
                a.spin += tang * 2.0
                b.spin -= tang * 2.0
                for bag in (a, b):
                    if bag.how not in ("airmail", "slid", "landed"):
                        bag.how = "knocked"
            push = (reach - d) / 2
            a.p = [a.p[0] - push * nx, a.p[1] - push * nc]
            b.p = [b.p[0] + push * nx, b.p[1] + push * nc]


def bag_spin(shot):
    """How fast the bag spins flat (rad/s, + is clockwise seen from above, like a fade), from the
    ball's side spin only. Backspin and topspin don't show: the bag never tumbles in the air."""
    side_rpm = shot.get("spin_rpm", 0.0) * math.sin(math.radians(shot.get("spin_axis_deg", 0.0)))
    w = side_rpm * BAG_SPIN_PER_RPM
    w = math.copysign(min(abs(w), BAG_SPIN_MAX), w)
    return 0.0 if abs(w) < 0.3 else w


def throw(board, bags, shot, side, player, seed=0, frames=True):
    """Throw one bag (the shot's ball flight) onto a board that already has `bags` on it.

    Returns {"bags": every bag afterwards (the thrown one last), "frames": per frame
    (1/FPS s) a pose for every bag (empty when frames=False), "flight_s", "rest_s",
    "thrown": the new Bag, "before": the other bags' states before the throw}.
    """
    bags = [b.copy() for b in bags]
    for b in bags:
        b.how = None if b.state == "board" else b.how
    before = [b.state for b in bags]
    h = (seed * 2654435761) & 0xFFFFFFFF   # which way the bag faces, the same every time for the same shot
    new = Bag(side, player, len(bags), yaw=(h % 360) * math.pi / 180)
    new.spin = bag_spin(shot)
    everyone = bags + [new]
    out = []
    flight = shot["flight"]
    land = board.from_range(flight["carry_yd"], flight["offline_yd"])
    path, flight_s = _flight_frames(board, flight, board.over(land[0], land[1]))
    for q in path:
        new.air = q
        new.yaw += new.spin / FPS
        if frames:
            out.append([b.pose(board) for b in everyone])
    _land(board, new, flight)
    t = flight_s
    next_frame = flight_s + 1.0 / FPS
    while t < flight_s + MAX_SETTLE_S:
        if not any(b.moving(t) for b in everyone):
            break
        for b in everyone:
            _step(board, b, t, DT_SLIDE)
        _collide(board, everyone)
        t += DT_SLIDE
        if frames and t >= next_frame - 1e-9:
            out.append([b.pose(board, t) for b in everyone])
            next_frame += 1.0 / FPS
    for b in everyone:
        b.v = [0.0] * len(b.v)
        b.hole_t = None
    if frames:
        out.append([b.pose(board) for b in everyone])
    return {"bags": everyone, "frames": out, "flight_s": flight_s, "rest_s": t,
            "thrown": new, "before": before}


# ---------------- cameras and the shot plan ----------------

def cameras(board):
    """Camera positions (yards). "tee" is the golfer's view, life-size on the garage screen."""
    i = board.info()
    hx, hz, ln = i["hole"][0], i["hole"][2], max(i["length"], 1.0)
    return {
        "tee": {"pos": [0, 0, round(hz + hx * tee_drop(), 3)], "look": [hx, 0, hz], "fov": round(TEE_FOV, 2)},
        # in close over the front-left corner, on the top half of the board where the bags land and bump
        "board": {"pos": [hx - 0.9 * ln, -0.55 * ln, hz + 0.75 * ln], "look": [hx - 0.08 * ln, 0, hz], "fov": 36},
        # high over the front of the board: the whole top and the grass behind it, where knocked bags fall
        "top": {"pos": [hx - 0.55 * ln, 0, hz + 1.5 * ln], "look": [hx + 0.05 * ln, 0, 0], "fov": 48},
    }


def tee_drop():
    """How steeply a 6 ft thrower at the foul line looks down at the hole (rise over run)."""
    hole_h = FRONT_H + (BOARD_L - HOLE_FROM_BACK) * math.sin(SLOPE)
    run = THROW_LINE + (BOARD_L - HOLE_FROM_BACK) * math.cos(SLOPE)
    return (THROWER_EYE - hole_h) / run


def idle_camera(board):
    c = cameras(board)["tee"]
    return {"pos": c["pos"], "look": c["look"], "fov": c["fov"]}


def _r(v):
    return round(v, 3)


def message(board, sim, shot, result, player, side_colors, mode="quick", drama=None, fps=FPS):
    """A shot plan in the same format as director.to_message, plus a "cornhole" part
    with the board and every bag's poses. ball[] follows the thrown bag."""
    frames = sim["frames"]
    flight_s, rest_s = sim["flight_s"], sim["rest_s"]
    hold = {"broadcast": 3.0, "quick": 1.8}.get(mode, 1.5)
    total = rest_s + hold
    n = int(math.ceil(total * fps)) + 1
    frames = (frames + [frames[-1]] * max(0, n - len(frames)))[:n]
    cams = cameras(board)
    cuts = []

    def cut(kind, t0, t1):
        if t1 - t0 > 0.05:
            cuts.append({"type": kind, "t0": _r(t0), "t1": _r(t1)})
    if mode == "static":
        cut("tee", 0, total)
    else:
        # the golfer's own view for the flight, then a closer look at the board
        tee_end = max(0.5, flight_s - (0.35 if mode == "broadcast" else 0.2))
        cut("tee", 0, tee_end)
        cut("board", tee_end, rest_s + 0.6)
        cut("top", rest_s + 0.6, total)
    camera, ball = [], []
    for k in range(n):
        wall = k / fps
        idx = next((i for i, c in enumerate(cuts) if wall < c["t1"]), len(cuts) - 1)
        c = cams[cuts[idx]["type"]]
        camera.append(c["pos"] + c["look"] + [c["fov"], idx])
        q = frames[k][-1]
        ball.append([q[0], q[1], q[2], 1])   # 1: no tracer line (a bag doesn't leave one)
    tracks = []
    for i, b in enumerate(sim["bags"]):
        poses = [f[i] for f in frames]
        entry = {"side": b.side, "player": b.player, "color": side_colors[b.side], "state": b.state}
        if all(p == poses[0] for p in poses):
            entry["pose"] = poses[0]
        else:
            entry["frames"] = poses
        tracks.append(entry)
    rest_ms = int(round(rest_s * 1000))
    total_ms = int(round(total * 1000))
    who = {"player": player["name"], "color": player.get("color")}
    f = shot["flight"]
    if mode == "broadcast":
        captions = [
            dict(who, kind="lower", at_ms=600, until_ms=rest_ms, reveal=False, tag="ON THE TEE",
                 text="%.1f mph · %.1f° launch · %.0f yds carry" % (shot["speed_mph"], shot["vla_deg"],
                                                                   f["carry_yd"])),
            dict(who, kind="lower", at_ms=rest_ms, until_ms=total_ms - 250, reveal=True,
                 tag="IN THE HOLE" if sim["thrown"].state == "hole" else "RESULT",
                 text=result["what"] + (" · " + result["detail"] if result.get("detail") else "")),
        ]
    else:
        captions = [dict(who, kind="banner", at_ms=rest_ms, until_ms=rest_ms + 3500, reveal=True,
                         text=result["what"], detail=result.get("detail") or "")]
    return {
        "version": 1,
        "units": "yards; x downrange, y right, z up",
        "fps": fps,
        "mode": mode,
        "drama": drama or {"broadcast": mode == "broadcast"},
        "total_ms": total_ms,
        "rest_ms": rest_ms,
        "land_ms": int(round(flight_s * 1000)),
        "flight_s": _r(flight_s),
        "in_cup": False,
        "end": frames[-1][-1][:3],
        "cuts": cuts,
        "tracer": [],
        "ball": ball,
        "camera": camera,
        "captions": captions,
        "cornhole": {"board": board.info(), "bags": tracks, "thrown": len(tracks) - 1,
                     "aspect": round(SCREEN_W_FT / SCREEN_H_FT, 4)},
    }
