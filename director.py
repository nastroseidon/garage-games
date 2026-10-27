"""Camera director for the 3D Target Range.

A Python port of web/director.js. When a shot arrives we already know its
whole flight, where it stops and how it changes the scores. The director
uses that to:
  1. decide whether the shot deserves "broadcast" coverage (assess), and
  2. plan the whole sequence: ball path with bounces, slow motion, and
     camera cuts (plan).
  3. turn the plan into a "shot plan" message any renderer can play back
     (to_message): the ball and camera sampled at a fixed frame rate, the
     camera cuts, and the captions with their timings.

Positions are [downrange, right, height] in yards. Times: "sim" seconds are
ball time; "wall" seconds are what the viewer sees (slow motion stretches
wall time).
"""

import math

from games import js_round, num, to_fixed

GRAVITY = 10.73  # yd/s^2
RANDOM_BROADCAST = 0.08  # the odd routine shot gets the full treatment, so a cut never gives the result away
NEAR_MISS_YD = 1.5
MESSAGE_VERSION = 1


# ---------------- drama ----------------

def leader_of(totals):
    best, who = -math.inf, None
    for i, v in enumerate(totals):
        if v > best:
            best, who = v, i
        elif v == best:
            who = None
    return who  # None when tied at the top


def assess(inp):
    """inp: {players:[{name}], shooter, before:[totals], after:[totals],
    shotsLeft, totalShots, finalBall, pressureGap, ladder:{need:[]}|None,
    gameOverAfter, hit:{target, zone, rolledIn}, nearMissYd, chance}"""
    p, s = inp["players"], inp["shooter"]
    multi = len(p) > 1
    out = {"pressure": False, "preTag": "", "preText": "", "headline": "", "reasons": []}
    before_t = inp["before"]

    if multi and inp.get("ladder"):
        need = inp["ladder"]["need"]

        def left(i):
            return need[i] - before_t[i]

        if left(s) == 1:
            out.update(pressure=True, preTag="FOR THE WIN", preText="One hit from the top of the ladder")
        else:
            for i in range(len(p)):
                if i != s and left(i) == 1:
                    out.update(pressure=True, preTag="MUST KEEP PACE",
                               preText=p[i]["name"] + " is one rung from winning")
                    break
    elif multi and inp["shotsLeft"] <= 2:
        best_other, other_name = -math.inf, ""
        for j in range(len(p)):
            if j != s and before_t[j] > best_other:
                best_other, other_name = before_t[j], p[j]["name"]
        gap = before_t[s] - best_other
        limit = inp["pressureGap"] * (2 if inp["finalBall"] else 1)
        if abs(gap) <= limit:
            balls = "final ball" if inp["shotsLeft"] == 1 else "2 balls left"
            out["pressure"] = True
            out["preTag"] = "FINAL BALL" if inp["shotsLeft"] == 1 else "PRESSURE SHOT"
            out["preText"] = (num(-gap) + " behind " + other_name + " · " + balls if gap < 0
                              else "Leads by " + num(gap) + " · " + balls if gap > 0
                              else "All square · " + balls)
    if out["pressure"]:
        out["reasons"].append("pressure")

    hit = inp.get("hit") or {"target": -1}
    before, after = leader_of(before_t), leader_of(inp["after"])
    winning = multi and inp["gameOverAfter"] and after == s
    # a real overtake (not breaking an early tie) in the back half of the game
    back_half = inp["shotsLeft"] <= math.ceil((inp.get("totalShots") or inp["shotsLeft"]) / 2)
    lead_change = multi and not winning and back_half and after == s and before is not None and before != s
    flag_zone = hit["target"] >= 0 and hit.get("zone") == "center"
    inner = hit["target"] >= 0 and hit.get("zone") == "inner"
    nm = inp.get("nearMissYd")
    near_miss = hit["target"] < 0 and nm is not None and nm <= NEAR_MISS_YD
    rolled_in = hit["target"] >= 0 and bool(hit.get("rolledIn"))
    lucky = inp.get("chance") is not None and inp["chance"] < RANDOM_BROADCAST

    for flag, reason in ((winning, "winning"), (lead_change, "lead-change"), (flag_zone, "flag-zone"),
                         (inner, "inner-ring"), (near_miss, "near-miss")):
        if flag:
            out["reasons"].append(reason)
    if lucky and not out["reasons"]:
        out["reasons"].append("random")

    out["broadcast"] = len(out["reasons"]) > 0
    out["slowmo"] = bool(winning or lead_change or flag_zone or inner or near_miss)
    out["headline"] = ("WINS IT!" if winning else "TAKES THE LEAD!" if lead_change else
                       "FLAG ZONE!" if flag_zone else "SO CLOSE!" if near_miss else
                       "ROLLED IN!" if rolled_in else "")
    out["celebrate"] = bool(winning)
    return out


def broadcast_chance(shot_id):
    """A repeatable 0..1 number per shot (the JS used the same formula)."""
    return ((shot_id or 1) * 2654435761 & 0xFFFFFFFF) / 4294967296


# ---------------- ball path ----------------

def lerp(a, b, t):
    return [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t]


def dist2(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def ease_out(t):
    return 1 - (1 - t) * (1 - t)


def ease_in_out(t):
    return 2 * t * t if t < 0.5 else 1 - (-2 * t + 2) ** 2 / 2


def clamp(v, a, b):
    return max(a, min(b, v))


class Path:
    """The ball's flight (from flight.py samples) plus bounces, roll and the cup."""

    def __init__(self, shot, stop, cup):
        f = shot["flight"]
        pts = [[q[0], q[1], q[2] / 3] for q in f["points"]]
        self.flight_t = max(0.3, f["flight_time_s"])
        land = [f["carry_yd"], f["offline_yd"], 0]
        if len(pts) < 2:
            pts = [[0, 0, 0], land]
        pts[-1] = land
        n = len(pts)
        dt = self.flight_t / (n - 1)
        a, b = pts[n - 2], pts[n - 1]
        vv = max(0, (a[2] - b[2]) / dt)
        self.pts, self.n, self.land = pts, n, land
        self.segs = []  # (t0, t1, kind, at(u))
        self._t = self.flight_t
        self._from = land
        end = [stop[0], stop[1], 0]

        h1 = clamp(0.25 * vv * vv / (2 * GRAVITY), 0.04, 4)
        length = dist2(land, end)
        if length > 1.5:
            self._hop(lerp(land, end, 0.35), h1)
            self._hop(lerp(land, end, 0.5), h1 * 0.25)
            self._roll(end, clamp(0.4 + length * 0.5 * 0.08, 0.4, 2.5), ease_out)
        else:
            self._hop(end, h1 * 0.5)
        if cup:
            c = [cup[0], cup[1], 0]
            self._roll(c, clamp(0.5 + dist2(end, c) * 0.06, 0.5, 1.6), ease_in_out, "funnel")
            t0 = self._t
            self.segs.append((t0, t0 + 0.3, "sink", lambda u, c=c: [c[0], c[1], -0.15 * u]))
            self._t += 0.3
        self.rest_t = self._t
        self.end = [cup[0], cup[1], 0] if cup else end
        self.in_cup = bool(cup)

    def _hop(self, to, height):
        dur = 2 * math.sqrt(2 * height / GRAVITY)
        p0 = self._from

        def at(u):
            p = lerp(p0, to, u)
            p[2] = 4 * height * u * (1 - u)
            return p
        self.segs.append((self._t, self._t + dur, "bounce", at))
        self._t += dur
        self._from = to

    def _roll(self, to, dur, ease, kind="roll"):
        p0 = self._from
        self.segs.append((self._t, self._t + dur, kind, lambda u: lerp(p0, to, ease(u))))
        self._t += dur
        self._from = to

    def at(self, sim):
        if sim <= 0:
            return {"pos": self.pts[0], "phase": "flight", "visible": True}
        if sim < self.flight_t:
            x = sim / self.flight_t * (self.n - 1)
            i = int(math.floor(x))
            return {"pos": lerp(self.pts[i], self.pts[min(i + 1, self.n - 1)], x - i),
                    "phase": "flight", "visible": True}
        for t0, t1, kind, fn in self.segs:
            if sim < t1:
                return {"pos": fn((sim - t0) / (t1 - t0)), "phase": kind, "visible": True}
        last = self.segs[-1][3](1) if self.segs else self.land
        return {"pos": last, "phase": "cup" if self.in_cup else "rest", "visible": not self.in_cup}


# ---------------- timeline (slow motion) ----------------

class Timeline:
    """keys: [[wall, sim], ...], strictly increasing in both."""

    def __init__(self, keys):
        self.keys = keys

    def _interp(self, x, frm, to):
        arr = self.keys
        if x <= arr[0][frm]:
            return arr[0][to] + (x - arr[0][frm])
        for i in range(1, len(arr)):
            if x <= arr[i][frm]:
                a, b = arr[i - 1], arr[i]
                return a[to] + (x - a[frm]) / (b[frm] - a[frm]) * (b[to] - a[to])
        l2, l1 = arr[-1], arr[-2]
        return l2[to] + (x - l2[frm]) * (l2[to] - l1[to]) / (l2[frm] - l1[frm])

    def sim_at(self, wall):
        return self._interp(wall, 0, 1)

    def wall_at(self, sim):
        return self._interp(sim, 1, 0)


# ---------------- cameras ----------------
# Each returns {pos, look, fov, follow, lookFollow}. follow / lookFollow are
# smoothing rates (per second); 0 means the camera sticks to its target.

def cam_range(c=None, ball=None, sim=0, t=0):
    """Overview from behind and above the bay (also the idle camera)."""
    return {"pos": [-26, 0, 30], "look": [95, 0, -8], "fov": 38, "follow": 0}


def cam_bay(c, ball, sim, t):
    """Low, behind the hitter, looking out along the start line."""
    return {"pos": [-3.6, -1.1, 1.9], "look": [30, 30 * math.tan(c["hla"]), 6], "fov": 52, "follow": 0}


def cam_chase(c, ball, sim, t):
    """Trails the ball."""
    u = c["u"]
    return {"pos": [ball[0] - 14 * u[0], ball[1] - 14 * u[1], ball[2] + 4.5],
            "look": [ball[0] + 20 * u[0], ball[1] + 20 * u[1], max(0, ball[2] - 3)], "fov": 50, "follow": 3}


def cam_tower(c, ball, sim, t):
    """Tower behind and off to the side, long lens following the ball against the sky."""
    return {"pos": [-20, c["side"] * 35, 9], "look": ball, "fov": 28, "follow": 0, "lookFollow": 5}


def cam_target(c, ball, sim, t):
    """Low camera beyond the target, looking back as the ball drops in."""
    a, u, v, side = c["anchor"], c["u"], c["v"], c["side"]
    look = lerp(a, ball, 0.45) if sim < c["flightT"] else ball
    back, off = c["radius"] + 12, 6 + c["radius"] * 0.3
    return {"pos": [a[0] + back * u[0] + off * side * v[0], a[1] + back * u[1] + off * side * v[1],
                    4 + c["radius"] * 0.15],
            "look": [look[0], look[1], max(0.2, look[2])], "fov": 34, "follow": 0, "lookFollow": 4}


def cam_orbit(c, ball, sim, t):
    """Slow orbit around where the ball finished."""
    ang = c["orbitStart"] + 0.32 * t
    a = c["anchor"]
    rad = c["radius"] + 5
    return {"pos": [a[0] + math.cos(ang) * rad, a[1] + math.sin(ang) * rad, 4.5],
            "look": [a[0], a[1], 1.6], "fov": 40, "follow": 0}


def cam_land(c, ball, sim, t):
    """Behind and above the landing area, watching it come down."""
    a, u = c["anchor"], c["u"]
    return {"pos": [a[0] - 30 * u[0], a[1] - 30 * u[1], 13], "look": ball, "fov": 40, "follow": 0, "lookFollow": 4}


CAMERAS = {"range": cam_range, "bay": cam_bay, "chase": cam_chase, "tower": cam_tower,
           "target": cam_target, "orbit": cam_orbit, "land": cam_land}


def idle_camera():
    return cam_range()


# ---------------- plan ----------------

class Plan:
    def __init__(self, mode, drama, path, tl, total, rest_wall, land_wall, shots, c):
        self.mode, self.drama, self.path, self.tl = mode, drama, path, tl
        self.total_ms = js_round(total * 1000)
        self.rest_ms = js_round(rest_wall * 1000)
        self.land_ms = js_round(land_wall * 1000)
        self.flight_t = path.flight_t
        self.in_cup = path.in_cup
        self.shots = shots
        self._c = c

    def sim_at(self, wall):
        return self.tl.sim_at(wall)

    def ball(self, wall):
        return self.path.at(self.tl.sim_at(wall))

    def tracer_progress(self, wall):
        return clamp(self.tl.sim_at(wall) / self.path.flight_t, 0, 1)

    def shot_index_at(self, wall):
        for i, sh in enumerate(self.shots):
            if wall < sh["t1"]:
                return i
        return len(self.shots) - 1

    def camera(self, index, wall, ball_pos):
        sh = self.shots[index]
        return CAMERAS[sh["type"]](self._c, ball_pos, self.tl.sim_at(wall), wall - sh["t0"])


def plan(shot, result, opts):
    """opts: {style: auto|broadcast|quick|static, drama, hit:{target}, targets}"""
    style = opts.get("style") or "auto"
    drama = opts.get("drama") or {"broadcast": False}
    if style == "static":
        mode = "static"
    elif style == "quick":
        mode = "quick"
    elif style == "broadcast" or drama.get("broadcast"):
        mode = "broadcast"
    else:
        mode = "quick"

    hit = opts.get("hit") or {"target": -1}
    targets = opts.get("targets")
    cup_t = targets[hit["target"]] if hit["target"] >= 0 and targets else None
    stop = result.get("stop") or shot["flight"]["rest"]
    path = Path(shot, stop, [cup_t["d"], cup_t["l"]] if cup_t else None)

    # wall <-> sim mapping
    rate = 1 if mode == "broadcast" else 1.25
    keys = [[0, 0]]
    if mode == "broadcast" and drama.get("slowmo") and path.flight_t > 1:
        s0, s1, slow = path.flight_t - 0.5, min(path.rest_t, path.flight_t + 0.9), 0.45
        keys.append([s0, s0])
        keys.append([s0 + (s1 - s0) / slow, s1])
        keys.append([s0 + (s1 - s0) / slow + (path.rest_t + 1 - s1), path.rest_t + 1])
    else:
        keys.append([(path.rest_t + 1) / rate, path.rest_t + 1])
    tl = Timeline(keys)
    rest_wall = tl.wall_at(path.rest_t)
    hold = (3.8 if drama.get("celebrate") else 2.8) if mode == "broadcast" else 1.6 if mode == "quick" else 1.4
    total = rest_wall + hold

    # geometry the cameras use. On a miss the cameras frame the ball together
    # with the nearest target, so you can see how close it was.
    end = path.end
    anchor, radius = end, cup_t["r"] if cup_t else 2
    if not cup_t and targets:
        near, nd = None, math.inf
        for T in targets:
            dd = math.hypot(T["d"] - end[0], T["l"] - end[1]) - T["r"]
            if dd < nd:
                nd, near = dd, T
        if near and nd < 25:
            anchor = [(end[0] + near["d"]) / 2, (end[1] + near["l"]) / 2, 0]
            radius = math.hypot(near["d"] - end[0], near["l"] - end[1]) / 2 + near["r"] * 0.5
    length = math.hypot(end[0], end[1]) or 1
    u = [end[0] / length, end[1] / length] if length > 1 else [1, 0]
    c = {"u": u, "v": [-u[1], u[0]], "end": end, "anchor": anchor, "flightT": path.flight_t,
         "side": -1 if end[1] >= 0 else 1, "hla": math.radians(shot.get("hla_deg") or 0),
         "radius": radius}
    # the orbit starts where the target camera was, so the cut feels continuous
    back, off = radius + 12, 6 + radius * 0.3
    c["orbitStart"] = math.atan2(c["side"] * c["v"][1] * off + u[1] * back,
                                 c["side"] * c["v"][0] * off + u[0] * back)
    short = end[0] < 45 or path.flight_t < 1.8

    shots = []

    def add(kind, t0, t1):
        if t1 - t0 > 0.05:
            shots.append({"type": kind, "t0": t0, "t1": t1})
    land_wall = tl.wall_at(path.flight_t)
    if mode == "static":
        add("range", 0, total)
    elif mode == "quick":
        if short:
            add("bay", 0, 0.5)
            add("land", 0.5, total)
        else:
            chase_end = tl.wall_at(path.flight_t * 0.75)
            add("bay", 0, 0.5)
            add("chase", 0.5, chase_end)
            add("land", chase_end, total)
    else:
        target_from = 0.7 if short else max(0.9 + 0.8, tl.wall_at(path.flight_t * 0.55))
        add("bay", 0, 0.7 if short else 0.9)
        if not short:
            add("tower", 0.9, target_from)
        add("target", 0.7 if short else target_from, rest_wall + 0.4)
        add("orbit", rest_wall + 0.4, total)

    return Plan(mode, drama, path, tl, total, rest_wall, land_wall, shots, c)


# ---------------- the shot plan message ----------------

def _r(v):
    return round(v, 3)


def captions(p, shot, result, player):
    """What to put on screen and when. Results only appear once the ball stops."""
    f = shot["flight"]
    who = {"player": player["name"], "color": player.get("color")}
    if p.mode != "broadcast":
        return [dict(who, kind="banner", at_ms=p.rest_ms, until_ms=p.rest_ms + 3500, reveal=True,
                     text=result["what"], detail=result.get("detail") or "")]
    d = p.drama
    pre = d.get("preText") or "%s mph · %s° launch · %d rpm" % (
        to_fixed(shot["speed_mph"]), to_fixed(shot["vla_deg"]), js_round(shot["spin_rpm"]))
    end_ms = p.total_ms - 250
    tag = d.get("headline") or ("ON TARGET" if result.get("great") else "RESULT")
    return [
        dict(who, kind="lower", at_ms=800, until_ms=p.rest_ms, reveal=False,
             tag=d.get("preTag") or "ON THE TEE", text=pre),
        dict(who, kind="lower", at_ms=p.rest_ms, until_ms=end_ms, reveal=True, tag=tag,
             text=result["what"] + (" · " + result["detail"] if result.get("detail") else "")),
        dict(who, kind="data", at_ms=p.rest_ms, until_ms=end_ms, reveal=True,
             items=[["BALL SPEED", to_fixed(shot["speed_mph"])], ["CARRY", to_fixed(f["carry_yd"])],
                    ["TOTAL", to_fixed(f.get("total_yd") or f["carry_yd"])],
                    ["APEX FT", str(js_round(f.get("apex_ft", 0)))]]),
    ]


def to_message(p, shot, result, player, fps=60):
    """Sample a plan into a renderer-neutral message.

    ball[i] and camera[i] are the state at wall time i / fps seconds.
      ball:   [x, y, z, tracer]  - tracer is how much of the flight line to draw (0..1)
      camera: [px, py, pz, lx, ly, lz, fov, cut] - cut indexes `cuts`; when it
              changes between two frames, jump (don't blend).
    Camera smoothing is already applied, so a renderer only interpolates.
    Units are yards: x downrange, y to the right, z up.
    """
    dt = 1.0 / fps
    frames = int(math.ceil(p.total_ms / 1000.0 * fps)) + 1
    ball, camera = [], []
    pos = look = None
    last_cut = None
    for i in range(frames):
        wall = i * dt
        b = p.ball(wall)
        ball.append([_r(b["pos"][0]), _r(b["pos"][1]), _r(b["pos"][2]), _r(p.tracer_progress(wall))])
        idx = p.shot_index_at(wall)
        cam = p.camera(idx, wall, b["pos"])
        cut = idx != last_cut
        last_cut = idx
        if cut or not cam.get("follow"):
            pos = list(cam["pos"])
        else:
            k = 1 - math.exp(-cam["follow"] * dt)
            pos = [pos[j] + (cam["pos"][j] - pos[j]) * k for j in range(3)]
        if cut or not cam.get("lookFollow"):
            look = list(cam["look"])
        else:
            k = 1 - math.exp(-cam["lookFollow"] * dt)
            look = [look[j] + (cam["look"][j] - look[j]) * k for j in range(3)]
        camera.append([_r(pos[0]), _r(pos[1]), _r(pos[2]), _r(look[0]), _r(look[1]), _r(look[2]),
                       cam["fov"], idx])
    pts = shot["flight"]["points"]
    return {
        "version": MESSAGE_VERSION,
        "units": "yards; x downrange, y right, z up",
        "fps": fps,
        "mode": p.mode,
        "drama": p.drama,
        "total_ms": p.total_ms,
        "rest_ms": p.rest_ms,
        "land_ms": p.land_ms,
        "flight_s": p.flight_t,
        "in_cup": p.in_cup,
        "end": [_r(v) for v in p.path.end],
        "cuts": [{"type": s["type"], "t0": _r(s["t0"]), "t1": _r(s["t1"])} for s in p.shots],
        "tracer": [[q[0], q[1], _r(q[2] / 3)] for q in pts[:-1]] +
                  [[shot["flight"]["carry_yd"], shot["flight"]["offline_yd"], 0]],
        "ball": ball,
        "camera": camera,
        "captions": captions(p, shot, result, player),
    }
