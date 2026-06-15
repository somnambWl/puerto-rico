"""Evaluation harness: seat-rotated Arena + Elo + standard benchmarks (design/05).

This module turns "how strong is an agent?" into reproducible numbers. It plays
many full Puerto Rico games among a fixed line-up of agents, **rotating the seat
assignment each game** so seat-order asymmetry (governor advantage, deal order)
averages out, and reports per-agent win rate, mean placement, and mean VP plus a
reproducible Elo table.

A uniform notion of a "player"
------------------------------
The baseline agents have *different* call interfaces (see design/05):

* ``RandomAgent.act(obs_dict) -> int``  — observation/mask based;
* ``HeuristicAgent.act(game)`` / ``act_id(game) -> int`` — live-``Game`` based;
* ``RLPolicy.act(game)`` / ``act_id(game) -> int`` — live-``Game`` based.

The arena driver needs a single shape, so everything is normalized to a
``PlayerFn = callable(game) -> int`` returning a *legal* discrete action id (the
same contract as :data:`puerto_rico.training.rollout.OpponentFn`). Every baseline
now exposes the canonical ``act_id(game) -> int`` interface, so :func:`make_player`
simply uses ``act_id`` when present, else treats an already-bare ``callable(game)``
as-is.

Seat-rotation scheme
--------------------
Given ``num_players`` agents (indexed ``0..N-1`` in the line-up) and game ``g``,
agent ``a`` is seated at ``seat = (a + g) % N``. Equivalently the line-up is
rotated by ``g`` each game. Over a multiple of ``N`` games every agent occupies
every seat an equal number of times, so the *only* thing distinguishing agents in
the aggregate is their decisions, not their seat. The engine seed is ``base_seed
+ g`` (distinct deal per game), independent of the rotation, so results are fully
deterministic given ``(base_seed, num_games, line-up)``.

Elo method
----------
Elo here is a multiplayer generalization of the standard pairwise update, applied
to the recorded per-game placements (design/05 "Elo"). For each game we convert
the N-way finish into all ``C(N,2)`` ordered pairs: the better-placed agent
scores ``1`` against the worse-placed one, ``0.5`` on a tie. Each such pairwise
outcome drives a standard Elo update

    expected = 1 / (1 + 10 ** ((R_opp - R_self) / 400))
    R_self  += k * (score - expected)

All ratings start at ``1500``. To make the result **order-independent and
reproducible**, updates within one pass are computed against the ratings at the
start of that pass and applied simultaneously (synchronous update), and we run a
fixed number of ``iters`` passes over the full game record. Given the same
records, ``k`` and ``iters`` the table is bit-for-bit reproducible.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import combinations
from typing import Callable

from ..engine import scoring
from ..engine.game import Game
from ..engine.state import GameConfig
from ..env import action_codec

# A player drives the current seat: receives the live Game, returns a legal id.
PlayerFn = Callable[[Game], int]


# --------------------------------------------------------------------------- #
# agent -> uniform player adapter                                             #
# --------------------------------------------------------------------------- #


def make_player(agent) -> PlayerFn:
    """Normalize any supported agent to a ``callable(game) -> int`` (legal id).

    Dispatch (duck-typed, in priority order):

    1. exposes ``act_id(game)`` (every baseline: RandomAgent, HeuristicAgent,
       RLPolicy) — call it directly;
    2. already a bare ``callable(game) -> int`` (e.g. a ``PlayerFn`` returned by a
       previous ``make_player``) — used as-is.

    All three baselines implement ``act_id`` now, so the legacy class-name check is
    gone and there is a single canonical mechanism.
    """
    if hasattr(agent, "act_id") and callable(agent.act_id):
        return lambda game: int(agent.act_id(game))

    if callable(agent):
        return lambda game: int(agent(game))

    raise TypeError(
        f"cannot adapt {type(agent).__name__!r} to a player; expected an object "
        "with act_id(game) or a callable(game)->int"
    )


# --------------------------------------------------------------------------- #
# results                                                                     #
# --------------------------------------------------------------------------- #


@dataclass
class AgentResult:
    """Aggregated metrics for one agent across an :class:`Arena` run."""

    name: str
    games: int = 0
    wins: int = 0
    placement_sum: int = 0  # sum of 1..N placements
    vp_sum: int = 0

    @property
    def win_rate(self) -> float:
        return self.wins / self.games if self.games else 0.0

    @property
    def mean_placement(self) -> float:
        return self.placement_sum / self.games if self.games else 0.0

    @property
    def mean_vp(self) -> float:
        return self.vp_sum / self.games if self.games else 0.0


@dataclass
class Result:
    """Structured outcome of an :class:`Arena.run`.

    ``agents`` maps agent name -> :class:`AgentResult`. ``records`` is the raw
    per-game placement record used for Elo: each entry is ``{name: placement}``
    with placement in ``1..N`` (1 = winner). ``mask_violations`` counts any
    occasion an agent returned an id outside the legal mask (should be 0).
    """

    agents: dict[str, AgentResult]
    records: list[dict[str, int]] = field(default_factory=list)
    num_players: int = 4
    num_games: int = 0
    mask_violations: int = 0

    def to_table(self) -> str:
        """Render a human-readable metrics + Elo table."""
        elo = compute_elo(self.records)
        header = f"{'agent':<16}{'games':>7}{'win%':>8}{'mean_pl':>9}{'mean_vp':>9}{'elo':>8}"
        lines = [header, "-" * len(header)]
        # Sort by Elo desc for a leaderboard feel.
        for name in sorted(self.agents, key=lambda n: elo.get(n, 0.0), reverse=True):
            a = self.agents[name]
            lines.append(
                f"{name:<16}{a.games:>7}{a.win_rate * 100:>7.1f}%"
                f"{a.mean_placement:>9.2f}{a.mean_vp:>9.1f}{elo[name]:>8.0f}"
            )
        if self.mask_violations:
            lines.append(f"\n!! mask_violations = {self.mask_violations} (SUSPECT: engine/agent bug)")
        return "\n".join(lines)

    def __str__(self) -> str:  # pragma: no cover - thin delegation
        return self.to_table()

    def elo(self, **kwargs) -> dict[str, float]:
        """Elo table from this result's records (see :func:`compute_elo`)."""
        return compute_elo(self.records, **kwargs)


# --------------------------------------------------------------------------- #
# arena                                                                        #
# --------------------------------------------------------------------------- #


class Arena:
    """Play many seat-rotated games among a fixed agent line-up.

    Parameters
    ----------
    players:
        List of ``(name, agent)``; length must equal ``num_players``. Each agent
        is normalized via :func:`make_player`. Names must be unique.
    num_players:
        Table size (default 4).
    seed:
        Base engine seed; game ``g`` uses ``seed + g`` (distinct deal per game).
    """

    def __init__(self, players, *, num_players: int = 4, seed: int = 0) -> None:
        if len(players) != num_players:
            raise ValueError(
                f"line-up has {len(players)} agents but num_players={num_players}"
            )
        names = [name for name, _ in players]
        if len(set(names)) != len(names):
            raise ValueError(f"agent names must be unique, got {names}")
        self.names = names
        self.fns: list[PlayerFn] = [make_player(agent) for _, agent in players]
        self.num_players = num_players
        self.seed = seed

    def run(self, num_games: int = 500) -> Result:
        """Play ``num_games`` full games with rotating seats; aggregate metrics."""
        n = self.num_players
        results = {name: AgentResult(name) for name in self.names}
        records: list[dict[str, int]] = []
        mask_violations = 0

        for g in range(num_games):
            # Seat -> line-up index for this game: agent ``a`` sits at (a+g) % n,
            # equivalently seat ``s`` is driven by line-up index (s - g) % n.
            seat_to_agent = [(s - g) % n for s in range(n)]
            game = Game(GameConfig(num_players=n, seed=self.seed + g))

            while not game.is_terminal:
                seat = game.current_player
                agent_idx = seat_to_agent[seat]
                action_id = int(self.fns[agent_idx](game))
                if not _is_legal(game, action_id):
                    mask_violations += 1
                action = action_codec.from_int(action_id, game.state)
                game.apply(action, validate=False)

            # Game over: placement (1..n) and VP per seat.
            order = scoring.rankings(game.state)  # seat indices, best -> worst
            scores = scoring.final_scores(game.state)
            placement_by_seat = [0] * n
            for place, seat_idx in enumerate(order):
                placement_by_seat[seat_idx] = place + 1  # 1 = winner

            record: dict[str, int] = {}
            for seat in range(n):
                agent_idx = seat_to_agent[seat]
                name = self.names[agent_idx]
                placement = placement_by_seat[seat]
                ar = results[name]
                ar.games += 1
                ar.placement_sum += placement
                ar.vp_sum += scores[seat]
                if placement == 1:
                    ar.wins += 1
                record[name] = placement
            records.append(record)

        return Result(
            agents=results,
            records=records,
            num_players=n,
            num_games=num_games,
            mask_violations=mask_violations,
        )

    def elo(self, num_games: int = 500, **kwargs) -> dict[str, float]:
        """Convenience: run then return the Elo table."""
        return self.run(num_games).elo(**kwargs)


def _is_legal(game: Game, action_id: int) -> bool:
    """Whether ``action_id`` is set in the current legality mask."""
    m = action_codec.mask(game)
    return bool(0 <= action_id < m.shape[0] and m[action_id])


# --------------------------------------------------------------------------- #
# Elo                                                                          #
# --------------------------------------------------------------------------- #


def compute_elo(
    records: list[dict[str, int]],
    *,
    k: float = 32.0,
    iters: int = 1,
    init: float = 1500.0,
) -> dict[str, float]:
    """Multiplayer Elo from per-game placement records (see module docstring).

    Each game (a ``{name: placement}`` dict, 1 = best) is expanded to all ordered
    pairs; the better-placed agent scores 1 (0.5 on a tie) and a standard Elo
    update is applied. Updates within a pass are synchronous (computed against the
    pass-start ratings) so the table is independent of game/pair ordering and thus
    reproducible. ``iters`` passes over the full record allow the ratings to
    settle. Returns ``{name: rating}``; empty records -> empty dict.
    """
    names: set[str] = set()
    for rec in records:
        names.update(rec.keys())
    ratings = {name: float(init) for name in names}
    if not records:
        return ratings

    for _ in range(max(1, iters)):
        deltas = {name: 0.0 for name in ratings}
        snapshot = dict(ratings)
        for rec in records:
            items = list(rec.items())
            for (na, pa), (nb, pb) in combinations(items, 2):
                # Lower placement number = better finish -> score 1.
                if pa < pb:
                    sa = 1.0
                elif pa > pb:
                    sa = 0.0
                else:
                    sa = 0.5
                ra, rb = snapshot[na], snapshot[nb]
                ea = 1.0 / (1.0 + 10.0 ** ((rb - ra) / 400.0))
                deltas[na] += k * (sa - ea)
                deltas[nb] += k * ((1.0 - sa) - (1.0 - ea))
        for name in ratings:
            ratings[name] += deltas[name]

    return ratings


# --------------------------------------------------------------------------- #
# benchmarks                                                                   #
# --------------------------------------------------------------------------- #


def _benchmark(candidate, make_opponent, *, num_games: int, seed: int, num_players: int) -> float:
    """Run ``candidate`` vs ``num_players-1`` fresh opponents; return its win rate."""
    from ..agents.heuristic_agent import HeuristicAgent  # noqa: F401  (typing only)

    players = [("candidate", candidate)]
    for i in range(num_players - 1):
        players.append((f"opp{i}", make_opponent(seed + 101 + i)))
    arena = Arena(players, num_players=num_players, seed=seed)
    result = arena.run(num_games)
    return result.agents["candidate"].win_rate


def benchmark_vs_random(agent, num_games: int = 500, *, seed: int = 0, num_players: int = 4) -> float:
    """Win rate of ``agent`` (rotating seats) vs all-``RandomAgent`` opponents."""
    from ..agents.random_agent import RandomAgent

    return _benchmark(
        agent,
        lambda s: RandomAgent(seed=s),
        num_games=num_games,
        seed=seed,
        num_players=num_players,
    )


def benchmark_vs_heuristic(agent, num_games: int = 500, *, seed: int = 0, num_players: int = 4) -> float:
    """Win rate of ``agent`` (rotating seats) vs all-``HeuristicAgent`` opponents."""
    from ..agents.heuristic_agent import HeuristicAgent

    return _benchmark(
        agent,
        lambda s: HeuristicAgent(seed=s),
        num_games=num_games,
        seed=seed,
        num_players=num_players,
    )


# --------------------------------------------------------------------------- #
# CLI                                                                          #
# --------------------------------------------------------------------------- #


def _main(argv=None) -> None:
    import argparse

    from ..agents.heuristic_agent import HeuristicAgent
    from ..agents.random_agent import RandomAgent

    parser = argparse.ArgumentParser(
        description="Run a seat-rotated arena of {RL?, Heuristic, Random, Random} and report a table + Elo."
    )
    parser.add_argument(
        "--checkpoint",
        default=None,
        help="Path to an RLPolicy checkpoint; if given, the RL agent fills seat 0.",
    )
    parser.add_argument("--games", type=int, default=200, help="Number of games (default 200).")
    parser.add_argument("--seed", type=int, default=0, help="Base engine seed (default 0).")
    args = parser.parse_args(argv)

    if args.checkpoint:
        from ..agents.rl_policy import RLPolicy

        first = ("rl", RLPolicy.from_checkpoint(args.checkpoint))
    else:
        first = ("heuristic", HeuristicAgent(seed=1))

    players = [
        first,
        ("heuristic2" if not args.checkpoint else "heuristic", HeuristicAgent(seed=2)),
        ("random1", RandomAgent(seed=3)),
        ("random2", RandomAgent(seed=4)),
    ]
    arena = Arena(players, num_players=4, seed=args.seed)
    result = arena.run(args.games)
    print(result.to_table())


if __name__ == "__main__":  # pragma: no cover
    _main()
