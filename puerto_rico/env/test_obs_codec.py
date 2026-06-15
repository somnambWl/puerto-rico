"""Tests for the flat observation encoder (``obs_codec``).

Covers: constant length / dtype / finiteness / range across many random
playthrough states and all perspectives; ``describe()`` length agreement;
perspective symmetry (self-first, own VP visible, opponents' VP hidden); and
hidden-info guarantees (no opponent VP leak, no face-down tile identities).
"""

from __future__ import annotations

import random

import numpy as np

from ..engine.enums import Good, TileType
from ..engine.game import Game
from ..engine.state import GameConfig
from . import obs_codec
from .obs_codec import OBS_LEN, PLAYER_BLOCK_LEN, describe, encode


def _states_from_playthrough(num_players: int, seed: int, limit: int = 400):
    """Yield states sampled along one random-legal playthrough."""
    game = Game(GameConfig(num_players=num_players, seed=seed))
    chooser = random.Random(seed)
    states = [game.state.clone()]
    steps = 0
    while not game.is_terminal and steps < limit:
        actions = game.legal_actions()
        game.apply(chooser.choice(actions))
        states.append(game.state.clone())
        steps += 1
    return states


def _assert_valid_vector(vec: np.ndarray) -> None:
    assert vec.shape == (OBS_LEN,)
    assert vec.dtype == np.float32
    assert np.all(np.isfinite(vec)), "non-finite value in observation"
    # All features are normalized to [0, 1] (one-hots/flags are exactly 0/1).
    assert float(vec.min()) >= -1e-6, f"value below 0: {vec.min()}"
    assert float(vec.max()) <= 1.0 + 1e-6, f"value above 1: {vec.max()}"


def test_obs_len_constant() -> None:
    """Every encoded state (many seeds, all perspectives) has shape/dtype/range."""
    seen = 0
    for seed in range(8):
        states = _states_from_playthrough(4, seed)
        # Sample a spread of states to keep the test fast but broad.
        for st in states[:: max(1, len(states) // 25)]:
            for p in range(4):
                _assert_valid_vector(encode(st, p))
                seen += 1
    assert seen > 0
    # A 2-player game must encode into the same fixed length.
    for st in _states_from_playthrough(2, 1)[::20]:
        for p in range(2):
            _assert_valid_vector(encode(st, p))


def test_describe_matches() -> None:
    names = describe()
    assert len(names) == OBS_LEN
    assert len(set(names)) == OBS_LEN, "feature names must be unique"


def test_perspective_self_first() -> None:
    """Perspective p's self block holds player p's data, incl. its real VP."""
    game = Game(GameConfig(num_players=4, seed=3))
    chooser = random.Random(3)
    # Advance into mid-game so players have diverged.
    for _ in range(120):
        if game.is_terminal:
            break
        game.apply(chooser.choice(game.legal_actions()))
    state = game.state

    # Give each player a distinct, non-zero VP so the self block is identifiable.
    for idx, p in enumerate(state.players):
        p.vp_chips = 5 + 3 * idx

    vp_idx = describe().index("self.vp_chips")
    flag_idx = describe().index("self.vp_known_flag")

    vectors = [encode(state, p) for p in range(4)]

    # Different perspectives give different vectors.
    for a in range(4):
        for b in range(a + 1, 4):
            assert not np.array_equal(vectors[a], vectors[b]), (
                f"perspectives {a} and {b} produced identical vectors"
            )

    # Self block carries player p's own real VP and known flag == 1.
    from .obs_codec import _MAX_VP

    for p in range(4):
        expected = (5 + 3 * p) / _MAX_VP
        assert vectors[p][vp_idx] == np.float32(expected)
        assert vectors[p][flag_idx] == np.float32(1.0)


def test_hidden_info() -> None:
    """Opponent VP is never leaked; face-down tile identities are not encoded."""
    game = Game(GameConfig(num_players=4, seed=11))
    chooser = random.Random(11)
    for _ in range(80):
        if game.is_terminal:
            break
        game.apply(chooser.choice(game.legal_actions()))
    state = game.state

    names = describe()

    # 1) Opponent VP hidden: give opponents huge distinct VP; the encoding from
    #    perspective 0 must not change in any opponent vp_chips slot (stays 0).
    base = encode(state, 0).copy()
    for idx in range(1, 4):
        state.players[idx].vp_chips = 999 + idx
    after = encode(state, 0)

    opp_vp_indices = [i for i, nm in enumerate(names) if nm.endswith(".vp_chips") and nm.startswith("opp")]
    assert opp_vp_indices, "expected opponent vp_chips features"
    for i in opp_vp_indices:
        assert base[i] == 0.0 and after[i] == 0.0, "opponent VP leaked into observation"
    # The change to opponents' hidden VP leaves the whole vector untouched.
    assert np.array_equal(base, after), "hidden opponent VP changed the observation"

    # 2) Face-down plantation identities are not encoded. Reorder the face-down
    #    stack (same multiset, same size) -> identical observation. Only the
    #    SIZE feature exists for the face-down stack.
    facedown_features = [nm for nm in names if "facedown" in nm]
    assert facedown_features == ["shared.plantation_facedown_size"], (
        f"face-down stack must expose size only, got {facedown_features}"
    )
    before = encode(state, 0).copy()
    state.plantation_facedown.reverse()
    state.rng.shuffle(state.plantation_facedown)
    assert np.array_equal(before, encode(state, 0)), (
        "shuffling hidden face-down stack changed the observation"
    )


def test_opponent_block_ordering() -> None:
    """Opponents appear clockwise after self; absent seats (2p) stay zero-padded."""
    state = Game(GameConfig(num_players=2, seed=5)).state
    vec = encode(state, 0)
    # The two trailing opponent blocks (opp1, opp2) correspond to absent seats in
    # a 2-player game and must be all zero.
    # self + opp0 occupy the first two player blocks.
    start_absent = 2 * PLAYER_BLOCK_LEN
    end_absent = 4 * PLAYER_BLOCK_LEN
    assert np.all(vec[start_absent:end_absent] == 0.0), "absent seat block not zero-padded"
