"""Tests for the Gymnasium single-agent wrapper (env-task-04).

Covers: the Gymnasium reset/step contract, a full episode against the default
random opponent, opponent-policy invocation discipline, and determinism under a
fixed seed.

API-check approach
------------------
``gymnasium.utils.env_checker.check_env`` does *not* tolerate this env: it
samples ``action_space`` (an unmasked ``Discrete``) and feeds the sampled action
straight to ``step``, which the underlying AEC rejects as masked-illegal. There
is no hook to mask the checker's sampling. So ``test_gymnasium_api`` asserts the
reset/step signatures, return-tuple shapes, and types manually instead of using
``check_env`` (documented in that test).
"""

from __future__ import annotations

import numpy as np
import pytest

from puerto_rico.env import action_codec, obs_codec
from puerto_rico.env.gymnasium_wrapper import PuertoRicoSingle
from puerto_rico.training.reward_config import terminal_rewards


def _legal_ids(mask) -> np.ndarray:
    return np.where(np.asarray(mask) != 0)[0]


def _legal_learner_action(env: PuertoRicoSingle, obs: dict, rng) -> int:
    return int(rng.choice(_legal_ids(obs["action_mask"])))


def test_gymnasium_api():
    """Manual Gymnasium contract check (see module docstring for why not check_env)."""
    env = PuertoRicoSingle({"num_players": 4, "seed": 1})

    # Spaces are well-formed.
    assert env.action_space.n == action_codec.N_ACTIONS
    assert set(env.observation_space.spaces) == {"observation", "action_mask"}

    # reset -> (obs_dict, info)
    obs, info = env.reset(seed=1)
    assert isinstance(obs, dict)
    assert set(obs) == {"observation", "action_mask"}
    assert obs["observation"].shape == (obs_codec.OBS_LEN,)
    assert obs["observation"].dtype == np.float32
    assert obs["action_mask"].shape == (action_codec.N_ACTIONS,)
    assert isinstance(info, dict)
    assert env.observation_space.contains(obs)

    # step -> (obs, reward, terminated, truncated, info)
    rng = np.random.default_rng(0)
    action = _legal_learner_action(env, obs, rng)
    obs2, reward, terminated, truncated, info2 = env.step(action)
    assert isinstance(obs2, dict)
    assert set(obs2) == {"observation", "action_mask"}
    assert isinstance(reward, float)
    assert isinstance(terminated, bool)
    assert isinstance(truncated, bool)
    assert truncated is False
    assert isinstance(info2, dict)


def test_episode_completes():
    """A full episode vs the default random opponent runs to terminated=True."""
    env = PuertoRicoSingle({"num_players": 4, "seed": 7})
    rng = np.random.default_rng(11)
    obs, _ = env.reset(seed=7)

    steps = 0
    terminated = False
    while not terminated:
        # The learner only ever sees states where it is to move => >=1 legal.
        legal = _legal_ids(obs["action_mask"])
        assert legal.size >= 1
        action = int(rng.choice(legal))
        obs, reward, terminated, truncated, _ = env.step(action)
        assert truncated is False
        steps += 1
        assert steps < 100_000, "episode did not terminate within step bound"

    assert terminated is True
    assert env._aec.game.is_terminal
    # Final reward is the learner's engine return (default "rank" mode).
    expected = float(env._aec.game.returns()[env.learner_seat])
    assert reward == pytest.approx(expected)


def test_terminal_reward_honors_reward_mode():
    """The configured reward_mode drives the terminal reward (not always rank).

    With reward_mode="win" the learner's final reward must equal
    terminal_rewards(state, "win")[learner_seat] — 1.0 for a sole winner, a
    tie-share otherwise, 0.0 for a loser — rather than the default rank payoff.
    """
    env = PuertoRicoSingle({"num_players": 4, "seed": 7, "reward_mode": "win"})
    rng = np.random.default_rng(11)
    obs, _ = env.reset(seed=7)

    terminated = False
    reward = None
    while not terminated:
        action = int(rng.choice(_legal_ids(obs["action_mask"])))
        obs, reward, terminated, _t, _ = env.step(action)

    assert terminated is True
    expected_win = terminal_rewards(env._aec.game.state, "win")[env.learner_seat]
    assert reward == pytest.approx(float(expected_win))
    # And it must be a "win"-mode value (in {0.0, tie-shares, 1.0}), distinct in
    # general from the rank payoff that the buggy code returned.
    assert reward in (0.0, 1.0) or 0.0 < reward < 1.0


def test_opponent_called():
    """Spy opponent is invoked only for non-learner turns and returns legal ids."""
    calls: list[dict] = []

    base_rng = np.random.default_rng(5)

    def spy_policy(obs: dict) -> int:
        # The spy must itself only ever see opponent turns (the wrapper never
        # asks the opponent to act on the learner's behalf). Record the call and
        # return a legal action.
        legal = _legal_ids(obs["action_mask"])
        assert legal.size >= 1, "opponent handed a state with no legal action"
        chosen = int(base_rng.choice(legal))
        assert chosen in legal, "opponent must return a legal action id"
        calls.append({"mask": np.asarray(obs["action_mask"]).copy(), "action": chosen})
        return chosen

    env = PuertoRicoSingle({"num_players": 4, "seed": 9}, opponent_policy=spy_policy)
    rng = np.random.default_rng(3)
    obs, _ = env.reset(seed=9)

    learner_turns = 0
    terminated = False
    while not terminated:
        # Sanity: at every learner decision point the seat to move is the learner.
        assert env._current_agent() == env.learner_agent
        learner_turns += 1
        action = int(rng.choice(_legal_ids(obs["action_mask"])))
        obs, _r, terminated, _t, _ = env.step(action)

    # Opponent was invoked at least once and every returned action was legal.
    assert len(calls) > 0
    assert learner_turns > 0
    for c in calls:
        assert c["mask"][c["action"]] != 0


def test_determinism():
    """Same seed (env + default opponent rng) -> identical obs/reward sequence."""

    def run():
        env = PuertoRicoSingle({"num_players": 4, "seed": 42})
        act_rng = np.random.default_rng(99)
        obs, _ = env.reset(seed=42)
        obs_hashes: list[bytes] = [obs["observation"].tobytes()]
        rewards: list[float] = []
        terminated = False
        while not terminated:
            action = int(act_rng.choice(_legal_ids(obs["action_mask"])))
            obs, reward, terminated, _t, _ = env.step(action)
            obs_hashes.append(obs["observation"].tobytes())
            rewards.append(reward)
        return obs_hashes, rewards

    h1, r1 = run()
    h2, r2 = run()
    assert h1 == h2
    assert r1 == r2
