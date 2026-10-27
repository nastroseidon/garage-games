"""Camera director (Python port of tests/test_director.js, same cases) and
the shot plan message every renderer plays back."""

import json
import math
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import director as D  # noqa: E402
from games import TARGETS  # noqa: E402

PLAYERS = [{"name": "Dad"}, {"name": "Maddie"}]


def drama(**over):
    inp = {"players": PLAYERS, "shooter": 1, "before": [20, 10], "after": [20, 10], "shotsLeft": 5,
           "totalShots": 10, "finalBall": False, "pressureGap": 10, "ladder": None, "gameOverAfter": False,
           "hit": {"target": -1}, "nearMissYd": None, "chance": 0.9}
    inp.update(over)
    return D.assess(inp)


def flight_shot(carry, offline, flight_t, apex_ft, rest=None):
    """A believable 92 mph wedge, sampled like flight.py output."""
    pts = [[carry * u, offline * u, 4 * apex_ft * u * (1 - u)] for u in (i / 40 for i in range(41))]
    return {"speed_mph": 92, "vla_deg": 31.0, "spin_rpm": 8100, "hla_deg": 4,
            "flight": {"carry_yd": carry, "offline_yd": offline, "flight_time_s": flight_t, "apex_ft": apex_ft,
                       "total_yd": (rest or [carry + 4])[0], "points": pts, "rest": rest or [carry + 4, offline]}}


BLUE = TARGETS[3]
SHOT = flight_shot(BLUE["d"] - 2, BLUE["l"], 5, 80, [BLUE["d"] + 2, BLUE["l"]])
RESULT = {"stop": [BLUE["d"] - 2, BLUE["l"]], "what": "BLUE  +12", "detail": "Flag zone x3", "great": True}
HIT = {"target": 3}


def frange(start, stop, step):
    v = start
    while v < stop:
        yield v
        v += step


class DramaTests(unittest.TestCase):
    def test_routine_shot_early_in_the_game_stays_quick(self):
        self.assertFalse(drama()["broadcast"])

    def test_close_score_near_the_end_is_a_pressure_shot(self):
        d = drama(before=[20, 14], after=[20, 14], shotsLeft=1, finalBall=True)
        self.assertTrue(d["broadcast"] and d["pressure"])
        self.assertEqual(d["preTag"], "FINAL BALL")
        self.assertIn("6 behind Dad", d["preText"])
        far = drama(before=[60, 10], after=[60, 10], shotsLeft=1, finalBall=True)
        self.assertFalse(far["pressure"], "a blowout is not pressure")

    def test_lead_change_and_winning_shot(self):
        lc = drama(before=[20, 15], after=[20, 27], shotsLeft=3, hit={"target": 3, "zone": "inner"})
        self.assertEqual(lc["headline"], "TAKES THE LEAD!")
        self.assertTrue(lc["slowmo"])
        win = drama(before=[20, 15], after=[20, 27], gameOverAfter=True, hit={"target": 3, "zone": "outer"})
        self.assertEqual(win["headline"], "WINS IT!")
        self.assertTrue(win["celebrate"])

    def test_near_miss_and_flag_zone_broadcast_a_plain_roll_in_does_not(self):
        self.assertEqual(drama(nearMissYd=1)["headline"], "SO CLOSE!")
        self.assertFalse(drama(nearMissYd=3)["broadcast"])
        self.assertEqual(drama(hit={"target": 2, "zone": "center"})["headline"], "FLAG ZONE!")
        rolled = drama(hit={"target": 2, "zone": "outer", "rolledIn": True})
        self.assertFalse(rolled["broadcast"])
        self.assertEqual(rolled["headline"], "ROLLED IN!")

    def test_lead_changes_only_count_as_a_real_overtake_late_in_the_game(self):
        self.assertFalse(drama(before=[0, 0], after=[0, 8], shotsLeft=3)["broadcast"],
                         "breaking a tie is not an overtake")
        self.assertFalse(drama(before=[12, 10], after=[12, 18], shotsLeft=9)["broadcast"], "too early to matter")
        self.assertIn("lead-change", drama(before=[12, 10], after=[12, 18], shotsLeft=4)["reasons"])

    def test_ladder_pressure(self):
        ladder = {"need": [5, 3]}
        self.assertEqual(drama(before=[1, 2], after=[1, 2], ladder=ladder)["preTag"], "FOR THE WIN")
        self.assertEqual(drama(shooter=1, before=[4, 0], after=[4, 0], ladder=ladder)["preTag"], "MUST KEEP PACE")

    def test_solo_play_only_broadcasts_close_calls(self):
        def solo(**o):
            return drama(**dict({"players": [{"name": "Dad"}], "shooter": 0, "before": [5], "after": [5]}, **o))
        self.assertFalse(solo(shotsLeft=1)["broadcast"])
        self.assertTrue(solo(nearMissYd=1)["broadcast"])
        self.assertTrue(solo(chance=0.05)["broadcast"])
        self.assertFalse(solo(chance=0.1)["broadcast"])

    def test_broadcast_chance_matches_the_js_formula(self):
        # (Math.imul(id, 2654435761) >>> 0) / 4294967296
        self.assertAlmostEqual(D.broadcast_chance(1), 2654435761 / 4294967296)
        self.assertAlmostEqual(D.broadcast_chance(2), (2 * 2654435761 % 2 ** 32) / 4294967296)
        self.assertEqual(D.broadcast_chance(None), D.broadcast_chance(1))


class PlanTests(unittest.TestCase):
    def test_broadcast_plan_tee_tower_target_orbit_slow_motion_stretches_time(self):
        big = drama(hit={"target": 3, "zone": "center"})
        p = D.plan(SHOT, RESULT, {"style": "auto", "drama": big, "hit": HIT, "targets": TARGETS})
        self.assertEqual(p.mode, "broadcast")
        self.assertEqual([s["type"] for s in p.shots], ["bay", "tower", "target", "orbit"])
        quick = D.plan(SHOT, RESULT, {"style": "quick", "drama": big, "hit": HIT, "targets": TARGETS})
        self.assertEqual([s["type"] for s in quick.shots], ["bay", "chase", "land"])
        self.assertGreater(p.total_ms, quick.total_ms + 2000, "broadcast takes its time")
        self.assertGreater(p.land_ms, 5000, "slow motion around landing")
        self.assertLess(p.total_ms, 12500, "but a broadcast still moves along (%d ms)" % p.total_ms)
        for w in frange(0, p.total_ms / 1000, 0.05):
            self.assertGreater(p.sim_at(w + 0.05), p.sim_at(w))
        for a, b in zip(p.shots, p.shots[1:]):
            self.assertEqual(b["t0"], a["t1"])

    def test_ball_path_is_continuous_and_finishes_in_the_cup(self):
        p = D.plan(SHOT, RESULT, {"style": "broadcast", "drama": drama(), "hit": HIT, "targets": TARGETS})
        prev = p.ball(0)["pos"]
        for w in frange(0.01, p.total_ms / 1000, 0.01):
            pos = p.ball(w)["pos"]
            jump = math.dist(pos, prev)
            self.assertLess(jump, 2, "no teleporting at %.2fs (%.2f yd)" % (w, jump))
            prev = pos
        end = p.ball(p.total_ms / 1000)
        self.assertEqual(end["phase"], "cup")
        self.assertFalse(end["visible"])
        self.assertLess(abs(end["pos"][0] - BLUE["d"]), 0.01)
        self.assertLess(abs(end["pos"][1] - BLUE["l"]), 0.01)

    def test_a_miss_rolls_out_and_stays_visible_static_style_never_moves_the_camera(self):
        miss = flight_shot(100, -30, 4.5, 70, [108, -31])
        p = D.plan(miss, {"stop": [108, -31]}, {"style": "static", "drama": drama(), "hit": {"target": -1},
                                               "targets": TARGETS})
        self.assertEqual([s["type"] for s in p.shots], ["range"])
        end = p.ball(p.total_ms / 1000)
        self.assertEqual(end["phase"], "rest")
        self.assertTrue(end["visible"])
        self.assertLess(abs(end["pos"][0] - 108), 0.01)

    def test_every_camera_returns_a_finite_position_target_and_lens(self):
        p = D.plan(SHOT, RESULT, {"style": "broadcast", "drama": drama(hit={"target": 3, "zone": "center"}),
                                  "hit": HIT, "targets": TARGETS})
        for w in frange(0, p.total_ms / 1000, 0.1):
            cam = p.camera(p.shot_index_at(w), w, p.ball(w)["pos"])
            for v in cam["pos"] + cam["look"] + [cam["fov"]]:
                self.assertTrue(math.isfinite(v))


class MessageTests(unittest.TestCase):
    """The shot plan message: what the browser and Unreal both play back."""

    def make(self, style="broadcast", fps=60, **drama_over):
        d = drama(**dict({"hit": {"target": 3, "zone": "center"}}, **drama_over))
        p = D.plan(SHOT, RESULT, {"style": style, "drama": d, "hit": HIT, "targets": TARGETS})
        return p, D.to_message(p, SHOT, RESULT, {"name": "Maddie", "color": "#ff6b6b"}, fps=fps)

    def test_frames_cover_the_whole_shot_at_the_frame_rate(self):
        p, m = self.make()
        self.assertEqual(m["fps"], 60)
        self.assertEqual(len(m["ball"]), len(m["camera"]))
        self.assertGreaterEqual((len(m["ball"]) - 1) / 60, p.total_ms / 1000)
        self.assertLess((len(m["ball"]) - 2) / 60, p.total_ms / 1000)
        self.assertEqual([c["type"] for c in m["cuts"]], ["bay", "tower", "target", "orbit"])
        self.assertTrue(m["in_cup"])

    def test_samples_match_the_plan(self):
        p, m = self.make()
        for i in range(0, len(m["ball"]), 7):
            w = i / 60
            b = p.ball(w)["pos"]
            for j in range(3):
                self.assertAlmostEqual(m["ball"][i][j], b[j], places=3)
            self.assertAlmostEqual(m["ball"][i][3], p.tracer_progress(w), places=3)
            self.assertEqual(m["camera"][i][7], p.shot_index_at(w))
        self.assertEqual(m["ball"][0][3], 0)
        self.assertEqual(m["ball"][-1][3], 1)

    def test_camera_cuts_jump_and_fixed_cameras_hold_still(self):
        p, m = self.make()
        cams = m["camera"]
        for i in range(1, len(cams)):
            if cams[i][7] != cams[i - 1][7]:
                # first frame of a new cut is exactly where that camera wants to be
                w = i / 60
                want = p.camera(cams[i][7], w, p.ball(w)["pos"])
                for j in range(3):
                    self.assertAlmostEqual(cams[i][j], want["pos"][j], places=3)
        bay = [c for c in cams if m["cuts"][c[7]]["type"] == "bay"]
        self.assertTrue(bay and all(c[:3] == bay[0][:3] for c in bay), "the tee camera does not drift")

    def test_smoothed_cameras_never_jump_mid_cut(self):
        _, m = self.make(style="quick")
        cams = m["camera"]
        for i in range(1, len(cams)):
            if cams[i][7] == cams[i - 1][7]:
                self.assertLess(math.dist(cams[i][:3], cams[i - 1][:3]), 3, "frame %d" % i)

    def test_captions_never_spoil_the_result(self):
        p, m = self.make(shotsLeft=1, finalBall=True, before=[20, 14], after=[20, 26])
        pre, post, data = m["captions"]
        self.assertEqual((pre["kind"], pre["reveal"], pre["at_ms"]), ("lower", False, 800))
        self.assertEqual(pre["tag"], "FINAL BALL")
        self.assertNotIn("BLUE", pre["text"])
        self.assertLessEqual(pre["until_ms"], m["rest_ms"])
        self.assertEqual((post["at_ms"], post["reveal"], post["player"]), (m["rest_ms"], True, "Maddie"))
        self.assertEqual(post["text"], "BLUE  +12 · Flag zone x3")
        self.assertEqual(data["items"][0], ["BALL SPEED", "92.0"])
        for c in m["captions"]:
            self.assertTrue(c["reveal"] or c["until_ms"] <= m["rest_ms"])

    def test_routine_shot_gets_a_banner_when_the_ball_stops(self):
        _, m = self.make(style="quick")
        self.assertEqual(len(m["captions"]), 1)
        banner = m["captions"][0]
        self.assertEqual((banner["kind"], banner["at_ms"], banner["text"]), ("banner", m["rest_ms"], "BLUE  +12"))

    def test_message_is_plain_json_and_reasonably_small(self):
        _, m = self.make()
        text = json.dumps(m)
        self.assertEqual(json.loads(text)["version"], D.MESSAGE_VERSION)
        self.assertLess(len(text), 150000, "%d bytes" % len(text))


if __name__ == "__main__":
    unittest.main()
