"""Tests for the evaluation harness (Arena + Elo + benchmarks)."""

from __future__ import annotations

import pytest

from ..agents.heuristic_agent import HeuristicAgent
from ..agents.random_agent import RandomAgent
from ..engine.game import Game
from ..engine.state import GameConfig
from . import evaluate
from .evaluate import Arena, benchmark_vs_random, compute_elo, make_player


# --------------------------------------------------------------------------- #
# make_player adapters                                                         #
# --------------------------------------------------------------------------- #


def _legal_ids(game: Game):
    from ..env import action_codec

    m = action_codec.mask(game)
    return set(int(i) for i in range(m.shape[0]) if m[i])


def _drive_one_game_check_legal(player_fn, *, seed=0) -> int:
    """Play a full game with player_fn at every seat; count mask violations."""
    from ..env import action_codec

    game = Game(GameConfig(num_players=4, seed=seed))
    violations = 0
    while not game.is_terminal:
        aid = int(player_fn(game))
        if aid not in _legal_ids(game):
            violations += 1
        game.apply(action_codec.from_int(aid, game.state), validate=False)
    return violations


def test_make_player_random_returns_legal_ids():
    fn = make_player(RandomAgent(seed=1))
    assert _drive_one_game_check_legal(fn, seed=7) == 0


def test_make_player_heuristic_returns_legal_ids():
    fn = make_player(HeuristicAgent(seed=1))
    assert _drive_one_game_check_legal(fn, seed=7) == 0


def test_make_player_game_based_callable_and_act_id():
    # An agent exposing act_id(game) (heuristic) and a bare callable both adapt.
    h = HeuristicAgent(seed=2)
    fn_attr = make_player(h)
    fn_call = make_player(make_player(h))  # callable wrapping a callable
    assert _drive_one_game_check_legal(fn_attr, seed=3) == 0
    assert _drive_one_game_check_legal(fn_call, seed=3) == 0


# --------------------------------------------------------------------------- #
# Arena: all-random ~25%                                                       #
# --------------------------------------------------------------------------- #


def test_arena_all_random_balanced():
    players = [(f"r{i}", RandomAgent(seed=i)) for i in range(4)]
    result = Arena(players, num_players=4, seed=0).run(120)

    assert result.mask_violations == 0
    total_win = sum(a.win_rate for a in result.agents.values())
    assert total_win == pytest.approx(1.0, abs=1e-9)

    for a in result.agents.values():
        assert a.games == 120
        assert 0.12 <= a.win_rate <= 0.40, (a.name, a.win_rate)
        # mean placement should sit near (N+1)/2 = 2.5
        assert 2.0 <= a.mean_placement <= 3.0, (a.name, a.mean_placement)

    # Across all agents the mean placement averages exactly (N+1)/2.
    avg_pl = sum(a.mean_placement for a in result.agents.values()) / 4
    assert avg_pl == pytest.approx(2.5, abs=1e-9)


# --------------------------------------------------------------------------- #
# Arena: heuristic clearly beats random                                        #
# --------------------------------------------------------------------------- #


def test_arena_heuristic_beats_random():
    players = [
        ("heuristic", HeuristicAgent(seed=10)),
        ("r1", RandomAgent(seed=1)),
        ("r2", RandomAgent(seed=2)),
        ("r3", RandomAgent(seed=3)),
    ]
    result = Arena(players, num_players=4, seed=0).run(120)

    assert result.mask_violations == 0
    h = result.agents["heuristic"]
    assert h.win_rate > 0.45, h.win_rate
    assert h.mean_placement < 2.0, h.mean_placement
    # Table renders without error.
    assert "heuristic" in result.to_table()


def test_benchmark_vs_random_heuristic():
    win = benchmark_vs_random(HeuristicAgent(seed=5), num_games=120, seed=0)
    assert win > 0.4, win


# --------------------------------------------------------------------------- #
# Elo                                                                          #
# --------------------------------------------------------------------------- #


def test_elo_stronger_higher_and_reproducible():
    players = [
        ("heuristic", HeuristicAgent(seed=10)),
        ("r1", RandomAgent(seed=1)),
        ("r2", RandomAgent(seed=2)),
        ("r3", RandomAgent(seed=3)),
    ]
    result = Arena(players, num_players=4, seed=0).run(120)

    elo = compute_elo(result.records)
    assert elo["heuristic"] > elo["r1"]
    assert elo["heuristic"] > elo["r2"]
    assert elo["heuristic"] > elo["r3"]

    # Reproducible given identical records.
    elo2 = compute_elo(result.records)
    assert elo == elo2

    # Order-independence: shuffling records yields the same table (synchronous).
    import random

    shuffled = list(result.records)
    random.Random(0).shuffle(shuffled)
    elo3 = compute_elo(shuffled)
    for name in elo:
        assert elo3[name] == pytest.approx(elo[name], abs=1e-9)


def test_elo_empty_records():
    assert compute_elo([]) == {}


# --------------------------------------------------------------------------- #
# determinism                                                                  #
# --------------------------------------------------------------------------- #


def test_arena_deterministic():
    def build():
        return Arena(
            [
                ("heuristic", HeuristicAgent(seed=10)),
                ("r1", RandomAgent(seed=1)),
                ("r2", RandomAgent(seed=2)),
                ("r3", RandomAgent(seed=3)),
            ],
            num_players=4,
            seed=0,
        )

    r1 = build().run(40)
    r2 = build().run(40)
    assert r1.records == r2.records
    for name in r1.agents:
        a1, a2 = r1.agents[name], r2.agents[name]
        assert (a1.wins, a1.placement_sum, a1.vp_sum, a1.games) == (
            a2.wins,
            a2.placement_sum,
            a2.vp_sum,
            a2.games,
        )
