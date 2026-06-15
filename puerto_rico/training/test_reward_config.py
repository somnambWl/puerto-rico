"""Tests for reward modes + dense-shaping schedule (agents-task-06).

Covers the three terminal reward modes (``rank`` / ``win`` / ``vp_margin``),
their tie handling, the :class:`ShapingSchedule` anneal, and the env honoring
``reward_mode`` end-to-end (default ``rank`` unchanged, ``win`` matches
:func:`terminal_rewards`).
"""

from __future__ import annotations

import numpy as np
import pytest

from puerto_rico.engine.enums import Phase
from puerto_rico.engine.setup import new_game
from puerto_rico.engine.state import GameConfig
from puerto_rico.env.pettingzoo_env import PuertoRicoAEC
from puerto_rico.training import reward_config


def _terminal_state(vp_chips: list[int]):
    """Build a GAME_OVER state whose final scores equal ``vp_chips`` per seat.

    A fresh game has empty cities, so ``final_score`` reduces to ``vp_chips``;
    we set them directly and flip the phase to GAME_OVER for full control.
    """
    s = new_game(GameConfig(num_players=len(vp_chips), seed=1))
    for p, v in zip(s.players, vp_chips):
        p.vp_chips = v
    s.phase = Phase.GAME_OVER
    return s


# --- rank ---------------------------------------------------------------- #


def test_rank_four_player_evenly_spaced_zero_mean():
    # Strictly decreasing scores -> ranks [seat0, seat1, seat2, seat3].
    s = _terminal_state([40, 30, 20, 10])
    r = reward_config.terminal_rewards(s, "rank")
    assert r == pytest.approx([1.0, 1.0 / 3.0, -1.0 / 3.0, -1.0])
    assert sum(r) == pytest.approx(0.0)


def test_rank_default_mode_matches_explicit():
    s = _terminal_state([5, 4, 3, 2])
    assert reward_config.terminal_rewards(s) == reward_config.terminal_rewards(s, "rank")


def test_rank_ties_share_averaged_reward():
    # Seats 1 and 2 are genuinely tied on (score, wealth). The seat-index
    # discriminator is removed by hand so the grouping branch is exercised.
    import puerto_rico.training.reward_config as rc

    s = _terminal_state([40, 25, 25, 10])

    orig = rc.scoring.tiebreak_key

    def keyed(state, idx):
        score, wealth, _seat = orig(state, idx)
        return (score, wealth, 0)  # drop seat tie-breaker -> real ties

    rc.scoring.tiebreak_key = keyed
    try:
        r = rc.terminal_rewards(s, "rank")
    finally:
        rc.scoring.tiebreak_key = orig

    # targets [1, 1/3, -1/3, -1]; seats 1&2 span ranks 1&2 -> average 0.
    assert r[0] == pytest.approx(1.0)
    assert r[1] == pytest.approx(0.0)
    assert r[2] == pytest.approx(0.0)
    assert r[3] == pytest.approx(-1.0)
    assert sum(r) == pytest.approx(0.0)


def test_rank_matches_game_returns():
    from puerto_rico.engine.game import Game

    g = Game(GameConfig(num_players=4, seed=3))
    while not g.is_terminal:
        g.apply(g.legal_actions()[0])
    assert g.returns() == pytest.approx(
        reward_config.terminal_rewards(g.state, "rank")
    )


# --- win ----------------------------------------------------------------- #


def test_win_only_winner_gets_one():
    s = _terminal_state([40, 30, 20, 10])
    r = reward_config.terminal_rewards(s, "win")
    assert r == pytest.approx([1.0, 0.0, 0.0, 0.0])
    assert sum(r) == pytest.approx(1.0)


def test_win_ties_split_evenly():
    import puerto_rico.training.reward_config as rc

    s = _terminal_state([40, 40, 20, 10])
    orig = rc.scoring.tiebreak_key

    def keyed(state, idx):
        score, wealth, _seat = orig(state, idx)
        return (score, wealth, 0)

    rc.scoring.tiebreak_key = keyed
    try:
        r = rc.terminal_rewards(s, "win")
    finally:
        rc.scoring.tiebreak_key = orig
    assert r == pytest.approx([0.5, 0.5, 0.0, 0.0])
    assert sum(r) == pytest.approx(1.0)


# --- vp_margin ----------------------------------------------------------- #


def test_vp_margin_zero_mean_unit_std():
    s = _terminal_state([40, 30, 20, 10])
    r = reward_config.terminal_rewards(s, "vp_margin")
    assert sum(r) == pytest.approx(0.0)
    arr = np.array(r)
    assert arr.mean() == pytest.approx(0.0)
    assert arr.std() == pytest.approx(1.0)
    # Order preserved: highest VP -> highest z-score.
    assert r[0] > r[1] > r[2] > r[3]


def test_vp_margin_zero_std_returns_zeros():
    s = _terminal_state([15, 15, 15, 15])
    r = reward_config.terminal_rewards(s, "vp_margin")
    assert r == [0.0, 0.0, 0.0, 0.0]


# --- mode validation / non-terminal -------------------------------------- #


def test_unknown_mode_raises():
    s = _terminal_state([1, 2, 3, 4])
    with pytest.raises(ValueError):
        reward_config.terminal_rewards(s, "nope")


def test_non_terminal_returns_zeros():
    s = new_game(GameConfig(num_players=4, seed=1))
    assert reward_config.terminal_rewards(s, "rank") == [0.0, 0.0, 0.0, 0.0]
    assert reward_config.terminal_rewards(s, "win") == [0.0, 0.0, 0.0, 0.0]


# --- shaping schedule ---------------------------------------------------- #


def test_shaping_schedule_anneals_to_zero():
    sched = reward_config.ShapingSchedule(coef0=0.5, horizon=100)
    assert sched.coef(0) == pytest.approx(0.5)
    assert sched.coef(100) == pytest.approx(0.0)
    assert sched.coef(200) == pytest.approx(0.0)
    assert sched.coef(50) == pytest.approx(0.25)
    # Monotonically non-increasing across the horizon.
    vals = [sched.coef(t) for t in range(0, 101, 10)]
    assert all(a >= b for a, b in zip(vals, vals[1:]))


def test_shaping_schedule_rejects_bad_horizon():
    with pytest.raises(ValueError):
        reward_config.ShapingSchedule(coef0=1.0, horizon=0)


def test_round_shaping_scales_advantage_delta():
    prev = _terminal_state([10, 10, 10, 10])  # advantage 0 for all
    new = _terminal_state([16, 10, 10, 10])  # seat0 advantage = 16 - 10 = 6
    val = reward_config.round_shaping(prev, new, 0, coef=0.5)
    assert val == pytest.approx(0.5 * 6.0)
    # Zero coefficient short-circuits to 0.
    assert reward_config.round_shaping(prev, new, 0, coef=0.0) == 0.0


# --- env wiring ---------------------------------------------------------- #


def _run_episode(reward_mode: str, seed: int):
    rng = np.random.default_rng(seed)
    e = PuertoRicoAEC({"num_players": 4, "seed": seed, "reward_mode": reward_mode})
    e.reset(seed=seed)
    rewards = {a: 0.0 for a in e.possible_agents}
    for agent in e.agent_iter():
        obs, reward, term, trunc, _info = e.last()
        rewards[agent] = reward
        if term or trunc:
            action = None
        else:
            legal = np.where(np.asarray(obs["action_mask"]) != 0)[0]
            action = int(rng.choice(legal))
        e.step(action)
    return rewards, e


def test_env_default_mode_is_rank():
    rewards, e = _run_episode("rank", seed=7)
    expected = reward_config.terminal_rewards(e.game.state, "rank")
    for i, a in enumerate(e.possible_agents):
        assert rewards[a] == pytest.approx(expected[i])
    # Matches the legacy Game.returns() path too.
    assert expected == pytest.approx(e.game.returns())


def test_env_win_mode_matches_terminal_rewards():
    rewards, e = _run_episode("win", seed=11)
    expected = reward_config.terminal_rewards(e.game.state, "win")
    for i, a in enumerate(e.possible_agents):
        assert rewards[a] == pytest.approx(expected[i])
    assert sum(expected) == pytest.approx(1.0)
