"""Plays Garage Games shots in the Unreal editor.

Follows the server's live event stream (the same one the browser screens
use). When a Target Range shot arrives, it moves the ball (GG_Ball) and the
shot camera (GG_ShotCamera) along the shot plan, one editor frame at a time,
and looks through that camera in the level viewport.

During a Golf Cornhole game it also puts the server's board and bags in the
level, with the campsite in the woods around it at dusk (garage_camp.py).
Those actors are named GG_CH_..., transient (saving the map never stores them)
and removed when the game ends; the range is hidden meanwhile and its lighting
put back afterwards. Saving the map mid-game puts the range's own look back
for the save and the cornhole look straight after.

Started automatically by init_unreal.py when the project opens. From the
editor's Python console:
    import garage_bridge
    garage_bridge.status()     # connected? last shot? smoothness
    garage_bridge.stop() / garage_bridge.start()
"""

import json
import math
import time

import unreal

import garage_camp
import garage_env
import garage_stream as gs

BALL = "GG_Ball"
CAMERA = "GG_ShotCamera"
TRACER_CM = 4.0
TRACER_COLOR = unreal.LinearColor(1.0, 0.85, 0.25, 1.0)
CH = "GG_CH_"                       # Golf Cornhole actors
COLOR_MATERIAL = "/Game/Garage/M_GarageColor"
# A bag in the hole: the Free Spells "LevelUp" burst (a Fab pack, never committed; nothing plays without it),
# in the bag's colour, sized to the hole, for HOLE_FX_S seconds
HOLE_FX = "/Game/Free_Spells/VFX_Niagara/NS_Free_Spells_LevelUp"
HOLE_FX_COLORS = ("Color_Arrow", "Color_Ray", "Color_Sparks1", "Color_Sparks2", "Color_Wave")
HOLE_FX_SIZE = 3.0     # where its pieces land: hole radii per metre of the effect's own layout
HOLE_FX_SCALE = 5.0    # how big its rays, flames and sparks are (the effect's own Scale_All)
HOLE_FX_GLOW = 6.0     # the colour's brightness (the effect glows)
HOLE_FX_S = 4.0


def log(msg):
    unreal.log("[Garage Games] " + msg)


def editor_world():
    return unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()


def find_actor(label):
    for a in unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors():
        if a.get_actor_label() == label:
            return a
    return None


def vec(p):
    return unreal.Vector(p[0], p[1], p[2])


def _actors():
    return unreal.get_editor_subsystem(unreal.EditorActorSubsystem)


def _world_actors():
    """Every actor in the level, transient ones too (the editor's own list leaves those out)."""
    return unreal.GameplayStatics.get_all_actors_of_class(editor_world(), unreal.Actor)


def _hide(actor, hidden):
    actor.set_actor_hidden_in_game(hidden)
    actor.set_is_temporarily_hidden_in_editor(hidden)


def _range_dressing(label):
    """The driving range: hidden for Golf Cornhole, which has its own ground and woods.
    The towers' spot lights are turned off with the camp's evening instead (garage_camp)."""
    if label.startswith(("GG_Target_", "GG_Marker_", "GG_Stripe_", "GG_Tree_", "GG_Rock_", "GG_Hill_")):
        return True
    if label in ("GG_Rough", "GG_TeeBox", "GG_HittingMat"):
        return True
    return label.startswith("GG_Tower_") and label.endswith(("_Pole", "_Lamp"))


class CornholeSet:
    """The cornhole board and bags in the open level (sizes and positions come from the server, in yards)."""

    def __init__(self):
        self.key = None
        self.bags = []      # (actor, dynamic material)
        self.bag_size = (0.0, 0.0)
        self.camp = None
        self.hole = None
        self.fx = []        # (actor, seconds left)

    def _spawn(self, label, shape, color):
        a = _actors().spawn_actor_from_class(unreal.StaticMeshActor, unreal.Vector(0, 0, 0), transient=True)
        a.set_actor_label(label)
        smc = a.static_mesh_component
        smc.set_mobility(unreal.ComponentMobility.MOVABLE)
        smc.set_static_mesh(unreal.load_asset("/Engine/BasicShapes/" + shape))
        mid = smc.create_dynamic_material_instance(0, unreal.load_asset(COLOR_MATERIAL))
        mid.set_vector_parameter_value("Color", garage_env.hex_color(color))
        return a, mid

    def _place(self, actor, center_yd, size_yd, pitch=0.0, yaw=0.0):
        actor.set_actor_location(vec(gs.to_unreal(center_yd)), False, False)
        actor.set_actor_rotation(unreal.MathLibrary.compose_rotators(unreal.Rotator(yaw=yaw),
                                                                     unreal.Rotator(pitch=pitch)), False)
        actor.set_actor_scale3d(unreal.Vector(*[max(v, 1e-4) * gs.YARD_CM / 100.0 for v in size_yd]))

    def _place_axes(self, actor, center_yd, size_yd, x_axis, z_axis):
        """Place a basic shape with its X and Z axes along the given directions (yards)."""
        actor.set_actor_location(vec(gs.to_unreal(center_yd)), False, False)
        actor.set_actor_rotation(unreal.MathLibrary.make_rot_from_xz(vec(x_axis), vec(z_axis)), False)
        actor.set_actor_scale3d(unreal.Vector(*[max(v, 1e-4) * gs.YARD_CM / 100.0 for v in size_yd]))

    def _sign(self, sg):
        """The crooked yardage sign: a plank on a post, the number painted on in black strokes."""
        u, v, n, base = sg["u"], sg["v"], sg["n"], sg["base"]

        def at(a, b, c):
            return [base[i] + a * u[i] + b * v[i] + c * n[i] for i in range(3)]
        mid = sg["post_h"] + sg["h"] / 2
        plank, _ = self._spawn(CH + "Sign_Plank", "Cube", "#a8773f")
        self._place_axes(plank, at(0, mid, 0), [sg["w"], sg["t"], sg["h"]], u, v)
        post_len = sg["post_h"] + sg["h"] * 0.85
        post, _ = self._spawn(CH + "Sign_Post", "Cube", "#7a5530")
        self._place_axes(post, at(0, post_len / 2, -sg["t"] / 2 - sg["post_w"] * 0.4),
                         [sg["post_w"], sg["post_w"] * 0.8, post_len], u, v)
        face = sg["t"] / 2 + sg["t"] * 0.05
        k = 0
        for stroke in sg["strokes"]:
            pts, w = stroke["pts"], stroke["w"]
            for (a0, b0), (a1, b1) in zip(pts, pts[1:]):
                da, db = a1 - a0, b1 - b0
                ln = math.hypot(da, db)
                if ln < 1e-6:
                    continue
                d = [(da * u[i] + db * v[i]) / ln for i in range(3)]
                seg, _ = self._spawn(CH + "Sign_Paint_%02d" % k, "Cube", "#1a120a")
                self._place_axes(seg, at((a0 + a1) / 2, mid + (b0 + b1) / 2, face), [ln + w * 0.9, w, sg["t"] * 0.08],
                                 d, n)
                k += 1

    def show(self, board):
        key = json.dumps(board, sort_keys=True)
        if key == self.key:
            return
        self.clear()
        self.key = key
        s = math.radians(board["slope_deg"])
        n = [-math.sin(s), 0.0, math.cos(s)]           # the top's normal
        top = board["center"]

        def along_n(p, d):
            return [p[0] + n[0] * d, p[1] + n[1] * d, p[2] + n[2] * d]
        L, W, fr, bt = board["length"], board["width"], board["frame"], board["bag_t"]
        frame, _ = self._spawn(CH + "Frame", "Cube", "#8a5a2b")
        self._place(frame, along_n(top, -fr / 2 - 0.002 * L), [L, W, fr], board["slope_deg"])
        paint, _ = self._spawn(CH + "Top", "Cube", "#1d4f91")
        self._place(paint, along_n(top, -bt * 0.15), [L * 0.97, W * 0.94, bt * 0.3], board["slope_deg"])
        hole, _ = self._spawn(CH + "Hole", "Cylinder", "#050505")
        self._place(hole, along_n(board["hole"], 0.002 * L), [2 * board["hole_r"], 2 * board["hole_r"], bt * 0.05],
                    board["slope_deg"])
        for side in (-1, 1):
            leg, _ = self._spawn(CH + "Leg_%d" % side, "Cube", "#8a5a2b")
            h = board["back"][2] - 1.5 * fr   # up to the underside of the frame
            self._place(leg, [board["back"][0] - 1.5 * fr, side * W * 0.42, h / 2], [fr * 0.8, fr * 0.8, h])
        if board.get("sign"):
            self._sign(board["sign"])
        if board.get("camp"):
            self.camp = garage_camp.Camp(board["camp"])
            self.camp.build()
            self.camp.dusk()
        self.bag_size = (board["bag"], board["bag_t"])
        self.hole, self.hole_r = board["hole"], board["hole_r"]
        # all 8 bags up front: spawning them mid-throw stalls a frame
        while len(self.bags) < 8:
            actor, mid = self._spawn(CH + "Bag_%02d" % len(self.bags), "Cube", "#ffffff")
            _hide(actor, True)
            self.bags.append((actor, mid))
        for a in _actors().get_all_level_actors():
            if _range_dressing(a.get_actor_label()):
                _hide(a, True)

    def place_bags(self, bags):
        """bags: [(pose [x, y, z, yaw, pitch, visible, size], colour)]"""
        if self.key is None:
            return
        while len(self.bags) < len(bags):
            self.bags.append(self._spawn(CH + "Bag_%02d" % len(self.bags), "Cube", "#ffffff"))
        side, thick = self.bag_size
        for i, (actor, mid) in enumerate(self.bags):
            if i >= len(bags) or not bags[i][0][5]:
                _hide(actor, True)
                continue
            pose, color = bags[i]
            k = pose[6] if len(pose) > 6 else 1.0
            self._place(actor, pose[:3], [side * k, side * k, thick * k], pose[4], pose[3])
            mid.set_vector_parameter_value("Color", garage_env.hex_color(color))
            _hide(actor, False)

    def _dressing(self):
        return [a for a in _actors().get_all_level_actors() if _range_dressing(a.get_actor_label())]

    def suspend(self):
        """Just before the map is saved: the level's own lighting and range back (the board and the
        camp are transient, so they stay out of the saved map by themselves)."""
        if self.key is None:
            return
        if self.camp:
            self.camp.restore()
        for a in self._dressing():
            _hide(a, False)

    def resume(self):
        """Straight after the save: the cornhole look again."""
        if self.key is None:
            return
        if self.camp:
            self.camp.dusk()
        for a in self._dressing():
            _hide(a, True)

    def tick(self, dt):
        if self.camp:
            self.camp.tick(dt)
        for item in list(self.fx):
            item[1] -= dt
            if item[1] <= 0:
                self.fx.remove(item)
                _actors().destroy_actor(item[0])

    def in_the_hole(self, color):
        """A bag just dropped into the hole: a burst of the bag's colour rising out of it."""
        if self.hole is None or not unreal.EditorAssetLibrary.does_asset_exist(HOLE_FX):
            return
        a = _actors().spawn_actor_from_class(unreal.NiagaraActor, vec(gs.to_unreal(self.hole)))
        a.set_actor_label("%sHoleFX_%d" % (CH, len(self.fx)))
        s = self.hole_r * HOLE_FX_SIZE * gs.YARD_CM / 100.0
        a.set_actor_scale3d(unreal.Vector(s, s, s))
        fx = a.niagara_component
        fx.set_asset(unreal.load_asset(HOLE_FX))
        c = garage_env.hex_color(color, HOLE_FX_GLOW)
        for name in HOLE_FX_COLORS:
            fx.set_variable_linear_color(name, c)
        fx.set_variable_float("Scale_All", HOLE_FX_SCALE)
        fx.activate(True)
        self.fx.append([a, HOLE_FX_S])

    def clear(self):
        if self.camp:
            self.camp.restore()
            self.camp = None
        for a in _world_actors():
            label = a.get_actor_label()
            if label.startswith(CH):
                _actors().destroy_actor(a)
            elif _range_dressing(label):
                _hide(a, False)
        self.key, self.bags, self.fx, self.hole = None, [], [], None


class Bridge:
    def __init__(self, host="127.0.0.1", port=8080):
        self.stream = gs.EventStream(host, port)
        self.stream.on_change = lambda up: log("server %s (%s:%d)" % (
            "connected" if up else "not reachable, retrying", host, port))
        self.handle = None
        self.player = None
        self.hole_drops = []      # Golf Cornhole: (seconds, colour) still to play this shot
        self.start_time = 0.0
        self.last_tracer = None
        self.stats = None
        self.last_summary = None
        self.shots = 0
        self.home = None          # the camera's resting view (the range overview)
        self.cornhole = CornholeSet()
        self.idle = None          # Golf Cornhole's resting view (the golfer's), or None
        self.camera = self.ball = None

    # ---------------- lifecycle ----------------

    def start(self):
        if self.handle is None:
            self.handle = unreal.register_slate_post_tick_callback(self._tick)
            les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
            les.on_pre_save_world.add_callable(self._pre_save)
            les.on_post_save_world.add_callable(self._post_save)
            log("listening for shots from the Garage Games server")

    def stop(self):
        if self.handle is not None:
            unreal.unregister_slate_post_tick_callback(self.handle)
            self.handle = None
            les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
            les.on_pre_save_world.remove_callable(self._pre_save)
            les.on_post_save_world.remove_callable(self._post_save)
        self.stream.close()
        log("stopped")

    def _pre_save(self, save_flags, world):
        try:
            self.cornhole.suspend()
        except Exception as exc:  # never get in the way of a save
            unreal.log_error("[Garage Games] before saving: %r" % exc)

    def _post_save(self, save_flags, world, success):
        try:
            self.cornhole.resume()
        except Exception as exc:
            unreal.log_error("[Garage Games] after saving: %r" % exc)

    # ---------------- every editor frame ----------------

    def _tick(self, dt):
        try:
            for name, data in self.stream.poll():
                if name == "shot":
                    ev = gs.parse_shot(data)
                    if ev:
                        self.play(ev)
                elif name == "state":
                    self.on_state(json.loads(data))
            self.cornhole.tick(dt)
            if self.player:
                self.stats.add(dt)
                self._apply(time.perf_counter() - self.start_time)
        except Exception as exc:  # never let an error kill the editor tick
            unreal.log_error("[Garage Games] %r" % exc)
            self.player = None

    def on_state(self, state):
        """Golf Cornhole: show the board and bags between throws; tidy up when the game ends."""
        extra = state.get("extra") if state.get("active") else None
        if not (extra and state.get("game") == "cornhole"):
            if self.cornhole.key is not None:
                self.cornhole.clear()
                self.idle = None
                self._go_home()
            return
        self.cornhole.show(extra["board"])
        self.idle = extra["idle_camera"]
        if not self.player:
            self.cornhole.place_bags([(b["pose"], b["color"]) for b in extra["bags"]])
            self._go_home()

    def play(self, ev):
        self.ball = find_actor(BALL)
        self.camera = find_actor(CAMERA)
        if not self.ball or not self.camera:
            unreal.log_warning("[Garage Games] the open level has no %s / %s. Open Maps/Range "
                               "(or run build_range.py)." % (BALL, CAMERA))
            return
        if self.home is None:
            cc = self.camera.camera_component
            self.home = (self.camera.get_actor_location(), self.camera.get_actor_rotation(), cc.field_of_view)
        self.player = gs.ShotPlayer(ev["plan"])
        self.hole_drops = self.player.hole_drops()
        if self.player.cornhole:
            self.cornhole.show(self.player.cornhole["board"])
            self.idle = ev["state"]["extra"]["idle_camera"]
        self.start_time = time.perf_counter()
        self.last_tracer = None
        self.stats = gs.FrameStats()
        self.shots += 1
        unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).pilot_level_actor(self.camera)
        log("shot %s: %s coverage, %d cuts, %.1fs" % (
            ev["shot"].get("id"), ev["plan"]["mode"], len(ev["plan"]["cuts"]), self.player.total_s))

    def _apply(self, wall):
        p = self.player
        pos, tracer, visible = p.ball(wall)
        cpos, look, vfov, _ = p.camera(wall)
        ball_cm, cam_cm = gs.to_unreal(pos), gs.to_unreal(cpos)
        pitch, yaw, roll = gs.look_rotation(cam_cm, gs.to_unreal(look))
        self.camera.set_actor_location_and_rotation(vec(cam_cm), unreal.Rotator(roll=roll, pitch=pitch, yaw=yaw),
                                                    False, False)
        self.camera.camera_component.set_field_of_view(gs.horizontal_fov(vfov, p.aspect))
        if p.cornhole:
            self.cornhole.place_bags(p.bags(wall))
            while self.hole_drops and self.hole_drops[0][0] <= wall:
                self.cornhole.in_the_hole(self.hole_drops.pop(0)[1])
            _hide(self.ball, True)  # the bags are the ball
            if p.done(wall):
                self.last_summary = self.stats.summary()
                log("shot finished: %s" % json.dumps(self.last_summary))
                self.player = None
                self._go_home()
            return
        radius = gs.ball_radius_cm(math.dist(ball_cm, cam_cm))
        self.ball.set_actor_location(vec([ball_cm[0], ball_cm[1], max(ball_cm[2], 0) + radius]), False, False)
        scale = radius / 50.0  # the engine's sphere is 100 cm across
        self.ball.set_actor_scale3d(unreal.Vector(scale, scale, scale))
        self.ball.set_actor_hidden_in_game(not visible)
        self.ball.set_is_temporarily_hidden_in_editor(not visible)
        if tracer < 1 and self.last_tracer is not None:
            unreal.SystemLibrary.draw_debug_line(editor_world(), vec(self.last_tracer), vec(ball_cm), TRACER_COLOR,
                                                 p.total_s - wall + 2.0, TRACER_CM)
        self.last_tracer = ball_cm if tracer < 1 else None
        if p.done(wall):
            self.last_summary = self.stats.summary()
            log("shot finished: %s" % json.dumps(self.last_summary))
            self.player = None
            self._go_home()

    def _go_home(self):
        if self.idle and self.camera:
            pos, look = gs.to_unreal(self.idle["pos"]), gs.to_unreal(self.idle["look"])
            pitch, yaw, roll = gs.look_rotation(pos, look)
            self.camera.set_actor_location_and_rotation(vec(pos), unreal.Rotator(roll=roll, pitch=pitch, yaw=yaw),
                                                        False, False)
            self.camera.camera_component.set_field_of_view(gs.horizontal_fov(self.idle["fov"], 12 / 9))
            unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).pilot_level_actor(self.camera)
            if self.ball:
                _hide(self.ball, True)
            return
        if self.home:
            loc, rot, fov = self.home
            self.camera.set_actor_location_and_rotation(loc, rot, False, False)
            self.camera.camera_component.set_field_of_view(fov)
            self.ball.set_actor_location(unreal.Vector(0, 0, 2.7), False, False)
            self.ball.set_actor_scale3d(unreal.Vector(0.054, 0.054, 0.054))
            _hide(self.ball, False)


_bridge = None


def start(host="127.0.0.1", port=8080):
    global _bridge
    if _bridge is None:
        _bridge = Bridge(host, port)
    _bridge.start()
    return _bridge


def stop():
    if _bridge:
        _bridge.stop()


def status():
    b = _bridge
    info = {"running": bool(b and b.handle is not None), "connected": bool(b and b.stream.connected),
            "shots_played": b.shots if b else 0, "playing": bool(b and b.player),
            "last_shot_smoothness": b.last_summary if b else None}
    log(json.dumps(info))
    return info
