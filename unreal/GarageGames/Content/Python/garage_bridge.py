"""Plays Garage Games shots in the Unreal editor.

Follows the server's live event stream (the same one the browser screens
use). When a Target Range shot arrives, it moves the ball (GG_Ball) and the
shot camera (GG_ShotCamera) along the shot plan, one editor frame at a time,
and looks through that camera in the level viewport.

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

import garage_stream as gs

BALL = "GG_Ball"
CAMERA = "GG_ShotCamera"
TRACER_CM = 4.0
TRACER_COLOR = unreal.LinearColor(1.0, 0.85, 0.25, 1.0)


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
            if self.player:
                self.stats.add(dt)
                self._apply(time.perf_counter() - self.start_time)
        except Exception as exc:  # never let an error kill the editor tick
            unreal.log_error("[Garage Games] %r" % exc)
            self.player = None

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
        self.camera.camera_component.set_field_of_view(gs.horizontal_fov(vfov))
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
        if self.home:
            loc, rot, fov = self.home
            self.camera.set_actor_location_and_rotation(loc, rot, False, False)
            self.camera.camera_component.set_field_of_view(fov)
            self.ball.set_actor_location(unreal.Vector(0, 0, 2.7), False, False)
            self.ball.set_actor_scale3d(unreal.Vector(0.054, 0.054, 0.054))
            self.ball.set_is_temporarily_hidden_in_editor(False)


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
