/* Plays back a shot plan message from the server (see director.py,
 * to_message). The server has already worked out the ball path, the camera
 * cuts and the camera smoothing; this only interpolates between frames.
 *
 * Positions are [downrange, right, height] in yards; wall time in seconds.
 */
(function (root) {
  "use strict";

  function lerp(a, b, t) { return a + (b - a) * t; }

  function player(msg) {
    var fps = msg.fps, ball = msg.ball, cams = msg.camera, n = ball.length;
    var restS = msg.rest_ms / 1000;

    function at(wall) {
      var f = Math.max(0, wall * fps);
      var i = Math.min(n - 1, Math.floor(f));
      return { i: i, j: Math.min(n - 1, i + 1), t: Math.min(1, f - i) };
    }

    return {
      mode: msg.mode,
      drama: msg.drama,
      totalMs: msg.total_ms,
      restMs: msg.rest_ms,
      landMs: msg.land_ms,
      inCup: msg.in_cup,
      captions: msg.captions,
      ball: function (wall) {
        var k = at(wall), a = ball[k.i], b = ball[k.j];
        var inCup = msg.in_cup && wall >= restS;
        return {
          pos: [lerp(a[0], b[0], k.t), lerp(a[1], b[1], k.t), lerp(a[2], b[2], k.t)],
          phase: inCup ? "cup" : wall >= restS ? "rest" : "moving",
          visible: !inCup
        };
      },
      tracerProgress: function (wall) {
        var k = at(wall);
        return lerp(ball[k.i][3], ball[k.j][3], k.t);
      },
      // {pos, look, fov, cut}: a new cut means jump, don't blend
      camera: function (wall) {
        var k = at(wall), a = cams[k.i], b = cams[k.j];
        if (a[7] !== b[7]) b = a;
        return {
          pos: [lerp(a[0], b[0], k.t), lerp(a[1], b[1], k.t), lerp(a[2], b[2], k.t)],
          look: [lerp(a[3], b[3], k.t), lerp(a[4], b[4], k.t), lerp(a[5], b[5], k.t)],
          fov: lerp(a[6], b[6], k.t),
          cut: a[7]
        };
      }
    };
  }

  var api = { player: player };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.GarageShotPlan = api;
})(this);
