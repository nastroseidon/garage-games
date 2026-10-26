/* Game definitions. Each game turns a shot into points and knows how to
 * draw its targets on the range. Distances are in yards; "offline" is
 * positive to the right of the target line.
 *
 * Adding a game: copy one of these objects, give it a new id, and add it
 * to the GAMES list at the bottom.
 */
(function (root) {
  "use strict";

  var JUNIOR = 0.5; // juniors' targets are this fraction of the adult distance

  function randStep(min, max, step) {
    var n = Math.floor((max - min) / step) + 1;
    return min + step * Math.floor(Math.random() * n);
  }

  function dist(shot, d, l) {
    var dx = shot.flight.carry_yd - d;
    var dy = shot.flight.offline_yd - l;
    return Math.sqrt(dx * dx + dy * dy);
  }

  function fmtYards(yd) {
    if (yd < 10) return Math.round(yd * 3) + " ft";
    return yd.toFixed(1) + " yds";
  }

  function kindFor(distance) {
    if (distance < 45) return "chip";
    if (distance < 100) return "wedge";
    if (distance < 170) return "iron";
    return "driver";
  }

  function scaled(base, player, keys) {
    var t = Object.assign({}, base);
    if (player.junior) keys.forEach(function (k) { t[k] = Math.round(base[k] * JUNIOR); });
    return t;
  }

  function circle(g, view, d, l, r, fill, stroke) {
    var p = view.px(d, l);
    g.beginPath();
    g.arc(p[0], p[1], Math.max(2, r * view.scale), 0, Math.PI * 2);
    if (fill) { g.fillStyle = fill; g.fill(); }
    if (stroke) { g.strokeStyle = stroke; g.lineWidth = 2; g.stroke(); }
  }

  function flag(g, view, d, l, color) {
    var p = view.px(d, l);
    var h = Math.max(30, view.scale * 6);
    g.strokeStyle = "#fff"; g.lineWidth = 3;
    g.beginPath(); g.moveTo(p[0], p[1]); g.lineTo(p[0], p[1] - h); g.stroke();
    g.fillStyle = color || "#ff3b3b";
    g.beginPath(); g.moveTo(p[0], p[1] - h); g.lineTo(p[0] + h * 0.6, p[1] - h * 0.8);
    g.lineTo(p[0], p[1] - h * 0.6); g.closePath(); g.fill();
    circle(g, view, d, l, 0.4, "#111");
  }

  function label(g, view, d, l, text, color, size) {
    var p = view.px(d, l);
    g.font = "bold " + (size || 18) + "px Segoe UI, sans-serif";
    g.fillStyle = color || "#fff";
    g.textAlign = "center"; g.textBaseline = "middle";
    g.fillText(text, p[0], p[1]);
  }

  /* ---------------- Closest to the Pin ---------------- */
  var closest = {
    id: "closest",
    name: "Closest to the Pin",
    emoji: "📍",
    blurb: "A new pin every round. Fewest total yards from the flag wins.",
    view: "range",
    lowerIsBetter: true,
    combine: "sum",
    cap: 50,
    missPoints: 50,
    formatScore: function (v) { return v.toFixed(1) + " yds"; },
    makeTarget: function () { return { pin: randStep(50, 150, 5) }; },
    playerTarget: function (base, p) { return scaled(base, p, ["pin"]); },
    task: function (t) { return "Pin: " + t.pin + " yds"; },
    extent: function (t) { return t.pin; },
    testKind: function (t) { return kindFor(t.pin); },
    score: function (shot, t) {
      var miss = dist(shot, t.pin, 0);
      var pts = Math.min(this.cap, miss);
      return {
        points: pts,
        what: fmtYards(miss),
        detail: miss <= 3 ? "Tap-in range!" : miss <= 8 ? "Great shot" : "from the pin",
        great: miss <= 5,
        mark: [t.pin, 0]
      };
    },
    draw: function (g, view, t) {
      circle(g, view, t.pin, 0, 12, "rgba(120, 220, 120, 0.35)");
      circle(g, view, t.pin, 0, 5, null, "rgba(255,255,255,0.35)");
      circle(g, view, t.pin, 0, 10, null, "rgba(255,255,255,0.2)");
      flag(g, view, t.pin, 0);
    }
  };

  /* ---------------- Target Darts ---------------- */
  var RINGS = [[3, 50], [7, 30], [12, 20], [18, 10], [25, 5]];
  var darts = {
    id: "darts",
    name: "Target Darts",
    emoji: "🎯",
    blurb: "Land it in the rings. Bullseye is 50. Most points wins.",
    view: "range",
    lowerIsBetter: false,
    combine: "sum",
    missPoints: 0,
    formatScore: function (v) { return v + " pts"; },
    makeTarget: function () { return { d: randStep(60, 140, 10) }; },
    playerTarget: function (base, p) { return scaled(base, p, ["d"]); },
    task: function (t) { return "Bullseye at " + t.d + " yds"; },
    extent: function (t) { return t.d + 25; },
    testKind: function (t) { return kindFor(t.d); },
    score: function (shot, t) {
      var miss = dist(shot, t.d, 0);
      var pts = 0;
      for (var i = 0; i < RINGS.length; i++) {
        if (miss <= RINGS[i][0]) { pts = RINGS[i][1]; break; }
      }
      return {
        points: pts,
        what: pts === 50 ? "BULLSEYE!" : pts ? pts + " points" : "Missed",
        detail: fmtYards(miss) + " from center",
        great: pts >= 30,
        mark: [t.d, 0]
      };
    },
    draw: function (g, view, t) {
      var colors = ["#ff3b3b", "#ffffff", "#2f80ed", "#ffffff", "#ffd23f"];
      for (var i = RINGS.length - 1; i >= 0; i--) {
        circle(g, view, t.d, 0, RINGS[i][0], colors[i] + (i % 2 ? "55" : "99"), "rgba(0,0,0,0.4)");
      }
      for (var j = 1; j < RINGS.length; j++) {
        var r = (RINGS[j][0] + RINGS[j - 1][0]) / 2;
        label(g, view, t.d + r, 0, String(RINGS[j][1]), "#fff", 14);
      }
      label(g, view, t.d, 0, "50", "#fff", 16);
    }
  };

  /* ---------------- Hit the Number (ball speed) ---------------- */
  var speed = {
    id: "speed",
    name: "Hit the Number",
    emoji: "⚡",
    blurb: "Match the target ball speed. Pure feel - great for chips and kids.",
    view: "speed",
    lowerIsBetter: true,
    combine: "sum",
    cap: 30,
    missPoints: 30,
    formatScore: function (v) { return v.toFixed(1) + " mph off"; },
    makeTarget: function () { return { mph: randStep(30, 100, 5) }; },
    playerTarget: function (base, p) {
      return p.junior ? { mph: Math.max(15, Math.round(base.mph * JUNIOR / 5) * 5) } : base;
    },
    task: function (t) { return "Hit it " + t.mph + " mph"; },
    testKind: function (t) { return t.mph < 50 ? "chip" : t.mph < 90 ? "wedge" : "iron"; },
    score: function (shot, t) {
      var off = Math.abs(shot.speed_mph - t.mph);
      return {
        points: Math.min(this.cap, off),
        what: off <= 1 ? "BULLSEYE!" : shot.speed_mph.toFixed(1) + " mph",
        detail: off <= 1 ? "Within 1 mph!" : off.toFixed(1) + " mph " +
          (shot.speed_mph > t.mph ? "too hot" : "too soft"),
        great: off <= 3
      };
    }
  };

  /* ---------------- Long Drive (stay in the fairway) ---------------- */
  var FAIRWAY = 15;
  var longdrive = {
    id: "longdrive",
    name: "Long Drive",
    emoji: "💪",
    blurb: "Longest carry wins - but only if it lands in the fairway. Juniors count double.",
    view: "range",
    lowerIsBetter: false,
    combine: "max",
    missPoints: 0,
    formatScore: function (v) { return v.toFixed(1) + " yds"; },
    makeTarget: function () { return {}; },
    playerTarget: function (base, p) { return { junior: !!p.junior }; },
    task: function (t) {
      return "Stay within " + FAIRWAY + " yds of center" + (t.junior ? " (x2 bonus)" : "");
    },
    extent: function () { return 0; },
    testKind: function (t) { return t.junior ? "iron" : "driver"; },
    score: function (shot, t) {
      var carry = shot.flight.carry_yd;
      var inFairway = Math.abs(shot.flight.offline_yd) <= FAIRWAY;
      var counted = inFairway ? carry * (t.junior ? 2 : 1) : 0;
      return {
        points: Math.round(counted * 10) / 10,
        what: inFairway ? carry.toFixed(1) + " yds" : "In the rough!",
        detail: inFairway ? (t.junior ? "Junior x2 = " + counted.toFixed(1) + " yds" : "Carry")
          : carry.toFixed(1) + " yds, " + Math.abs(shot.flight.offline_yd).toFixed(1) + " yds " +
            (shot.flight.offline_yd > 0 ? "right" : "left"),
        great: inFairway && carry >= 200
      };
    },
    draw: function (g, view) {
      var a = view.px(0, -FAIRWAY), b = view.px(view.maxYd, FAIRWAY);
      g.fillStyle = "rgba(140, 230, 140, 0.18)";
      g.fillRect(a[0], b[1], b[0] - a[0], a[1] - b[1]);
      g.strokeStyle = "rgba(255,255,255,0.5)"; g.setLineDash([10, 10]); g.lineWidth = 2;
      g.beginPath(); g.moveTo(a[0], a[1]); g.lineTo(a[0], b[1]);
      g.moveTo(b[0], a[1]); g.lineTo(b[0], b[1]); g.stroke(); g.setLineDash([]);
    }
  };

  /* ---------------- Tic-Tac-Toe ---------------- */
  var COLS = [-24, -8, 8, 24];      // lateral edges, yards
  var ROWS = [40, 70, 100, 130];    // downrange edges, yards
  var LINES = [[0, 1, 2], [3, 4, 5], [6, 7, 8], [0, 3, 6], [1, 4, 7], [2, 5, 8], [0, 4, 8], [2, 4, 6]];
  var TEAMS = [{ name: "Team X", mark: "X", color: "#ff8c42" }, { name: "Team O", mark: "O", color: "#4ea8ff" }];

  function teamOf(ctx, playerIdx) { return playerIdx % 2; }

  function cellFor(shot, t) {
    var d = shot.flight.carry_yd, l = shot.flight.offline_yd;
    var row = -1, col = -1;
    for (var r = 0; r < 3; r++) if (d >= t.rows[r] && d < t.rows[r + 1]) row = r;
    for (var c = 0; c < 3; c++) if (l >= t.cols[c] && l < t.cols[c + 1]) col = c;
    if (row < 0 || col < 0) return -1;
    return (2 - row) * 3 + col; // top row of the board = farthest
  }

  var tictactoe = {
    id: "tictactoe",
    name: "Tic-Tac-Toe",
    emoji: "❌",
    blurb: "Two teams. Land in a square to claim it. Three in a row wins!",
    view: "range",
    lowerIsBetter: false,
    combine: "sum",
    missPoints: 0,
    minPlayers: 2,
    usesRounds: false,
    formatScore: function (v) { return v; },
    reset: function (ctx) { ctx.board = [null, null, null, null, null, null, null, null, null]; ctx.tttWinner = null; ctx.boards = 1; },
    playerForTurn: function (ctx, turn) {
      // Alternate teams every shot, rotating through each team's players.
      var team = turn % 2;
      var members = [];
      for (var i = 0; i < ctx.players.length; i++) if (teamOf(ctx, i) === team) members.push(i);
      return members[Math.floor(turn / 2) % members.length];
    },
    makeTarget: function () { return { cols: COLS, rows: ROWS }; },
    playerTarget: function (base, p) {
      if (!p.junior) return base;
      var s = function (v) { return Math.round(v * JUNIOR); };
      return { cols: base.cols.map(s), rows: base.rows.map(s) };
    },
    task: function (t, p, ctx, idx) { return TEAMS[teamOf(ctx, idx)].name + " - claim a square!"; },
    extent: function (t) { return t.rows[3]; },
    testKind: function (t) { return kindFor(t.rows[1]); },
    score: function (shot, t, p, ctx, idx) {
      var team = teamOf(ctx, idx);
      var cell = cellFor(shot, t);
      var res;
      if (cell < 0) res = { points: 0, what: "Off the board", detail: "No square claimed", great: false };
      else if (ctx.board[cell] !== null) res = { points: 0, what: "Already taken!", detail: "That square belongs to " + TEAMS[ctx.board[cell]].name, great: false };
      else {
        ctx.board[cell] = team;
        res = { points: 1, what: "Square claimed!", detail: TEAMS[team].name + " takes it", great: true };
        for (var i = 0; i < LINES.length; i++) {
          var L = LINES[i];
          if (ctx.board[L[0]] === team && ctx.board[L[1]] === team && ctx.board[L[2]] === team) {
            ctx.tttWinner = team;
            res.what = "THREE IN A ROW!";
            res.detail = TEAMS[team].name + " wins!";
          }
        }
        if (ctx.tttWinner === null && ctx.board.every(function (c) { return c !== null; })) {
          ctx.board = [null, null, null, null, null, null, null, null, null];
          ctx.boards++;
          res.detail = "Cat's game - new board!";
        }
      }
      return res;
    },
    isOver: function (ctx) { return ctx.tttWinner !== null && ctx.tttWinner !== undefined; },
    scoreboard: function (ctx, current) {
      return TEAMS.map(function (team, ti) {
        var owned = ctx.board.filter(function (c) { return c === ti; }).length;
        var names = ctx.players.filter(function (p, i) { return teamOf(ctx, i) === ti; })
          .map(function (p) { return p.name; }).join(", ");
        return {
          name: team.name + " (" + team.mark + ")", sub: names, color: team.color,
          value: owned + (owned === 1 ? " square" : " squares"),
          current: teamOf(ctx, current) === ti
        };
      });
    },
    winnerText: function (ctx) { return TEAMS[ctx.tttWinner].name + " wins!"; },
    draw: function (g, view, t, ctx) {
      for (var cell = 0; cell < 9; cell++) {
        var row = 2 - Math.floor(cell / 3), col = cell % 3;
        var a = view.px(t.rows[row], t.cols[col]), b = view.px(t.rows[row + 1], t.cols[col + 1]);
        var owner = ctx.board[cell];
        g.fillStyle = owner === null ? "rgba(255,255,255,0.08)" : TEAMS[owner].color + "88";
        g.fillRect(a[0], b[1], b[0] - a[0], a[1] - b[1]);
        g.strokeStyle = "rgba(255,255,255,0.8)"; g.lineWidth = 3;
        g.strokeRect(a[0], b[1], b[0] - a[0], a[1] - b[1]);
        if (owner !== null) {
          var size = Math.min(b[0] - a[0], a[1] - b[1]) * 0.7;
          g.font = "900 " + Math.round(size) + "px Segoe UI, sans-serif";
          g.fillStyle = "#fff"; g.textAlign = "center"; g.textBaseline = "middle";
          g.fillText(TEAMS[owner].mark, (a[0] + b[0]) / 2, (a[1] + b[1]) / 2);
        }
      }
    }
  };

  /* ================= Target Range (3D view, real balls) =================
   * Seven target greens. A ball that lands in a target stays there (they
   * are dish-shaped), and a ball that lands short can roll into one.
   */
  var TARGETS = [
    { name: "Red", color: "#ff4d4d", d: 20, l: -4, r: 5, pts: 1 },
    { name: "Yellow", color: "#ffd23f", d: 50, l: 7, r: 7, pts: 2 },
    { name: "Green", color: "#3ddc84", d: 85, l: -9, r: 9, pts: 3 },
    { name: "Blue", color: "#4ea8ff", d: 120, l: 8, r: 11, pts: 4 },
    { name: "Purple", color: "#c77dff", d: 155, l: -12, r: 13, pts: 5 },
    { name: "White", color: "#f2f2f2", d: 190, l: 12, r: 15, pts: 6 },
    { name: "Gold", color: "#ffa630", d: 225, l: -4, r: 17, pts: 8 }
  ];
  var INNER = 0.4;          // inner ring = 40% of the radius: double points
  var CENTER = 1.5;         // within 1.5 yds of the flag: triple points
  var ZONE_MULT = { center: 3, inner: 2, outer: 1 };
  var ZONE_TEXT = { center: "Flag zone x3", inner: "Inner ring x2", outer: "" };
  var JUNIOR_BONUS = 2;     // juniors get +2 on every target hit
  var LADDER = { adult: 5, junior: 3 };

  function targetAt(p) {
    for (var i = 0; i < TARGETS.length; i++) {
      var T = TARGETS[i];
      var dd = Math.sqrt(Math.pow(p[0] - T.d, 2) + Math.pow(p[1] - T.l, 2));
      if (dd <= T.r) return { i: i, dd: dd };
    }
    return null;
  }

  /* Where the ball ends up: {target (index or -1), zone, stop [d, l], rolledIn}. */
  function rangeHit(shot) {
    var f = shot.flight;
    var land = [f.carry_yd, f.offline_yd];
    var rest = f.rest || land;
    var hit = targetAt(land);
    if (hit) {
      var zone = hit.dd <= CENTER ? "center" : hit.dd <= TARGETS[hit.i].r * INNER ? "inner" : "outer";
      return { target: hit.i, zone: zone, stop: land, rolledIn: false };
    }
    var len = Math.sqrt(Math.pow(rest[0] - land[0], 2) + Math.pow(rest[1] - land[1], 2));
    var steps = Math.ceil(len / 0.5);
    for (var s = 1; s <= steps; s++) {
      var p = [land[0] + (rest[0] - land[0]) * s / steps, land[1] + (rest[1] - land[1]) * s / steps];
      hit = targetAt(p);
      if (hit) return { target: hit.i, zone: "outer", stop: p, rolledIn: true };
    }
    return { target: -1, zone: null, stop: rest, rolledIn: false };
  }

  /* How far (yds) a miss finished from the nearest target edge, or null on a hit. */
  function nearMiss(shot) {
    var f = shot.flight;
    if (rangeHit(shot).target >= 0) return null;
    var pts = [[f.carry_yd, f.offline_yd], f.rest || [f.carry_yd, f.offline_yd]];
    var best = Infinity;
    TARGETS.forEach(function (T) {
      pts.forEach(function (p) {
        best = Math.min(best, Math.sqrt(Math.pow(p[0] - T.d, 2) + Math.pow(p[1] - T.l, 2)) - T.r);
      });
    });
    return Math.max(0, best);
  }

  /* Animation timing shared by the scorer and the 3D renderer. */
  function rangeTiming(shot, stop) {
    var f = shot.flight;
    var flightMs = Math.min(5500, Math.max(1200, f.flight_time_s * 800));
    var land = [f.carry_yd, f.offline_yd];
    var end = stop || f.rest || land;
    var roll = Math.sqrt(Math.pow(end[0] - land[0], 2) + Math.pow(end[1] - land[1], 2));
    var rollMs = roll > 0.3 ? 400 + Math.min(1400, roll * 50) : 0;
    return { flightMs: flightMs, rollMs: rollMs, totalMs: flightMs + rollMs };
  }

  function hash(str) {
    var h = 2166136261;
    for (var i = 0; i < str.length; i++) { h ^= str.charCodeAt(i); h = Math.imul(h, 16777619); }
    return h >>> 0;
  }

  function hitText(hit, pts) {
    var T = TARGETS[hit.target];
    var bits = [];
    if (ZONE_TEXT[hit.zone]) bits.push(ZONE_TEXT[hit.zone]);
    if (hit.rolledIn) bits.push("rolled in!");
    return { what: T.name.toUpperCase() + "  +" + pts, detail: bits.join(" · ") || T.name + " target", color: T.color };
  }

  function yds(v) { var n = Math.round(v); return n + (n === 1 ? " yd" : " yds"); }

  function missText(shot) {
    var f = shot.flight;
    return {
      what: "No target",
      detail: f.total_yd.toFixed(0) + " yds, " + yds(Math.abs(f.rest[1])) + " " + (f.rest[1] >= 0 ? "right" : "left")
    };
  }

  var rangeBase = {
    view: "range3d",
    lowerIsBetter: false,
    combine: "sum",
    missPoints: 0,
    roundChoices: [5, 10, 20],
    defaultRounds: 10,
    formatScore: function (v) { return v + " pts"; },
    animMs: function (shot, result) { return rangeTiming(shot, result && result.stop).totalMs; },
    testKind: function () { return ["chip", "wedge", "iron", "iron", "driver"][Math.floor(Math.random() * 5)]; },
    highlight: function () { return -1; }
  };

  var targetRange = Object.assign({}, rangeBase, {
    id: "targetrange",
    name: "Target Range",
    pressureGap: 10,   // "one good shot" - scores this close late in the game are pressure shots
    emoji: "🏟️",
    blurb: "Hit any target. Farther targets and inner rings score more. Final ball counts double!",
    makeTarget: function (round) { return { round: round }; },
    playerTarget: function (base, p) { return { round: base.round, junior: !!p.junior }; },
    task: function (t, p, ctx) {
      return t.round === ctx.rounds - 1 ? "FINAL BALL - double points!" : "Hit any target";
    },
    score: function (shot, t, p, ctx) {
      var hit = rangeHit(shot);
      if (hit.target < 0) return Object.assign({ points: 0, great: false, stop: hit.stop }, missText(shot));
      var last = t.round === ctx.rounds - 1;
      var pts = (TARGETS[hit.target].pts + (t.junior ? JUNIOR_BONUS : 0)) * ZONE_MULT[hit.zone] * (last ? 2 : 1);
      var txt = hitText(hit, pts);
      if (last) txt.detail = (txt.detail ? txt.detail + " · " : "") + "final ball x2";
      return Object.assign({ points: pts, great: true, stop: hit.stop, hitTarget: hit.target }, txt);
    }
  });

  var calledShot = Object.assign({}, rangeBase, {
    id: "calledshot",
    name: "Called Shot",
    pressureGap: 14,
    emoji: "📣",
    blurb: "Every ball gets a called target. Hit it for double points - any other target scores zero.",
    roundChoices: [5, 10],
    defaultRounds: 5,
    makeTarget: function () { return { seed: Math.floor(Math.random() * 1e9) }; },
    playerTarget: function (base, p) {
      var choices = p.junior ? 3 : TARGETS.length;
      return { called: hash(base.seed + ":" + p.name) % choices, junior: !!p.junior };
    },
    task: function (t) {
      var T = TARGETS[t.called];
      return "Called: " + T.name.toUpperCase() + " (" + T.d + " yds)";
    },
    highlight: function (t) { return t.called; },
    testKind: function (t) { return kindFor(TARGETS[t.called].d); },
    score: function (shot, t) {
      var hit = rangeHit(shot);
      if (hit.target < 0) return Object.assign({ points: 0, great: false, stop: hit.stop }, missText(shot));
      if (hit.target !== t.called) {
        return { points: 0, great: false, stop: hit.stop, what: "Wrong target!",
          detail: "That was " + TARGETS[hit.target].name + " - needed " + TARGETS[t.called].name };
      }
      var pts = (TARGETS[hit.target].pts + (t.junior ? JUNIOR_BONUS : 0)) * ZONE_MULT[hit.zone] * 2;
      var txt = hitText(hit, pts);
      txt.what = "CALLED IT!  +" + pts;
      return Object.assign({ points: pts, great: true, stop: hit.stop, hitTarget: hit.target }, txt);
    }
  });

  function ladderStep(ctx, idx) {
    return ctx.history.filter(function (r) { return r.idx === idx && r.result.points > 0; }).length;
  }
  function ladderLength(p) { return p.junior ? LADDER.junior : LADDER.adult; }

  var ladder = Object.assign({}, rangeBase, {
    id: "ladder",
    name: "Ladder Climb",
    emoji: "🪜",
    blurb: "Hit the targets in order, nearest first. First to the top wins. Juniors climb 3, adults 5.",
    roundChoices: [10, 20],
    defaultRounds: 10,
    formatScore: function (v) { return "Step " + v; },
    makeTarget: function () { return {}; },
    playerTarget: function (base, p) { return { junior: !!p.junior }; },
    task: function (t, p, ctx, idx) {
      var step = ladderStep(ctx, idx), T = TARGETS[Math.min(step, TARGETS.length - 1)];
      return "Climb to " + T.name.toUpperCase() + " (" + T.d + " yds) - step " + (step + 1) + " of " + ladderLength(p);
    },
    highlight: function (t, ctx, idx) { return Math.min(ladderStep(ctx, idx), TARGETS.length - 1); },
    testKind: function (t, ctx, idx) { return kindFor(TARGETS[Math.min(ladderStep(ctx, idx), TARGETS.length - 1)].d); },
    score: function (shot, t, p, ctx, idx) {
      var step = ladderStep(ctx, idx);
      var hit = rangeHit(shot);
      if (hit.target === step) {
        var done = step + 1 >= ladderLength(p);
        return { points: 1, great: true, stop: hit.stop, hitTarget: hit.target, color: TARGETS[step].color,
          what: done ? "TOP OF THE LADDER!" : TARGETS[step].name.toUpperCase() + " ✓",
          detail: done ? p.name + " wins!" : "Next up: " + TARGETS[step + 1].name };
      }
      if (hit.target >= 0) {
        return { points: 0, great: false, stop: hit.stop, what: "Wrong rung!",
          detail: "Hit " + TARGETS[hit.target].name + " - need " + TARGETS[step].name };
      }
      return Object.assign({ points: 0, great: false, stop: hit.stop }, missText(shot));
    },
    isOver: function (ctx) {
      for (var i = 0; i < ctx.players.length; i++) {
        if (ladderStep(ctx, i) >= ladderLength(ctx.players[i])) return true;
      }
      return ctx.turn >= ctx.rounds * ctx.players.length;
    }
  });

  var GAMES = [targetRange, calledShot, ladder, closest, darts, speed, longdrive, tictactoe];
  var api = {
    GAMES: GAMES, fmtYards: fmtYards, kindFor: kindFor, JUNIOR: JUNIOR,
    TARGETS: TARGETS, INNER: INNER, CENTER: CENTER, rangeHit: rangeHit, rangeTiming: rangeTiming,
    nearMiss: nearMiss, ladderLength: ladderLength
  };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.GarageGames = api;
})(this);
