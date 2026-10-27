"""Golf Cornhole's campsite in the Unreal level: a grassy clearing in the woods at night, with a
campfire, tents, a picnic table and string lights (the same camp web/camp-gl.js draws).

The layout comes from the server (cornhole.campsite, board["camp"]) in yards, already scaled with
the board; camp["k"] is yards per real metre, for the sizes of the small things built here.

Everything that stands still is batched by shape and colour into a few instanced-mesh actors;
the fire's flames, embers and the lights are their own actors so they can flicker. All actors are
named GG_CH_Camp_... so CornholeSet.clear() removes them with the board.
"""

import math
import random

import unreal

import garage_env
import garage_stream as gs

CAMP = "GG_CH_Camp_"
COLOR_MATERIAL = "/Game/Garage/M_GarageColor"
SHAPES = "/Engine/BasicShapes/"
METAL = "#1b1b1d"
BARK = "#6b5040"
LAMP = "#ffc98a"
CAMP_EXPOSURE = -0.3    # exposure compensation (EV) while the camp is up
FIRE_CD = 20.0    # the campfire's light, in real candelas (it flickers around this)


def _actors():
    return unreal.get_editor_subsystem(unreal.EditorActorSubsystem)


def _yaw(v, deg):
    """Turn a vector about the vertical by yaw degrees (downrange towards right, as the server measures it)."""
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    return [v[0] * c - v[1] * s, v[0] * s + v[1] * c, v[2]]


def _add(a, b):
    return [a[0] + b[0], a[1] + b[1], a[2] + b[2]]


def _tint(h, t):
    """A hex colour scaled by t, rounded to a few steps so similar tints share one instanced mesh."""
    t = round(t * 4) / 4
    h = h.lstrip("#")
    return "#" + "".join("%02x" % min(255, int(int(h[i:i + 2], 16) * t)) for i in (0, 2, 4))


def _exposure_bias(pp, on, bias):
    s = pp.get_editor_property("settings")
    s.set_editor_property("override_auto_exposure_bias", on)
    s.set_editor_property("auto_exposure_bias", bias)
    pp.set_editor_property("settings", s)


def _cd(real_cd, k):
    """A real light's candelas at the camp's scale: a real metre is 0.9144 k Unreal metres."""
    return real_cd * (0.9144 * k) ** 2


class Camp:
    def __init__(self, camp):
        self.c = camp
        self.k = camp["k"]
        self.parts = {}       # (shape, colour, glow) -> [Transform]
        self.flames = []      # (actor, base [x, y, z] yards, width, height, phase)
        self.embers = []      # [actor, age, life, pos, vel]
        self.fire_light = None
        self.time = 0.0
        self.rnd = random.Random(1234)
        self.saved = None     # the level's own lighting, put back by restore()

    # ---------------- building ----------------

    def part(self, shape, color, center, size, x_axis=(1, 0, 0), z_axis=(0, 0, 1), glow=0.0):
        """One basic shape: centre and size in yards, its X and Z axes along the given world directions."""
        # keep exactly the axis that was asked for: Z for long parts (logs, legs), else X
        x, z = unreal.Vector(*x_axis), unreal.Vector(*z_axis)
        if tuple(z_axis) == (0, 0, 1):
            rot = unreal.MathLibrary.make_rot_from_xz(x, z)
        else:
            rot = unreal.MathLibrary.make_rot_from_zx(z, x)
        t = unreal.Transform(location=unreal.Vector(*gs.to_unreal(center)), rotation=rot,
                             scale=unreal.Vector(*[max(v, 1e-4) * gs.YARD_CM / 100.0 for v in size]))
        self.parts.setdefault((shape, color, glow), []).append(t)

    def local(self, shape, color, origin, yaw, center, size, x_axis=(1, 0, 0), z_axis=(0, 0, 1), glow=0.0):
        """A part of a thing standing at origin turned by yaw: centre and axes in its own frame
        (x towards its front, y to its right, z up)."""
        self.part(shape, color, _add(origin, _yaw(center, yaw)), size, _yaw(x_axis, yaw), _yaw(z_axis, yaw), glow)

    def build(self):
        c, k = self.c, self.k
        self.ground()
        self.woods()
        self.fire()
        self.lamps()
        for t in c["tents"]:
            self.tent(t)
        self.table(c["table"])
        self.cooler(c["cooler"])
        for lg in c["logs"]:
            self.local("Cylinder", BARK, lg["p"], lg["yaw"], [0, 0, lg["r"] * 0.9],
                       [2 * lg["r"], 2 * lg["r"], lg["len"]],
                       z_axis=(0, 1, 0), x_axis=(0, 0, 1))
        wp = c["woodpile"]
        for row, n in enumerate((6, 5, 4)):
            for i in range(n):
                at = [0, (i - (n - 1) / 2) * wp["r"] * 2.05, wp["r"] * (1 + row * 1.75)]
                self.local("Cylinder", BARK, wp["p"], wp["yaw"], at,
                           [2 * wp["r"], 2 * wp["r"], wp["len"]], z_axis=(1, 0, 0), x_axis=(0, 0, 1))
        for s in c["stumps"]:
            self.part("Cylinder", BARK, _add(s["p"], [0, 0, s["h"] / 2]), [2 * s["r"], 2.2 * s["r"], s["h"]])
            self.part("Cylinder", "#a07a50", _add(s["p"], [0, 0, s["h"]]), [1.8 * s["r"], 1.8 * s["r"], 0.01 * k])
        for ch in c["chairs"]:
            self.chair(ch)
        self.spawn_parts()

    def ground(self):
        c, k = self.c, self.k
        # forest floor everywhere, grass in the clearing (with a softer ring at its edge), ash round the fire
        self.part("Cylinder", "#2c2418", _add(c["center"], [0, 0, -0.02 * k]),
                  [2 * c["ground_r"], 2 * c["ground_r"], 0.04 * k])
        r = c["clearing_r"] + 4 * k
        self.part("Cylinder", "#28331a", _add(c["center"], [0, 0, -0.012 * k]), [2 * r, 2 * r, 0.02 * k])
        r = c["clearing_r"] + 1.5 * k
        self.part("Cylinder", "#29461f", _add(c["center"], [0, 0, -0.008 * k]), [2 * r, 2 * r, 0.02 * k])
        f = c["fire"]
        self.part("Cylinder", "#2e2b27", _add(f["p"], [0, 0, -0.006 * k]), [5.2 * f["r"], 5.2 * f["r"], 0.02 * k])

    def woods(self):
        c, k = self.c, self.k
        tiers = ((0.2, 0.44, 1.0), (0.38, 0.62, 0.8), (0.55, 0.8, 0.58), (0.72, 1.0, 0.36))
        blobs = ((0, 0.7, 0, 0.6, 0.24), (0.38, 0.6, 0.15, 0.42, 0.18), (-0.32, 0.62, -0.22, 0.45, 0.19),
                 (0.05, 0.88, 0.04, 0.4, 0.15), (-0.12, 0.56, 0.4, 0.4, 0.16))
        for t in c["trees"]:
            p, h, r, yaw = t["p"], t["h"], t["r"], t["yaw"]
            if t["kind"] == "pine":
                leaf = _tint("#1d4428", t["tint"])
                self.part("Cylinder", "#4a3828", _add(p, [0, 0, h * 0.45]), [0.1 * r, 0.1 * r, h * 0.9])
                for b, top, rr in tiers:
                    self.part("Cone", leaf, _add(p, [0, 0, (b + top) / 2 * h]), [2 * rr * r, 2 * rr * r, (top - b) * h],
                              x_axis=_yaw([1, 0, 0], yaw))
            else:
                leaf = _tint("#3a5f28", t["tint"])
                self.part("Cylinder", "#4a3828", _add(p, [0, 0, h * 0.33]), [0.17 * r, 0.17 * r, h * 0.66])
                for x, y, z, rr, ry in blobs:
                    self.local("Sphere", leaf, p, yaw, [-z * r, x * r, y * h], [2 * rr * r, 2 * rr * r, 2 * ry * h])
        for b in c["bushes"]:
            self.part("Sphere", _tint("#2c5524", b["tint"]), _add(b["p"], [0, 0, 0.25 * b["r"]]),
                      [2 * b["r"], 2 * b["r"], 1.4 * b["r"]])
        for rk in c["rocks"]:
            self.local("Sphere", _tint("#6a655d", 0.75 + self.rnd.random() * 0.4), rk["p"], rk["yaw"],
                       [0, 0, 0.12 * rk["r"]], [1.7 * rk["r"], 2 * rk["r"], 1.1 * rk["r"]])

    def fire(self):
        f, k, R = self.c["fire"], self.k, self.rnd
        p, r = f["p"], f["r"]
        for i in range(12):
            a = i / 12 * 2 * math.pi + R.random() * 0.2
            sz = (0.11 + R.random() * 0.06) * k
            self.local("Sphere", _tint("#6f6a62", 0.7 + R.random() * 0.4), p, math.degrees(a),
                       [r, 0, sz * 0.4], [1.7 * sz, 2 * sz, 1.3 * sz])
        self.part("Cylinder", "#ff5a14", _add(p, [0, 0, 0.004 * k]), [1.6 * r, 1.6 * r, 0.02 * k], glow=4.0)
        for i in range(5):    # charred logs leaning in, a teepee
            a = i / 5 * 2 * math.pi + 0.3
            foot = [math.cos(a) * 0.33 * k, math.sin(a) * 0.33 * k, 0.03 * k]
            tip = [math.cos(a + 2.4) * 0.04 * k, math.sin(a + 2.4) * 0.04 * k, 0.5 * k]
            d = [tip[j] - foot[j] for j in range(3)]
            ln = math.sqrt(sum(v * v for v in d))
            d = [v / ln for v in d]
            self.part("Cylinder", "#3a2214", _add(p, [(foot[j] + tip[j]) / 2 for j in range(3)]),
                      [0.09 * k, 0.09 * k, 0.75 * k], x_axis=(-d[2] * d[0], -d[2] * d[1], 1 - d[2] * d[2]),
                      z_axis=d, glow=0.6)
        # flames: glowing cones that flicker every frame (see tick)
        for i in range(11):
            core = i >= 8
            a = R.random() * 2 * math.pi
            rr = (0.04 if core else 0.06 + R.random() * 0.12) * k
            w = (0.16 if core else 0.18 + R.random() * 0.12) * k
            h = (0.5 if core else 0.45 + R.random() * 0.45) * k
            actor = self.spawn_actor("Flame_%02d" % i, "Cone", "#ffd27a" if core else "#ff7a1a", 40.0 if core else 25.0)
            actor.static_mesh_component.set_cast_shadow(False)
            self.flames.append((actor, _add(p, [math.cos(a) * rr, math.sin(a) * rr, 0.06 * k]), w, h, R.random() * 10))
        for i in range(16):
            actor = self.spawn_actor("Ember_%02d" % i, "Sphere", "#ff8a2a", 60.0)
            actor.static_mesh_component.set_cast_shadow(False)
            e = [actor, 0.0, 1.0, None, None]
            self._ember(e, R.random() * 2.5)
            self.embers.append(e)
        self.fire_light = self.light("FireLight", _add(p, [0, 0, 0.6 * k]), "#ff7b30", FIRE_CD, 45, shadows=True)

    def _ember(self, e, age):
        R, k = self.rnd, self.k
        a, r = R.random() * 2 * math.pi, R.random() * 0.2 * k
        e[1], e[2] = age, 1.2 + R.random() * 1.8
        e[3] = _add(self.c["fire"]["p"], [math.cos(a) * r, math.sin(a) * r, 0.15 * k])
        e[4] = [(R.random() - 0.5) * 0.3 * k, (R.random() - 0.5) * 0.3 * k, (0.6 + R.random() * 1.1) * k]

    def lantern(self, at, s):
        """A little lantern, its glass centred at `at` (yards)."""
        self.part("Cylinder", LAMP, at, [0.11 * s, 0.11 * s, 0.15 * s], glow=30.0)
        self.part("Cone", METAL, _add(at, [0, 0, 0.11 * s]), [0.15 * s, 0.15 * s, 0.07 * s])
        self.part("Cylinder", METAL, _add(at, [0, 0, -0.09 * s]), [0.14 * s, 0.14 * s, 0.03 * s])

    def lamps(self):
        c, k = self.c, self.k
        # the lantern on the shepherd's hook, just off the left of the starting view: it lights the board
        hk = c["hook"]
        p, h, arm = hk["p"], hk["h"], hk["arm"]
        self.part("Cylinder", METAL, _add(p, [0, 0, h / 2]), [0.026 * k, 0.026 * k, h])
        self.part("Cube", METAL, _add(p, [0, arm / 2, h]), [0.015 * k, arm, 0.015 * k])
        glass = _add(p, [0, arm, h - 0.16 * k])
        self.part("Cylinder", METAL, _add(glass, [0, 0, 0.08 * k]), [0.004 * k, 0.004 * k, 0.16 * k])
        self.lantern(glass, k)
        self.light("HookLight", glass, "#ffb46b", 14, 25)
        # string lights between two trees: a sagging wire with warm bulbs hanging off it
        pts = c["lights"]
        for a, b in zip(pts, pts[1:]):
            d = [b[j] - a[j] for j in range(3)]
            ln = math.sqrt(sum(v * v for v in d))
            self.part("Cube", "#141414", [(a[j] + b[j]) / 2 for j in range(3)], [ln, 0.008 * k, 0.008 * k],
                      x_axis=[v / ln for v in d])
        for q in pts:
            self.part("Sphere", "#ffe0a8", _add(q, [0, 0, -0.07 * k]), [0.09 * k] * 3, glow=40.0)
        mid = pts[len(pts) // 2]
        self.light("StringLight", _add(mid, [0, 0, -0.4 * k]), "#ffc27a", 5, 25)

    def tent(self, t):
        k, p, yaw = self.k, t["p"], t["yaw"]
        L, W, H, glow = t["l"], t["w"], t["h"], t.get("glow", 0.0) * 0.3
        # a lit tent glows faintly through its fabric and warmly at the door
        door, door_glow = ("#ff9a40", t["glow"] * 1.2) if t.get("glow") else ("#1a1410", 0.0)
        if t["kind"] == "dome":
            self.local("Sphere", t["color"], p, yaw, [0, 0, 0], [L, W, 2 * H], glow=glow)
            self.local("Sphere", door, p, yaw, [L / 2 * 0.93, 0, 0], [0.04 * k, W * 0.44, H * 1.24], glow=door_glow)
        else:
            slant = math.hypot(W / 2, H)
            ang = math.atan2(H, W / 2)
            for side in (-1, 1):    # the two sloping sides of an A-frame
                self.local("Cube", t["color"], p, yaw, [0, side * W / 4, H / 2], [L, slant, 0.02 * k],
                           z_axis=(0, side * math.sin(ang), math.cos(ang)), glow=glow)
            self.local("Cube", door, p, yaw, [L / 2 - 0.02 * k, 0, H * 0.3], [0.02 * k, W * 0.4, H * 0.6],
                       glow=door_glow)
            self.local("Cube", t["color"], p, yaw, [-L / 2 + 0.02 * k, 0, H * 0.3], [0.02 * k, W * 0.5, H * 0.5],
                       glow=glow)
            self.local("Cylinder", "#3a3a3a", p, yaw, [0, 0, H], [0.02 * k, 0.02 * k, L * 1.04],
                       z_axis=(1, 0, 0), x_axis=(0, 0, 1))

    def table(self, tb):
        k, p, yaw, wood = self.k, tb["p"], tb["yaw"], "#8a6440"
        L, W, H = tb["l"], tb["w"], tb["h"]
        self.local("Cube", wood, p, yaw, [0, 0, H], [W, L, 0.045 * k])
        for sd in (-1, 1):
            self.local("Cube", wood, p, yaw, [sd * (W / 2 + 0.3 * k), 0, tb["bench"]], [0.26 * k, L, 0.04 * k])
            for end in (-1, 1):    # A-frame legs: feet out under the benches, tops under the table
                lean = sd * 0.5
                self.local("Cube", wood, p, yaw, [sd * 0.32 * k, end * L * 0.36, H / 2], [0.07 * k, 0.05 * k, H * 1.15],
                           z_axis=(-math.sin(lean), 0, math.cos(lean)), x_axis=(math.cos(lean), 0, math.sin(lean)))
        glass = _add(p, _yaw([0, L * 0.2, H + 0.12 * k], yaw))
        self.lantern(glass, k)
        self.light("TableLight", _add(glass, [0, 0, 0.03 * k]), "#ffb46b", 2.5, 20)

    def cooler(self, cl):
        p, yaw = cl["p"], cl["yaw"]
        w, d, h = cl["size"]
        self.local("Cube", "#b8322a", p, yaw, [0, 0, h * 0.41], [d, w, h * 0.82])
        self.local("Cube", "#f0f0ea", p, yaw, [0, 0, h * 0.91], [d * 1.05, w * 1.03, h * 0.18])

    def chair(self, ch):
        p, yaw, s, cloth = ch["p"], ch["yaw"], ch["size"], ch["color"]
        self.local("Cube", cloth, p, yaw, [0, 0, 0.42 * s], [s * 0.85, s, 0.03 * s])
        tilt = 0.25    # the back leans away from the fire
        self.local("Cube", cloth, p, yaw, [-0.45 * s, 0, 0.85 * s], [0.03 * s, s, 0.95 * s],
                   z_axis=(-math.sin(tilt), 0, math.cos(tilt)), x_axis=(math.cos(tilt), 0, math.sin(tilt)))
        for sx in (-1, 1):
            for sz in (-1, 1):
                lean = sz * 0.35
                self.local("Cylinder", METAL, p, yaw, [sz * s * 0.35, sx * s * 0.45, 0.4 * s],
                           [0.04 * s, 0.04 * s, 0.85 * s],
                           z_axis=(-math.sin(lean), 0, math.cos(lean)), x_axis=(math.cos(lean), 0, math.sin(lean)))
            self.local("Cube", METAL, p, yaw, [0, sx * s * 0.52, 0.65 * s], [s * 0.8, 0.08 * s, 0.03 * s])

    # ---------------- actors ----------------

    def spawn_parts(self):
        """One instanced-mesh actor per (shape, colour, glow)."""
        sub = unreal.get_engine_subsystem(unreal.SubobjectDataSubsystem)
        lib = unreal.SubobjectDataBlueprintFunctionLibrary
        base = unreal.load_asset(COLOR_MATERIAL)
        for n, ((shape, color, glow), transforms) in enumerate(sorted(self.parts.items(), key=lambda kv: kv[0])):
            a = _actors().spawn_actor_from_class(unreal.StaticMeshActor, unreal.Vector(0, 0, 0))
            a.set_actor_label("%s%s_%02d" % (CAMP, shape, n))
            a.static_mesh_component.set_mobility(unreal.ComponentMobility.MOVABLE)
            root = sub.k2_gather_subobject_data_for_instance(a)[0]
            handle, _ = sub.add_new_subobject(unreal.AddNewSubobjectParams(
                parent_handle=root, new_class=unreal.InstancedStaticMeshComponent))
            ism = lib.get_associated_object(lib.get_data(handle))
            ism.set_mobility(unreal.ComponentMobility.MOVABLE)
            ism.set_static_mesh(unreal.load_asset(SHAPES + shape))
            mid = ism.create_dynamic_material_instance(0, base)
            mid.set_vector_parameter_value("Color", garage_env.hex_color(color))
            mid.set_scalar_parameter_value("Glow", glow)
            mid.set_scalar_parameter_value("Roughness", 0.9)
            if glow > 5:
                ism.set_cast_shadow(False)    # lamps and bulbs: their lights sit inside them
            ism.add_instances(transforms, False, True)
        self.parts = {}

    def spawn_actor(self, name, shape, color, glow):
        a = _actors().spawn_actor_from_class(unreal.StaticMeshActor, unreal.Vector(0, 0, 0))
        a.set_actor_label(CAMP + name)
        smc = a.static_mesh_component
        smc.set_mobility(unreal.ComponentMobility.MOVABLE)
        smc.set_static_mesh(unreal.load_asset(SHAPES + shape))
        mid = smc.create_dynamic_material_instance(0, unreal.load_asset(COLOR_MATERIAL))
        mid.set_vector_parameter_value("Color", garage_env.hex_color(color))
        mid.set_scalar_parameter_value("Glow", glow)
        return a

    def light(self, name, at, color, real_cd, reach_m, shadows=False):
        a = _actors().spawn_actor_from_class(unreal.PointLight, unreal.Vector(*gs.to_unreal(at)))
        a.set_actor_label(CAMP + name)
        lc = a.point_light_component
        lc.set_mobility(unreal.ComponentMobility.MOVABLE)
        lc.set_editor_property("intensity_units", unreal.LightUnits.CANDELAS)
        lc.set_intensity(_cd(real_cd, self.k))
        lc.set_light_color(garage_env.hex_color(color))
        lc.set_attenuation_radius(reach_m * self.k * gs.YARD_CM)
        lc.set_source_radius(0.05 * self.k * gs.YARD_CM)
        lc.set_cast_shadows(shadows)
        return a

    # ---------------- every frame ----------------

    def tick(self, dt):
        """The fire flickers: the light's brightness, the flames' heights and the rising embers."""
        if self.fire_light is None:
            return
        self.time += dt
        t, k = self.time, self.k
        flick = 0.82 + 0.1 * math.sin(t * 13.1) + 0.06 * math.sin(t * 23.7 + 1.3) + 0.05 * math.sin(t * 7.3 + 0.4)
        self.fire_light.point_light_component.set_intensity(_cd(FIRE_CD * flick, k))
        for actor, base, w, h, ph in self.flames:
            hh = h * (0.72 + 0.18 * math.sin(t * 8.3 + ph) + 0.1 * math.sin(t * 13.7 + ph * 2)
                      + 0.06 * math.sin(t * 21 + ph * 3))
            ww = w * (0.9 + 0.12 * math.sin(t * 7 + ph))
            at = _add(base, [math.sin(t * 3.1 + ph) * 0.025 * k, math.cos(t * 2.7 + ph) * 0.02 * k, hh / 2])
            actor.set_actor_location(unreal.Vector(*gs.to_unreal(at)), False, False)
            actor.set_actor_scale3d(unreal.Vector(*[v * gs.YARD_CM / 100.0 for v in (ww, ww, hh)]))
        for i, e in enumerate(self.embers):
            e[1] += dt
            if e[1] > e[2]:
                self._ember(e, 0.0)
            vel = e[4]
            vel[0] += math.sin(t * 2.3 + i) * 0.4 * k * dt
            vel[1] += math.cos(t * 1.9 + i * 1.7) * 0.4 * k * dt
            e[3] = [e[3][j] + vel[j] * dt for j in range(3)]
            size = 0.022 * k * max(0.0, 1 - e[1] / e[2])
            e[0].set_actor_location(unreal.Vector(*gs.to_unreal(e[3])), False, False)
            e[0].set_actor_scale3d(unreal.Vector(*[max(size, 1e-4) * gs.YARD_CM / 100.0] * 3))

    # ---------------- the night ----------------

    def night(self):
        """A dark night for the camp: a dim moon, the range's tower lights off, fog at the camp's scale.
        Remembers the level's own settings for restore()."""
        k = self.k
        self.saved = []

        def put(setter, value, *old):
            self.saved.append((setter, old))
            setter(*value)
        for a in _actors().get_all_level_actors():
            label = a.get_actor_label()
            if label == "GG_Sun":
                lc = a.light_component
                c = lc.light_color
                put(lc.set_intensity, [0.03], lc.intensity)
                # exactly the colour it had: given as 0-1 bytes, not converted from sRGB
                put(lc.set_light_color, [garage_env.hex_color("#9fb4ff")],
                    unreal.LinearColor(c.r / 255.0, c.g / 255.0, c.b / 255.0, 1.0), False)
            elif label == "GG_SkyLight":
                lc = a.light_component
                put(lc.set_intensity, [0.03], lc.intensity)
            elif label == "GG_Fog":
                fc = a.component
                put(fc.set_fog_density, [0.02 / k * 8], fc.fog_density)
                put(fc.set_fog_height_falloff, [0.2 / k], fc.fog_height_falloff)
                put(fc.set_fog_inscattering_color, [garage_env.hex_color("#070b14")],
                    fc.get_editor_property("fog_inscattering_luminance"))
                put(fc.set_start_distance, [2 * k * gs.YARD_CM], fc.start_distance)
            elif label == "GG_PostProcess":
                # darker than the range's night: auto exposure would brighten the woods right back up
                s = a.get_editor_property("settings")
                put(lambda on, bias, pp=a: _exposure_bias(pp, on, bias), [True, CAMP_EXPOSURE],
                    s.override_auto_exposure_bias, s.auto_exposure_bias)
            elif label.startswith("GG_Tower_") and isinstance(a, unreal.SpotLight):
                lc = a.spot_light_component
                put(lc.set_visibility, [False], lc.is_visible())

    def restore(self):
        for setter, old in reversed(self.saved or []):
            setter(*old)
        self.saved = None
