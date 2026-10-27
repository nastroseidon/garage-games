"""Game scoring (Python port of tests/test_games.js, same cases)."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import games  # noqa: E402
from games import TARGETS, game_by_id, range_hit, to_fixed  # noqa: E402


def shot(carry, offline, speed=80):
    return {"speed_mph": speed, "flight": {"carry_yd": carry, "offline_yd": offline}}


def rshot(land, rest=None):
    rest = rest or land
    return {"speed_mph": 90, "flight": {"carry_yd": land[0], "offline_yd": land[1], "rest": rest,
                                        "total_yd": rest[0], "flight_time_s": 4,
                                        "points": [[0, 0, 0], [land[0], land[1], 0]]}}


class Ctx:
    def __init__(self, players=None, rounds=0):
        self.players = players or []
        self.rounds = rounds
        self.history = []
        self.turn = 0


BLUE = next(t for t in TARGETS if t["name"] == "Blue")
RED = next(t for t in TARGETS if t["name"] == "Red")


class ClassicGameTests(unittest.TestCase):
    def test_closest_measures_distance_and_caps_big_misses(self):
        g = game_by_id("closest")
        self.assertEqual(g.score(shot(100, 0), {"pin": 100}, {}, None, 0)["points"], 0)
        self.assertEqual(g.score(shot(103, 4), {"pin": 100}, {}, None, 0)["points"], 5)
        self.assertEqual(g.score(shot(10, 0), {"pin": 100}, {}, None, 0)["points"], 50)
        self.assertEqual(g.score(shot(98, 0), {"pin": 100}, {}, None, 0)["what"], "6 ft")

    def test_junior_targets_are_half_distance(self):
        self.assertEqual(game_by_id("closest").player_target({"pin": 100}, {"junior": True}), {"pin": 50})
        self.assertEqual(game_by_id("closest").player_target({"pin": 100}, {"junior": False}), {"pin": 100})
        self.assertEqual(game_by_id("speed").player_target({"mph": 80}, {"junior": True}), {"mph": 40})

    def test_darts_rings(self):
        g = game_by_id("darts")
        self.assertEqual(g.score(shot(100, 2), {"d": 100}, {}, None, 0)["points"], 50)
        self.assertEqual(g.score(shot(106, 0), {"d": 100}, {}, None, 0)["points"], 30)
        self.assertEqual(g.score(shot(100, 24), {"d": 100}, {}, None, 0)["points"], 5)
        self.assertEqual(g.score(shot(140, 0), {"d": 100}, {}, None, 0)["points"], 0)

    def test_hit_the_number(self):
        g = game_by_id("speed")
        self.assertEqual(g.score(shot(0, 0, 60.5), {"mph": 60}, {}, None, 0)["what"], "BULLSEYE!")
        self.assertEqual(g.score(shot(0, 0, 50), {"mph": 60}, {}, None, 0)["points"], 10)
        self.assertEqual(g.score(shot(0, 0, 150), {"mph": 60}, {}, None, 0)["points"], 30)

    def test_long_drive_needs_the_fairway_juniors_count_double(self):
        g = game_by_id("longdrive")
        self.assertEqual(g.score(shot(200, 10), {"junior": False}, {}, None, 0)["points"], 200)
        self.assertEqual(g.score(shot(200, 20), {"junior": False}, {}, None, 0)["points"], 0)
        self.assertEqual(g.score(shot(90, -5), {"junior": True}, {}, None, 0)["points"], 180)

    def test_tictactoe_teams_alternate_even_with_3_players(self):
        g = game_by_id("tictactoe")
        ctx = Ctx([{}, {}, {}])
        g.reset(ctx)
        self.assertEqual([g.player_for_turn(ctx, t) for t in range(6)], [0, 1, 2, 1, 0, 1])

    def test_tictactoe_claim_block_and_win(self):
        g = game_by_id("tictactoe")
        ctx = Ctx([{}, {}])
        g.reset(ctx)
        t = g.make_target(0)
        # near row is 40-70 yds; columns -24..-8, -8..8, 8..24
        self.assertEqual(g.score(shot(55, -15), t, {}, ctx, 0)["points"], 1)
        self.assertEqual(g.score(shot(55, -15), t, {}, ctx, 1)["what"], "Already taken!")
        self.assertEqual(g.score(shot(200, 0), t, {}, ctx, 1)["what"], "Off the board")
        g.score(shot(55, 0), t, {}, ctx, 0)
        self.assertFalse(g.is_over(ctx))
        res = g.score(shot(55, 15), t, {}, ctx, 0)
        self.assertEqual(res["what"], "THREE IN A ROW!")
        self.assertTrue(g.is_over(ctx))
        self.assertEqual(g.winner_text(ctx), "Team X wins!")

    def test_tictactoe_full_board_without_a_winner_resets(self):
        g = game_by_id("tictactoe")
        ctx = Ctx([{}, {}])
        g.reset(ctx)
        ctx.board = [0, 1, 0, 0, 1, 1, 1, 0, None]
        t = g.make_target(0)
        # cell 8 = near row, right column; X there makes no line
        res = g.score(shot(55, 15), t, {}, ctx, 0)
        self.assertIn("new board", res["detail"])
        self.assertTrue(all(c is None for c in ctx.board))
        self.assertEqual(ctx.boards, 2)

    def test_every_game_has_the_required_pieces(self):
        self.assertEqual([g.id for g in games.GAMES],
                         ["targetrange", "calledshot", "ladder", "closest", "darts", "speed", "longdrive",
                          "tictactoe"])
        for g in games.GAMES:
            for k in ("id", "name", "emoji", "blurb", "view"):
                self.assertTrue(getattr(g, k), "%s missing %s" % (g.id, k))
            self.assertIsNot(type(g).score, games.Game.score, g.id + " has no score()")


class RangeGameTests(unittest.TestCase):
    def test_landing_zones_and_multipliers(self):
        g = game_by_id("targetrange")
        ctx = Ctx(rounds=10)
        adult = {"round": 0, "junior": False}
        self.assertEqual(g.score(rshot([BLUE["d"], BLUE["l"]]), adult, {}, ctx, 0)["points"], 12)  # flag zone x3
        self.assertEqual(g.score(rshot([BLUE["d"] + 3, BLUE["l"]]), adult, {}, ctx, 0)["points"], 8)  # inner x2
        self.assertEqual(g.score(rshot([BLUE["d"] + 9, BLUE["l"]]), adult, {}, ctx, 0)["points"], 4)  # outer
        self.assertEqual(g.score(rshot([BLUE["d"] + 30, BLUE["l"]]), adult, {}, ctx, 0)["points"], 0)
        final = {"round": 9, "junior": False}
        self.assertEqual(g.score(rshot([BLUE["d"] + 9, BLUE["l"]]), final, {}, ctx, 0)["points"], 8)  # final ball
        junior = {"round": 0, "junior": True}
        self.assertEqual(g.score(rshot([RED["d"] + 4, RED["l"]]), junior, {}, ctx, 0)["points"], 3)  # junior +2

    def test_a_ball_that_lands_short_can_roll_in_and_stops_in_the_target(self):
        short = rshot([BLUE["d"] - 20, BLUE["l"]], [BLUE["d"] + 30, BLUE["l"]])
        hit = range_hit(short)
        self.assertEqual(hit["target"], TARGETS.index(BLUE))
        self.assertTrue(hit["rolledIn"])
        self.assertEqual(hit["zone"], "outer")
        self.assertLess(abs(hit["stop"][0] - (BLUE["d"] - BLUE["r"])), 0.6)
        stays = range_hit(rshot([BLUE["d"], BLUE["l"] + 9], [BLUE["d"] + 25, BLUE["l"] + 9]))
        self.assertFalse(stays["rolledIn"])
        self.assertEqual(stays["stop"], [BLUE["d"], BLUE["l"] + 9])

    def test_called_shot_only_pays_on_the_called_target(self):
        g = game_by_id("calledshot")
        t = {"called": TARGETS.index(BLUE), "junior": False}
        self.assertEqual(g.score(rshot([BLUE["d"] + 9, BLUE["l"]]), t, {}, None, 0)["points"], 8)
        self.assertEqual(g.score(rshot([RED["d"], RED["l"]]), t, {}, None, 0)["what"], "Wrong target!")
        jr = g.player_target({"seed": 12345}, {"name": "Kid", "junior": True})
        self.assertLess(jr["called"], 3, "juniors are only called to the three nearest targets")

    def test_ladder_climbs_in_order_and_ends_at_the_top(self):
        g = game_by_id("ladder")
        players = [{"name": "Kid", "junior": True}, {"name": "Dad", "junior": False}]
        ctx = Ctx(players, rounds=10)

        def play(idx, T):
            result = g.score(rshot([T["d"], T["l"]]), {}, players[idx], ctx, idx)
            ctx.history.append({"idx": idx, "result": result})
            ctx.turn += 1
            return result
        self.assertEqual(play(0, TARGETS[1])["what"], "Wrong rung!")
        self.assertEqual(play(0, TARGETS[0])["points"], 1)
        self.assertEqual(play(0, TARGETS[1])["points"], 1)
        self.assertFalse(g.is_over(ctx))
        self.assertEqual(play(0, TARGETS[2])["what"], "TOP OF THE LADDER!")
        self.assertTrue(g.is_over(ctx))


class FormattingTests(unittest.TestCase):
    def test_numbers_print_like_javascript(self):
        self.assertEqual(to_fixed(2.25), "2.3")    # JS rounds halves up; Python's round() would say 2.2
        self.assertEqual(to_fixed(-0.04), "-0.0")
        self.assertEqual(to_fixed(-0.0), "0.0")
        self.assertEqual(to_fixed(118.46, 0), "118")
        self.assertEqual(games.js_round(-2.5), -2)
        self.assertEqual(games.num(10.0), "10")
        self.assertEqual(games.num(2.5), "2.5")
        self.assertEqual(games.fnv_hash("12345:Kid"), 537144186)  # value from the JS hash()


if __name__ == "__main__":
    unittest.main()
