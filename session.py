"""The running game: players, turns, scoring history, undo and skip.

The server owns one GameSession. Every screen (the browser scoreboard and
the Unreal renderer) gets the same state snapshots and shot plans from it.
"""

import random

import director
import games


class GameSession:
    def __init__(self, rng=None):
        self.rng = rng or random.Random()
        self.games = games.make_games(self.rng)
        self.camera = "auto"
        self.game = None
        self.players = []
        self.rounds = 0
        self.history = []
        self.targets = {}
        self.turn = 0
        # Tic-Tac-Toe state (set by its reset())
        self.board = None
        self.ttt_winner = None
        self.boards = 1
        self.options = {}         # game options (Golf Cornhole's hole distance)
        self.replaying = False    # True while undo replays the shots

    # ---------------- setup ----------------

    def start(self, game_id, players, rounds=None, camera=None, options=None):
        game = games.game_by_id(game_id, self.games)
        if game is None:
            raise ValueError("unknown game: %s" % game_id)
        clean = []
        for p in players or []:
            name = str(p.get("name", "")).strip()
            if name:
                clean.append({"name": name, "junior": bool(p.get("junior")), "color": p.get("color") or "#ffffff"})
        if len(clean) < game.min_players:
            raise ValueError("%s needs at least %d player%s." % (
                game.name, game.min_players, "s" if game.min_players > 1 else ""))
        options = game.check_options(options)
        if camera:
            self.set_camera(camera)
        self.game = game
        self.options = options
        self.players = clean
        self.rounds = int(rounds or game.default_rounds or 5)
        if self.rounds < 1:
            raise ValueError("rounds must be at least 1")
        self.history = []
        self.targets = {}
        self.turn = 0
        self.board, self.ttt_winner, self.boards = None, None, 1
        game.reset(self)

    def end(self):
        self.game = None
        self.players = []
        self.history = []

    def set_camera(self, camera):
        if camera not in ("auto", "broadcast", "quick", "static"):
            raise ValueError("unknown camera style: %s" % camera)
        self.camera = camera

    @property
    def active(self):
        return self.game is not None

    # ---------------- turns ----------------

    def player_idx_for_turn(self, turn):
        return self.game.player_for_turn(self, turn)

    def round_of(self, turn):
        return 0 if not self.game.uses_rounds else turn // len(self.players)

    def target_for(self, idx, turn):
        r = self.round_of(turn)
        if r not in self.targets:
            self.targets[r] = self.game.make_target(r)
        return self.game.player_target(self.targets[r], self.players[idx])

    def is_over(self):
        return self.game.is_over(self)

    def current(self):
        idx = self.player_idx_for_turn(self.turn)
        return idx, self.target_for(idx, self.turn)

    def test_kind(self):
        if not self.active or self.is_over():
            return None
        idx, t = self.current()
        return self.game.test_kind(t, self, idx)

    def test_shot(self):
        """Launch numbers the game wants for a test shot ({}: the server picks)."""
        if not self.active or self.is_over():
            return {}
        idx, t = self.current()
        return self.game.test_shot(t, self, idx)

    # ---------------- shots ----------------

    def totals(self, history=None):
        if history is None:
            given = self.game.player_totals(self)
            if given is not None:
                return given
        t = [0] * len(self.players)
        for r in self.history if history is None else history:
            t[r["idx"]] += r["result"]["points"]
        return t

    def apply_shot(self, shot):
        """Score a shot for whoever is up. Returns the event every screen gets."""
        if not self.active or self.is_over():
            return {"free": True, "shot": shot}
        before = self.totals()
        idx = self.player_idx_for_turn(self.turn)
        target = self.target_for(idx, self.turn)
        player = self.players[idx]
        # the target to light up while the ball flies (before the result changes it)
        highlight = self.game.highlight(target, self, idx)
        result = self.game.score(shot, target, player, self, idx)
        rec = {"turn": self.turn, "idx": idx, "shot": shot, "target": target, "result": result}
        self.history.append(rec)
        self.turn += 1
        event = {"free": False, "shot": shot, "turn": rec["turn"], "idx": idx, "target": target,
                 "highlight": highlight, "result": result,
                 "scores": {"before": before, "after": self.totals()}}
        if self.game.view == "range3d":
            hit = games.range_hit(shot)
            drama = director.assess(self._drama_input(rec, hit, shot, before))
            p = director.plan(shot, result, {"style": self.camera, "drama": drama, "hit": hit,
                                             "targets": games.TARGETS})
            event["plan"] = director.to_message(p, shot, result, player)
        elif self.game.view == "cornhole":
            event["plan"] = self.game.plan(self, shot, result, player, self.camera)
        else:
            event["anim_ms"] = self._anim_ms(shot, result)
        event["state"] = self.snapshot()
        return event

    def _anim_ms(self, shot, result):
        return min(2200, max(900, shot["flight"]["flight_time_s"] * 450))

    def _drama_input(self, rec, hit, shot, before):
        round_ = self.round_of(rec["turn"])
        return {
            "players": self.players,
            "shooter": rec["idx"],
            "before": before,
            "after": self.totals(),
            "shotsLeft": self.rounds - round_,
            "totalShots": self.rounds,
            "finalBall": self.game.id == "targetrange" and round_ == self.rounds - 1,
            "pressureGap": self.game.pressure_gap,
            "ladder": {"need": [games.ladder_length(p) for p in self.players]} if self.game.id == "ladder" else None,
            "gameOverAfter": self.is_over(),
            "hit": hit,
            "nearMissYd": games.near_miss(shot),
            "chance": director.broadcast_chance(shot.get("id")),
        }

    def skip(self):
        if not self.active or self.is_over():
            return False
        idx = self.player_idx_for_turn(self.turn)
        self.history.append({"turn": self.turn, "idx": idx, "shot": None, "target": self.target_for(idx, self.turn),
                             "result": {"points": self.game.miss_points, "what": "Skipped", "detail": "",
                                        "great": False}})
        self.game.on_skip(self)
        self.turn += 1
        return True

    def undo(self):
        if not self.active or not self.history:
            return False
        self.history.pop()
        # Rebuild any game state (e.g. the tic-tac-toe board) by replaying shots.
        if self.game.stateful:
            self.game.reset(self)
            self.replaying = True
            try:
                for rec in self.history:
                    if rec["shot"]:
                        self.game.score(rec["shot"], rec["target"], self.players[rec["idx"]], self, rec["idx"])
                    else:
                        self.game.on_skip(self)
            finally:
                self.replaying = False
        self.turn = len(self.history)
        return True

    # ---------------- scoreboard ----------------

    def standings(self):
        g = self.game
        rows = []
        for i, p in enumerate(self.players):
            vals = [r["result"]["points"] for r in self.history if r["idx"] == i]
            total = (max(vals) if vals else 0) if g.combine == "max" else sum(vals)
            rows.append({"idx": i, "name": p["name"], "color": p["color"], "junior": p["junior"],
                         "total": total, "shots": len(vals)})
        sign = 1 if g.lower_is_better else -1
        return sorted(rows, key=lambda s: (0 if s["shots"] else 1, sign * s["total"]))

    def scoreboard_rows(self, current):
        if self.game.scoreboard:
            return self.game.scoreboard(self, current)
        return [{"name": s["name"] + (" (Jr)" if s["junior"] else ""), "color": s["color"],
                 "value": self.game.format_score(s["total"]) if s["shots"] else "—",
                 "sub": "%d shot%s" % (s["shots"], "" if s["shots"] == 1 else "s"),
                 "current": s["idx"] == current} for s in self.standings()]

    def winner(self):
        if self.game.winner_text:
            return {"text": self.game.winner_text(self), "board": self.game.scoreboard(self, -1),
                    "numbered": False}
        s = self.standings()
        best = [x for x in s if x["total"] == s[0]["total"]]
        text = " & ".join(x["name"] for x in best) + " tie!" if len(best) > 1 else s[0]["name"] + " wins!"
        return {"text": text, "numbered": True,
                "board": [{"name": x["name"], "color": x["color"], "value": self.game.format_score(x["total"])}
                          for x in s]}

    def snapshot(self):
        """Everything a scoreboard screen needs (no flight paths, so it stays small)."""
        if not self.active:
            return {"active": False, "camera": self.camera}
        g = self.game
        idx, t = self.current()
        p = self.players[idx]
        over = self.is_over()
        if g.round_info(self):
            round_info = g.round_info(self)
        elif not g.uses_rounds:
            round_info = "BOARD %d" % (self.boards or 1)
        else:
            round_info = "ROUND %d OF %d" % (min(self.rounds, self.round_of(self.turn) + 1), self.rounds)
        history = []
        for r in self.history:
            shot = None
            if r["shot"]:
                f = r["shot"]["flight"]
                shot = {"id": r["shot"].get("id"), "speed_mph": r["shot"]["speed_mph"],
                        "flight": {k: f.get(k) for k in ("carry_yd", "offline_yd", "total_yd", "rest")}}
            history.append({"turn": r["turn"], "idx": r["idx"], "target": r["target"], "result": r["result"],
                            "shot": shot})
        return {
            "active": True,
            "camera": self.camera,
            "game": g.id,
            "rounds": self.rounds,
            "turn": self.turn,
            "players": self.players,
            "current": {"idx": idx, "name": p["name"], "color": p["color"], "target": t,
                        "task": g.task(t, p, self, idx), "highlight": g.highlight(t, self, idx)},
            "round_info": round_info,
            "scoreboard": self.scoreboard_rows(idx),
            "numbered": not g.scoreboard,
            "totals": self.totals(),
            "history": history,
            "board": self.board,
            "boards": self.boards,
            "options": self.options,
            "extra": g.extra(self),
            "headline": g.headline(self),
            "over": over,
            "winner": self.winner() if over else None,
        }
