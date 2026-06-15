"""Tests for the PettingZoo AEC wrapper (env-task-03).

Covers: PettingZoo ``api_test`` conformance, a random *masked* self-play episode
with reward/winner consistency, determinism under a fixed seed + rng, and the
masked-illegal ``ValueError`` contract.
"""

from __future__ import annotations

import numpy as np
import pytest
from pettingzoo.test import api_test

from puerto_rico.env import action_codec
from puerto_rico.env.pettingzoo_env import PuertoRicoAEC, env


def _legal_ids(mask: np.ndarray) -> np.ndarray:
    return np.where(np.asarray(mask) != 0)[0]


def _run_episode(seed: int, rng: np.random.Generator):
    """Play one full random-masked episode; return (rewards, action_sequence)."""
    e = PuertoRicoAEC({"num_players": 4, "seed": seed})
    e.reset(seed=seed)
    actions: list[int] = []
    # Track each agent's cumulative reward as reported by last(); the cumulative
    # total is delivered to an agent on its first dead-step after termination.
    rewards = {a: 0.0 for a in e.possible_agents}
    for agent in e.agent_iter():
        obs, reward, term, trunc, _info = e.last()
        rewards[agent] = reward
        if term or trunc:
            action = None
        else:
            legal = _legal_ids(obs["action_mask"])
            action = int(rng.choice(legal))
            actions.append(action)
        e.step(action)
    return rewards, actions, e


def test_api():
    api_test(PuertoRicoAEC(), num_cycles=10)


def test_factory_builds():
    e = env(num_players=4, seed=1)
    assert e.possible_agents == ["player_0", "player_1", "player_2", "player_3"]
    e.reset()
    assert e.agent_selection in e.possible_agents


def test_random_masked_selfplay_episode():
    rng = np.random.default_rng(123)
    rewards, actions, e = _run_episode(seed=7, rng=rng)

    assert e.game.is_terminal
    # PettingZoo prunes terminated agents from `agents`/`terminations` once they
    # take their dead-step, so post-episode the dicts are empty by design.
    assert e.agents == []
    assert len(actions) > 0

    # Terminal rewards equal engine.returns() per seat.
    returns = e.game.returns()
    for i, a in enumerate(e.possible_agents):
        assert rewards[a] == pytest.approx(returns[i])

    # Winner (engine ranking) holds the unique maximum reward.
    win_seat = e.game.winner()
    win_reward = returns[win_seat]
    assert win_reward == max(returns)
    assert returns.count(win_reward) == 1


def test_determinism():
    r1, a1, _ = _run_episode(seed=42, rng=np.random.default_rng(99))
    r2, a2, _ = _run_episode(seed=42, rng=np.random.default_rng(99))
    assert a1 == a2
    assert r1 == r2


def test_illegal_action_raises():
    e = PuertoRicoAEC({"num_players": 4, "seed": 3})
    e.reset()
    obs = e.observe(e.agent_selection)
    illegal = int(np.where(np.asarray(obs["action_mask"]) == 0)[0][0])
    with pytest.raises(ValueError):
        e.step(illegal)


def test_observe_shapes_and_dtypes():
    e = PuertoRicoAEC({"num_players": 4, "seed": 5})
    e.reset()
    obs = e.observe(e.agent_selection)
    from puerto_rico.env import obs_codec

    assert obs["observation"].shape == (obs_codec.OBS_LEN,)
    assert obs["observation"].dtype == np.float32
    assert obs["action_mask"].shape == (action_codec.N_ACTIONS,)
    # Mask is binary and matches engine legality count.
    mask = np.asarray(obs["action_mask"])
    assert set(np.unique(mask)).issubset({0, 1})
    assert int(mask.sum()) == len(e.game.legal_actions())
