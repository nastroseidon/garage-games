"""Garage Games: party games driven by a launch monitor over Open Connect.

Run:  python server.py
Then open http://localhost:8080 on the projector screen and point the
launch monitor's Open Connect output at this PC (default 127.0.0.1:921).

Standard library only - no installs needed beyond Python 3.9+.
"""

import argparse
import json
import os
import queue
import random
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import director
import games
from flight import simulate
from openconnect import OpenConnectServer
from session import GameSession

HERE = os.path.dirname(os.path.abspath(__file__))
WEB_DIR = os.path.join(HERE, "web")
LOG_DIR = os.path.join(HERE, "logs")
CONTENT_TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript",
                 ".css": "text/css", ".png": "image/png", ".svg": "image/svg+xml",
                 ".ico": "image/x-icon", ".json": "application/json"}


class Hub:
    """Fan-out of events to every connected browser (Server-Sent Events)."""

    def __init__(self):
        self._clients = set()
        self._lock = threading.Lock()
        self.status = {"connected": False, "ready": False,
                       "ball_detected": False, "device": "", "last_seen": None}

    def subscribe(self):
        q = queue.Queue(maxsize=100)
        with self._lock:
            self._clients.add(q)
        return q

    def unsubscribe(self, q):
        with self._lock:
            self._clients.discard(q)

    def publish(self, event, data):
        payload = "event: %s\ndata: %s\n\n" % (event, json.dumps(data))
        with self._lock:
            clients = list(self._clients)
        for q in clients:
            try:
                q.put_nowait(payload)
            except queue.Full:
                pass


class ShotLog:
    """Appends every raw Open Connect message to logs/shots-YYYYMMDD.jsonl."""

    def __init__(self, enabled):
        self.enabled = enabled
        self._lock = threading.Lock()
        if enabled:
            os.makedirs(LOG_DIR, exist_ok=True)

    def write(self, kind, payload):
        if not self.enabled:
            return
        name = time.strftime("shots-%Y%m%d.jsonl")
        line = json.dumps({"time": time.strftime("%Y-%m-%d %H:%M:%S"),
                           "kind": kind, "data": payload})
        with self._lock, open(os.path.join(LOG_DIR, name), "a",
                              encoding="utf-8") as f:
            f.write(line + "\n")


hub = Hub()
shot_log = ShotLog(enabled=True)
session = GameSession()
_shot_counter = 0
_shot_lock = threading.Lock()   # also guards `session`


def publish_state(reason):
    with _shot_lock:
        state = session.snapshot()
    hub.publish("state", dict(state, reason=reason))


def handle_shot(shot, raw=None, source="launch_monitor"):
    global _shot_counter
    flight = simulate(shot["speed_mph"], shot["vla_deg"], shot["hla_deg"],
                      shot["spin_rpm"], shot["spin_axis_deg"])
    with _shot_lock:
        _shot_counter += 1
        shot_id = _shot_counter
        full = dict(shot, id=shot_id, source=source, flight=flight)
        event = session.apply_shot(full)
    shot_log.write("shot", {"source": source, "shot": shot,
                            "carry_yd": flight["carry_yd"],
                            "offline_yd": flight["offline_yd"]})
    hub.publish("shot", event)
    print("Shot %d (%s): %.1f mph, launch %.1f, dir %.1f, spin %d @ %.1f"
          " -> carry %.1f yd, %.1f yd %s" % (
              shot_id, source, shot["speed_mph"], shot["vla_deg"],
              shot["hla_deg"], shot["spin_rpm"], shot["spin_axis_deg"],
              flight["carry_yd"], abs(flight["offline_yd"]),
              "right" if flight["offline_yd"] >= 0 else "left"), flush=True)


def handle_status(status):
    hub.status = status
    hub.publish("status", status)
    print("Launch monitor: %s%s" % (
        "connected" if status["connected"] else "disconnected",
        ", ready" if status["ready"] else ""), flush=True)


def random_test_shot(opts):
    """A plausible shot for testing without swinging."""
    kind = opts.get("kind") or random.choice(["wedge", "iron", "driver", "chip"])
    base = {"chip": (35, 28, 4500), "wedge": (75, 28, 8500),
            "iron": (110, 18, 6500), "driver": (140, 12, 3000)}.get(
                kind, (110, 18, 6500))
    return {
        "shot_number": None, "device": "Test shot",
        "speed_mph": float(opts.get("speed_mph", base[0] * random.uniform(0.85, 1.1))),
        "vla_deg": float(opts.get("vla_deg", base[1] + random.uniform(-3, 3))),
        "hla_deg": float(opts.get("hla_deg", random.uniform(-4, 4))),
        "spin_rpm": float(opts.get("spin_rpm", base[2] * random.uniform(0.85, 1.15))),
        "spin_axis_deg": float(opts.get("spin_axis_deg", random.uniform(-12, 12))),
        "reported_carry": None, "club_speed_mph": None,
    }


class Handler(BaseHTTPRequestHandler):
    server_version = "GarageGames/1.0"

    def log_message(self, fmt, *args):
        pass  # keep the console for shot output

    def _json(self, code, data):
        body = json.dumps(data).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path == "/events":
            return self._events()
        if path == "/api/status":
            return self._json(200, hub.status)
        if path == "/api/games":
            return self._json(200, {"games": [g.info() for g in games.GAMES],
                                    "targets": games.TARGETS, "inner": games.INNER,
                                    "center": games.CENTER,
                                    "idle_camera": director.idle_camera()})
        if path == "/api/state":
            with _shot_lock:
                return self._json(200, session.snapshot())
        if path == "/":
            path = "/index.html"
        full = os.path.realpath(os.path.join(WEB_DIR, path.lstrip("/")))
        if not full.startswith(os.path.realpath(WEB_DIR) + os.sep) or \
                not os.path.isfile(full):
            return self._json(404, {"error": "not found"})
        with open(full, "rb") as f:
            body = f.read()
        self.send_response(200)
        self.send_header("Content-Type", CONTENT_TYPES.get(
            os.path.splitext(full)[1], "application/octet-stream"))
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        try:
            opts = json.loads(self.rfile.read(length) or b"{}")
            if not isinstance(opts, dict):
                raise ValueError("expected an object")
        except ValueError as exc:
            return self._json(400, {"error": str(exc)})
        if self.path == "/api/test-shot":
            try:
                if not opts.get("kind"):
                    with _shot_lock:
                        opts["kind"] = session.test_kind()
                        for k, v in session.test_shot().items():
                            opts.setdefault(k, v)
                shot = random_test_shot(opts)
            except (ValueError, TypeError) as exc:
                return self._json(400, {"error": str(exc)})
            handle_shot(shot, source="test")
            return self._json(200, {"ok": True})
        actions = {
            "/api/game/start": lambda: session.start(opts.get("game"), opts.get("players"),
                                                     opts.get("rounds"), opts.get("camera"),
                                                     opts.get("options")),
            "/api/game/undo": session.undo,
            "/api/game/skip": session.skip,
            "/api/game/end": session.end,
            "/api/settings": lambda: session.set_camera(opts.get("camera")),
        }
        if self.path not in actions:
            return self._json(404, {"error": "not found"})
        try:
            with _shot_lock:
                actions[self.path]()
        except (ValueError, TypeError) as exc:
            return self._json(400, {"error": str(exc)})
        publish_state(self.path.rsplit("/", 1)[1])
        return self._json(200, {"ok": True})

    def _events(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        q = hub.subscribe()
        try:
            with _shot_lock:
                state = dict(session.snapshot(), reason="sync")
            self.wfile.write(("event: status\ndata: %s\n\nevent: state\ndata: %s\n\n" %
                              (json.dumps(hub.status), json.dumps(state))).encode("utf-8"))
            self.wfile.flush()
            while True:
                try:
                    payload = q.get(timeout=15)
                except queue.Empty:
                    payload = ": keepalive\n\n"
                self.wfile.write(payload.encode("utf-8"))
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass
        finally:
            hub.unsubscribe(q)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--oc-host", default="127.0.0.1",
                        help="Open Connect listen address (use 0.0.0.0 if the "
                             "launch monitor software runs on another PC)")
    parser.add_argument("--oc-port", type=int, default=921,
                        help="Open Connect port (default 921, same as GSPro)")
    parser.add_argument("--web-port", type=int, default=8080,
                        help="Port for the game screen (default 8080)")
    parser.add_argument("--no-log", action="store_true",
                        help="Don't write shots to the logs folder")
    parser.add_argument("--no-browser", action="store_true",
                        help="Don't open the game screen automatically")
    args = parser.parse_args()

    shot_log.enabled = not args.no_log
    if shot_log.enabled:
        os.makedirs(LOG_DIR, exist_ok=True)

    oc = OpenConnectServer(args.oc_host, args.oc_port, handle_shot,
                           handle_status,
                           on_raw=lambda m: shot_log.write("raw", m))
    try:
        oc.start()
    except OSError as exc:
        raise SystemExit(
            "Could not listen for the launch monitor on port %d (%s).\n"
            "Close GSPro / MuniGolfSim / other sim software first - only one "
            "program can use the Open Connect port at a time."
            % (args.oc_port, exc))

    web = ThreadingHTTPServer(("127.0.0.1", args.web_port), Handler)
    web.daemon_threads = True
    print("Garage Games is running.")
    print("  Game screen:   http://localhost:%d" % args.web_port)
    print("  Launch monitor: send Open Connect shots to %s:%d" %
          ("127.0.0.1" if args.oc_host == "0.0.0.0" else args.oc_host,
           args.oc_port))
    print("Press Ctrl+C to quit.\n", flush=True)
    if not args.no_browser:
        webbrowser.open("http://localhost:%d" % args.web_port)
    try:
        web.serve_forever()
    except KeyboardInterrupt:
        print("\nBye!")


if __name__ == "__main__":
    main()
