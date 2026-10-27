"""What the Unreal range is made of, as plain data (no `import unreal`).

layout(targets) returns a list of pieces; build_range.py turns each piece
into an Unreal actor. Keeping the layout here means it can be tested
without Unreal (tests/test_range_layout.py).

Units are yards: x downrange, y to the right, z up. A piece is a dict:
  name      actor label (all start with GG_ so build_range can replace them)
  kind      "mesh" | "text" | "spot"
  mesh      engine basic shape: Plane, Cube, Cylinder, Sphere, Cone
  role      what Fab/Quixel dressing may replace it with ("tree", "rock")
  material  key into MATERIALS
  pos       [x, y, z] centre of the piece
  size      [x, y, z] full size in yards
  yaw       degrees (optional)
Text and spotlights carry their own fields (see below).

LIGHTING holds the day and night setups that garage_env switches between.
"""

import math
import random

# ---- the range ----
RANGE_LENGTH = 300       # yards of mown range
RANGE_HALF_WIDTH = 60    # yards either side of the target line
STRIPE = 10              # mowing stripe length
TOWER_X = [-12, 48, 108, 168, 228]
TOWER_Y = 66
TOWER_HEIGHT = 24
TREE_LINE_Y = (78, 105)  # trees stand between these distances from the centre line
HILL_RING = 520          # distant hills, this far from the tee

# material key -> (colour hex, glow, roughness). Target colours come from TARGETS.
MATERIALS = {
    "grass_a": ("#2e7a37", 0.0, 0.95),
    "grass_b": ("#3a8c42", 0.0, 0.95),
    "rough": ("#264d24", 0.0, 1.0),
    "tee_turf": ("#4c9c4a", 0.0, 0.9),
    "mat": ("#2b2b2b", 0.0, 0.8),
    "post": ("#9aa0a6", 0.0, 0.45),
    "lamp": ("#fff4d6", 0.0, 0.3),       # glows at night (see LIGHTING)
    "sign": ("#1d2b3a", 0.0, 0.6),
    "white": ("#f2f2f2", 0.0, 0.5),
    "flag": ("#ff3b3b", 0.3, 0.6),
    "trunk": ("#5a3d26", 0.0, 0.95),
    "leaves": ("#1f5a2a", 0.0, 0.95),
    "hill": ("#2c4a2e", 0.0, 1.0),
    "rock": ("#7b7a74", 0.0, 0.9),
}


def target_material(i):
    return "target_%d" % i


def target_inner_material(i):
    return "target_%d_inner" % i


def _mesh(name, mesh, material, pos, size, yaw=0.0, role=None):
    return {"name": name, "kind": "mesh", "mesh": mesh, "material": material, "pos": list(pos),
            "size": list(size), "yaw": yaw, "role": role}


def ground():
    pieces = []
    # mown stripes from the tee to the end of the range, alternating shades
    for i, x0 in enumerate(range(-10, RANGE_LENGTH, STRIPE)):
        pieces.append(_mesh("GG_Stripe_%02d" % i, "Plane", "grass_a" if i % 2 else "grass_b",
                            (x0 + STRIPE / 2, 0, 0), (STRIPE, RANGE_HALF_WIDTH * 2, 0)))
    # rough all around, a hair lower so it never flickers through the stripes
    pieces.append(_mesh("GG_Rough", "Plane", "rough", (RANGE_LENGTH / 2, 0, -0.03),
                        (RANGE_LENGTH + 900, RANGE_HALF_WIDTH * 2 + 900, 0)))
    # the hitting area
    pieces.append(_mesh("GG_TeeBox", "Cube", "tee_turf", (-3, 0, 0.05), (10, 24, 0.1)))
    pieces.append(_mesh("GG_HittingMat", "Cube", "mat", (0, 0, 0.12), (1.6, 1.6, 0.04)))
    return pieces


def targets_pieces(targets, inner=0.4, center=1.5):
    pieces = []
    for i, T in enumerate(targets):
        d, l, r = T["d"], T["l"], T["r"]
        tag = T["name"]
        pieces.append(_mesh("GG_Target_%s" % tag, "Cylinder", target_material(i), (d, l, 0.04), (2 * r, 2 * r, 0.08)))
        pieces.append(_mesh("GG_Target_%s_Inner" % tag, "Cylinder", target_inner_material(i), (d, l, 0.09),
                            (2 * r * inner, 2 * r * inner, 0.03)))
        pieces.append(_mesh("GG_Target_%s_Center" % tag, "Cylinder", target_material(i), (d, l, 0.115),
                            (2 * center, 2 * center, 0.02)))
        pieces.append(_mesh("GG_Target_%s_Pin" % tag, "Cylinder", "white", (d, l, 1.9), (0.05, 0.05, 3.8)))
        pieces.append(_mesh("GG_Target_%s_Flag" % tag, "Cube", target_material(i), (d, l + 0.5, 3.45),
                            (0.02, 1.0, 0.65)))
        # a yardage board on the far side of each target, facing the tee
        side = 1 if l >= 0 else -1
        sx, sy = d + 1, l + side * (r + 3)
        pieces.append(_mesh("GG_Target_%s_Board" % tag, "Cube", "sign", (sx, sy, 1.6), (0.3, 4.5, 2.2)))
        pieces.append({"name": "GG_Target_%s_Yards" % tag, "kind": "text", "text": str(T["d"]),
                       "pos": [sx - 0.2, sy, 1.6], "height": 1.5, "color": T["color"], "yaw": 180.0})
    return pieces


def markers():
    """Distance boards along the left edge every 50 yds."""
    pieces = []
    for d in range(50, RANGE_LENGTH + 1, 50):
        pieces.append(_mesh("GG_Marker_%d" % d, "Cube", "sign", (d, -RANGE_HALF_WIDTH + 2, 1.0), (0.3, 3.0, 2.0)))
        pieces.append({"name": "GG_Marker_%d_Text" % d, "kind": "text", "text": str(d),
                       "pos": [d - 0.2, -RANGE_HALF_WIDTH + 2, 1.0], "height": 1.3, "color": "#ffffff",
                       "yaw": 180.0})
    return pieces


def towers():
    """Light towers down both sides: a pole, a lamp head, and a spotlight aimed at the range."""
    pieces = []
    for x in TOWER_X:
        for side in (-1, 1):
            y = side * TOWER_Y
            tag = "%d%s" % (x, "R" if side > 0 else "L")
            pieces.append(_mesh("GG_Tower_%s_Pole" % tag, "Cylinder", "post", (x, y, TOWER_HEIGHT / 2),
                                (0.7, 0.7, TOWER_HEIGHT)))
            pieces.append(_mesh("GG_Tower_%s_Lamp" % tag, "Cube", "lamp", (x, y - side * 0.6, TOWER_HEIGHT + 0.6),
                                (1.2, 3.5, 1.4)))
            aim = [x + 30, -side * 15, 0]  # down the range and across it
            src = [x, y - side * 1.2, TOWER_HEIGHT]
            dx, dy, dz = aim[0] - src[0], aim[1] - src[1], aim[2] - src[2]
            pieces.append({"name": "GG_Tower_%s_Light" % tag, "kind": "spot", "pos": src,
                           "yaw": math.degrees(math.atan2(dy, dx)),
                           "pitch": math.degrees(math.atan2(dz, math.hypot(dx, dy))),
                           "cone": 75.0, "reach": 160.0})
    return pieces


def trees(seed=7):
    """A tree line two rows deep down both sides of the range (placeholders: a trunk and a cone)."""
    rng = random.Random(seed)
    pieces = []
    n = 0
    mid = sum(TREE_LINE_Y) / 2
    rows = ((TREE_LINE_Y[0], mid), (mid, TREE_LINE_Y[1]))
    for side in (-1, 1):
        for near, far in rows:
            x = -20.0 + rng.uniform(0, 6)
            while x < RANGE_LENGTH + 40:
                x += rng.uniform(5, 10)
                y = side * rng.uniform(near, far)
                h = rng.uniform(9, 16)
                yaw = rng.uniform(0, 360)
                pieces.append(_mesh("GG_Tree_%03d" % n, "Cone", "leaves", (x, y, h * 0.3 + h * 0.75 / 2),
                                    (h * 0.45, h * 0.45, h * 0.75), yaw=yaw, role="tree"))
                pieces.append(_mesh("GG_Tree_%03d_Trunk" % n, "Cylinder", "trunk", (x, y, h * 0.3 / 2),
                                    (h * 0.06, h * 0.06, h * 0.3), yaw=yaw, role="trunk"))
                n += 1
    # a few rocks between the trees and the range
    for i in range(10):
        side = 1 if i % 2 else -1
        s = rng.uniform(1.2, 3.0)
        pieces.append(_mesh("GG_Rock_%02d" % i, "Sphere", "rock",
                            (rng.uniform(20, RANGE_LENGTH), side * rng.uniform(70, 76), s * 0.2),
                            (s * 1.4, s, s * 0.7), yaw=rng.uniform(0, 360), role="rock"))
    return pieces


def hills(seed=3):
    """Low hills on the horizon so the range isn't floating in space."""
    rng = random.Random(seed)
    pieces = []
    for i in range(18):
        ang = math.radians(-80 + i * 160 / 17 + rng.uniform(-3, 3))
        dist = HILL_RING + rng.uniform(-60, 80)
        w, h = rng.uniform(140, 260), rng.uniform(25, 60)
        pieces.append(_mesh("GG_Hill_%02d" % i, "Sphere", "hill",
                            (math.cos(ang) * dist, math.sin(ang) * dist, -h * 0.2), (w, w * 0.6, h * 2),
                            yaw=math.degrees(ang)))
    return pieces


def layout(targets, inner=0.4, center=1.5):
    return ground() + targets_pieces(targets, inner, center) + markers() + towers() + trees() + hills()


# ---- day and night ----
# sun: pitch/yaw degrees, intensity in lux, colour.  sky: sky light intensity.
# towers: spotlight intensity in candela (0 = off).  glow: target rim glow.
# exposure: EV100 range for auto exposure.
LIGHTING = {
    "day": {"sun_pitch": -42, "sun_yaw": -35, "sun_lux": 10.0, "sun_color": "#fff4e5", "sky": 1.0,
            "towers": 0.0, "lamp_glow": 0.0, "glow": 0.3, "fog": 0.01, "fog_color": "#b8cbe0",
            "exposure": (3.0, 6.0)},
    "night": {"sun_pitch": -55, "sun_yaw": 140, "sun_lux": 0.02, "sun_color": "#9fb4ff", "sky": 0.08,
              "towers": 3500.0, "lamp_glow": 40.0, "glow": 0.5, "fog": 0.02, "fog_color": "#0b1733",
              "exposure": (0.5, 3.0)},
}
