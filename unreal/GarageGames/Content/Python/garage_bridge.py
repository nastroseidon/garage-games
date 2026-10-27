"""Plays Garage Games shots in the Unreal editor.

Follows the server's live event stream (the same one the browser screens
use). When a Target Range shot arrives, it moves the ball (GG_Ball) and the
shot camera (GG_ShotCamera) along the shot plan, one editor frame at a time,
and looks through that camera in the level viewport.

During a Golf Cornhole game it also puts the server's board and bags in the
level (actors named GG_CH_..., removed when the game ends) and hides the
range targets.

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

import garage_env
import garage_stream as gs

BALL = "GG_Ball"
CAMERA = "GG_ShotCamera"
TRACER_CM = 4.0
TRACER_COLOR = unreal.LinearColor(1.0, 0.85, 0.25, 1.0)
CH = "GG_CH_"                       # Golf Cornhole actors
COLOR_MATERIAL = "/Game/Garage/M_GarageColor"


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


def _hide(actor, hidden):
    actor.set_actor_hidden_in_game(hidden)
    actor.set_is_temporarily_hidden_in_editor(hidden)


class CornholeSet:
    """The cornhole board and bags in the open level (sizes and positions come from the server, in yards)."""

    def __init__(self):
        self.key = None
        self.bags = []      # (actor, dynamic material)
        self.bag_size = (0.0, 0.0)

    def _spawn(self, label, shape, color):
        a = _actors().spawn_actor_from_class(unreal.StaticMeshActor, unreal.Vector(0, 0, 0))
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
        self.bag_size = (board["bag"], board["bag_t"])
        # all 8 bags up front: spawning them mid-throw stalls a frame
        while len(self.bags) < 8:
            actor, mid = self._spawn(CH + "Bag_%02d" % len(self.bags), "Cube", "#ffffff")
            _hide(actor, True)
            self.bags.append((actor, mid))
        for a in _actors().get_all_level_actors():
            if a.get_actor_label().startswith("GG_Target_"):
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

    def clear(self):
        for a in _actors().get_all_level_actors():
            label = a.get_actor_label()
            if label.startswith(CH):
                _actors().destroy_actor(a)
            elif label.startswith("GG_Target_"):
                _hide(a, False)
        self.key, self.bags = None, []


class Bridge:
    def __init__(self, host="127.0.0.1", port=8080):
        self.stream = gs.EventStream(host, port)
        self.stream.on_change = lambda up: log("server %s (%s:%d)" % (
            "connected" if up else "not reachable, retrying", host, port))
        self.handle = None
        self.player = None
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
            log("listening for shots from the Garage Games server")

    def stop(self):
        if self.handle is not None:
            unreal.unregister_slate_post_tick_callback(self.handle)
            self.handle = None
        self.stream.close()
        log("stopped")

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
