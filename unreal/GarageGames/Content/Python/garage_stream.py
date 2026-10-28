"""Garage Games live stream and shot plan playback, without Unreal.

Everything here is plain Python (no `import unreal`), so it can be tested
outside the editor. garage_bridge.py uses it inside Unreal.

- EventStream: a non-blocking client for the server's /events stream
  (Server-Sent Events). Call poll() once per frame; it never waits.
- ShotPlayer: plays back a shot plan message (see director.to_message in
  the repo root), the same way web/shotplan.js does in the browser.
- Unreal coordinates: the plan is in yards (x downrange, y right, z up);
  Unreal uses centimetres with X forward, Y right, Z up.
- FrameStats: how smoothly a shot played (frame times).
"""

import json
import math
import socket
import time

YARD_CM = 91.44


# ---------------- Server-Sent Events ----------------

class SseParser:
    """Turns raw bytes from /events (HTTP headers first) into (event, data) pairs."""

    def __init__(self):
        self._buf = b""
        self._headers_done = False
        self.status = None

    def feed(self, data):
        self._buf += data
        events = []
        if not self._headers_done:
            end = self._buf.find(b"\r\n\r\n")
            if end < 0:
                return events
            first = self._buf.split(b"\r\n", 1)[0].decode("latin-1")
            parts = first.split(" ")
            self.status = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else None
            self._buf = self._buf[end + 4:]
            self._headers_done = True
        self._buf = self._buf.replace(b"\r\n", b"\n")
        while True:
            end = self._buf.find(b"\n\n")
            if end < 0:
                break
            block, self._buf = self._buf[:end], self._buf[end + 2:]
            name, data_lines = "message", []
            for line in block.decode("utf-8").split("\n"):
                if not line or line.startswith(":"):
                    continue  # keep-alive comment
                field, _, value = line.partition(":")
                value = value[1:] if value.startswith(" ") else value
                if field == "event":
                    name = value
                elif field == "data":
                    data_lines.append(value)
            if data_lines:
                events.append((name, "\n".join(data_lines)))
        return events


class EventStream:
    """Follows http://host:port/events without ever blocking the caller.

    poll() returns the events that arrived since the last call. If the
    server isn't running (or restarts), it keeps retrying every few seconds.
    """

    def __init__(self, host="127.0.0.1", port=8080, path="/events", retry_s=2.0, clock=time.monotonic):
        self.host, self.port, self.path = host, port, path
        self.retry_s = retry_s
        self.clock = clock
        self.sock = None
        self.parser = None
        self.connected = False
        self._next_try = 0.0
        self.on_change = None  # optional callback(connected: bool)

    def _set_connected(self, value):
        if value != self.connected:
            self.connected = value
            if self.on_change:
                self.on_change(value)

    def _open(self):
        self._next_try = self.clock() + self.retry_s
        try:
            s = socket.create_connection((self.host, self.port), timeout=0.25)
            s.sendall(("GET %s HTTP/1.1\r\nHost: %s:%d\r\nAccept: text/event-stream\r\n"
                       "Cache-Control: no-cache\r\n\r\n" % (self.path, self.host, self.port)).encode("ascii"))
            s.setblocking(False)
        except OSError:
            return
        self.sock, self.parser = s, SseParser()

    def close(self):
        if self.sock:
            try:
                self.sock.close()
            except OSError:
                pass
        self.sock = None
        self._set_connected(False)

    def poll(self, max_bytes=4 * 1024 * 1024):
        if self.sock is None:
            if self.clock() >= self._next_try:
                self._open()
            if self.sock is None:
                return []
        events, read = [], 0
        while read < max_bytes:
            try:
                chunk = self.sock.recv(65536)
            except (BlockingIOError, InterruptedError):
                break
            except OSError:
                self.close()
                break
            if not chunk:  # server closed the stream
                self.close()
                break
            read += len(chunk)
            events.extend(self.parser.feed(chunk))
        if self.sock is not None and self.parser.status is not None:
            if self.parser.status != 200:
                self.close()
            else:
                self._set_connected(True)
        return events


# ---------------- shot plan playback ----------------

def _lerp(a, b, t):
    return a + (b - a) * t


class ShotPlayer:
    """One shot plan. Positions are [downrange, right, height] in yards."""

    def __init__(self, msg):
        self.msg = msg
        self.fps = msg["fps"]
        self.ball_frames = msg["ball"]
        self.cam_frames = msg["camera"]
        self.n = len(self.ball_frames)
        self.total_s = msg["total_ms"] / 1000.0
        self.rest_s = msg["rest_ms"] / 1000.0
        self.in_cup = msg["in_cup"]
        self.cuts = msg["cuts"]
        self.cornhole = msg.get("cornhole")   # Golf Cornhole: the board and every bag
        self.aspect = (self.cornhole or {}).get("aspect", 16 / 9)

    def _at(self, wall):
        f = max(0.0, wall * self.fps)
        i = min(self.n - 1, int(math.floor(f)))
        return i, min(self.n - 1, i + 1), min(1.0, f - i)

    def done(self, wall):
        return wall >= self.total_s

    def ball(self, wall):
        """(pos, tracer 0..1, visible)"""
        i, j, t = self._at(wall)
        a, b = self.ball_frames[i], self.ball_frames[j]
        pos = [_lerp(a[k], b[k], t) for k in range(3)]
        return pos, _lerp(a[3], b[3], t), not (self.in_cup and wall >= self.rest_s)

    def camera(self, wall):
        """(pos, look, vertical fov in degrees, cut index). A new cut index means jump."""
        i, j, t = self._at(wall)
        a, b = self.cam_frames[i], self.cam_frames[j]
        if a[7] != b[7]:
            b = a
        return ([_lerp(a[k], b[k], t) for k in range(3)], [_lerp(a[k], b[k], t) for k in range(3, 6)],
                _lerp(a[6], b[6], t), int(a[7]))

    def hole_drops(self):
        """Golf Cornhole: [(seconds, colour)] for each bag that drops into the hole during this shot,
        at the moment it goes out of sight (a bag knocked in by the throw counts too)."""
        drops = []
        for b in (self.cornhole or {}).get("bags", []):
            if b.get("state") != "hole" or "frames" not in b:
                continue    # not in the hole, or already in it before this shot
            hidden = next((i for i, f in enumerate(b["frames"]) if not f[5]), None)
            if hidden is not None:
                drops.append((hidden / self.fps, b["color"]))
        return sorted(drops)

    def bags(self, wall):
        """Golf Cornhole: [(pose, colour)] for every bag. pose = [x, y, z, yaw, pitch, visible, size]."""
        if not self.cornhole:
            return []
        i, j, t = self._at(wall)
        out = []
        for b in self.cornhole["bags"]:
            if "frames" not in b:
                out.append((b["pose"], b["color"]))
                continue
            p, q = b["frames"][i], b["frames"][j]
            dy = ((q[3] - p[3] + 540) % 360) - 180   # the short way round
            vis = 1 if p[5] and q[5] else (p[5] if t < 0.5 else q[5])
            out.append(([_lerp(p[0], q[0], t), _lerp(p[1], q[1], t), _lerp(p[2], q[2], t), p[3] + dy * t,
                         _lerp(p[4], q[4], t), vis, _lerp(p[6], q[6], t)], b["color"]))
        return out


# ---------------- Unreal coordinates ----------------

def to_unreal(p):
    """Yards [downrange, right, up] -> Unreal centimetres [X, Y, Z]."""
    return [p[0] * YARD_CM, p[1] * YARD_CM, p[2] * YARD_CM]


def look_rotation(pos, look):
    """(pitch, yaw, roll) in degrees for a camera at pos looking at look (same units)."""
    dx, dy, dz = look[0] - pos[0], look[1] - pos[1], look[2] - pos[2]
    yaw = math.degrees(math.atan2(dy, dx))
    pitch = math.degrees(math.atan2(dz, math.hypot(dx, dy)))
    return pitch, yaw, 0.0


def horizontal_fov(vertical_deg, aspect=16 / 9):
    """The plan's lens is a vertical FOV (like three.js); Unreal cameras use horizontal."""
    return math.degrees(2 * math.atan(math.tan(math.radians(vertical_deg) / 2) * aspect))


def ball_radius_cm(camera_distance_cm):
    """A real ball is tiny on a range-sized screen, so grow it with distance (as the browser does)."""
    return min(55.0, max(2.7, camera_distance_cm * 0.0045))


# ---------------- smoothness ----------------

class FrameStats:
    """Frame times while a shot plays."""

    def __init__(self):
        self.deltas = []

    def add(self, dt):
        if dt > 0:
            self.deltas.append(dt)

    def summary(self):
        if not self.deltas:
            return None
        d = sorted(self.deltas)
        avg = sum(d) / len(d)
        return {"frames": len(d), "avg_fps": round(1 / avg, 1), "worst_ms": round(d[-1] * 1000, 1),
                "p95_ms": round(d[int(0.95 * (len(d) - 1))] * 1000, 1),
                "slow_frames": sum(1 for x in d if x > 1 / 30)}


def parse_shot(data):
    """The shot event's JSON, or None if it isn't a scored Target Range shot with a plan."""
    ev = json.loads(data)
    return ev if ev.get("plan") else None
