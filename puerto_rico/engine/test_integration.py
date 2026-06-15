"""End-to-end smoke test: a random legal-move playthrough.

This test drives a :class:`Game` by repeatedly selecting a random *legal*
action until the game is terminal, asserting the engine never dead-ends, never
raises, and always terminates within a sane step bound. It also checks that
``returns()`` and ``winner()`` are well-formed at termination, and that the
whole rollout is deterministic given the engine seed and the action-choice rng
seed.

M1 STUB NOTE
------------
At milestone 1 the phase handlers beyond ``ROLE_SELECTION`` are stubs (see
``game.py`` and engine-core-task-07); the real round/phase state machine is
delivered by the **engine-phases** epic (design/02). Consequently a game here
terminates quickly via the stubbed transitions. This is intentionally a *smoke
test* of the engine loop + phase dispatch + termination working end-to-end, not
a test of real gameplay. As the phases epic lands, the same invariants
(legal actions present while non-terminal, no exceptions, deterministic) will
naturally exercise much deeper play with no changes here.
"""

from __future__ import annotations

import random

import pytest

from .game import Game
from .state import GameConfig

# Generous cap: large enough never to fire for a real game, small enough to
# catch an infinite loop (e.g. a phase that never advances toward GAME_OVER).
MAX_STEPS = 10_000


def _playthrough(game_seed: int, choice_seed: int) -> tuple[list, list[float], int]:
    """Run one random playthrough.

    Returns ``(applied_actions, final_returns, step_count)``. Asserts the core
    engine invariants along the way (legal actions present while non-terminal,
    no exceptions, bounded steps).
    """
    config = GameConfig(num_players=4, seed=game_seed)
    game = Game(config)
    chooser = random.Random(choice_seed)

    applied: list = []
    steps = 0
    while not game.is_terminal:
        actions = game.legal_actions()
        assert actions, "non-terminal state must have >= 1 legal action (no dead-ends)"
        action = chooser.choice(actions)
        game.apply(action)
        applied.append(action)
        steps += 1
        assert steps < MAX_STEPS, f"playthrough exceeded {MAX_STEPS} steps (infinite loop?)"

    assert steps > 0, "game terminated before any action was applied"
    return applied, game.returns(), steps


@pytest.mark.parametrize("game_seed", [0, 1, 42])
def test_random_playthrough_reaches_terminal(game_seed: int) -> None:
    """A random legal-move game reaches terminal cleanly across seeds.

    Verifies: no dead-ends, no exceptions, bounded steps, and that the terminal
    results (``returns()`` / ``winner()``) are well-formed.
    """
    config = GameConfig(num_players=4, seed=game_seed)
    n = config.num_players

    applied, returns, steps = _playthrough(game_seed=game_seed, choice_seed=game_seed)

    assert 0 < steps < MAX_STEPS

    # returns(): one rank-based payoff per player, summing to ~0 (see Game.returns).
    assert isinstance(returns, list)
    assert len(returns) == n
    assert sum(returns) == pytest.approx(0.0, abs=1e-9)

    # winner(): a valid player index, re-derived from a fresh terminal game.
    game = Game(config)
    chooser = random.Random(game_seed)
    while not game.is_terminal:
        game.apply(chooser.choice(game.legal_actions()))
    winner = game.winner()
    assert winner is not None
    assert 0 <= winner < n


def test_random_playthrough_is_deterministic() -> None:
    """Same engine seed + same action-choice seed -> identical rollout.

    Two playthroughs with matched seeds must apply the identical sequence of
    actions and produce identical final ``returns()``.
    """
    applied_a, returns_a, steps_a = _playthrough(game_seed=42, choice_seed=7)
    applied_b, returns_b, steps_b = _playthrough(game_seed=42, choice_seed=7)

    assert steps_a == steps_b
    assert applied_a == applied_b
    assert returns_a == returns_b
