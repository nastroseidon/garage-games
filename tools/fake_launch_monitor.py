"""Pretend to be a launch monitor: send Open Connect shots to Garage Games.

Usage:
    python tools/fake_launch_monitor.py            # one random shot
    python tools/fake_launch_monitor.py -n 5       # five shots, 3 s apart
    python tools/fake_launch_monitor.py --speed 60 --launch 30 --spin 6000
"""

import argparse
import json
import random
import socket
import time


def shot_message(n, speed, launch, direction, spin, axis):
    return {
        "DeviceID": "Fake LM",
        "Units": "Yards",
        "ShotNumber": n,
        "APIversion": "1",
        "BallData": {"Speed": speed, "SpinAxis": axis, "TotalSpin": spin,
                     "HLA": direction, "VLA": launch},
        "ClubData": {},
        "ShotDataOptions": {"ContainsBallData": True, "ContainsClubData": False,
                            "LaunchMonitorIsReady": True,
                            "LaunchMonitorBallDetected": True,
                            "IsHeartBeat": False},
    }


def heartbeat():
    return {"DeviceID": "Fake LM", "Units": "Yards", "ShotNumber": 0,
            "APIversion": "1",
            "ShotDataOptions": {"ContainsBallData": False,
                                "ContainsClubData": False,
                                "LaunchMonitorIsReady": True,
                                "LaunchMonitorBallDetected": True,
                                "IsHeartBeat": True}}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=921)
    p.add_argument("-n", type=int, default=1, help="number of shots")
    p.add_argument("--gap", type=float, default=3.0, help="seconds between shots")
    p.add_argument("--speed", type=float)
    p.add_argument("--launch", type=float)
    p.add_argument("--direction", type=float)
    p.add_argument("--spin", type=float)
    p.add_argument("--axis", type=float)
    a = p.parse_args()

    with socket.create_connection((a.host, a.port), timeout=5) as s:
        s.sendall(json.dumps(heartbeat()).encode())
        for i in range(1, a.n + 1):
            msg = shot_message(
                i,
                a.speed if a.speed is not None else round(random.uniform(55, 120), 1),
                a.launch if a.launch is not None else round(random.uniform(14, 30), 1),
                a.direction if a.direction is not None else round(random.uniform(-4, 4), 1),
                a.spin if a.spin is not None else round(random.uniform(4000, 9000)),
                a.axis if a.axis is not None else round(random.uniform(-10, 10), 1),
            )
            s.sendall(json.dumps(msg).encode())
            reply = s.recv(4096).decode()
            print("Sent shot %d (%.1f mph) -> %s" % (i, msg["BallData"]["Speed"], reply))
            if i < a.n:
                time.sleep(a.gap)


if __name__ == "__main__":
    main()
