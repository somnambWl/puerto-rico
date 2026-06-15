"""Tests for :class:`~puerto_rico.agents.heuristic_agent.HeuristicAgent`.

Covers three things (task agents-02):

1. **Legality / completion** — full 4-player games of 4 HeuristicAgents driven
   straight through the engine: every chosen action is in ``legal_actions`` and
   every game terminates (0 mask violations).
2. **Determinism** — same seed -> identical action sequence.
3. **Strength** — 1 HeuristicAgent vs 3 RandomAgents over many seat-rotated
   games; the heuristic's win rate is clearly above the 25% chance baseline.
"""

from __future__ import annotations

import types

import numpy as np
import pytest

from puerto_rico.agents.heuristic_agent import HeuristicAgent
from puerto_rico.engine.actions import Action
from puerto_rico.engine.enums import DecisionType, Good, Phase
from puerto_rico.engine.game import Game
from puerto_rico.engine.state import CargoShip, GameConfig

CAPTAIN_WHARF = 1

NUM_PLAYERS = 4
# Keep games short so the strength sweep stays fast (engine is the safety valve
# regardless; this just bounds the deliberately-random opponents).
MAX_ROUNDS = 20


def _new_game(seed: int) -> Game:
    return Game(GameConfig(num_players=NUM_PLAYERS, seed=seed, max_rounds=MAX_ROUNDS))


def _random_action(game: Game, rng: np.random.Generator):
    """Uniform pick over the engine's legal actions (state-based random seat)."""
    legal = game.legal_actions()
    return legal[int(rng.integers(len(legal)))]


def _play_game(seat_agents, seat_rngs, game: Game) -> Game:
    """Drive ``game`` to termination; each seat uses its assigned agent/rng.

    ``seat_agents[i]`` is either a ``HeuristicAgent`` (called with the game) or
    ``None`` for a random seat (uniform over ``legal_actions`` with its rng).
    """
    steps = 0
    while not game.is_terminal:
        seat = game.current_player
        agent = seat_agents[seat]
        if agent is None:
            action = _random_action(game, seat_rngs[seat])
        else:
            action = agent.act(game)
        # Asserting legality here is the mask-violation guard.
        assert action in game.legal_actions(), (
            f"agent returned illegal action {action!r} for seat {seat}"
        )
        game.apply(action)
        steps += 1
        assert steps < 100_000, "game failed to terminate"
    return game


# --------------------------------------------------------------------------- #
# 1. legality + completion
# --------------------------------------------------------------------------- #


def test_heuristic_only_games_are_legal_and_terminate():
    """4 HeuristicAgents play full games with 0 illegal actions; all complete."""
    for seed in range(25):
        game = _new_game(seed)
        agents = [HeuristicAgent(seed=100 + seed * 4 + i) for i in range(NUM_PLAYERS)]
        result = _play_game(agents, [None] * NUM_PLAYERS, game)
        assert result.is_terminal
        assert result.winner() is not None


def test_act_id_matches_codec_and_is_legal():
    """``act_id`` returns the encoded id of the chosen legal action across states."""
    from puerto_rico.env.action_codec import mask, to_int

    game = _new_game(3)
    steps = 0
    while not game.is_terminal and steps < 500:
        # Use two fresh agents with the SAME seed so act and act_id resolve ties
        # identically on this state (each agent's rng is at the same position).
        action = HeuristicAgent(seed=7).act(game)
        aid = HeuristicAgent(seed=7).act_id(game)
        assert mask(game)[aid], "act_id encoded an illegal action"
        assert to_int(action) == aid
        game.apply(action)
        steps += 1


# --------------------------------------------------------------------------- #
# 1b. focused captain decisions (ship selection + windrose CHOOSE)
# --------------------------------------------------------------------------- #


def _fake_captain_game(goods: dict[Good, int], cargo_ships, legal):
    """Minimal stand-in exposing what ``_captain`` reads: goods + cargo_ships.

    ``_captain`` only touches ``game.state.cargo_ships`` and the acting player's
    ``goods``, plus the supplied ``legal_actions``. A tiny namespace is enough to
    exercise the captain rule in isolation without driving a whole game.
    """
    goods_arr = [goods.get(Good(i), 0) for i in range(len(Good))]
    player = types.SimpleNamespace(goods=goods_arr)
    state = types.SimpleNamespace(
        phase=Phase.CAPTAIN,
        current_player=0,
        players=[player],
        cargo_ships=cargo_ships,
    )
    return types.SimpleNamespace(
        state=state, legal_actions=lambda: list(legal)
    )


def test_captain_load_picks_legal_ship_with_most_space():
    """A good loadable on multiple ships -> a legal LOAD targeting a real ship.

    The player holds 4 SUGAR; ship 0 has 1 free slot, ship 1 has 3 free. The
    heuristic should pick the ship that ships the most (ship 1), and the returned
    action must be a legal LOAD with a valid target ship index.
    """
    ships = [
        CargoShip(capacity=4, good=Good.SUGAR, count=3),  # 1 slot free
        CargoShip(capacity=6, good=None, count=0),  # 6 free, but corn rule n/a
    ]
    # Make ship 1 empty-and-legal for SUGAR by clearing held-elsewhere concerns:
    # the engine builds the pairs; here we just hand both as legal targets.
    legal = [
        Action.load(Good.SUGAR, target=0),
        Action.load(Good.SUGAR, target=1),
    ]
    game = _fake_captain_game({Good.SUGAR: 4}, ships, legal)
    agent = HeuristicAgent(seed=1)
    action = agent.act(game)

    assert action in legal
    assert action.type == DecisionType.LOAD
    assert action.target in (0, 1)
    # Ship 1 (3 free) ships more SUGAR than ship 0 (1 free) -> picked.
    assert action.target == 1


def test_captain_windrose_choose_keeps_a_held_good():
    """A windrose CHOOSE state -> a legal CHOOSE keeping the most-held kind.

    The player holds 1 INDIGO and 3 COFFEE (both unprotected). The heuristic
    keeps the kind it holds the most of -> COFFEE.
    """
    legal = [
        Action(DecisionType.CHOOSE, good=Good.INDIGO),
        Action(DecisionType.CHOOSE, good=Good.COFFEE),
    ]
    game = _fake_captain_game(
        {Good.INDIGO: 1, Good.COFFEE: 3}, cargo_ships=[], legal=legal
    )
    agent = HeuristicAgent(seed=1)
    action = agent.act(game)

    assert action in legal
    assert action.type == DecisionType.CHOOSE
    assert action.good == Good.COFFEE  # most-held kind is retained.


def test_captain_wharf_used_when_it_ships_more():
    """Wharf is chosen over a cramped cargo ship for a big held pile.

    The player holds 5 TOBACCO. The only cargo ship has 1 free slot (ships 1),
    while the wharf ships all 5 -> the wharf is the better load.
    """
    ships = [CargoShip(capacity=4, good=Good.TOBACCO, count=3)]  # 1 free
    legal = [
        Action.load(Good.TOBACCO, target=0),
        Action(DecisionType.LOAD, good=Good.TOBACCO, choice=CAPTAIN_WHARF),
    ]
    game = _fake_captain_game({Good.TOBACCO: 5}, ships, legal)
    action = HeuristicAgent(seed=1).act(game)

    assert action in legal
    assert action.choice == CAPTAIN_WHARF


# --------------------------------------------------------------------------- #
# 2. determinism
# --------------------------------------------------------------------------- #


def test_determinism_same_seed_same_actions():
    """Same agent seed + same game seed -> identical action sequence."""

    def run() -> list:
        game = _new_game(42)
        agent = HeuristicAgent(seed=2024)
        actions = []
        while not game.is_terminal:
            a = agent.act(game)
            actions.append(a)
            game.apply(a)
        return actions

    assert run() == run()


# --------------------------------------------------------------------------- #
# 3. strength vs random
# --------------------------------------------------------------------------- #


def test_heuristic_beats_random_baseline():
    """1 Heuristic vs 3 Random over many seat-rotated games: win rate >> 25%."""
    n_games = 300
    wins = 0
    for g in range(n_games):
        hero_seat = g % NUM_PLAYERS  # rotate the heuristic across seats
        game = _new_game(g)
        seat_agents = [None] * NUM_PLAYERS
        seat_agents[hero_seat] = HeuristicAgent(seed=10_000 + g)
        seat_rngs = [np.random.default_rng(20_000 + g * NUM_PLAYERS + i) for i in range(NUM_PLAYERS)]
        result = _play_game(seat_agents, seat_rngs, game)
        if result.winner() == hero_seat:
            wins += 1

    win_rate = wins / n_games
    print(f"\nHeuristic vs 3 Random over {n_games} games: {wins} wins ({win_rate:.1%})")
    # Chance baseline is 25%; require a clearly dominant baseline agent.
    assert win_rate > 0.40, f"heuristic win rate {win_rate:.3f} not clearly above 25%"
