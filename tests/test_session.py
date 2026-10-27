"""The running game on the server, and its HTTP control API."""

import json
import os
import random
import sys
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import games  # noqa: E402
import server  # noqa: E402
from flight import simulate  # noqa: E402
from session import GameSession  # noqa: E402

BLUE = games.TARGETS[3]
_ids = iter(range(1, 10 ** 6))


def at(T, dd=0.0, dl=0.0, roll=0.0):
    """A shot that lands at a target (offset by dd/dl yds) with flight.py-style points."""
    d, l = T["d"] + dd, T["l"] + dl
    pts = [[round(d * u, 2), round(l * u, 2), round(320 * u * (1 - u), 2)] for u in (i / 30 for i in range(31))]
    return {"id": next(_ids), "speed_mph": 95.0, "vla_deg": 24.0, "hla_deg": 1.0, "spin_rpm": 7000.0,
            "spin_axis_deg": 0.0,
            "flight": {"carry_yd": d, "offline_yd": l, "apex_ft": 80.0, "flight_time_s": 4.5, "points": pts,
                       "roll_yd": roll, "total_yd": d + roll, "rest": [d + roll, l]}}


def miss():
    return at({"d": 60, "l": 40})


PLAYERS = [{"name": "Dad", "color": "#ffd23f"}, {"name": "Maddie", "junior": True, "color": "#ff6b6b"}]


def new_session(game="targetrange", rounds=2, players=PLAYERS, camera="auto"):
    s = GameSession(rng=random.Random(3))
    s.start(game, players, rounds, camera)
    return s


class SessionTests(unittest.TestCase):
    def test_start_checks_the_game_and_players(self):
        s = GameSession()
        with self.assertRaises(ValueError):
            s.start("nope", PLAYERS)
        with self.assertRaisesRegex(ValueError, "at least 2 players"):
            s.start("tictactoe", PLAYERS[:1])
        with self.assertRaises(ValueError):
            s.start("targetrange", [{"name": "   "}])
        with self.assertRaises(ValueError):
            s.set_camera("drone")
        self.assertFalse(s.active)
        self.assertEqual(s.snapshot(), {"active": False, "camera": "auto"})

    def test_turns_scores_and_the_winner(self):
        s = new_session()
        self.assertEqual(s.snapshot()["current"]["name"], "Dad")
        ev = s.apply_shot(at(BLUE, dd=9))
        self.assertEqual((ev["idx"], ev["result"]["points"]), (0, 4))
        self.assertEqual(ev["scores"], {"before": [0, 0], "after": [4, 0]})
        ev = s.apply_shot(at(BLUE, dd=9))        # junior: (4 + 2) points
        self.assertEqual(ev["result"]["points"], 6)
        self.assertEqual(ev["state"]["round_info"], "ROUND 2 OF 2")
        self.assertEqual(ev["state"]["current"]["task"], "FINAL BALL - double points!")
        s.apply_shot(miss())
        ev = s.apply_shot(at(BLUE, dd=9))        # final ball x2
        self.assertEqual(ev["result"]["points"], 12)
        st = ev["state"]
        self.assertTrue(st["over"])
        self.assertEqual(st["winner"]["text"], "Maddie wins!")
        self.assertEqual([r["value"] for r in st["scoreboard"]], ["18 pts", "4 pts"])
        self.assertTrue(s.apply_shot(miss())["free"], "shots after the end are not scored")

    def test_range_shots_come_with_a_shot_plan(self):
        s = new_session(camera="broadcast")
        ev = s.apply_shot(at(BLUE))
        plan = ev["plan"]
        self.assertEqual(plan["mode"], "broadcast")
        self.assertTrue(plan["in_cup"])
        self.assertEqual(plan["captions"][1]["text"], "BLUE  +12 · Flag zone x3")
        self.assertEqual(plan["captions"][0]["player"], "Dad")
        json.dumps(ev)  # every event must be plain JSON
        classic = new_session(game="darts").apply_shot(at({"d": 100, "l": 0}))
        self.assertNotIn("plan", classic)
        self.assertGreaterEqual(classic["anim_ms"], 900)

    def test_ladder_highlights_the_rung_before_the_result(self):
        s = new_session(game="ladder", rounds=10)
        ev = s.apply_shot(at(games.TARGETS[0]))
        self.assertEqual(ev["highlight"], 0, "while the ball flies, the old rung is lit")
        s.apply_shot(miss())
        self.assertEqual(s.snapshot()["current"]["highlight"], 1, "Dad is now on rung 2")

    def test_undo_and_skip(self):
        s = new_session(rounds=3)
        s.apply_shot(at(BLUE))
        self.assertTrue(s.skip())
        self.assertEqual(s.history[-1]["result"]["what"], "Skipped")
        self.assertEqual(s.snapshot()["current"]["name"], "Dad")
        self.assertTrue(s.undo())
        self.assertTrue(s.undo())
        self.assertFalse(s.undo())
        self.assertEqual((s.turn, s.totals()), (0, [0, 0]))

    def test_undo_rebuilds_the_tictactoe_board(self):
        s = new_session(game="tictactoe")
        s.apply_shot(at({"d": 55, "l": -15}))     # X takes a square
        s.apply_shot(at({"d": 55, "l": 0}))       # O takes another
        self.assertEqual(sum(c is not None for c in s.board), 2)
        s.undo()
        self.assertEqual(s.board.count(None), 8)
        self.assertEqual(s.snapshot()["current"]["task"], "Team O - claim a square!")

    def test_test_shot_kind_follows_the_game(self):
        s = new_session(game="ladder")
        self.assertEqual(s.test_kind(), "chip")   # first rung is Red at 20 yds
        self.assertIsNone(GameSession().test_kind())

    def test_real_flight_model_shots_play_through_every_game(self):
        rng = random.Random(9)
        for g in games.GAMES:
            s = new_session(game=g.id, rounds=3)
            for _ in range(8):
                f = simulate(rng.uniform(30, 160), rng.uniform(10, 30), rng.uniform(-5, 5), rng.uniform(2000, 9000),
                             rng.uniform(-10, 10))
                ev = s.apply_shot({"id": next(_ids), "speed_mph": 90.0, "vla_deg": 20.0, "hla_deg": 0.0,
                                   "spin_rpm": 5000.0, "spin_axis_deg": 0.0, "flight": f})
                json.dumps(ev)
            # tic-tac-toe and cornhole (to 21) run on until someone wins
            self.assertTrue(s.snapshot()["over"] or g.id in ("tictactoe", "cornhole"), g.id)


class ApiTests(unittest.TestCase):
    """The control API the browser (or a tablet) uses."""

    @classmethod
    def setUpClass(cls):
        server.shot_log.enabled = False
        server.session.__init__(rng=random.Random(1))
        cls.events = []
        server.hub.publish = lambda event, data: cls.events.append((event, data))
        cls.web = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        threading.Thread(target=cls.web.serve_forever, daemon=True).start()
        cls.base = "http://127.0.0.1:%d" % cls.web.server_address[1]

    @classmethod
    def tearDownClass(cls):
        cls.web.shutdown()
        cls.web.server_close()
        del server.hub.publish

    def call(self, path, body=None):
        req = urllib.request.Request(self.base + path, data=None if body is None else json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def test_play_a_game_over_http(self):
        status, cat = self.call("/api/games")
        self.assertEqual(status, 200)
        self.assertEqual(cat["games"][0]["id"], "targetrange")
        self.assertEqual(len(cat["targets"]), 7)
        self.assertEqual(cat["idle_camera"]["fov"], 38)

        self.assertEqual(self.call("/api/game/start", {"game": "tictactoe", "players": PLAYERS[:1]})[0], 400)
        self.assertEqual(self.call("/api/game/start", {"game": "targetrange", "players": PLAYERS, "rounds": 5,
                                                       "camera": "quick"}), (200, {"ok": True}))
        self.assertEqual(self.events[-1][0], "state")
        self.assertEqual(self.events[-1][1]["reason"], "start")

        self.assertEqual(self.call("/api/test-shot", {})[0], 200)
        name, ev = self.events[-1]
        self.assertEqual(name, "shot")
        self.assertEqual(ev["plan"]["mode"], "quick")
        self.assertEqual(ev["shot"]["source"], "test")

        self.assertEqual(self.call("/api/game/skip", {})[0], 200)
        self.assertEqual(self.call("/api/game/undo", {})[0], 200)
        self.assertEqual(self.events[-1][1]["reason"], "undo")
        status, state = self.call("/api/state")
        self.assertEqual((status, state["turn"]), (200, 1))
        self.assertEqual(self.call("/api/settings", {"camera": "drone"})[0], 400)
        self.assertEqual(self.call("/api/settings", {"camera": "static"})[0], 200)
        self.assertEqual(self.call("/api/game/end", {})[0], 200)
        self.assertFalse(self.call("/api/state")[1]["active"])
        self.assertEqual(self.call("/api/nope", {})[0], 404)


if __name__ == "__main__":
    unittest.main()
