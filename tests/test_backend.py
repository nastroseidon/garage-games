import json
import os
import socket
import sys
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flight import simulate  # noqa: E402
from openconnect import MessageStream, OpenConnectServer, normalize_shot  # noqa: E402


def shot(speed=100.0, vla=20.0, hla=0.0, spin=6000, axis=0.0, heartbeat=False):
    return {"DeviceID": "Test", "ShotNumber": 1, "APIversion": "1",
            "BallData": {"Speed": speed, "VLA": vla, "HLA": hla,
                         "TotalSpin": spin, "SpinAxis": axis},
            "ShotDataOptions": {"ContainsBallData": not heartbeat,
                                "LaunchMonitorIsReady": True,
                                "IsHeartBeat": heartbeat}}


class FlightTests(unittest.TestCase):
    def test_tour_carries_within_ten_percent(self):
        for speed, vla, spin, carry in [(167, 10.9, 2686, 275),
                                        (120, 16.3, 7097, 172),
                                        (102, 24.2, 9304, 136)]:
            r = simulate(speed, vla, 0, spin, 0)
            self.assertAlmostEqual(r["carry_yd"], carry, delta=carry * 0.1)

    def test_curve_and_start_direction(self):
        straight = simulate(120, 16, 0, 7000, 0)
        self.assertAlmostEqual(straight["offline_yd"], 0, delta=0.5)
        self.assertGreater(simulate(120, 16, 0, 7000, 15)["offline_yd"], 5)
        self.assertLess(simulate(120, 16, 0, 7000, -15)["offline_yd"], -5)
        self.assertGreater(simulate(120, 16, 3, 7000, 0)["offline_yd"], 5)

    def test_tiny_and_zero_shots_do_not_crash(self):
        self.assertEqual(simulate(0, 0)["carry_yd"], 0)
        self.assertGreaterEqual(simulate(5, 45, 0, 0, 0)["carry_yd"], 0)
        self.assertGreater(len(simulate(60, 30, 0, 5000)["points"]), 2)


class StreamTests(unittest.TestCase):
    def test_concatenated_and_split_messages(self):
        a, b = json.dumps(shot(90)), json.dumps(shot(95))
        data = (a + b).encode()
        s = MessageStream()
        got = s.feed(data[:10]) + s.feed(data[10:len(a) + 5]) + s.feed(data[len(a) + 5:])
        self.assertEqual([m["BallData"]["Speed"] for m in got], [90, 95])

    def test_skips_leading_noise(self):
        got = MessageStream().feed(b"\r\n  junk " + json.dumps(shot()).encode())
        self.assertEqual(len(got), 1)


class NormalizeTests(unittest.TestCase):
    def test_heartbeat_and_empty_ignored(self):
        self.assertIsNone(normalize_shot(shot(heartbeat=True)))
        self.assertIsNone(normalize_shot(shot(speed=0)))
        self.assertIsNone(normalize_shot({"ShotDataOptions": {}}))

    def test_back_and_side_spin_converted(self):
        msg = shot(spin=0)
        msg["BallData"].update(BackSpin=3000, SideSpin=-500)
        n = normalize_shot(msg)
        self.assertEqual(n["spin_rpm"], 3041)
        self.assertLess(n["spin_axis_deg"], 0)

    def test_bad_numbers_tolerated(self):
        msg = shot()
        msg["BallData"]["VLA"] = "n/a"
        self.assertEqual(normalize_shot(msg)["vla_deg"], 0)


class ServerTests(unittest.TestCase):
    def test_round_trip_over_tcp(self):
        shots, statuses = [], []
        srv = OpenConnectServer("127.0.0.1", 0, lambda s, raw: shots.append(s),
                                statuses.append)
        srv.start()
        port = srv._sock.getsockname()[1]
        with socket.create_connection(("127.0.0.1", port), timeout=3) as c:
            c.sendall(json.dumps(shot(heartbeat=True)).encode())
            c.sendall(json.dumps(shot(88.8)).encode())
            reply = json.loads(c.recv(4096))
        self.assertEqual(reply["Code"], 200)
        for _ in range(50):
            if statuses and not statuses[-1]["connected"]:
                break
            time.sleep(0.02)
        self.assertEqual([s["speed_mph"] for s in shots], [88.8])
        self.assertTrue(any(s["ready"] for s in statuses))
        self.assertFalse(statuses[-1]["connected"])


if __name__ == "__main__":
    unittest.main()
