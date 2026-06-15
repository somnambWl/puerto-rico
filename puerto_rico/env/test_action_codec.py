"""Tests for the fixed-size discrete action codec (env-task-01).

Invariants under test (across many random legal playthroughs):

* round-trip: ``from_int(to_int(a), game) == a`` for every legal ``a``;
* injectivity: ``to_int`` is one-to-one over each state's legal set;
* mask: ``mask.sum() == len(legal_actions)`` and the ``True`` id set equals
  ``{to_int(a) for a in legal_actions}``, and every ``True`` id decodes legal;
* ``N_ACTIONS`` is a frozen constant and ``to_int`` always lands in range.
"""

from __future__ import annotations

import random

import numpy as np
import pytest

from puerto_rico.engine.actions import Action
from puerto_rico.engine.enums import DecisionType, Good
from puerto_rico.engine.game import Game
from puerto_rico.engine.phases import CAPTAIN_WHARF
from puerto_rico.engine.state import GameConfig
from puerto_rico.env import action_codec as ac

_N_GAMES = 50
_MAX_STEPS = 5000


def _playthrough(seed: int):
    """Yield ``game`` at each decision node of one random legal playthrough."""
    game = Game(GameConfig(num_players=4, seed=seed))
    rng = random.Random(seed * 31 + 7)
    steps = 0
    while not game.is_terminal and steps < _MAX_STEPS:
        yield game
        legal = game.legal_actions()
        game.apply(rng.choice(legal), validate=False)
        steps += 1


def test_n_actions_stable():
    """N_ACTIONS is constant and to_int is always in [0, N_ACTIONS)."""
    assert ac.N_ACTIONS == 92
    assert ac.ActionCodec.N_ACTIONS == ac.N_ACTIONS

    for seed in range(_N_GAMES):
        for game in _playthrough(seed):
            for a in game.legal_actions():
                i = ac.to_int(a)
                assert 0 <= i < ac.N_ACTIONS


def test_roundtrip():
    """from_int(to_int(a), state) == a; to_int injective over the legal set."""
    for seed in range(_N_GAMES):
        for game in _playthrough(seed):
            legal = game.legal_actions()
            ids = [ac.to_int(a) for a in legal]

            # injective over this state's legal set
            assert len(set(ids)) == len(ids), (
                f"to_int collided on legal set at seed={seed}: {legal}"
            )

            for a, i in zip(legal, ids):
                back = ac.from_int(i, game)
                assert back == a, f"roundtrip failed: {a!r} -> {i} -> {back!r}"


def test_mask_matches_legal():
    """mask.sum() == len(legal); True-id set == {to_int(a)}; all decode legal."""
    for seed in range(_N_GAMES):
        for game in _playthrough(seed):
            legal = game.legal_actions()
            m = ac.mask(game)

            assert m.shape == (ac.N_ACTIONS,)
            assert m.dtype == np.bool_
            assert int(m.sum()) == len(legal)

            true_ids = set(np.where(m)[0].tolist())
            assert true_ids == {ac.to_int(a) for a in legal}

            legal_set = set(legal)
            for i in true_ids:
                assert ac.from_int(i, game) in legal_set


def test_cargo_loads_distinct_ship_ids():
    """Two same-good cargo loads onto different ships get distinct ids/mask slots.

    The reworked captain phase makes ship selection explicit, so LOAD(CORN, ship0)
    and LOAD(CORN, ship1) MUST encode to different action ids (and thus different
    mask positions). This guards against a regression to the old ship-agnostic
    encoding where both collapsed to one id.
    """
    a0 = Action.load(Good.CORN, target=0)
    a1 = Action.load(Good.CORN, target=1)
    a2 = Action.load(Good.CORN, target=2)
    i0, i1, i2 = ac.to_int(a0), ac.to_int(a1), ac.to_int(a2)
    assert len({i0, i1, i2}) == 3, f"ship ids collided: {i0}, {i1}, {i2}"

    # Round-trip: each decodes back to its exact (good, ship) action.
    assert ac.from_int(i0, None) == a0
    assert ac.from_int(i1, None) == a1
    assert ac.from_int(i2, None) == a2

    # Wharf load for the same good is yet another distinct id.
    wharf = Action(DecisionType.LOAD, good=Good.CORN, choice=CAPTAIN_WHARF)
    iw = ac.to_int(wharf)
    assert iw not in {i0, i1, i2}
    assert ac.from_int(iw, None) == wharf


def test_captain_multi_ship_loads_roundtrip_in_play():
    """In real games, states offering same-good loads on >1 ship round-trip cleanly.

    Asserts at least one such multi-ship-for-one-good captain state is actually hit
    across the random playthroughs, then that every legal load there encodes to a
    distinct id and decodes back to the engine's exact action.
    """
    seen_multi_ship = False
    for seed in range(_N_GAMES):
        for game in _playthrough(seed):
            legal = game.legal_actions()
            cargo = [
                a
                for a in legal
                if a.type == DecisionType.LOAD and a.choice != CAPTAIN_WHARF
            ]
            by_good: dict[Good, list[int]] = {}
            for a in cargo:
                by_good.setdefault(a.good, []).append(a.target)
            if any(len(ships) >= 2 for ships in by_good.values()):
                seen_multi_ship = True
                ids = [ac.to_int(a) for a in cargo]
                assert len(set(ids)) == len(ids)
                for a, i in zip(cargo, ids):
                    assert ac.from_int(i, game) == a
    assert seen_multi_ship, "no state with same-good loads on multiple ships was hit"


def test_decode_every_id_in_range():
    """Every id in [0, N_ACTIONS) decodes without error (total decoder)."""
    dummy = Game(GameConfig(num_players=4, seed=0))
    for i in range(ac.N_ACTIONS):
        a = ac.from_int(i, dummy)
        assert ac.to_int(a) == i  # decode then encode is identity on all ids

    with pytest.raises(ValueError):
        ac.from_int(ac.N_ACTIONS, dummy)
    with pytest.raises(ValueError):
        ac.from_int(-1, dummy)
