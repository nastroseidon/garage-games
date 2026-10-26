// Game scoring tests. Run: node tests/test_games.js
const assert = require("assert");
const { GAMES } = require("../web/games.js");
const game = (id) => GAMES.find((g) => g.id === id);

function shot(carry, offline, speed = 80) {
  return { speed_mph: speed, flight: { carry_yd: carry, offline_yd: offline } };
}

let passed = 0;
function test(name, fn) {
  fn();
  passed++;
  console.log("ok -", name);
}

test("closest to the pin measures distance and caps big misses", () => {
  const g = game("closest");
  assert.strictEqual(g.score(shot(100, 0), { pin: 100 }).points, 0);
  assert.strictEqual(g.score(shot(103, 4), { pin: 100 }).points, 5);
  assert.strictEqual(g.score(shot(10, 0), { pin: 100 }).points, 50);
  assert.strictEqual(g.score(shot(98, 0), { pin: 100 }).what, "6 ft");
});

test("junior targets are half distance", () => {
  assert.deepStrictEqual(game("closest").playerTarget({ pin: 100 }, { junior: true }), { pin: 50 });
  assert.deepStrictEqual(game("closest").playerTarget({ pin: 100 }, { junior: false }), { pin: 100 });
  assert.deepStrictEqual(game("speed").playerTarget({ mph: 80 }, { junior: true }), { mph: 40 });
});

test("darts rings", () => {
  const g = game("darts");
  assert.strictEqual(g.score(shot(100, 2), { d: 100 }).points, 50);
  assert.strictEqual(g.score(shot(106, 0), { d: 100 }).points, 30);
  assert.strictEqual(g.score(shot(100, 24), { d: 100 }).points, 5);
  assert.strictEqual(g.score(shot(140, 0), { d: 100 }).points, 0);
});

test("hit the number", () => {
  const g = game("speed");
  assert.strictEqual(g.score(shot(0, 0, 60.5), { mph: 60 }).what, "BULLSEYE!");
  assert.strictEqual(g.score(shot(0, 0, 50), { mph: 60 }).points, 10);
  assert.strictEqual(g.score(shot(0, 0, 150), { mph: 60 }).points, 30);
});

test("long drive needs the fairway; juniors count double", () => {
  const g = game("longdrive");
  assert.strictEqual(g.score(shot(200, 10), { junior: false }).points, 200);
  assert.strictEqual(g.score(shot(200, 20), { junior: false }).points, 0);
  assert.strictEqual(g.score(shot(90, -5), { junior: true }).points, 180);
});

test("tic-tac-toe: teams alternate even with 3 players", () => {
  const g = game("tictactoe");
  const ctx = { players: [{}, {}, {}] };
  g.reset(ctx);
  const order = [0, 1, 2, 3, 4, 5].map((t) => g.playerForTurn(ctx, t));
  assert.deepStrictEqual(order, [0, 1, 2, 1, 0, 1]);
});

test("tic-tac-toe: claim, block, and win", () => {
  const g = game("tictactoe");
  const ctx = { players: [{}, {}] };
  g.reset(ctx);
  const t = g.makeTarget();
  // near row is 40-70 yds; columns -24..-8, -8..8, 8..24
  assert.strictEqual(g.score(shot(55, -15), t, {}, ctx, 0).points, 1);
  assert.strictEqual(g.score(shot(55, -15), t, {}, ctx, 1).what, "Already taken!");
  assert.strictEqual(g.score(shot(200, 0), t, {}, ctx, 1).what, "Off the board");
  g.score(shot(55, 0), t, {}, ctx, 0);
  assert.ok(!g.isOver(ctx));
  const res = g.score(shot(55, 15), t, {}, ctx, 0);
  assert.strictEqual(res.what, "THREE IN A ROW!");
  assert.ok(g.isOver(ctx));
  assert.strictEqual(g.winnerText(ctx), "Team X wins!");
});

test("tic-tac-toe: full board without a winner resets", () => {
  const g = game("tictactoe");
  const ctx = { players: [{}, {}] };
  g.reset(ctx);
  ctx.board = [0, 1, 0, 0, 1, 1, 1, 0, null];
  const t = g.makeTarget();
  // cell 8 = near row, right column; X there makes no line
  const res = g.score(shot(55, 15), t, {}, ctx, 0);
  assert.match(res.detail, /new board/);
  assert.ok(ctx.board.every((c) => c === null));
  assert.strictEqual(ctx.boards, 2);
});

test("every game has the required pieces", () => {
  for (const g of GAMES) {
    for (const k of ["id", "name", "emoji", "blurb", "view", "makeTarget", "playerTarget", "task", "score", "formatScore"]) {
      assert.ok(g[k] !== undefined, g.id + " missing " + k);
    }
  }
});

const { rangeHit, TARGETS } = require("../web/games.js");
function rshot(land, rest) {
  return { speed_mph: 90, flight: { carry_yd: land[0], offline_yd: land[1], rest: rest || land,
    total_yd: (rest || land)[0], flight_time_s: 4, points: [[0, 0, 0], [land[0], land[1], 0]] } };
}
const blue = TARGETS.find((t) => t.name === "Blue");
const red = TARGETS.find((t) => t.name === "Red");

test("range: landing zones and multipliers", () => {
  const g = game("targetrange");
  const ctx = { rounds: 10 };
  const adult = { round: 0, junior: false };
  assert.strictEqual(g.score(rshot([blue.d, blue.l]), adult, {}, ctx).points, 12); // flag zone x3
  assert.strictEqual(g.score(rshot([blue.d + 3, blue.l]), adult, {}, ctx).points, 8); // inner x2
  assert.strictEqual(g.score(rshot([blue.d + 9, blue.l]), adult, {}, ctx).points, 4); // outer
  assert.strictEqual(g.score(rshot([blue.d + 30, blue.l]), adult, {}, ctx).points, 0);
  assert.strictEqual(g.score(rshot([blue.d + 9, blue.l]), { round: 9, junior: false }, {}, ctx).points, 8); // final ball
  assert.strictEqual(g.score(rshot([red.d + 4, red.l]), { round: 0, junior: true }, {}, ctx).points, 3); // junior +2
});

test("range: a ball that lands short can roll in, and stops in the target", () => {
  const short = rshot([blue.d - 20, blue.l], [blue.d + 30, blue.l]);
  const hit = rangeHit(short);
  assert.strictEqual(hit.target, TARGETS.indexOf(blue));
  assert.ok(hit.rolledIn);
  assert.strictEqual(hit.zone, "outer");
  assert.ok(Math.abs(hit.stop[0] - (blue.d - blue.r)) < 0.6);
  const stays = rangeHit(rshot([blue.d, blue.l + 9], [blue.d + 25, blue.l + 9]));
  assert.ok(!stays.rolledIn);
  assert.deepStrictEqual(stays.stop, [blue.d, blue.l + 9]);
});

test("called shot only pays on the called target", () => {
  const g = game("calledshot");
  const t = { called: TARGETS.indexOf(blue), junior: false };
  assert.strictEqual(g.score(rshot([blue.d + 9, blue.l]), t).points, 8);
  assert.strictEqual(g.score(rshot([red.d, red.l]), t).what, "Wrong target!");
  const jr = g.playerTarget({ seed: 12345 }, { name: "Kid", junior: true });
  assert.ok(jr.called < 3, "juniors are only called to the three nearest targets");
});

test("ladder climbs in order and ends at the top", () => {
  const g = game("ladder");
  const players = [{ name: "Kid", junior: true }, { name: "Dad", junior: false }];
  const ctx = { players, rounds: 10, history: [], turn: 0 };
  const play = (idx, T) => {
    const result = g.score(rshot([T.d, T.l]), {}, players[idx], ctx, idx);
    ctx.history.push({ idx, result });
    ctx.turn++;
    return result;
  };
  assert.strictEqual(play(0, TARGETS[1]).what, "Wrong rung!");
  assert.strictEqual(play(0, TARGETS[0]).points, 1);
  assert.strictEqual(play(0, TARGETS[1]).points, 1);
  assert.ok(!g.isOver(ctx));
  assert.strictEqual(play(0, TARGETS[2]).what, "TOP OF THE LADDER!");
  assert.ok(g.isOver(ctx));
});

console.log(passed + " tests passed");
