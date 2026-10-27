/* Garage Games screen: setup, scoreboard, and drawing.
 *
 * The game itself (turns, scoring, undo, the camera director) runs in the
 * Python server, so every screen shows the same game. This page sends
 * commands (start, undo, skip, ...) and draws the state and shot plans the
 * server sends back. web/games.js is only used here for drawing.
 */
(function () {
  "use strict";

  var DRAW = {};          // game id -> drawing helpers from web/games.js
  window.GarageGames.GAMES.forEach(function (g) { DRAW[g.id] = g; });
  var catalog = { games: [] };  // from /api/games: the games, targets and idle camera
  var COLORS = ["#ffd23f", "#ff6b6b", "#4ea8ff", "#3ddc84", "#c77dff", "#ff9f1c", "#2ec4b6", "#f15bb5"];
  var ROUND_CHOICES = [3, 5, 10];
  var BANNER_MS = 3500;

  var $ = function (id) { return document.getElementById(id); };
  var canvas = $("field");
  var g2 = canvas.getContext("2d");

  var players = loadPlayers();
  var selectedGame = null;
  var rounds = 5;
  var gameOpts = {};     // game id -> {option key: value} (Golf Cornhole's hole distance)
  var ctx = null;        // the running game: {info, game (drawing helpers), state (from the server), players, history, board}
  var replay = null;     // {rec, start, until} - the shot currently being shown
  var soundOn = true;
  var bannerTimer = null;
  var settings = loadSettings();  // {camera: auto|broadcast|quick|static, quality: high|low|classic}
  var gl = null, glQuality = null, glFailed = false;
  var bcTimers = [];
  var CAMERA_CHOICES = [["auto", "Auto broadcast"], ["broadcast", "Always broadcast"], ["quick", "Quick"], ["static", "Fixed"]];
  var QUALITY_CHOICES = [["high", "High"], ["low", "Low"], ["classic", "Classic 2D"]];

  /* ---------------- storage ---------------- */
  function loadPlayers() {
    try {
      var saved = JSON.parse(localStorage.getItem("gg.players") || "null");
      if (Array.isArray(saved)) return saved;
    } catch (e) { /* storage unavailable */ }
    return [];
  }
  function savePlayers() {
    try { localStorage.setItem("gg.players", JSON.stringify(players)); } catch (e) { /* ignore */ }
  }
  function loadSettings() {
    var s = { camera: "auto", quality: "high" };
    try { Object.assign(s, JSON.parse(localStorage.getItem("gg.settings") || "{}")); } catch (e) { /* ignore */ }
    return s;
  }
  function saveSettings() {
    try { localStorage.setItem("gg.settings", JSON.stringify(settings)); } catch (e) { /* ignore */ }
  }

  /* ---------------- setup screen ---------------- */
  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text !== undefined) e.textContent = text;
    return e;
  }

  function renderPlayers() {
    var list = $("player-list");
    list.innerHTML = "";
    players.forEach(function (p, i) {
      p.color = COLORS[i % COLORS.length];
      var li = el("li");
      var sw = el("span", "swatch"); sw.style.background = p.color;
      li.appendChild(sw);
      li.appendChild(el("span", "pname", p.name));
      var jr = el("button", "", p.junior ? "Junior ✓" : "Junior");
      jr.title = "Toggle junior";
      jr.onclick = function () { p.junior = !p.junior; savePlayers(); renderPlayers(); };
      li.appendChild(jr);
      var up = el("button", "", "▲");
      up.title = "Move up";
      up.disabled = i === 0;
      up.onclick = function () { players.splice(i - 1, 0, players.splice(i, 1)[0]); savePlayers(); renderPlayers(); };
      li.appendChild(up);
      var rm = el("button", "", "✕");
      rm.title = "Remove";
      rm.onclick = function () { players.splice(i, 1); savePlayers(); renderPlayers(); };
      li.appendChild(rm);
      list.appendChild(li);
    });
    if (!players.length) list.appendChild(el("li", "hint", "Add at least one player."));
  }

  function renderGameCards() {
    var box = $("game-cards");
    box.innerHTML = "";
    catalog.games.forEach(function (game) {
      var b = el("button", "game-card" + (game === selectedGame ? " selected" : ""));
      b.appendChild(el("div", "emoji", game.emoji));
      b.appendChild(el("div", "gname", game.name));
      b.appendChild(el("div", "blurb", game.blurb));
      b.onclick = function () { selectedGame = game; renderGameCards(); renderRounds(); renderGameOptions(); };
      box.appendChild(b);
    });
  }

  function renderRounds() {
    var box = $("rounds");
    box.innerHTML = "";
    if (!selectedGame) return;
    box.parentElement.style.visibility = selectedGame.uses_rounds === false ? "hidden" : "visible";
    var choices = selectedGame.round_choices || ROUND_CHOICES;
    if (choices.indexOf(rounds) < 0) rounds = selectedGame.default_rounds || choices[1];
    choices.forEach(function (n) {
      var b = el("button", n === rounds ? "selected" : "", String(n));
      b.onclick = function () { rounds = n; renderRounds(); };
      box.appendChild(b);
    });
  }

  // Extra choices a game asks for (e.g. Golf Cornhole's hole distance), from /api/games.
  function renderGameOptions() {
    var box = $("game-options");
    box.innerHTML = "";
    if (!selectedGame || !selectedGame.options) return;
    var chosen = gameOpts[selectedGame.id] = gameOpts[selectedGame.id] || {};
    selectedGame.options.forEach(function (o) {
      if (o.choices.indexOf(chosen[o.key]) < 0) chosen[o.key] = o.default;
      var row = el("div", "opt-row");
      row.appendChild(el("span", "", o.label + ":"));
      var seg = el("div", "seg");
      o.choices.forEach(function (v) {
        var b = el("button", v === chosen[o.key] ? "selected" : "", v + (o.unit ? " " + o.unit : ""));
        b.onclick = function () { chosen[o.key] = v; renderGameOptions(); };
        seg.appendChild(b);
      });
      row.appendChild(seg);
      box.appendChild(row);
    });
  }

  function renderOptions() {
    [["opt-camera", CAMERA_CHOICES, "camera"], ["opt-quality", QUALITY_CHOICES, "quality"]].forEach(function (o) {
      var box = $(o[0]);
      box.innerHTML = "";
      o[1].forEach(function (choice) {
        var b = el("button", settings[o[2]] === choice[0] ? "selected" : "", choice[1]);
        b.onclick = function () {
          settings[o[2]] = choice[0]; saveSettings(); renderOptions();
          if (o[2] === "camera") api("/api/settings", { camera: choice[0] });
        };
        box.appendChild(b);
      });
    });
  }

  $("add-player").onsubmit = function (e) {
    e.preventDefault();
    var name = $("new-name").value.trim();
    if (!name) return;
    players.push({ name: name, junior: $("new-junior").checked });
    $("new-name").value = "";
    $("new-junior").checked = false;
    savePlayers();
    renderPlayers();
    $("new-name").focus();
  };

  $("btn-start").onclick = function () { startGame(selectedGame); };

  /* ---------------- talking to the server ---------------- */
  function api(path, body) {
    return fetch(path, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body || {})
    }).then(function (r) {
      return r.json().then(function (data) {
        if (!r.ok) throw new Error(data.error || "request failed");
        return data;
      });
    });
  }

  function infoFor(id) {
    return catalog.games.filter(function (g) { return g.id === id; })[0];
  }

  /* ---------------- game state (owned by the server) ---------------- */
  function startGame(info) {
    if (!info) return;
    var need = info.min_players || 1;
    if (players.length < need) {
      $("setup-error").textContent = info.name + " needs at least " + need + " player" + (need > 1 ? "s" : "") + ".";
      return;
    }
    $("setup-error").textContent = "";
    api("/api/game/start", {
      game: info.id, rounds: rounds, camera: settings.camera, options: gameOpts[info.id] || {},
      players: players.map(function (p) { return { name: p.name, junior: !!p.junior, color: p.color }; })
    }).catch(function (e) { $("setup-error").textContent = e.message; });
  }

  // Keep the local view of the game in step with the server's state.
  function applyState(state) {
    if (!state.active) { ctx = null; return; }
    if (!ctx || ctx.state.game !== state.game) {
      ctx = { info: infoFor(state.game), game: DRAW[state.game] };
    }
    ctx.state = state;
    ctx.players = state.players;
    ctx.history = state.history;
    ctx.board = state.board;
    ctx.rounds = state.rounds;
  }

  function onState(state) {
    if (state.camera && state.camera !== settings.camera) {
      settings.camera = state.camera; saveSettings(); renderOptions();
    }
    var wasPlaying = !!ctx;
    applyState(state);
    if (!ctx) {
      replay = null;
      clearBroadcast();
      hideOverlay();
      if (wasPlaying || state.reason === "sync") { showScreen("setup"); renderPlayers(); }
      return;
    }
    if (state.reason === "start" || state.reason === "sync" || state.reason === "undo" || !wasPlaying) {
      replay = null;
      clearBroadcast();
      hideOverlay();
      hideBanner();
      showScreen("game");
      $("game-title").textContent = ctx.info.emoji + " " + ctx.info.name;
      $("last-shot").innerHTML = "";
      renderSide();
      if (state.over) setTimeout(showWinner, 300);
    } else if (state.reason === "skip") {
      replay = null;
      afterTurn();
    }
  }

  function playerCount() { return ctx.players.length; }
  function isCornhole() { return !!ctx && ctx.info.view === "cornhole"; }
  function isOver() { return ctx.state.over; }

  function skipTurn() { if (ctx && !isOver()) api("/api/game/skip"); }
  function undo() { if (ctx && ctx.history.length) api("/api/game/undo"); }

  function renderBoard(list, rows, numbered) {
    list.innerHTML = "";
    rows.forEach(function (r, i) {
      var li = el("li", r.current ? "current" : "");
      if (numbered) li.appendChild(el("span", "rank", String(i + 1)));
      var sw = el("span", "swatch"); sw.style.background = r.color;
      li.appendChild(sw);
      var nameBox = el("span", "sname", r.name);
      if (r.sub) { nameBox.appendChild(el("div", "ssub", r.sub)); }
      li.appendChild(nameBox);
      li.appendChild(el("span", "sval", String(r.value)));
      list.appendChild(li);
    });
  }

  function renderSide() {
    if (!ctx) return;
    var s = ctx.state, cur = s.current;
    $("up-name").textContent = cur.name;
    $("up-name").style.color = cur.color;
    $("up-task").textContent = cur.task;
    $("round-info").textContent = s.round_info;
    renderHeadline(s.headline);
    renderBoard($("scoreboard"), s.scoreboard, s.numbered);
  }

  // head-to-head game score (Golf Cornhole), each side's number in its own color
  function renderHeadline(h) {
    var box = $("h2h");
    box.innerHTML = "";
    box.style.display = h ? "" : "none";
    $("board-title").textContent = h && h.board_title ? h.board_title : "Scoreboard";
    if (!h) return;
    box.appendChild(el("div", "small", h.label));
    var row = el("div", "h2h-row");
    h.sides.forEach(function (sd, i) {
      if (i) row.appendChild(el("span", "h2h-dash", "-"));
      var v = el("span", "h2h-val", String(sd.value));
      v.style.color = sd.color;
      v.title = sd.name;
      row.appendChild(v);
    });
    box.appendChild(row);
  }

  function renderLastShot(shot) {
    var f = shot.flight;
    var items = [
      ["Ball speed", shot.speed_mph.toFixed(1) + " mph"],
      ["Launch", shot.vla_deg.toFixed(1) + "°"],
      ["Spin", Math.round(shot.spin_rpm) + " rpm"],
      ["Direction", Math.abs(shot.hla_deg).toFixed(1) + "° " + (shot.hla_deg >= 0 ? "R" : "L")],
      ["Carry", f.carry_yd.toFixed(1) + " yds"],
      ["Offline", Math.abs(f.offline_yd).toFixed(1) + " " + (f.offline_yd >= 0 ? "R" : "L")]
    ];
    if (ctx && ctx.info.view !== "speed" && f.total_yd) items.push(["Total (with roll)", f.total_yd.toFixed(1) + " yds"]);
    if (shot.club_speed_mph) {
      items.push(["Club speed", shot.club_speed_mph.toFixed(1) + " mph"]);
      items.push(["Smash", (shot.speed_mph / shot.club_speed_mph).toFixed(2)]);
    }
    var box = $("last-shot");
    box.innerHTML = "";
    items.forEach(function (it) {
      var d = el("div", "", it[0]);
      d.appendChild(el("br"));
      d.appendChild(el("b", "", it[1]));
      box.appendChild(d);
    });
  }

  function afterTurn(sideLater) {
    if (!sideLater) renderSide();
    if (isOver()) setTimeout(showWinner, replay ? replay.dur + 2000 : 300);
  }

  /* ---------------- shots ---------------- */
  function onShot(ev) {
    var shot = ev.shot;
    if (ev.free || !ctx) {
      $("free-shot").textContent = "Last shot: " + shot.speed_mph.toFixed(1) + " mph, " +
        shot.flight.carry_yd.toFixed(1) + " yds carry (start a game to score it)";
      sound("blip");
      return;
    }
    applyState(ev.state);
    var rec = { turn: ev.turn, idx: ev.idx, shot: shot, target: ev.target, result: ev.result,
      highlight: ev.highlight, scores: ev.scores };
    var now = performance.now();
    clearBroadcast();
    if (ev.plan && (glRenderer() || isCornhole())) {
      var plan = window.GarageShotPlan.player(ev.plan);
      replay = { rec: rec, start: now, dur: plan.totalMs, until: now + plan.totalMs, plan: plan };
      if (plan.mode === "broadcast") runBroadcast(rec, plan);
      else later(plan.restMs, function () { showBanner(rec); });
      // keep the shot numbers and scoreboard hidden until the ball stops - no spoilers
      $("last-shot").innerHTML = "";
      later(plan.restMs, function () { renderLastShot(shot); renderSide(); });
      afterTurn(true);
      return;
    }
    renderLastShot(shot);
    var dur = ctx.game && ctx.game.animMs ? ctx.game.animMs(shot, rec.result) : ev.anim_ms;
    replay = { rec: rec, start: now, dur: dur, until: now + dur + BANNER_MS };
    setTimeout(function () { showBanner(rec); }, ctx.info.view === "speed" ? 900 : dur);
    afterTurn();
  }

  /* ---------------- broadcast moments ---------------- */
  // Timers tied to the shot on screen; cleared when the next shot (or undo) arrives.
  function later(ms, fn) { bcTimers.push(setTimeout(fn, ms)); }

  function clearBroadcast() {
    bcTimers.forEach(clearTimeout);
    bcTimers = [];
    hideBanner();
    $("bc").classList.remove("on");
    $("bc-lower").classList.remove("show");
    $("bc-data").classList.remove("show");
  }

  function renderBug(totals, shooter) {
    var list = $("bc-scores");
    list.innerHTML = "";
    ctx.players.map(function (p, i) { return { p: p, i: i, v: totals[i] }; })
      .sort(function (a, b) { return b.v - a.v; })
      .slice(0, 4)
      .forEach(function (row) {
        var li = el("li", row.i === shooter ? "shooter" : "");
        var dot = el("span", "dot"); dot.style.background = row.p.color;
        li.appendChild(dot);
        li.appendChild(el("span", "n", row.p.name));
        li.appendChild(el("span", "", ctx.game ? ctx.game.formatScore(row.v) : String(row.v)));
        list.appendChild(li);
      });
  }

  function lowerThird(tag, player, text) {
    $("bc-tag").textContent = tag;
    $("bc-name").textContent = player.name;
    $("bc-name").style.color = player.color;
    $("bc-text").textContent = text;
    var box = $("bc-lower");
    box.classList.remove("show");
    void box.offsetWidth; // restart the slide-in
    box.classList.add("show");
  }

  // The captions and their timings come from the server's shot plan.
  function runBroadcast(rec, plan) {
    var p = ctx.players[rec.idx], d = plan.drama, r = rec.result;
    renderBug(rec.scores.before, rec.idx);
    $("bc").classList.add("on");
    plan.captions.forEach(function (c) {
      if (c.kind === "lower") later(c.at_ms, function () { lowerThird(c.tag, p, c.text); });
      else if (c.kind === "data") {
        later(c.at_ms, function () {
          var box = $("bc-data");
          box.innerHTML = "";
          c.items.forEach(function (it) {
            var cell = el("div");
            cell.appendChild(el("small", "", it[0]));
            cell.appendChild(el("b", "", it[1]));
            box.appendChild(cell);
          });
          box.classList.add("show");
        });
      }
    });
    later(plan.restMs, function () {
      renderBug(rec.scores.after, rec.idx);
      sound(r.great ? "crowd" : d.headline === "SO CLOSE!" ? "ooh" : "blip");
      if (r.great) sound("great");
    });
    later(plan.totalMs - 250, clearBroadcast);
  }

  function showBanner(rec) {
    var b = $("result-banner");
    var p = ctx.players[rec.idx];
    b.innerHTML = "";
    b.appendChild(el("div", "who", p.name));
    b.appendChild(el("div", "what", rec.result.what));
    if (rec.result.detail) b.appendChild(el("div", "detail", rec.result.detail));
    b.classList.toggle("great", !!rec.result.great);
    b.style.borderColor = rec.result.color || "";
    b.querySelector(".what").style.color = rec.result.color || "";
    b.classList.add("show");
    sound(rec.result.great ? "great" : "blip");
    clearTimeout(bannerTimer);
    bannerTimer = setTimeout(hideBanner, BANNER_MS);
  }
  function hideBanner() { $("result-banner").classList.remove("show"); }

  function showWinner() {
    if (!ctx || !isOver() || !ctx.state.winner) return;
    var w = ctx.state.winner;
    renderBoard($("final-board"), w.board, w.numbered);
    $("winner-text").textContent = w.text;
    $("winner").classList.add("show");
    sound("win");
  }
  function hideOverlay() { $("winner").classList.remove("show"); }

  // The server picks a sensible club for whoever is up.
  function testShot() {
    api("/api/test-shot").catch(function () { setStatus(null); });
  }

  /* ---------------- drawing ---------------- */
  function fit() {
    var dpr = window.devicePixelRatio || 1;
    var w = canvas.clientWidth, h = canvas.clientHeight;
    if (canvas.width !== Math.round(w * dpr) || canvas.height !== Math.round(h * dpr)) {
      canvas.width = Math.round(w * dpr);
      canvas.height = Math.round(h * dpr);
    }
    g2.setTransform(dpr, 0, 0, dpr, 0, 0);
    return { w: w, h: h };
  }

  function niceCeil(v) {
    var step = v <= 100 ? 10 : v <= 250 ? 25 : 50;
    return Math.ceil(v / step) * step;
  }

  /* The WebGL range, or null to fall back to the 2D drawing. */
  function glRenderer() {
    if (settings.quality === "classic" || glFailed || !window.GarageRangeGL) return null;
    if (gl && glQuality === settings.quality) return gl;
    var canvas3d = $("field3d");
    if (gl) {
      // a canvas keeps its WebGL context, so swap in a fresh canvas for the new quality
      gl.renderer.dispose();
      var fresh = canvas3d.cloneNode(false);
      canvas3d.replaceWith(fresh);
      canvas3d = fresh;
    }
    try {
      gl = window.GarageRangeGL.create(canvas3d, { targets: catalog.targets, inner: catalog.inner, center: catalog.center,
        idleCamera: catalog.idle_camera, quality: settings.quality });
      glQuality = settings.quality;
    } catch (e) {
      console.warn("3D graphics unavailable, using 2D view:", e);
      glFailed = true;
      gl = null;
    }
    return gl;
  }

  // Earlier shots stay on the range as markers (not the one being shown).
  function recentShots(showing) {
    return ctx.history.filter(function (h) { return h.shot && (!showing || h.turn !== showing.rec.turn); })
      .slice(-2 * playerCount());
  }

  function drawRangeGL(r, highlight, showing, now) {
    var stage = $("field3d").parentElement;
    r.resize(stage.clientWidth, stage.clientHeight);
    var recent = isCornhole() ? [] : recentShots(showing);
    var plan = showing && showing.plan;
    if (plan && debugWall !== null) showing.start = now - debugWall * 1000;
    var extra = ctx.state.extra;
    r.render({
      cornhole: isCornhole() ? { board: extra.board, bags: cornholeBags(showing, now),
        idleCamera: extra.idle_camera } : null,
      now: now,
      plan: plan || null,
      wall: plan ? (now - showing.start) / 1000 : 0,
      shot: plan ? showing.rec.shot : null,
      shotId: plan ? showing.rec.shot.id : null,
      color: showing ? ctx.players[showing.rec.idx].color : "#ffffff",
      highlight: highlight,
      markers: recent.map(function (h) {
        return { p: h.result.stop || h.shot.flight.rest, color: ctx.players[h.idx].color };
      })
    });
  }

  function frame(now) {
    requestAnimationFrame(frame);
    if (!ctx || !$("game").classList.contains("active")) return;
    var showing = replay && now < replay.until ? replay : null;
    var target = showing ? showing.rec.target : ctx.state.current.target;
    var highlight = showing ? showing.rec.highlight : ctx.state.current.highlight;
    var r = ctx.info.view === "range3d" || isCornhole() ? glRenderer() : null;
    canvas.style.display = r ? "none" : "block";
    $("field3d").style.display = r ? "block" : "none";
    if (r && (!showing || showing.plan)) return drawRangeGL(r, highlight, showing, now);
    var size = fit();
    if (isCornhole()) drawCornhole2D(size, showing, now);
    else if (ctx.info.view === "speed") drawSpeed(size, target, showing, now);
    else if (ctx.info.view === "range3d") drawRange3D(size, highlight, showing, now);
    else drawRange(size, target, showing, now);
  }

  /* Golf Cornhole: every bag's [x, y, z, yaw, pitch, visible] and colour, from the shot
   * plan while a throw plays, otherwise from the state the server sent. */
  function cornholeBags(showing, now) {
    if (showing && showing.plan && showing.plan.cornhole) {
      return showing.plan.bags((now - showing.start) / 1000);
    }
    return ctx.state.extra.bags.map(function (b) { return { pose: b.pose, color: b.color }; });
  }

  // Classic 2D: the board from above.
  function drawCornhole2D(size, showing, now) {
    var W = size.w, H = size.h, g = g2, B = ctx.state.extra.board;
    g.fillStyle = "#1f5f34"; g.fillRect(0, 0, W, H);
    var span = B.length * 1.9, scale = Math.min(H / span, W / (B.width * 2.4));
    var mid = (B.front[0] + B.back[0]) / 2;
    var px = function (d, l) { return [W / 2 + l * scale, H / 2 - (d - mid) * scale]; };
    var a = px(B.back[0], -B.width / 2), b = px(B.front[0], B.width / 2);
    g.fillStyle = "#c8a165"; g.fillRect(a[0], a[1], b[0] - a[0], b[1] - a[1]);
    g.strokeStyle = "#6b4a22"; g.lineWidth = 4; g.strokeRect(a[0], a[1], b[0] - a[0], b[1] - a[1]);
    var h = px(B.hole[0], 0);
    g.fillStyle = "#111"; g.beginPath(); g.arc(h[0], h[1], B.hole_r * scale, 0, Math.PI * 2); g.fill();
    cornholeBags(showing, now).forEach(function (bag) {
      var p = bag.pose;
      if (!p[5]) return;
      var c = px(p[0], p[1]), s = B.bag * scale * (p[6] || 1);
      g.save(); g.translate(c[0], c[1]); g.rotate(p[3] * Math.PI / 180);
      g.fillStyle = bag.color; g.strokeStyle = "rgba(0,0,0,0.6)"; g.lineWidth = 2;
      g.fillRect(-s / 2, -s / 2, s, s); g.strokeRect(-s / 2, -s / 2, s, s);
      g.restore();
    });
    g.fillStyle = "rgba(255,255,255,0.7)"; g.font = "bold 16px Segoe UI, sans-serif"; g.textAlign = "left";
    g.fillText("Hole at " + B.distance + " yds", 12, 24);
  }

  function drawRange3D(size, highlight, showing, now) {
    var G = window.GarageGames;
    var recent = recentShots(showing);
    var shot = null, timing = null;
    if (showing) {
      var rec = showing.rec;
      shot = {
        flight: rec.shot.flight, color: ctx.players[rec.idx].color, stop: rec.result.stop,
        hitColor: rec.result.great ? rec.result.color || "#ffffff" : null, elapsed: now - showing.start
      };
      timing = G.rangeTiming(rec.shot, rec.result.stop);
    }
    window.GarageRange3D.render(g2, size.w, size.h, {
      targets: catalog.targets, inner: catalog.inner, center: catalog.center, now: now,
      highlight: highlight,
      markers: recent.map(function (r) {
        return { p: r.result.stop || r.shot.flight.rest, color: ctx.players[r.idx].color };
      }),
      shot: shot, timing: timing
    });
  }

  function sameTarget(a, b) { return JSON.stringify(a) === JSON.stringify(b); }

  function drawRange(size, target, showing, now) {
    var W = size.w, H = size.h, g = g2;
    var game = ctx.game;
    var others = ctx.history.filter(function (r) {
      return r.shot && sameTarget(r.target, target) && (!showing || r.turn !== showing.rec.turn);
    });
    var far = game.extent ? game.extent(target) * 1.25 : 0;
    others.concat(showing ? [showing.rec] : []).forEach(function (r) {
      if (r.shot) far = Math.max(far, r.shot.flight.carry_yd * 1.08);
    });
    if (game.id === "longdrive") far = Math.max(far, 150);
    var maxYd = niceCeil(Math.max(60, far));
    var top = 30, bottom = 60;
    var scale = (H - top - bottom) / maxYd;
    var view = {
      scale: scale, maxYd: maxYd,
      px: function (d, l) { return [W / 2 + l * scale, H - bottom - d * scale]; }
    };

    // grass stripes and yard lines
    g.fillStyle = "#1f5f34"; g.fillRect(0, 0, W, H);
    var stripe = maxYd <= 100 ? 5 : 10;
    for (var y = 0; y < maxYd + stripe; y += stripe * 2) {
      var a = view.px(y, 0), b = view.px(y + stripe, 0);
      g.fillStyle = "#246b3b"; g.fillRect(0, b[1], W, a[1] - b[1]);
    }
    var step = maxYd <= 100 ? 10 : maxYd <= 250 ? 25 : 50;
    g.font = "bold 16px Segoe UI, sans-serif"; g.textAlign = "left"; g.textBaseline = "middle";
    for (var d = step; d <= maxYd; d += step) {
      var p = view.px(d, 0);
      g.strokeStyle = "rgba(255,255,255,0.18)"; g.lineWidth = 1;
      g.beginPath(); g.moveTo(0, p[1]); g.lineTo(W, p[1]); g.stroke();
      g.fillStyle = "rgba(255,255,255,0.6)"; g.fillText(d + " yd", 10, p[1] - 10);
    }
    var c0 = view.px(0, 0), c1 = view.px(maxYd, 0);
    g.strokeStyle = "rgba(255,255,255,0.12)"; g.setLineDash([6, 8]);
    g.beginPath(); g.moveTo(c0[0], c0[1]); g.lineTo(c1[0], c1[1]); g.stroke(); g.setLineDash([]);

    if (game.draw) game.draw(g, view, target, ctx);

    // tee box
    g.fillStyle = "#e8e8e8"; g.fillRect(c0[0] - 20, c0[1] - 4, 40, 8);

    others.forEach(function (r) { drawLanding(view, r, false); });

    if (showing) {
      var rec = showing.rec, pts = rec.shot.flight.points;
      var t = Math.min(1, (now - showing.start) / showing.dur);
      var color = ctx.players[rec.idx].color;
      var n = Math.max(1, Math.floor(t * (pts.length - 1)));
      // ground track
      g.strokeStyle = color; g.lineWidth = 3; g.globalAlpha = 0.6;
      g.beginPath();
      for (var i = 0; i <= n; i++) {
        var q = view.px(pts[i][0], pts[i][1]);
        if (i === 0) g.moveTo(q[0], q[1]); else g.lineTo(q[0], q[1]);
      }
      g.stroke(); g.globalAlpha = 1;
      if (t < 1) {
        var cur = pts[n];
        var ground = view.px(cur[0], cur[1]);
        var lift = (cur[2] / 3) * scale * 0.5;
        g.fillStyle = "rgba(0,0,0,0.35)";
        g.beginPath(); g.ellipse(ground[0], ground[1], 7, 4, 0, 0, Math.PI * 2); g.fill();
        g.fillStyle = "#fff"; g.strokeStyle = color; g.lineWidth = 3;
        g.beginPath(); g.arc(ground[0], ground[1] - lift, 8 + Math.min(10, cur[2] / 12), 0, Math.PI * 2);
        g.fill(); g.stroke();
      } else {
        drawLanding(view, rec, true);
      }
    }
  }

  function drawLanding(view, rec, highlight) {
    var g = g2, f = rec.shot.flight;
    var p = view.px(f.carry_yd, f.offline_yd);
    var color = ctx.players[rec.idx].color;
    if (highlight && rec.result.mark) {
      var m = view.px(rec.result.mark[0], rec.result.mark[1]);
      g.strokeStyle = "#fff"; g.lineWidth = 2; g.setLineDash([6, 6]);
      g.beginPath(); g.moveTo(p[0], p[1]); g.lineTo(m[0], m[1]); g.stroke(); g.setLineDash([]);
    }
    var r = highlight ? 13 : 9;
    g.fillStyle = color; g.strokeStyle = highlight ? "#fff" : "rgba(0,0,0,0.6)"; g.lineWidth = highlight ? 4 : 2;
    g.beginPath(); g.arc(p[0], p[1], r, 0, Math.PI * 2); g.fill(); g.stroke();
    g.fillStyle = "#111"; g.font = "bold " + (highlight ? 14 : 11) + "px Segoe UI, sans-serif";
    g.textAlign = "center"; g.textBaseline = "middle";
    g.fillText(ctx.players[rec.idx].name.charAt(0).toUpperCase(), p[0], p[1] + 1);
  }

  function drawSpeed(size, target, showing, now) {
    var W = size.w, H = size.h, g = g2;
    g.fillStyle = "#13261c"; g.fillRect(0, 0, W, H);
    var speedNow = showing ? showing.rec.shot.speed_mph : null;
    var maxMph = niceCeil(Math.max(60, target.mph * 1.4, (speedNow || 0) * 1.1));
    var cx = W / 2, cy = H * 0.45, R = Math.min(W * 0.3, H * 0.33);
    var a0 = Math.PI * 0.85, a1 = Math.PI * 2.15;
    var ang = function (v) { return a0 + (a1 - a0) * Math.min(1, Math.max(0, v / maxMph)); };

    g.lineCap = "round";
    g.strokeStyle = "#2b4a37"; g.lineWidth = R * 0.12;
    g.beginPath(); g.arc(cx, cy, R, a0, a1); g.stroke();
    g.strokeStyle = "#3ddc84";
    g.beginPath(); g.arc(cx, cy, R, ang(target.mph - 3), ang(target.mph + 3)); g.stroke();
    g.lineCap = "butt";

    g.font = "bold " + Math.round(R * 0.07) + "px Segoe UI, sans-serif";
    g.textAlign = "center"; g.textBaseline = "middle"; g.fillStyle = "#9db8a6";
    var tick = maxMph <= 100 ? 10 : 20;
    for (var v = 0; v <= maxMph; v += tick) {
      var a = ang(v);
      g.fillText(String(v), cx + Math.cos(a) * R * 0.8, cy + Math.sin(a) * R * 0.8);
    }
    // target marker
    var ta = ang(target.mph);
    g.fillStyle = "#ffd23f";
    g.beginPath();
    g.arc(cx + Math.cos(ta) * R * 1.12, cy + Math.sin(ta) * R * 1.12, R * 0.04, 0, Math.PI * 2);
    g.fill();

    var shown = 0;
    if (showing) {
      var t = Math.min(1, (now - showing.start) / 900);
      shown = speedNow * (1 - Math.pow(1 - t, 3));
      var na = ang(shown);
      g.strokeStyle = "#ff6b6b"; g.lineWidth = R * 0.03; g.lineCap = "round";
      g.beginPath(); g.moveTo(cx, cy); g.lineTo(cx + Math.cos(na) * R * 0.95, cy + Math.sin(na) * R * 0.95); g.stroke();
      g.lineCap = "butt";
    }
    g.fillStyle = "#fff";
    g.beginPath(); g.arc(cx, cy, R * 0.05, 0, Math.PI * 2); g.fill();

    g.font = "900 " + Math.round(R * 0.28) + "px Segoe UI, sans-serif";
    g.fillStyle = "#fff";
    g.fillText(showing ? shown.toFixed(1) : "--", cx, cy + R * 0.32);
    g.font = "bold " + Math.round(R * 0.09) + "px Segoe UI, sans-serif";
    g.fillStyle = "#ffd23f";
    g.fillText("TARGET " + target.mph + " MPH", cx, cy + R * 0.62);
  }

  /* ---------------- sound ---------------- */
  var audio = null;
  function tone(freq, start, dur, type) {
    var o = audio.createOscillator(), v = audio.createGain();
    o.type = type || "sine"; o.frequency.value = freq;
    v.gain.setValueAtTime(0.0001, audio.currentTime + start);
    v.gain.exponentialRampToValueAtTime(0.25, audio.currentTime + start + 0.02);
    v.gain.exponentialRampToValueAtTime(0.0001, audio.currentTime + start + dur);
    o.connect(v); v.connect(audio.destination);
    o.start(audio.currentTime + start); o.stop(audio.currentTime + start + dur + 0.05);
  }
  // Filtered noise makes a passable crowd.
  function crowd(dur, freq, endFreq, level) {
    var len = Math.floor(audio.sampleRate * dur);
    var buf = audio.createBuffer(1, len, audio.sampleRate);
    var data = buf.getChannelData(0);
    for (var i = 0; i < len; i++) data[i] = Math.random() * 2 - 1;
    var src = audio.createBufferSource(), filt = audio.createBiquadFilter(), v = audio.createGain();
    src.buffer = buf;
    filt.type = "bandpass"; filt.Q.value = 0.8;
    filt.frequency.setValueAtTime(freq, audio.currentTime);
    filt.frequency.linearRampToValueAtTime(endFreq, audio.currentTime + dur);
    v.gain.setValueAtTime(0.0001, audio.currentTime);
    v.gain.exponentialRampToValueAtTime(level, audio.currentTime + dur * 0.2);
    v.gain.exponentialRampToValueAtTime(0.0001, audio.currentTime + dur);
    src.connect(filt); filt.connect(v); v.connect(audio.destination);
    src.start();
  }
  function sound(kind) {
    if (!soundOn) return;
    try {
      audio = audio || new (window.AudioContext || window.webkitAudioContext)();
      if (kind === "crowd") { crowd(2.6, 800, 1400, 0.5); crowd(2.2, 2200, 2600, 0.15); return; }
      if (kind === "ooh") { crowd(1.6, 700, 380, 0.45); return; }
      if (kind === "great") { tone(660, 0, 0.15); tone(880, 0.12, 0.15); tone(1320, 0.24, 0.35); }
      else if (kind === "win") { [523, 659, 784, 1047].forEach(function (f, i) { tone(f, i * 0.15, 0.4, "triangle"); }); }
      else tone(520, 0, 0.18, "triangle");
    } catch (e) { /* no audio */ }
  }

  /* ---------------- launch monitor status ---------------- */
  function setStatus(s) {
    var box = $("lm-status");
    var labelEl = box.querySelector(".label");
    box.className = "status";
    if (!s) { labelEl.textContent = "Game server offline - is server.py running?"; return; }
    if (s.connected) box.classList.add(s.ready ? "ready" : "connected");
    labelEl.textContent = s.connected
      ? (s.device || "Launch monitor") + (s.ready ? " - ready" : " - connected")
      : "Launch monitor: waiting for connection…";
  }

  function connectEvents() {
    var es = new EventSource("/events");
    es.addEventListener("status", function (e) { setStatus(JSON.parse(e.data)); });
    es.addEventListener("state", function (e) { onState(JSON.parse(e.data)); });
    es.addEventListener("shot", function (e) { onShot(JSON.parse(e.data)); });
    es.onerror = function () { setStatus(null); };
  }

  /* ---------------- navigation and keys ---------------- */
  function showScreen(id) {
    ["setup", "game"].forEach(function (s) { $(s).classList.toggle("active", s === id); });
    document.body.classList.toggle("playing", id === "game");
  }

  // Ends the game for every screen; the server's "end" state brings them all back here.
  function toMenu() {
    if (ctx && ctx.history.length && !isOver() && !confirm("Quit this game?")) return;
    api("/api/game/end").catch(function () { setStatus(null); });
  }

  $("btn-test").onclick = testShot;
  $("btn-undo").onclick = undo;
  $("btn-skip").onclick = skipTurn;
  $("btn-menu").onclick = toMenu;
  $("btn-menu2").onclick = toMenu;
  $("btn-again").onclick = function () { startGame(ctx && ctx.info); };
  $("btn-sound").onclick = function () {
    soundOn = !soundOn;
    this.textContent = soundOn ? "🔊" : "🔇";
  };

  document.addEventListener("keydown", function (e) {
    if (e.target.tagName === "INPUT") return;
    var k = e.key.toLowerCase();
    if (k === "t") testShot();
    else if (k === "u" && ctx) undo();
    else if (k === "s" && ctx) skipTurn();
    else if (k === "escape" && ctx) toMenu();
  });

  renderPlayers();
  renderOptions();
  // The game list comes from the server, then the live events start.
  fetch("/api/games").then(function (r) { return r.json(); }).then(function (data) {
    catalog = data;
    selectedGame = catalog.games[0];
    renderGameCards();
    renderRounds();
    renderGameOptions();
    connectEvents();
  }).catch(function () { setStatus(null); });
  // read-only peek for automated tests
  var debugWall = null;
  window.GarageDebug = {
    replay: function () { return replay; },
    glActive: function () { return !!gl; },
    freeze: function (sec) { debugWall = sec; if (replay) replay.until = Infinity; },
    unfreeze: function () { debugWall = null; if (replay) replay.until = replay.start + replay.dur; }
  };
  requestAnimationFrame(frame);
})();
