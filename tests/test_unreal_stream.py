"""The Unreal side's stream client and shot player (garage_stream.py), run
against the real server. These parts need no Unreal, so they are tested here;
garage_bridge.py (the Unreal glue) is checked in the editor."""

import json
import math
import os
import random
import sys
import threading
import time
import unittest
import urllib.request
from http.server import ThreadingHTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "unreal", "GarageGames", "Content", "Python"))

import garage_stream as gs  # noqa: E402
import server  # noqa: E402


def wait_for(stream, name, timeout=5.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        for ev, data in stream.poll():
            if ev == name:
                return json.loads(data)
        time.sleep(0.01)
    raise AssertionError("no %r event within %.0fs" % (name, timeout))


class SseParserTests(unittest.TestCase):
    def test_events_split_across_reads_and_keepalives(self):
        p = gs.SseParser()
        raw = (b"HTTP/1.0 200 OK\r\nContent-Type: text/event-stream\r\n\r\n"
               b"event: status\ndata: {\"connected\": false}\n\n: keepalive\n\n"
               b"event: shot\ndata: {\"plan\": 1}\n\n")
        got = []
        for i in range(0, len(raw), 7):  # arrive in small pieces
            got += p.feed(raw[i:i + 7])
        self.assertEqual(p.status, 200)
        self.assertEqual(got, [("status", '{"connected": false}'), ("shot", '{"plan": 1}')])


class LiveStreamTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        server.shot_log.enabled = False
        server.session.__init__(rng=random.Random(2))
        cls.web = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        cls.web.daemon_threads = True
        threading.Thread(target=cls.web.serve_forever, daemon=True).start()
        cls.port = cls.web.server_address[1]

    @classmethod
    def tearDownClass(cls):
        cls.web.shutdown()
        cls.web.server_close()

    def post(self, path, body):
        req = urllib.request.Request("http://127.0.0.1:%d%s" % (self.port, path), data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=5).read()

    def test_unreal_receives_the_same_shot_plan_as_the_browser(self):
        stream = gs.EventStream(port=self.port)
        changes = []
        stream.on_change = changes.append
        try:
            state = wait_for(stream, "state")         # sent as soon as a screen connects
            self.assertTrue(stream.connected)
            self.assertEqual(changes, [True])
            self.assertIn("active", state)
            self.post("/api/game/start", {"game": "targetrange", "camera": "broadcast",
                                          "players": [{"name": "Dad"}, {"name": "Maddie"}]})
            self.post("/api/test-shot", {"kind": "iron"})
            ev = wait_for(stream, "shot")
            self.assertIsNotNone(gs.parse_shot(json.dumps(ev)))
            plan = ev["plan"]
            self.assertEqual(plan["mode"], "broadcast")
            player = gs.ShotPlayer(plan)
            # sampling at the frame times gives exactly the plan's frames
            for i in range(0, player.n, 11):
                pos, tracer, _ = player.ball(i / plan["fps"])
                self.assertEqual(pos + [tracer], plan["ball"][i])
                cpos, look, fov, cut = player.camera(i / plan["fps"])
                self.assertEqual(cpos + look + [fov, cut], plan["camera"][i])
            # in between, it blends - except across a camera cut
            pos, _, _ = player.ball(0.5 / plan["fps"])
            self.assertAlmostEqual(pos[0], (plan["ball"][0][0] + plan["ball"][1][0]) / 2, places=6)
            cams = plan["camera"]
            k = next(i for i in range(1, len(cams)) if cams[i][7] != cams[i - 1][7])
            before = player.camera((k - 0.5) / plan["fps"])
            self.assertEqual(before[3], cams[k - 1][7])
            self.assertEqual(before[0], cams[k - 1][:3], "no blending across a cut")
            self.assertFalse(player.done(player.total_s - 0.01))
            self.assertTrue(player.done(player.total_s))
        finally:
            stream.close()
        self.assertEqual(changes, [True, False])

    def test_poll_never_blocks_and_retries_when_the_server_is_down(self):
        now = [0.0]
        stream = gs.EventStream(port=1, retry_s=2.0, clock=lambda: now[0])  # nothing listens on port 1
        t0 = time.monotonic()
        self.assertEqual(stream.poll(), [])
        self.assertLess(time.monotonic() - t0, 1.0)
        self.assertFalse(stream.connected)
        stream.port = self.port
        self.assertEqual(stream.poll(), [], "waits for the retry time before trying again")
        now[0] = 2.5
        try:
            wait_for(stream, "state")
            self.assertTrue(stream.connected)
        finally:
            stream.close()


class UnrealMathTests(unittest.TestCase):
    def test_yards_to_unreal_centimetres(self):
        self.assertEqual(gs.to_unreal([100, -2, 1]), [9144.0, -182.88, 91.44])

    def test_camera_rotation(self):
        self.assertEqual(gs.look_rotation([0, 0, 0], [10, 0, 0]), (0.0, 0.0, 0.0))
        pitch, yaw, _ = gs.look_rotation([0, 0, 10], [10, 10, 10])
        self.assertAlmostEqual(yaw, 45)            # Unreal yaw turns from X toward +Y (right)
        self.assertAlmostEqual(pitch, 0)
        pitch, _, _ = gs.look_rotation([0, 0, 10], [10, 0, 0])
        self.assertAlmostEqual(pitch, -45)         # looking down

    def test_lens_and_ball_size(self):
        self.assertAlmostEqual(gs.horizontal_fov(90, 1), 90)
        self.assertAlmostEqual(gs.horizontal_fov(34), 2 * math.degrees(math.atan(math.tan(math.radians(17)) * 16 / 9)))
        self.assertEqual(gs.ball_radius_cm(0), 2.7)
        self.assertEqual(gs.ball_radius_cm(1e9), 55.0)

    def test_frame_stats(self):
        s = gs.FrameStats()
        for dt in [1 / 60] * 99 + [0.05]:
            s.add(dt)
        out = s.summary()
        self.assertEqual((out["frames"], out["slow_frames"], out["worst_ms"]), (100, 1, 50.0))
        self.assertAlmostEqual(out["avg_fps"], 100 / (99 / 60 + 0.05), places=0)


if __name__ == "__main__":
    unittest.main()
