"""The Python rules and director must give the same answers as the original
JavaScript (web/games.js, web/director.js) on hundreds of shots.

Needs Node.js; skipped when it isn't installed.
"""

import json
import math
import os
import random
import shutil
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import director  # noqa: E402
import games  # noqa: E402
from flight import simulate  # noqa: E402


def find_node():
    node = shutil.which("node")
    if node:
        return node
    default = os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), "nodejs", "node.exe")
    return default if os.path.isfile(default) else None


def run_js(cases):
    out = subprocess.run([NODE, os.path.join(HERE, "parity_harness.js")], input=json.dumps(cases),
                         capture_output=True, text=True, encoding="utf-8", check=True, timeout=120)
    return json.loads(out.stdout)


NODE = find_node()


def synthetic_flight(carry, offline, flight_t, apex_ft, rest):
    pts = []
    for i in range(41):
        u = i / 40
        pts.append([round(carry * u, 2), round(offline * u, 2), round(4 * apex_ft * u * (1 - u), 2)])
    return {"carry_yd": carry, "offline_yd": offline, "flight_time_s": flight_t, "apex_ft": apex_ft,
            "points": pts, "rest": rest, "total_yd": rest[0]}


def make_shots(rng, n):
    shots = []
    for i in range(n):
        if i % 2 == 0:
            speed = rng.uniform(25, 170)
            f = simulate(speed, rng.uniform(8, 35), rng.uniform(-6, 6), rng.uniform(1500, 9500),
                         rng.uniform(-15, 15))
        else:
            # aim at a target so plenty of shots land in, roll in, or just miss
            T = rng.choice(games.TARGETS)
            ang, r = rng.uniform(0, 2 * math.pi), T["r"] * rng.choice([0.05, 0.3, 0.6, 0.95, 1.1, 1.4])
            carry = round(T["d"] + math.cos(ang) * r - rng.choice([0, 0, 3, 8]), 1)
            off = round(T["l"] + math.sin(ang) * r, 1)
            roll = rng.choice([0, 0.2, 2, 6, 15])
            f = synthetic_flight(carry, off, round(rng.uniform(1.2, 6.5), 2), round(rng.uniform(10, 110), 1),
                                 [round(carry + roll, 2), round(off + rng.uniform(-1, 1), 2)])
            speed = rng.uniform(40, 160)
        shots.append({"id": i + 1, "speed_mph": round(speed, 1), "vla_deg": round(rng.uniform(8, 35), 1),
                      "hla_deg": round(rng.uniform(-6, 6), 1), "spin_rpm": round(rng.uniform(1500, 9500)),
                      "spin_axis_deg": 0.0, "flight": f})
    return shots


class Ctx:
    def __init__(self, d):
        self.players = d.get("players", [])
        self.history = d.get("history", [])
        self.turn = d.get("turn", 0)
        self.rounds = d.get("rounds", 0)


@unittest.skipIf(NODE is None, "Node.js is not installed")
class ParityTests(unittest.TestCase):
    maxDiff = None

    def assertSame(self, py, js, where):
        if isinstance(js, dict):
            self.assertIsInstance(py, dict, where)
            self.assertEqual(sorted(py), sorted(js), where)
            for k in js:
                self.assertSame(py[k], js[k], "%s.%s" % (where, k))
        elif isinstance(js, list):
            self.assertIsInstance(py, (list, tuple), where)
            self.assertEqual(len(py), len(js), where)
            for i, (a, b) in enumerate(zip(py, js)):
                self.assertSame(a, b, "%s[%d]" % (where, i))
        elif isinstance(js, bool) or js is None or isinstance(js, str):
            self.assertEqual(py, js, where)
        else:
            self.assertTrue(math.isclose(py, js, rel_tol=1e-9, abs_tol=1e-9), "%s: %r != %r" % (where, py, js))

    def test_scoring_matches_js(self):
        rng = random.Random(7)
        shots = make_shots(rng, 300)
        cases, expect = [], []
        for shot in shots:
            for junior in (False, True):
                player = {"name": "Maddie" if junior else "Dad", "junior": junior}
                rounds = 10
                for gid, target, ctx in (
                        ("closest", {"pin": rng.choice([25, 50, 85, 120, 150])}, {}),
                        ("darts", {"d": rng.choice([30, 60, 100, 140])}, {}),
                        ("speed", {"mph": rng.choice([30, 55, 80, 100])}, {}),
                        ("longdrive", {"junior": junior}, {}),
                        ("targetrange", {"round": rng.choice([0, 5, 9]), "junior": junior}, {"rounds": rounds}),
                        ("calledshot", {"called": rng.randrange(7), "junior": junior}, {}),
                        ("ladder", {"junior": junior}, {})):
                    cases.append({"kind": "score", "game": gid, "shot": shot, "target": target,
                                  "player": player, "ctx": ctx})
                    g = games.game_by_id(gid)
                    c = Ctx(dict({"players": [player]}, **ctx))
                    expect.append(g.score(shot, target, player, c, 0))
            cases.append({"kind": "range", "shot": shot})
            expect.append({"hit": games.range_hit(shot), "near": games.near_miss(shot),
                           "timing": games.range_timing(shot)})
        for i in range(200):
            base, player = {"seed": rng.randrange(10 ** 9)}, {"name": rng.choice(["Dad", "Maddie", "Zoë", "J"]),
                                                              "junior": rng.random() < 0.3}
            cases.append({"kind": "called", "base": base, "player": player})
            expect.append(games.game_by_id("calledshot").player_target(base, player))
        got = run_js(cases)
        for i, (py, js) in enumerate(zip(expect, got)):
            self.assertSame(py, js, "case %d (%s %s)" % (i, cases[i]["kind"], cases[i].get("game", "")))

    def test_drama_matches_js(self):
        rng = random.Random(11)
        cases, expect = [], []
        for _ in range(600):
            n = rng.choice([1, 2, 2, 3, 4])
            players = [{"name": "P%d" % i} for i in range(n)]
            s = rng.randrange(n)
            before = [rng.randrange(0, 30) for _ in range(n)]
            pts = rng.choice([0, 0, 2, 4, 8, 16])
            after = list(before)
            after[s] += pts
            ladder = None
            if rng.random() < 0.25:
                ladder = {"need": [rng.choice([3, 5]) for _ in range(n)]}
                before = [rng.randrange(0, 5) for _ in range(n)]
                after = list(before)
                after[s] += rng.choice([0, 1])
            hit_t = rng.choice([-1, -1, 0, 3, 6])
            inp = {"players": players, "shooter": s, "before": before, "after": after,
                   "shotsLeft": rng.randrange(1, 11), "totalShots": 10, "finalBall": rng.random() < 0.2,
                   "pressureGap": rng.choice([10, 14]), "ladder": ladder, "gameOverAfter": rng.random() < 0.2,
                   "hit": {"target": hit_t, "zone": rng.choice(["center", "inner", "outer"]) if hit_t >= 0 else None,
                           "rolledIn": rng.random() < 0.3},
                   "nearMissYd": rng.choice([None, 0.4, 1.5, 2.0, 9.0]), "chance": rng.random()}
            cases.append({"kind": "assess", "input": inp})
            expect.append(director.assess(inp))
        got = run_js(cases)
        for i, (py, js) in enumerate(zip(expect, got)):
            self.assertSame(py, js, "assess case %d" % i)

    def test_plans_match_js(self):
        rng = random.Random(5)
        cases, expect = [], []
        for shot in make_shots(rng, 160):
            hit = games.range_hit(shot)
            result = {"stop": hit["stop"]}
            for style in ("auto", "broadcast", "quick", "static"):
                drama = {"broadcast": rng.random() < 0.5, "slowmo": rng.random() < 0.5,
                         "celebrate": rng.random() < 0.2}
                p = director.plan(shot, result, {"style": style, "drama": drama, "hit": hit,
                                                 "targets": games.TARGETS})
                walls = [p.total_ms / 1000 * k / 40 for k in range(41)] + [p.rest_ms / 1000, p.land_ms / 1000]
                samples = []
                for w in walls:
                    b = p.ball(w)
                    i = p.shot_index_at(w)
                    cam = p.camera(i, w, b["pos"])
                    samples.append({"pos": b["pos"], "phase": b["phase"], "visible": b["visible"],
                                    "tracer": p.tracer_progress(w), "index": i,
                                    "cam": {"pos": cam["pos"], "look": cam["look"], "fov": cam["fov"],
                                            "follow": cam.get("follow") or 0,
                                            "lookFollow": cam.get("lookFollow") or 0}})
                cases.append({"kind": "plan", "shot": shot, "result": result, "style": style, "drama": drama,
                              "hit": hit, "walls": walls})
                expect.append({"mode": p.mode, "totalMs": p.total_ms, "restMs": p.rest_ms, "landMs": p.land_ms,
                               "inCup": p.in_cup, "shots": p.shots, "samples": samples})
        got = run_js(cases)
        for i, (py, js) in enumerate(zip(expect, got)):
            self.assertSame(py, js, "plan case %d (%s)" % (i, cases[i]["style"]))


if __name__ == "__main__":
    unittest.main()
