// Camera director tests. Run: node tests/test_director.js
const assert = require("assert");
const D = require("../web/director.js");
const { TARGETS } = require("../web/games.js");

let passed = 0;
function test(name, fn) { fn(); passed++; console.log("ok -", name); }

const players = [{ name: "Dad" }, { name: "Maddie" }];
function drama(over) {
  return D.assess(Object.assign({
    players, shooter: 1, before: [20, 10], after: [20, 10], shotsLeft: 5, totalShots: 10, finalBall: false,
    pressureGap: 10, ladder: null, gameOverAfter: false, hit: { target: -1 }, nearMissYd: null, chance: 0.9
  }, over));
}

// A believable 92 mph wedge that lands in Blue, sampled like flight.py output.
function flightShot(carry, offline, flightT, apexFt, rest) {
  const pts = [];
  for (let i = 0; i <= 40; i++) {
    const u = i / 40;
    pts.push([carry * u, offline * u, 4 * apexFt * u * (1 - u)]);
  }
  return { speed_mph: 92, hla_deg: 4, flight: { carry_yd: carry, offline_yd: offline, flight_time_s: flightT,
    points: pts, rest: rest || [carry + 4, offline] } };
}

test("routine shot early in the game stays quick", () => {
  const d = drama({});
  assert.strictEqual(d.broadcast, false);
});

test("close score near the end is a pressure shot (known before the result)", () => {
  const d = drama({ before: [20, 14], after: [20, 14], shotsLeft: 1, finalBall: true });
  assert.ok(d.broadcast && d.pressure);
  assert.strictEqual(d.preTag, "FINAL BALL");
  assert.match(d.preText, /6 behind Dad/);
  const far = drama({ before: [60, 10], after: [60, 10], shotsLeft: 1, finalBall: true });
  assert.ok(!far.pressure, "a blowout is not pressure");
});

test("lead change and winning shot", () => {
  const lc = drama({ before: [20, 15], after: [20, 27], shotsLeft: 3, hit: { target: 3, zone: "inner" } });
  assert.deepStrictEqual(lc.headline, "TAKES THE LEAD!");
  assert.ok(lc.slowmo);
  const win = drama({ before: [20, 15], after: [20, 27], gameOverAfter: true, hit: { target: 3, zone: "outer" } });
  assert.strictEqual(win.headline, "WINS IT!");
  assert.ok(win.celebrate);
});

test("near miss and flag zone broadcast; a plain roll-in does not", () => {
  assert.strictEqual(drama({ nearMissYd: 1 }).headline, "SO CLOSE!");
  assert.strictEqual(drama({ nearMissYd: 3 }).broadcast, false);
  assert.strictEqual(drama({ hit: { target: 2, zone: "center" } }).headline, "FLAG ZONE!");
  const rolled = drama({ hit: { target: 2, zone: "outer", rolledIn: true } });
  assert.strictEqual(rolled.broadcast, false);
  assert.strictEqual(rolled.headline, "ROLLED IN!");
});

test("lead changes only count as a real overtake late in the game", () => {
  assert.ok(!drama({ before: [0, 0], after: [0, 8], shotsLeft: 3 }).broadcast, "breaking a tie is not an overtake");
  assert.ok(!drama({ before: [12, 10], after: [12, 18], shotsLeft: 9 }).broadcast, "too early to matter");
  assert.ok(drama({ before: [12, 10], after: [12, 18], shotsLeft: 4 }).reasons.includes("lead-change"));
});

test("ladder pressure", () => {
  const ladder = { need: [5, 3] };
  const forWin = drama({ before: [1, 2], after: [1, 2], ladder });
  assert.strictEqual(forWin.preTag, "FOR THE WIN");
  const keepPace = drama({ shooter: 1, before: [4, 0], after: [4, 0], ladder });
  assert.strictEqual(keepPace.preTag, "MUST KEEP PACE");
});

test("solo play only broadcasts close calls (and the occasional random one)", () => {
  const solo = (o) => drama(Object.assign({ players: [{ name: "Dad" }], shooter: 0, before: [5], after: [5] }, o));
  assert.strictEqual(solo({ shotsLeft: 1 }).broadcast, false);
  assert.strictEqual(solo({ nearMissYd: 1 }).broadcast, true);
  assert.strictEqual(solo({ chance: 0.05 }).broadcast, true);
  assert.strictEqual(solo({ chance: 0.1 }).broadcast, false);
});

const blue = TARGETS[3];
const shot = flightShot(blue.d - 2, blue.l, 5, 80, [blue.d + 2, blue.l]);
const result = { stop: [blue.d - 2, blue.l] };
const hit = { target: 3 };

test("broadcast plan: tee, tower, target, orbit; slow motion stretches time", () => {
  const big = drama({ hit: { target: 3, zone: "center" } });
  const p = D.plan(shot, result, { style: "auto", drama: big, hit, targets: TARGETS });
  assert.strictEqual(p.mode, "broadcast");
  assert.deepStrictEqual(p.shots.map((s) => s.type), ["bay", "tower", "target", "orbit"]);
  const quick = D.plan(shot, result, { style: "quick", drama: big, hit, targets: TARGETS });
  assert.deepStrictEqual(quick.shots.map((s) => s.type), ["bay", "chase", "land"]);
  assert.ok(p.totalMs > quick.totalMs + 2000, "broadcast takes its time");
  assert.ok(p.landMs > 5000, "slow motion around landing");
  assert.ok(p.totalMs < 12500, "but a broadcast still moves along (" + p.totalMs + " ms)");
  for (let w = 0; w < p.totalMs / 1000; w += 0.05) assert.ok(p.simAt(w + 0.05) > p.simAt(w));
  for (let i = 1; i < p.shots.length; i++) assert.strictEqual(p.shots[i].t0, p.shots[i - 1].t1);
});

test("ball path is continuous and finishes in the cup", () => {
  const p = D.plan(shot, result, { style: "broadcast", drama: drama({}), hit, targets: TARGETS });
  let prev = p.ball(0).pos;
  for (let w = 0.01; w <= p.totalMs / 1000; w += 0.01) {
    const b = p.ball(w);
    const jump = Math.hypot(b.pos[0] - prev[0], b.pos[1] - prev[1], b.pos[2] - prev[2]);
    assert.ok(jump < 2, "no teleporting at " + w.toFixed(2) + "s (" + jump.toFixed(2) + " yd)");
    prev = b.pos;
  }
  const end = p.ball(p.totalMs / 1000);
  assert.strictEqual(end.phase, "cup");
  assert.strictEqual(end.visible, false);
  assert.ok(Math.abs(end.pos[0] - blue.d) < 0.01 && Math.abs(end.pos[1] - blue.l) < 0.01);
});

test("a miss rolls out and stays visible; static style never moves the camera", () => {
  const miss = flightShot(100, -30, 4.5, 70, [108, -31]);
  const p = D.plan(miss, { stop: [108, -31] }, { style: "static", drama: drama({}), hit: { target: -1 }, targets: TARGETS });
  assert.deepStrictEqual(p.shots.map((s) => s.type), ["range"]);
  const end = p.ball(p.totalMs / 1000);
  assert.strictEqual(end.phase, "rest");
  assert.ok(end.visible);
  assert.ok(Math.abs(end.pos[0] - 108) < 0.01);
});

test("every camera returns a finite position, target and lens", () => {
  const p = D.plan(shot, result, { style: "broadcast", drama: drama({ hit: { target: 3, zone: "center" } }), hit, targets: TARGETS });
  for (let w = 0; w < p.totalMs / 1000; w += 0.1) {
    const cam = p.camera(p.shotIndexAt(w), w, p.ball(w).pos);
    [...cam.pos, ...cam.look, cam.fov].forEach((v) => assert.ok(Number.isFinite(v)));
  }
});

console.log(passed + " tests passed");
