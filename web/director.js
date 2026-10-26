/* Camera director for the 3D Target Range.
 *
 * When a shot arrives we already know its whole flight, where it stops and
 * how it changes the scores. The director uses that to:
 *   1. decide whether the shot deserves "broadcast" coverage (assess), and
 *   2. plan the whole sequence: ball path with bounces, slow motion, and
 *      camera cuts (plan).
 *
 * Positions are [downrange, right, height] in yards. Times: "sim" seconds
 * are ball time; "wall" seconds are what the viewer sees (slow motion
 * stretches wall time).
 */
(function (root) {
  "use strict";

  var GRAVITY = 10.73; // yd/s^2
  var RANDOM_BROADCAST = 0.08; // the odd routine shot gets the full treatment, so a cut never gives the result away
  var NEAR_MISS_YD = 1.5;

  /* ---------------- drama ---------------- */

  function leaderOf(totals) {
    var best = -Infinity, who = null;
    for (var i = 0; i < totals.length; i++) {
      if (totals[i] > best) { best = totals[i]; who = i; }
      else if (totals[i] === best) who = null;
    }
    return who; // null when tied at the top
  }

  /* input: {players:[{name}], shooter, before:[totals], after:[totals],
   *         shotsLeft, totalShots, finalBall, pressureGap, ladder:{need:[]}|null,
   *         gameOverAfter, hit:{target, zone, rolledIn}, nearMissYd, chance} */
  function assess(input) {
    var p = input.players, s = input.shooter, multi = p.length > 1;
    var out = { pressure: false, preTag: "", preText: "", headline: "", reasons: [] };

    if (multi && input.ladder) {
      var left = function (i) { return input.ladder.need[i] - input.before[i]; };
      if (left(s) === 1) {
        out.pressure = true; out.preTag = "FOR THE WIN"; out.preText = "One hit from the top of the ladder";
      } else {
        for (var i = 0; i < p.length; i++) {
          if (i !== s && left(i) === 1) {
            out.pressure = true; out.preTag = "MUST KEEP PACE";
            out.preText = p[i].name + " is one rung from winning";
            break;
          }
        }
      }
    } else if (multi && input.shotsLeft <= 2) {
      var bestOther = -Infinity, otherName = "";
      for (var j = 0; j < p.length; j++) {
        if (j !== s && input.before[j] > bestOther) { bestOther = input.before[j]; otherName = p[j].name; }
      }
      var gap = input.before[s] - bestOther;
      var limit = input.pressureGap * (input.finalBall ? 2 : 1);
      if (Math.abs(gap) <= limit) {
        var balls = input.shotsLeft === 1 ? "final ball" : "2 balls left";
        out.pressure = true;
        out.preTag = input.shotsLeft === 1 ? "FINAL BALL" : "PRESSURE SHOT";
        out.preText = gap < 0 ? -gap + " behind " + otherName + " · " + balls
          : gap > 0 ? "Leads by " + gap + " · " + balls : "All square · " + balls;
      }
    }
    if (out.pressure) out.reasons.push("pressure");

    var hit = input.hit || { target: -1 };
    var before = leaderOf(input.before), after = leaderOf(input.after);
    var winning = multi && input.gameOverAfter && after === s;
    // a real overtake (not breaking an early tie) in the back half of the game
    var backHalf = input.shotsLeft <= Math.ceil((input.totalShots || input.shotsLeft) / 2);
    var leadChange = multi && !winning && backHalf && after === s && before !== null && before !== s;
    var flagZone = hit.target >= 0 && hit.zone === "center";
    var inner = hit.target >= 0 && hit.zone === "inner";
    var nearMiss = hit.target < 0 && input.nearMissYd !== null && input.nearMissYd !== undefined && input.nearMissYd <= NEAR_MISS_YD;
    var rolledIn = hit.target >= 0 && hit.rolledIn;
    var lucky = input.chance !== undefined && input.chance < RANDOM_BROADCAST;

    if (winning) out.reasons.push("winning");
    if (leadChange) out.reasons.push("lead-change");
    if (flagZone) out.reasons.push("flag-zone");
    if (inner) out.reasons.push("inner-ring");
    if (nearMiss) out.reasons.push("near-miss");
    if (lucky && !out.reasons.length) out.reasons.push("random");

    out.broadcast = out.reasons.length > 0;
    out.slowmo = winning || leadChange || flagZone || inner || nearMiss;
    out.headline = winning ? "WINS IT!" : leadChange ? "TAKES THE LEAD!" : flagZone ? "FLAG ZONE!"
      : nearMiss ? "SO CLOSE!" : rolledIn ? "ROLLED IN!" : "";
    out.celebrate = winning;
    return out;
  }

  /* ---------------- ball path ---------------- */

  function lerp(a, b, t) { return [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t]; }
  function dist2(a, b) { return Math.sqrt(Math.pow(a[0] - b[0], 2) + Math.pow(a[1] - b[1], 2)); }
  function easeOut(t) { return 1 - (1 - t) * (1 - t); }
  function easeInOut(t) { return t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2; }
  function clamp(v, a, b) { return Math.max(a, Math.min(b, v)); }

  function buildPath(shot, stop, cup) {
    var f = shot.flight;
    var pts = f.points.map(function (q) { return [q[0], q[1], q[2] / 3]; });
    var flightT = Math.max(0.3, f.flight_time_s);
    var land = [f.carry_yd, f.offline_yd, 0];
    pts[pts.length - 1] = land;
    var n = pts.length;
    var dt = flightT / (n - 1);
    var a = pts[n - 2], b = pts[n - 1];
    var vv = Math.max(0, (a[2] - b[2]) / dt);
    var segs = [];
    var t = flightT;
    var from = land;
    var end = [stop[0], stop[1], 0];

    function hop(to, height) {
      var dur = 2 * Math.sqrt(2 * height / GRAVITY);
      var p0 = from, t0 = t;
      segs.push({ t0: t0, t1: t0 + dur, kind: "bounce", at: function (u) {
        var p = lerp(p0, to, u);
        p[2] = 4 * height * u * (1 - u);
        return p;
      } });
      t += dur; from = to;
    }
    function roll(to, dur, ease, kind) {
      var p0 = from, t0 = t;
      segs.push({ t0: t0, t1: t0 + dur, kind: kind || "roll", at: function (u) { return lerp(p0, to, ease(u)); } });
      t += dur; from = to;
    }

    var h1 = clamp(0.25 * vv * vv / (2 * GRAVITY), 0.04, 4);
    var len = dist2(land, end);
    if (len > 1.5) {
      hop(lerp(land, end, 0.35), h1);
      hop(lerp(land, end, 0.5), h1 * 0.25);
      roll(end, clamp(0.4 + len * 0.5 * 0.08, 0.4, 2.5), easeOut);
    } else {
      hop(end, h1 * 0.5);
    }
    if (cup) {
      var c = [cup[0], cup[1], 0];
      roll(c, clamp(0.5 + dist2(end, c) * 0.06, 0.5, 1.6), easeInOut, "funnel");
      var t0 = t;
      segs.push({ t0: t0, t1: t0 + 0.3, kind: "sink", at: function (u) { return [c[0], c[1], -0.15 * u]; } });
      t += 0.3;
    }
    return {
      flightT: flightT, restT: t, land: land, end: cup ? [cup[0], cup[1], 0] : end, inCup: !!cup,
      at: function (sim) {
        if (sim <= 0) return { pos: pts[0], phase: "flight", visible: true };
        if (sim < flightT) {
          var x = sim / flightT * (n - 1), i = Math.floor(x);
          return { pos: lerp(pts[i], pts[Math.min(i + 1, n - 1)], x - i), phase: "flight", visible: true };
        }
        for (var k = 0; k < segs.length; k++) {
          var sg = segs[k];
          if (sim < sg.t1) return { pos: sg.at((sim - sg.t0) / (sg.t1 - sg.t0)), phase: sg.kind, visible: true };
        }
        var last = segs.length ? segs[segs.length - 1].at(1) : land;
        return { pos: last, phase: cup ? "cup" : "rest", visible: !cup };
      }
    };
  }

  /* ---------------- timeline (slow motion) ---------------- */

  function timeline(keys) {
    // keys: [[wall, sim], ...], strictly increasing in both
    function interp(arr, x, from, to) {
      if (x <= arr[0][from]) return arr[0][to] + (x - arr[0][from]) * 1;
      for (var i = 1; i < arr.length; i++) {
        if (x <= arr[i][from]) {
          var a = arr[i - 1], b = arr[i];
          return a[to] + (x - a[from]) / (b[from] - a[from]) * (b[to] - a[to]);
        }
      }
      var l2 = arr[arr.length - 1], l1 = arr[arr.length - 2];
      return l2[to] + (x - l2[from]) * (l2[to] - l1[to]) / (l2[from] - l1[from]);
    }
    return {
      simAt: function (wall) { return interp(keys, wall, 0, 1); },
      wallAt: function (sim) { return interp(keys, sim, 1, 0); }
    };
  }

  /* ---------------- cameras ---------------- */

  var CAMERAS = {
    // overview from behind and above the bay (also the idle camera)
    range: function () { return { pos: [-26, 0, 30], look: [95, 0, -8], fov: 38, follow: 0 }; },
    // low, behind the hitter, looking out along the start line
    bay: function (c) { return { pos: [-3.6, -1.1, 1.9], look: [30, 30 * Math.tan(c.hla), 6], fov: 52, follow: 0 }; },
    // trails the ball
    chase: function (c, ball) {
      return { pos: [ball[0] - 14 * c.u[0], ball[1] - 14 * c.u[1], ball[2] + 4.5],
        look: [ball[0] + 20 * c.u[0], ball[1] + 20 * c.u[1], Math.max(0, ball[2] - 3)], fov: 50, follow: 3 };
    },
    // tower behind and off to the side, long lens following the ball against the sky
    tower: function (c, ball) {
      return { pos: [-20, c.side * 35, 9], look: ball, fov: 28, follow: 0, lookFollow: 5 };
    },
    // low camera beyond the target, looking back as the ball drops in
    target: function (c, ball, sim) {
      var a = c.anchor;
      var look = sim < c.flightT ? lerp(a, ball, 0.45) : ball;
      var back = c.radius + 12, off = 6 + c.radius * 0.3;
      return { pos: [a[0] + back * c.u[0] + off * c.side * c.v[0], a[1] + back * c.u[1] + off * c.side * c.v[1], 4 + c.radius * 0.15],
        look: [look[0], look[1], Math.max(0.2, look[2])], fov: 34, follow: 0, lookFollow: 4 };
    },
    // slow orbit around where the ball finished
    orbit: function (c, ball, sim, t) {
      var ang = c.orbitStart + 0.32 * t;
      var a = c.anchor;
      var rad = c.radius + 5;
      return { pos: [a[0] + Math.cos(ang) * rad, a[1] + Math.sin(ang) * rad, 4.5], look: [a[0], a[1], 1.6], fov: 40, follow: 0 };
    },
    // behind and above the landing area, watching it come down
    land: function (c, ball) {
      var a = c.anchor;
      return { pos: [a[0] - 30 * c.u[0], a[1] - 30 * c.u[1], 13], look: ball, fov: 40, follow: 0, lookFollow: 4 };
    }
  };

  /* ---------------- plan ---------------- */

  /* opts: {style: auto|broadcast|quick|static, drama, hit:{target}, targets} */
  function plan(shot, result, opts) {
    var style = opts.style || "auto";
    var drama = opts.drama || { broadcast: false };
    var mode = style === "static" ? "static" : style === "quick" ? "quick"
      : style === "broadcast" || drama.broadcast ? "broadcast" : "quick";

    var hit = opts.hit || { target: -1 };
    var cupT = hit.target >= 0 && opts.targets ? opts.targets[hit.target] : null;
    var stop = result.stop || shot.flight.rest;
    var path = buildPath(shot, stop, cupT ? [cupT.d, cupT.l] : null);

    // wall <-> sim mapping
    var rate = mode === "broadcast" ? 1 : 1.25;
    var keys = [[0, 0]];
    if (mode === "broadcast" && drama.slowmo && path.flightT > 1) {
      var s0 = path.flightT - 0.5, s1 = Math.min(path.restT, path.flightT + 0.9), slow = 0.45;
      keys.push([s0, s0]);
      keys.push([s0 + (s1 - s0) / slow, s1]);
      keys.push([s0 + (s1 - s0) / slow + (path.restT + 1 - s1), path.restT + 1]);
    } else {
      keys.push([(path.restT + 1) / rate, path.restT + 1]);
    }
    var tl = timeline(keys);
    var restWall = tl.wallAt(path.restT);
    var hold = mode === "broadcast" ? (drama.celebrate ? 3.8 : 2.8) : mode === "quick" ? 1.6 : 1.4;
    var total = restWall + hold;

    // geometry the cameras use. On a miss the cameras frame the ball together
    // with the nearest target, so you can see how close it was.
    var end = path.end;
    var anchor = end, radius = cupT ? cupT.r : 2;
    if (!cupT && opts.targets) {
      var near = null, nd = Infinity;
      opts.targets.forEach(function (T) {
        var dd = Math.sqrt(Math.pow(T.d - end[0], 2) + Math.pow(T.l - end[1], 2)) - T.r;
        if (dd < nd) { nd = dd; near = T; }
      });
      if (near && nd < 25) {
        anchor = [(end[0] + near.d) / 2, (end[1] + near.l) / 2, 0];
        radius = Math.sqrt(Math.pow(near.d - end[0], 2) + Math.pow(near.l - end[1], 2)) / 2 + near.r * 0.5;
      }
    }
    var len = Math.sqrt(end[0] * end[0] + end[1] * end[1]) || 1;
    var u = len > 1 ? [end[0] / len, end[1] / len] : [1, 0];
    var c = {
      u: u, v: [-u[1], u[0]], end: end, anchor: anchor, flightT: path.flightT,
      side: end[1] >= 0 ? -1 : 1, hla: (shot.hla_deg || 0) * Math.PI / 180,
      radius: radius,
      orbitStart: 0
    };
    // the orbit starts where the target camera was, so the cut feels continuous
    var back = c.radius + 12, off = 6 + c.radius * 0.3;
    c.orbitStart = Math.atan2(c.side * c.v[1] * off + u[1] * back, c.side * c.v[0] * off + u[0] * back);
    var short = end[0] < 45 || path.flightT < 1.8;

    var shots = [];
    function add(type, t0, t1) { if (t1 - t0 > 0.05) shots.push({ type: type, t0: t0, t1: t1 }); }
    var landWall = tl.wallAt(path.flightT);
    if (mode === "static") {
      add("range", 0, total);
    } else if (mode === "quick") {
      if (short) { add("bay", 0, 0.5); add("land", 0.5, total); }
      else {
        var chaseEnd = tl.wallAt(path.flightT * 0.75);
        add("bay", 0, 0.5); add("chase", 0.5, chaseEnd); add("land", chaseEnd, total);
      }
    } else {
      var targetFrom = short ? 0.7 : Math.max(0.9 + 0.8, tl.wallAt(path.flightT * 0.55));
      add("bay", 0, short ? 0.7 : 0.9);
      if (!short) add("tower", 0.9, targetFrom);
      add("target", short ? 0.7 : targetFrom, restWall + 0.4);
      add("orbit", restWall + 0.4, total);
    }

    return {
      mode: mode,
      drama: drama,
      totalMs: Math.round(total * 1000),
      restMs: Math.round(restWall * 1000),
      landMs: Math.round(landWall * 1000),
      flightT: path.flightT,
      inCup: path.inCup,
      shots: shots,
      simAt: tl.simAt,
      ball: function (wall) { return path.at(tl.simAt(wall)); },
      tracerProgress: function (wall) { return clamp(tl.simAt(wall) / path.flightT, 0, 1); },
      shotIndexAt: function (wall) {
        for (var i = 0; i < shots.length; i++) if (wall < shots[i].t1) return i;
        return shots.length - 1;
      },
      camera: function (index, wall, ballPos) {
        var sh = shots[index];
        return CAMERAS[sh.type](c, ballPos, tl.simAt(wall), wall - sh.t0);
      }
    };
  }

  var api = { assess: assess, plan: plan, idleCamera: CAMERAS.range, RANDOM_BROADCAST: RANDOM_BROADCAST };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.GarageDirector = api;
})(this);
