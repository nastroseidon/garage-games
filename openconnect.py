"""Receive shots from a launch monitor over the GSPro Open Connect API (v1).

The launch monitor software (e.g. VTrack ToolKit) connects to us over TCP,
exactly as it would to GSPro or another Open Connect simulator, and streams
JSON messages. Messages are not newline-delimited, so we parse them out of
a rolling buffer.
"""

import json
import math
import socket
import threading
import time

_decoder = json.JSONDecoder()
MAX_BUFFER = 256 * 1024


class MessageStream:
    """Splits a TCP byte stream into JSON objects."""

    def __init__(self):
        self._buf = ""

    def feed(self, data):
        self._buf += data.decode("utf-8", errors="replace")
        messages = []
        while True:
            start = self._buf.find("{")
            if start < 0:
                self._buf = ""
                break
            self._buf = self._buf[start:]
            try:
                obj, end = _decoder.raw_decode(self._buf)
            except json.JSONDecodeError:
                if len(self._buf) > MAX_BUFFER:
                    # Garbage that will never parse; skip past this brace.
                    self._buf = self._buf[1:]
                    continue
                break  # wait for the rest of the message
            self._buf = self._buf[end:]
            if isinstance(obj, dict):
                messages.append(obj)
        return messages


def _num(d, key, default=0.0):
    try:
        value = float(d.get(key, default))
    except (TypeError, ValueError):
        return default
    return value if math.isfinite(value) else default


def normalize_shot(msg):
    """Turn an Open Connect shot message into a flat dict, or None.

    Returns None for heartbeats and messages without usable ball data.
    """
    opts = msg.get("ShotDataOptions") or {}
    if opts.get("IsHeartBeat"):
        return None
    ball = msg.get("BallData") or {}
    if opts.get("ContainsBallData") is False or not ball:
        return None

    speed = _num(ball, "Speed")
    if speed <= 0:
        return None

    total_spin = _num(ball, "TotalSpin")
    spin_axis = _num(ball, "SpinAxis")
    back_spin = _num(ball, "BackSpin")
    side_spin = _num(ball, "SideSpin")
    if total_spin <= 0 and (back_spin or side_spin):
        total_spin = math.hypot(back_spin, side_spin)
        spin_axis = math.degrees(math.atan2(side_spin, back_spin))

    club = msg.get("ClubData") or {}
    return {
        "shot_number": msg.get("ShotNumber"),
        "device": msg.get("DeviceID", ""),
        "speed_mph": round(speed, 1),
        "vla_deg": round(_num(ball, "VLA"), 1),
        "hla_deg": round(_num(ball, "HLA"), 1),
        "spin_rpm": round(total_spin),
        "spin_axis_deg": round(spin_axis, 1),
        "reported_carry": _num(ball, "CarryDistance") or None,
        "club_speed_mph": _num(club, "Speed") or None,
    }


class OpenConnectServer:
    """TCP server that speaks the receiving side of Open Connect.

    on_shot(shot_dict, raw_msg) is called for each real shot.
    on_status(status_dict) is called when connection/ready state changes.
    """

    def __init__(self, host, port, on_shot, on_status, on_raw=None):
        self.host = host
        self.port = port
        self.on_shot = on_shot
        self.on_status = on_status
        self.on_raw = on_raw
        self.status = {"connected": False, "ready": False,
                       "ball_detected": False, "device": "", "last_seen": None}
        self._lock = threading.Lock()
        self._sock = None

    def start(self):
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind((self.host, self.port))
        self._sock.listen(4)
        threading.Thread(target=self._accept_loop, daemon=True).start()

    def _accept_loop(self):
        while True:
            try:
                conn, addr = self._sock.accept()
            except OSError:
                return
            threading.Thread(target=self._handle, args=(conn, addr),
                             daemon=True).start()

    def _set_status(self, **changes):
        with self._lock:
            before = dict(self.status)
            self.status.update(changes)
            self.status["last_seen"] = time.time()
            changed = any(before.get(k) != self.status[k] for k in changes)
            snapshot = dict(self.status)
        if changed:
            self.on_status(snapshot)

    def _handle(self, conn, addr):
        stream = MessageStream()
        self._set_status(connected=True)
        try:
            while True:
                data = conn.recv(65536)
                if not data:
                    break
                for msg in stream.feed(data):
                    self._process(conn, msg)
        except OSError:
            pass
        finally:
            conn.close()
            self._set_status(connected=False, ready=False, ball_detected=False)

    def _process(self, conn, msg):
        if self.on_raw:
            self.on_raw(msg)
        opts = msg.get("ShotDataOptions") or {}
        changes = {}
        if "LaunchMonitorIsReady" in opts:
            changes["ready"] = bool(opts["LaunchMonitorIsReady"])
        if "LaunchMonitorBallDetected" in opts:
            changes["ball_detected"] = bool(opts["LaunchMonitorBallDetected"])
        if msg.get("DeviceID"):
            changes["device"] = str(msg["DeviceID"])
        self._set_status(**changes)

        shot = normalize_shot(msg)
        if shot is None:
            return
        reply = {"Code": 200, "Message": "Shot received successfully"}
        try:
            conn.sendall(json.dumps(reply).encode("utf-8"))
        except OSError:
            pass
        self.on_shot(shot, msg)
