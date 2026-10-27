// Runs the JavaScript rules and director on cases from tests/test_parity.py
// (JSON on stdin) and prints the results as JSON, so Python can check that
// games.py / director.py give the same answers as web/games.js / director.js.
const G = require("../web/games.js");
const D = require("../web/director.js");

const game = (id) => G.GAMES.find((g) => g.id === id);

let input = "";
process.stdin.on("data", (d) => { input += d; });
process.stdin.on("end", () => {
  const cases = JSON.parse(input);
  const out = cases.map((c) => {
    if (c.kind === "score") {
      const ctx = Object.assign({ players: [c.player], history: [], turn: 0 }, c.ctx || {});
      return game(c.game).score(c.shot, c.target, c.player, ctx, 0);
    }
    if (c.kind === "range") {
      return { hit: G.rangeHit(c.shot), near: G.nearMiss(c.shot), timing: G.rangeTiming(c.shot) };
    }
    if (c.kind === "called") return game("calledshot").playerTarget(c.base, c.player);
    if (c.kind === "assess") return D.assess(c.input);
    if (c.kind === "plan") {
      const p = D.plan(c.shot, c.result, { style: c.style, drama: c.drama, hit: c.hit, targets: G.TARGETS });
      const samples = c.walls.map((w) => {
        const b = p.ball(w);
        const i = p.shotIndexAt(w);
        const cam = p.camera(i, w, b.pos);
        return { pos: b.pos, phase: b.phase, visible: b.visible, tracer: p.tracerProgress(w), index: i,
          cam: { pos: cam.pos, look: cam.look, fov: cam.fov, follow: cam.follow || 0, lookFollow: cam.lookFollow || 0 } };
      });
      return { mode: p.mode, totalMs: p.totalMs, restMs: p.restMs, landMs: p.landMs, inCup: p.inCup,
        shots: p.shots, samples: samples };
    }
    throw new Error("unknown case " + c.kind);
  });
  process.stdout.write(JSON.stringify(out));
});
