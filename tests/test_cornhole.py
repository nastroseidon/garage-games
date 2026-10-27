"""Golf Cornhole: the scaled board, where bags end up, and official scoring."""

import json
import os
import random
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cornhole as C  # noqa: E402
import games  # noqa: E402
from flight import simulate  # noqa: E402
from session import GameSession  # noqa: E402

_ids = iter(range(1, 10 ** 6))
PLAYERS = [{"name": "Dad", "color": "#ffd23f"}, {"name": "Sam", "color": "#ff6b6b"}]


def shot(d, l=0.0, roll=0.0, roll_l=0.0):
    """A ball that carries d yds, l yds right, then rolls `roll` yds downrange."""
    pts = [[round(d * u, 2), round(l * u, 2), round(250 * u * (1 - u), 2)] for u in (i / 30 for i in range(31))]
    return {"id": next(_ids), "speed_mph": 80.0, "vla_deg": 28.0, "hla_deg": 0.0, "spin_rpm": 7000.0,
            "spin_axis_deg": 0.0,
            "flight": {"carry_yd": d, "offline_yd": l, "apex_ft": 60.0, "flight_time_s": 3.0, "points": pts,
                       "roll_yd": roll, "total_yd": d + roll, "rest": [d + roll, l + roll_l]}}


def new_game(distance=100, to=21, players=PLAYERS):
    s = GameSession(rng=random.Random(4))
    s.start("cornhole", players, options={"distance": distance, "to": to})
    return s


def throw_on(board, bags, sh, side=0):
    return C.throw(board, bags, sh, side, side, seed=sh["id"])


class BoardTests(unittest.TestCase):
    def test_the_set_scales_with_the_hole_distance(self):
        for d, hole in ((100, 3.0), (250, 7.5), (30, 0.9)):
            i = C.Board(d).info()
            self.assertAlmostEqual(i["hole_r"], hole, places=2)
            # official proportions: 2 x 4 board, 6 in hole, 6 in bag
            self.assertAlmostEqual(i["length"] / i["hole_r"], 16, places=2)
            self.assertAlmostEqual(i["width"] / i["hole_r"], 8, places=2)
            self.assertAlmostEqual(i["bag"] / i["hole_r"], 2, places=2)
            self.assertAlmostEqual(i["hole"][0], d, delta=0.02 * d)
            # the hole's centre is 9 in from the back: 3 hole radii
            self.assertAlmostEqual(i["back"][0] - i["hole"][0], 3 * hole * C.math.cos(C.SLOPE), delta=0.01 * d)

    def test_tee_camera_matches_the_garage_screen(self):
        cam = C.idle_camera(C.Board(100))
        self.assertAlmostEqual(cam["fov"], 48.46, places=1)   # 9 ft tall screen seen from 10 ft

    def test_tee_camera_looks_down_like_a_six_foot_thrower(self):
        for d in (30, 100, 250):
            b = C.Board(d)
            cam, hole = C.idle_camera(b), b.info()["hole"]
            self.assertEqual(cam["look"], hole)
            drop = C.math.degrees(C.math.atan2(cam["pos"][2] - hole[2], hole[0] - cam["pos"][0]))
            self.assertAlmostEqual(drop, 9.66, places=1)      # 6 ft eyes, hole ~30 ft away


class LandingTests(unittest.TestCase):
    def test_landing_within_the_hole_radius_is_in(self):
        b = C.Board(100)
        r = throw_on(b, [], shot(100 + 2.0, 1.0))
        self.assertEqual(r["thrown"].state, "hole")
        self.assertEqual(r["thrown"].how, "airmail")
        r = throw_on(C.Board(250), [], shot(250 - 5.0, 4.0))     # 6.4 yds out, inside 7.5
        self.assertEqual(r["thrown"].state, "hole")

    def test_misses_are_as_bad_as_on_the_range(self):
        b = C.Board(100)
        i = b.info()
        self.assertEqual(throw_on(b, [], shot(120, 0))["thrown"].how, "long")
        self.assertEqual(throw_on(b, [], shot(100, i["width"] / 2 + 5))["thrown"].how, "wide")
        self.assertEqual(throw_on(b, [], shot(i["front"][0] - 3, 0))["thrown"].how, "short")
        r = throw_on(b, [], shot(120, 0))
        self.assertEqual(r["thrown"].points, 0)

    def test_on_the_board_scores_one_and_rolls_up_the_slope(self):
        b = C.Board(100)
        front = b.info()["front"][0]
        r = throw_on(b, [], shot(front + 6, 0, roll=2.0))
        bag = r["thrown"]
        self.assertEqual(bag.state, "board")
        self.assertEqual(bag.points, 1)
        landed_a = (b.from_range(front + 6, 0)[0] - b.x0) / b.cos
        self.assertGreater(bag.p[0], landed_a)   # slid up toward the hole

    def test_a_big_roll_slides_off_the_back(self):
        b = C.Board(100)
        r = throw_on(b, [], shot(104, 0, roll=30))
        self.assertEqual(r["thrown"].how, "off_back")
        self.assertEqual(r["thrown"].state, "ground")
        self.assertGreater(r["thrown"].p[0], b.x1)   # on the grass behind the board, not under it

    def test_a_bag_knocked_off_the_side_lands_beside_the_board(self):
        b = C.Board(100)
        r = throw_on(b, [], shot(88, 8, roll=4, roll_l=14))    # lands right of centre, rolls further right
        self.assertEqual(r["thrown"].how, "off_side")
        self.assertGreater(abs(r["thrown"].p[1]), b.W / 2)

    def test_a_bag_can_knock_another_into_the_hole(self):
        b = C.Board(100)
        # one bag resting just short of the hole...
        first = throw_on(b, [], shot(100 - 6.2, 0))
        self.assertEqual(first["thrown"].state, "board")
        # ...then a sliding bag runs into it from behind
        r = throw_on(b, first["bags"], shot(100 - 14, 0, roll=8), side=1)
        knocked = r["bags"][0]
        self.assertEqual(r["before"][0], "board")
        self.assertEqual(knocked.state, "hole", "the first bag should be pushed in")

    def test_same_shot_same_result(self):
        b = C.Board(100)
        sh = shot(97, 2, roll=3)
        a, c = throw_on(b, [], sh), throw_on(b, [], sh)
        self.assertEqual(a["frames"], c["frames"])

    def test_real_ball_flights_never_crash(self):
        rng = random.Random(2)
        b = C.Board(150)
        bags = []
        for n in range(40):
            f = simulate(rng.uniform(60, 140), rng.uniform(12, 30), rng.uniform(-6, 6), rng.uniform(2500, 9000),
                         rng.uniform(-12, 12))
            if n % 8 == 0:
                bags = []
            r = C.throw(b, bags, {"id": n, "speed_mph": 1, "vla_deg": 1, "flight": f}, n % 2, n % 2, seed=n)
            bags = r["bags"]
            self.assertTrue(all(len(fr) == len(bags) for fr in r["frames"]))
            self.assertIn(r["thrown"].state, ("board", "hole", "ground"))


class RuleTests(unittest.TestCase):
    def play(self, s, d, l=0.0, roll=0.0):
        return s.apply_shot(shot(d, l, roll))

    def test_sides_alternate_four_bags_each(self):
        s = new_game()
        order = []
        for _ in range(8):
            order.append(s.current()[0])
            self.play(s, 130)      # all misses
        self.assertEqual(order, [0, 1] * 4)
        self.assertEqual(s.game and s.cornhole["inning"], 2)

    def test_cancellation_scoring_and_who_throws_first(self):
        s = new_game()
        # inning 1: Dad (side 0) 3 in the hole (one swish = 3) + 1 on board; Sam 1 on board
        plan = [(100.5, 0), (90, -8), (88, 8), (130, 0), (130, 0), (130, 0), (130, 0), (130, 0)]
        for d, l in plan:
            self.play(s, d, l)
        st = s.cornhole
        self.assertEqual(st["innings"][0]["points"], [4, 1])
        self.assertEqual(st["scores"], [3, 0])
        # Dad scored, so Dad throws first again; even innings cancel and keep the order
        self.assertEqual(s.current()[0], 0)
        snap = s.snapshot()
        self.assertEqual(snap["scoreboard"][0]["value"], "3")
        self.assertIn("INNING 2", snap["round_info"])

    def test_first_to_the_target_at_the_end_of_an_inning_wins(self):
        s = new_game(to=11)
        while not s.is_over():
            idx = s.current()[0]
            self.play(s, 100.4 if idx == 1 else 140)      # Sam swishes, Dad misses
        st = s.cornhole
        self.assertEqual(st["winner"], 1)
        self.assertEqual(st["scores"], [0, 12])            # 12 per inning: no bust in official rules
        self.assertEqual(s.snapshot()["winner"]["text"], "Sam wins 12-0!")
        self.assertEqual(len(st["innings"]), 1)

    def test_undo_and_skip_replay_the_board(self):
        s = new_game()
        self.play(s, 92, 0)
        self.play(s, 95, 3)
        s.skip()
        before = [b.pose(s.cornhole["board"]) for b in s.cornhole["bags"]]
        self.play(s, 97, 0, roll=4)
        s.undo()
        after = [b.pose(s.cornhole["board"]) for b in s.cornhole["bags"]]
        self.assertEqual(before, after)
        self.assertEqual(s.cornhole["thrown"], 3)

    def test_two_v_two_teammates_take_turns_by_inning(self):
        four = PLAYERS + [{"name": "Mom", "color": "#4ea8ff"}, {"name": "Lu", "color": "#3ddc84"}]
        s = new_game(players=four)
        firsts = []
        for _ in range(16):
            firsts.append(s.current()[0])
            self.play(s, 140)
        self.assertEqual(firsts[:8], [0, 1] * 4)
        self.assertEqual(firsts[8:], [2, 3] * 4)
        self.assertEqual(s.snapshot()["scoreboard"][0]["name"], "Dad & Mom")

    def test_options_are_checked(self):
        s = GameSession()
        with self.assertRaisesRegex(ValueError, "Hole distance"):
            s.start("cornhole", PLAYERS, options={"distance": 333})
        with self.assertRaisesRegex(ValueError, "at least 2"):
            s.start("cornhole", PLAYERS[:1])
        s.start("cornhole", PLAYERS, options={"distance": "250"})
        self.assertEqual(s.cornhole["board"].distance_yd, 250)

    def test_events_carry_a_plan_with_every_bag(self):
        s = new_game()
        self.play(s, 92)
        ev = self.play(s, 100.2, 0.5)
        json.dumps(ev)
        plan = ev["plan"]
        self.assertEqual(len(plan["ball"]), len(plan["camera"]))
        bags = plan["cornhole"]["bags"]
        self.assertEqual(len(bags), 2)
        for b in bags:
            self.assertTrue("pose" in b or len(b["frames"]) == len(plan["ball"]))
        self.assertEqual(plan["mode"], "broadcast")       # a hole is worth the broadcast treatment
        extra = ev["state"]["extra"]
        self.assertEqual(len(extra["bags"]), 2)
        self.assertIn("board", extra)

    def test_test_shots_aim_at_the_hole(self):
        s = new_game(distance=150)
        opts = s.test_shot()
        f = simulate(opts["speed_mph"], opts["vla_deg"], 0, opts["spin_rpm"], 0)
        self.assertAlmostEqual(f["carry_yd"], 150, delta=12)


if __name__ == "__main__":
    unittest.main()
