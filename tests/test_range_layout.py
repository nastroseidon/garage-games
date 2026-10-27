"""The Unreal range layout (range_layout.py): plain data, so tested here."""

import math
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "unreal", "GarageGames", "Content", "Python"))

import games  # noqa: E402
import range_layout as R  # noqa: E402

PIECES = R.layout(games.TARGETS, games.INNER, games.CENTER)
BY_NAME = {p["name"]: p for p in PIECES}


def footprint(p):
    """Rough radius of a piece seen from above (yards)."""
    return math.hypot(p["size"][0], p["size"][1]) / 2


class LayoutTests(unittest.TestCase):
    def test_every_target_matches_the_game_rules(self):
        for T in games.TARGETS:
            rim = BY_NAME["GG_Target_%s" % T["name"]]
            self.assertEqual(rim["pos"][:2], [T["d"], T["l"]])
            self.assertEqual(rim["size"][:2], [2 * T["r"], 2 * T["r"]])
            inner = BY_NAME["GG_Target_%s_Inner" % T["name"]]
            self.assertAlmostEqual(inner["size"][0], 2 * T["r"] * games.INNER)
            self.assertAlmostEqual(BY_NAME["GG_Target_%s_Center" % T["name"]]["size"][0], 2 * games.CENTER)
            self.assertEqual(BY_NAME["GG_Target_%s_Yards" % T["name"]]["text"], str(T["d"]))

    def test_names_are_unique_and_replaceable(self):
        names = [p["name"] for p in PIECES]
        self.assertEqual(len(names), len(set(names)))
        self.assertTrue(all(n.startswith("GG_") for n in names), "build_range replaces actors named GG_...")
        self.assertNotIn("GG_Ball", names)
        self.assertNotIn("GG_ShotCamera", names)

    def test_nothing_stands_on_a_target_or_the_hitting_area(self):
        for p in PIECES:
            if p["kind"] != "mesh" or p["mesh"] == "Plane":
                continue
            if p["name"].startswith("GG_Target_") and not p["name"].endswith("_Board"):
                continue  # the target itself, its pin and flag
            if p["name"] in ("GG_TeeBox", "GG_HittingMat") or p["name"].startswith("GG_Hill_"):
                continue
            for T in games.TARGETS:
                gap = math.hypot(p["pos"][0] - T["d"], p["pos"][1] - T["l"]) - footprint(p) - T["r"]
                self.assertGreater(gap, 0, "%s overlaps the %s target" % (p["name"], T["name"]))
            self.assertGreater(math.hypot(p["pos"][0], p["pos"][1]), 15, p["name"] + " is in the hitting area")

    def test_towers_and_trees_stay_outside_the_range(self):
        for p in PIECES:
            n = p["name"]
            if n.startswith(("GG_Tower_", "GG_Tree_", "GG_Rock_")):
                self.assertGreater(abs(p["pos"][1]), R.RANGE_HALF_WIDTH, n)
            if n.startswith("GG_Hill_"):
                self.assertGreater(math.hypot(p["pos"][0], p["pos"][1]) - footprint(p), R.RANGE_LENGTH, n)

    def test_tower_lights_point_down_at_the_range(self):
        spots = [p for p in PIECES if p["kind"] == "spot"]
        self.assertEqual(len(spots), 2 * len(R.TOWER_X))
        for s in spots:
            self.assertLess(s["pitch"], -10, "aimed downward")
            # the beam heads back toward the centre line
            dy = math.sin(math.radians(s["yaw"]))
            self.assertLess(dy * s["pos"][1], 0, s["name"])

    def test_every_material_is_defined(self):
        keys = set(R.MATERIALS) | {R.target_material(i) for i in range(len(games.TARGETS))} | \
            {R.target_inner_material(i) for i in range(len(games.TARGETS))}
        for p in PIECES:
            if p["kind"] == "mesh":
                self.assertIn(p["material"], keys, p["name"])
                self.assertIn(p["mesh"], ("Plane", "Cube", "Cylinder", "Sphere", "Cone"), p["name"])

    def test_layout_is_the_same_every_time(self):
        self.assertEqual(R.layout(games.TARGETS, games.INNER, games.CENTER), PIECES)

    def test_day_and_night_set_the_same_things(self):
        self.assertEqual(sorted(R.LIGHTING), ["day", "night"])
        self.assertEqual(set(R.LIGHTING["day"]), set(R.LIGHTING["night"]))
        self.assertEqual(R.LIGHTING["day"]["towers"], 0)
        self.assertGreater(R.LIGHTING["night"]["towers"], 0)
        self.assertGreater(R.LIGHTING["night"]["glow"], R.LIGHTING["day"]["glow"])


if __name__ == "__main__":
    unittest.main()
