/* Target Range 3D view: a down-the-line look at the target greens, drawn
 * on a 2D canvas with a simple perspective camera (no libraries).
 *
 * World units are yards: d = downrange, l = right of center, h = height.
 */
(function (root) {
  "use strict";

  var DEG = Math.PI / 180;
  var CAM = {
    fov: 32,         // vertical field of view, degrees
    height: 30,      // camera height above the mat, yards (high, so far targets spread out)
    horizon: 0.1,    // where the horizon sits, as a fraction of screen height
    tee: 0.94        // where the hitting mat sits, as a fraction of screen height
  };
  var FIELD_WIDTH = 55;   // side nets at +/- this many yards
  var FIELD_DEPTH = 270;  // back net

  /* Build a projector for a W x H canvas: (d, l, h) -> [x, y, pxPerYard]. */
  function camera(W, H) {
    var F = (H / 2) / Math.tan(CAM.fov / 2 * DEG);
    var pitch = Math.atan((0.5 - CAM.horizon) * H / F);
    var teeBelow = Math.atan((CAM.tee - 0.5) * H / F) + pitch;
    var back = CAM.height / Math.tan(teeBelow);
    var c = Math.cos(pitch), s = Math.sin(pitch);
    function project(d, l, h) {
      var rd = d + back, rh = (h || 0) - CAM.height;
      var z = rd * c - rh * s;
      if (z < 0.5) return null;
      var y = rd * s + rh * c;
      return [W / 2 + F * l / z, H / 2 - F * y / z, F / z];
    }
    return { project: project, horizonY: H / 2 - F * Math.tan(pitch), W: W, H: H };
  }

  function poly(g, cam, pts) {
    var first = true;
    g.beginPath();
    for (var i = 0; i < pts.length; i++) {
      var p = cam.project(pts[i][0], pts[i][1], pts[i][2]);
      if (!p) continue;
      if (first) { g.moveTo(p[0], p[1]); first = false; } else g.lineTo(p[0], p[1]);
    }
    g.closePath();
  }

  function ring(d, l, r, n) {
    var pts = [];
    for (var i = 0; i < n; i++) {
      var a = i / n * Math.PI * 2;
      pts.push([d + Math.cos(a) * r, l + Math.sin(a) * r, 0]);
    }
    return pts;
  }

  function drawSky(g, cam) {
    var sky = g.createLinearGradient(0, 0, 0, cam.horizonY);
    sky.addColorStop(0, "#0b1430");
    sky.addColorStop(0.7, "#27305a");
    sky.addColorStop(1, "#5b4a7a");
    g.fillStyle = sky;
    g.fillRect(0, 0, cam.W, cam.horizonY + 1);
    // tree line
    g.fillStyle = "#0e1f17";
    g.beginPath();
    g.moveTo(0, cam.horizonY);
    for (var x = 0; x <= cam.W; x += 24) {
      var bump = 6 + 5 * Math.sin(x * 0.031) + 4 * Math.sin(x * 0.11 + 1.3);
      g.lineTo(x, cam.horizonY - bump);
    }
    g.lineTo(cam.W, cam.horizonY);
    g.closePath();
    g.fill();
  }

  function drawGround(g, cam) {
    var grass = g.createLinearGradient(0, cam.horizonY, 0, cam.H);
    grass.addColorStop(0, "#173f26");
    grass.addColorStop(1, "#2f8a47");
    g.fillStyle = grass;
    g.fillRect(0, cam.horizonY, cam.W, cam.H - cam.horizonY);
    // mowing stripes
    g.fillStyle = "rgba(255,255,255,0.045)";
    for (var d = 0; d < FIELD_DEPTH; d += 20) {
      poly(g, cam, [[d, -FIELD_WIDTH, 0], [d, FIELD_WIDTH, 0], [d + 10, FIELD_WIDTH, 0], [d + 10, -FIELD_WIDTH, 0]]);
      g.fill();
    }
    // yardage lines and signs
    g.strokeStyle = "rgba(255,255,255,0.16)";
    g.lineWidth = 1;
    for (var y = 50; y < FIELD_DEPTH; y += 50) {
      var a = cam.project(y, -FIELD_WIDTH, 0), b = cam.project(y, FIELD_WIDTH, 0);
      g.beginPath(); g.moveTo(a[0], a[1]); g.lineTo(b[0], b[1]); g.stroke();
      [-1, 1].forEach(function (side) {
        var p = cam.project(y, side * (FIELD_WIDTH - 6), 2.2);
        var size = Math.max(10, Math.min(30, p[2] * 3));
        // keep near signs on screen
        p[0] = Math.max(size * 1.3, Math.min(cam.W - size * 1.3, p[0]));
        g.fillStyle = "rgba(255,255,255,0.85)";
        g.fillRect(p[0] - size * 1.1, p[1] - size * 0.6, size * 2.2, size * 1.2);
        g.fillStyle = "#183324";
        g.font = "bold " + Math.round(size * 0.8) + "px Segoe UI, sans-serif";
        g.textAlign = "center"; g.textBaseline = "middle";
        g.fillText(String(y), p[0], p[1] + 1);
      });
    }
  }

  function drawNets(g, cam) {
    g.strokeStyle = "rgba(220,230,255,0.35)";
    g.lineWidth = 1.5;
    var poleH = 24;
    [-1, 1].forEach(function (side) {
      var l = side * FIELD_WIDTH;
      var top = [];
      for (var d = 0; d <= FIELD_DEPTH; d += 30) {
        var base = cam.project(d, l, 0), tip = cam.project(d, l, poleH);
        if (!base) continue;
        g.beginPath(); g.moveTo(base[0], base[1]); g.lineTo(tip[0], tip[1]); g.stroke();
        top.push(tip);
      }
      g.beginPath();
      top.forEach(function (p, i) { if (i) g.lineTo(p[0], p[1]); else g.moveTo(p[0], p[1]); });
      g.stroke();
    });
    var bl = cam.project(FIELD_DEPTH, -FIELD_WIDTH, poleH), br = cam.project(FIELD_DEPTH, FIELD_WIDTH, poleH);
    g.beginPath(); g.moveTo(bl[0], bl[1]); g.lineTo(br[0], br[1]); g.stroke();
  }

  function drawTarget(g, cam, T, opts) {
    var dim = opts.dim, glow = opts.glow;
    g.globalAlpha = dim ? 0.35 : 1;
    // outer green
    poly(g, cam, ring(T.d, T.l, T.r, 64));
    g.fillStyle = T.color + "66";
    g.fill();
    g.lineWidth = glow ? 4 : 2;
    g.strokeStyle = glow ? "#ffffff" : T.color;
    g.stroke();
    // inner ring (double points)
    poly(g, cam, ring(T.d, T.l, T.r * opts.inner, 48));
    g.fillStyle = T.color + "bb";
    g.fill();
    // flag zone + cup
    poly(g, cam, ring(T.d, T.l, opts.center, 24));
    g.fillStyle = "rgba(255,255,255,0.35)";
    g.fill();
    poly(g, cam, ring(T.d, T.l, 0.5, 16));
    g.fillStyle = "#111";
    g.fill();
    // flag
    var base = cam.project(T.d, T.l, 0), tip = cam.project(T.d, T.l, 4);
    g.strokeStyle = "#fff"; g.lineWidth = Math.max(1, base[2] * 0.12);
    g.beginPath(); g.moveTo(base[0], base[1]); g.lineTo(tip[0], tip[1]); g.stroke();
    var fw = Math.max(5, base[2] * 1.4);
    g.fillStyle = T.color;
    g.beginPath(); g.moveTo(tip[0], tip[1]); g.lineTo(tip[0] + fw, tip[1] + fw * 0.3);
    g.lineTo(tip[0], tip[1] + fw * 0.6); g.closePath(); g.fill();
    // points badge, floating just above the flag
    var r = Math.max(13, Math.min(28, base[2] * 2.2));
    if (glow) r *= 1 + 0.12 * Math.sin(opts.now / 160);
    var badge = [tip[0], tip[1] - 6];
    g.beginPath(); g.arc(badge[0], badge[1] - r, r, 0, Math.PI * 2);
    g.fillStyle = T.color; g.fill();
    g.lineWidth = glow ? 4 : 2; g.strokeStyle = glow ? "#fff" : "rgba(0,0,0,0.5)"; g.stroke();
    g.fillStyle = T.color === "#f2f2f2" || T.color === "#ffd23f" ? "#222" : "#fff";
    g.font = "900 " + Math.round(r * 1.1) + "px Segoe UI, sans-serif";
    g.textAlign = "center"; g.textBaseline = "middle";
    g.fillText(String(T.pts), badge[0], badge[1] - r + 1);
    g.globalAlpha = 1;
  }

  function drawMat(g, cam, ballOnTee) {
    poly(g, cam, [[-0.8, -1.5, 0], [-0.8, 1.5, 0], [0.8, 1.5, 0], [0.8, -1.5, 0]]);
    g.fillStyle = "#1d4a2b"; g.fill();
    g.strokeStyle = "#e8e8e8"; g.lineWidth = 3; g.stroke();
    if (ballOnTee) {
      var p = cam.project(0, 0, 0);
      g.fillStyle = "#fff";
      g.beginPath(); g.arc(p[0], p[1] - 5, 6, 0, Math.PI * 2); g.fill();
    }
  }

  /* Ball position at a given time: {pos [d,l,hYd], trail [[d,l,hYd]...], phase}. */
  function ballState(shot, timing, elapsed) {
    var pts = shot.flight.points;
    var trail = [];
    if (elapsed < timing.flightMs) {
      var f = elapsed / timing.flightMs * (pts.length - 1);
      var i = Math.floor(f), frac = f - i;
      for (var k = 0; k <= i; k++) trail.push([pts[k][0], pts[k][1], pts[k][2] / 3]);
      var a = pts[i], b = pts[Math.min(i + 1, pts.length - 1)];
      var pos = [a[0] + (b[0] - a[0]) * frac, a[1] + (b[1] - a[1]) * frac, (a[2] + (b[2] - a[2]) * frac) / 3];
      trail.push(pos);
      return { pos: pos, trail: trail, phase: "flight" };
    }
    for (var j = 0; j < pts.length; j++) trail.push([pts[j][0], pts[j][1], pts[j][2] / 3]);
    var land = [shot.flight.carry_yd, shot.flight.offline_yd];
    var stop = shot.stop || land;
    var t = timing.rollMs ? Math.min(1, (elapsed - timing.flightMs) / timing.rollMs) : 1;
    var ease = 1 - Math.pow(1 - t, 2);
    var p = [land[0] + (stop[0] - land[0]) * ease, land[1] + (stop[1] - land[1]) * ease, 0];
    return { pos: p, trail: trail, phase: t < 1 ? "roll" : "rest", rollT: t };
  }

  function drawShot(g, cam, shot, timing) {
    var st = ballState(shot, timing, shot.elapsed);
    // tracer
    g.save();
    g.strokeStyle = shot.color; g.lineWidth = 4; g.lineCap = "round"; g.lineJoin = "round";
    g.shadowColor = shot.color; g.shadowBlur = 14;
    g.beginPath();
    var started = false;
    st.trail.forEach(function (q) {
      var p = cam.project(q[0], q[1], q[2]);
      if (!p) return;
      if (started) g.lineTo(p[0], p[1]); else { g.moveTo(p[0], p[1]); started = true; }
    });
    g.stroke();
    g.restore();
    // roll line
    if (st.phase !== "flight") {
      var land = cam.project(shot.flight.carry_yd, shot.flight.offline_yd, 0), now = cam.project(st.pos[0], st.pos[1], 0);
      g.strokeStyle = "rgba(255,255,255,0.6)"; g.lineWidth = 2; g.setLineDash([4, 5]);
      g.beginPath(); g.moveTo(land[0], land[1]); g.lineTo(now[0], now[1]); g.stroke(); g.setLineDash([]);
    }
    // shadow + ball
    var sh = cam.project(st.pos[0], st.pos[1], 0), ball = cam.project(st.pos[0], st.pos[1], st.pos[2]);
    if (!sh || !ball) return st;
    var r = Math.max(4, Math.min(12, ball[2] * 0.5));
    g.fillStyle = "rgba(0,0,0,0.4)";
    g.beginPath(); g.ellipse(sh[0], sh[1], r * 1.2, r * 0.45, 0, 0, Math.PI * 2); g.fill();
    g.fillStyle = "#fff"; g.strokeStyle = shot.color; g.lineWidth = 2.5;
    g.beginPath(); g.arc(ball[0], ball[1] - r * 0.3, r, 0, Math.PI * 2); g.fill(); g.stroke();
    // landing burst once the ball comes to rest in a target
    if (st.phase === "rest" && shot.hitColor) {
      var since = shot.elapsed - timing.totalMs;
      if (since < 1200) {
        var k = since / 1200;
        g.globalAlpha = 1 - k;
        poly(g, cam, ring(st.pos[0], st.pos[1], 1 + k * 10, 32));
        g.strokeStyle = shot.hitColor; g.lineWidth = 5; g.stroke();
        g.globalAlpha = 1;
      }
    }
    return st;
  }

  function drawMinimap(g, cam, targets, opts, ballPos) {
    var w = Math.min(170, cam.W * 0.16), h = w * 1.55;
    var x0 = cam.W - w - 14, y0 = 14;
    var maxD = 250, halfL = 40;
    var mx = function (l) { return x0 + w / 2 + l / halfL * (w / 2); };
    var my = function (d) { return y0 + h - 8 - d / maxD * (h - 16); };
    g.fillStyle = "rgba(8, 20, 14, 0.8)";
    g.strokeStyle = "rgba(255,255,255,0.3)"; g.lineWidth = 1.5;
    g.fillRect(x0, y0, w, h); g.strokeRect(x0, y0, w, h);
    var sc = (h - 16) / maxD;
    targets.forEach(function (T, i) {
      g.globalAlpha = opts.highlight >= 0 && opts.highlight !== i ? 0.4 : 1;
      g.beginPath(); g.arc(mx(T.l), my(T.d), Math.max(3, T.r * sc), 0, Math.PI * 2);
      g.fillStyle = T.color + "aa"; g.fill();
      if (opts.highlight === i) { g.strokeStyle = "#fff"; g.lineWidth = 2; g.stroke(); }
    });
    g.globalAlpha = 1;
    (opts.markers || []).forEach(function (m) {
      g.beginPath(); g.arc(mx(m.p[1]), my(Math.min(maxD, m.p[0])), 2.5, 0, Math.PI * 2);
      g.fillStyle = m.color; g.fill();
    });
    if (ballPos) {
      g.beginPath(); g.arc(mx(ballPos[1]), my(Math.min(maxD, ballPos[0])), 4, 0, Math.PI * 2);
      g.fillStyle = "#fff"; g.fill();
      g.strokeStyle = opts.shot.color; g.lineWidth = 2; g.stroke();
    }
  }

  /* opts: {targets, inner, center, highlight, markers:[{p,color}], now,
   *        shot: {flight, color, stop, hitColor, elapsed} | null, timing} */
  function render(g, W, H, opts) {
    var cam = camera(W, H);
    drawSky(g, cam);
    drawGround(g, cam);
    drawNets(g, cam);
    var order = opts.targets.map(function (T, i) { return i; })
      .sort(function (a, b) { return opts.targets[b].d - opts.targets[a].d; });
    order.forEach(function (i) {
      drawTarget(g, cam, opts.targets[i], {
        inner: opts.inner, center: opts.center, now: opts.now,
        dim: opts.highlight >= 0 && opts.highlight !== i,
        glow: opts.highlight === i
      });
    });
    (opts.markers || []).forEach(function (m) {
      var p = cam.project(m.p[0], m.p[1], 0);
      if (!p) return;
      var r = Math.max(3, Math.min(8, p[2] * 0.4));
      g.beginPath(); g.ellipse(p[0], p[1], r, r * 0.5, 0, 0, Math.PI * 2);
      g.fillStyle = m.color; g.globalAlpha = 0.8; g.fill(); g.globalAlpha = 1;
    });
    drawMat(g, cam, !opts.shot);
    var st = opts.shot ? drawShot(g, cam, opts.shot, opts.timing) : null;
    drawMinimap(g, cam, opts.targets, opts, st && st.pos);
  }

  root.GarageRange3D = { render: render, camera: camera, CAM: CAM };
})(this);
