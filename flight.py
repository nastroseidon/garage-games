"""Simple golf ball flight model.

Turns launch data (ball speed, launch angles, spin) into a landing spot.
It is a point-mass model with drag and Magnus lift, tuned so typical
full shots land near published tour carry averages. Good enough for
party games; not a replacement for a real simulator's model.

Coordinates: x = downrange, y = up, z = right of target line.
"""

import math

MPH_TO_MS = 0.44704
M_TO_YD = 1.0936133
M_TO_FT = 3.2808399

MASS = 0.04593          # kg
RADIUS = 0.021335       # m
AREA = math.pi * RADIUS ** 2
AIR_DENSITY = 1.225     # kg/m^3
GRAVITY = 9.81          # m/s^2
SPIN_DECAY_PER_S = 0.04  # fraction of spin lost per second of flight
MAX_ROLL_YD = 40.0

DT = 0.005
MAX_TIME = 15.0


def _coefficients(spin_factor):
    """Drag and lift coefficients from spin factor S = r*omega/v."""
    s = max(0.0, spin_factor)
    cd = 0.19 + 0.30 * s
    cl = min(0.30, 1.50 * s) if s > 0 else 0.0
    return cd, cl


def simulate(speed_mph, vla_deg, hla_deg=0.0, spin_rpm=0.0, spin_axis_deg=0.0,
             samples=40):
    """Fly the ball until it returns to launch height.

    hla_deg: positive = starts right of target.
    spin_axis_deg: positive = curves right (fade/slice for a right-hander).

    Returns carry/offline in yards, apex in feet, flight time and a list of
    sampled [downrange_yd, right_yd, height_ft] points for drawing.
    """
    v = max(0.0, speed_mph) * MPH_TO_MS
    vla = math.radians(vla_deg)
    hla = math.radians(hla_deg)
    axis = math.radians(spin_axis_deg)
    omega = max(0.0, spin_rpm) * 2 * math.pi / 60

    vx = v * math.cos(vla) * math.cos(hla)
    vy = v * math.sin(vla)
    vz = v * math.cos(vla) * math.sin(hla)
    x = y = z = 0.0
    t = 0.0
    apex = 0.0
    path = [(0.0, 0.0, 0.0)]
    k = 0.5 * AIR_DENSITY * AREA / MASS

    while t < MAX_TIME:
        speed = math.sqrt(vx * vx + vy * vy + vz * vz)
        if speed < 1e-6:
            break
        ux, uy, uz = vx / speed, vy / speed, vz / speed
        cd, cl = _coefficients(RADIUS * omega / speed)

        # Lift acts perpendicular to velocity: "up" tilted toward "right"
        # by the spin axis angle.
        upx, upy, upz = -uy * ux, 1 - uy * uy, -uy * uz
        n = math.sqrt(upx * upx + upy * upy + upz * upz) or 1.0
        upx, upy, upz = upx / n, upy / n, upz / n
        # right = velocity x up
        rx = uy * upz - uz * upy
        ry = uz * upx - ux * upz
        rz = ux * upy - uy * upx
        lx = math.cos(axis) * upx + math.sin(axis) * rx
        ly = math.cos(axis) * upy + math.sin(axis) * ry
        lz = math.cos(axis) * upz + math.sin(axis) * rz

        f = k * speed * speed
        ax = -f * cd * ux + f * cl * lx
        ay = -f * cd * uy + f * cl * ly - GRAVITY
        az = -f * cd * uz + f * cl * lz

        vx += ax * DT
        vy += ay * DT
        vz += az * DT
        nx, ny, nz = x + vx * DT, y + vy * DT, z + vz * DT
        t += DT
        omega *= (1 - SPIN_DECAY_PER_S * DT)

        if ny < 0 and t > DT:
            # Interpolate the landing point between the last two steps.
            frac = y / (y - ny) if y != ny else 1.0
            x += (nx - x) * frac
            z += (nz - z) * frac
            y = 0.0
            path.append((x, 0.0, z))
            break
        x, y, z = nx, ny, nz
        apex = max(apex, y)
        path.append((x, y, z))

    descent = math.degrees(math.atan2(-vy, math.sqrt(vx * vx + vz * vz))) if t > 0 else 0.0
    step = max(1, len(path) // samples)
    points = path[::step]
    if points[-1] is not path[-1]:
        points.append(path[-1])

    roll = roll_yards(math.sqrt(vx * vx + vz * vz), descent,
                      omega * 60 / (2 * math.pi)) if t > 0 else 0.0
    heading = math.atan2(vz, vx) if t > 0 else 0.0
    land = (x * M_TO_YD, z * M_TO_YD)
    rest = (land[0] + roll * math.cos(heading), land[1] + roll * math.sin(heading))

    return {
        "carry_yd": round(x * M_TO_YD, 1),
        "offline_yd": round(z * M_TO_YD, 1),
        "apex_ft": round(apex * M_TO_FT, 1),
        "flight_time_s": round(t, 2),
        "descent_deg": round(descent, 1),
        "points": [[round(p[0] * M_TO_YD, 2), round(p[2] * M_TO_YD, 2),
                    round(p[1] * M_TO_FT, 2)] for p in points],
        "roll_yd": round(roll, 1),
        "total_yd": round(rest[0], 1),
        "rest": [round(rest[0], 2), round(rest[1], 2)],
    }


def roll_yards(land_speed_ms, descent_deg, spin_rpm):
    """Roll-out after landing on firm range turf.

    Fitted to typical numbers: a driver rolls ~20 yds, a 7-iron ~4,
    a pitching wedge ~2, a low bump-and-run ~7.
    """
    along = land_speed_ms * math.cos(math.radians(max(0.0, descent_deg)))
    roll = 0.109 * along * along / (1 + max(0.0, spin_rpm) / 1782)
    return max(0.0, min(MAX_ROLL_YD, roll))
