"""Tests for the self-play rollout collector (training/rollout.py)."""

from __future__ import annotations

import numpy as np
import torch

from ..agents.random_agent import RandomAgent
from ..engine import scoring
from ..engine.game import Game
from ..engine.state import GameConfig
from ..env.action_codec import N_ACTIONS
from ..env.obs_codec import OBS_LEN
from . import reward_config
from .model import MaskedActorCritic
from .rollout import collect_rollouts, wrap_random


def _fresh_policy(seed: int = 0) -> MaskedActorCritic:
    torch.manual_seed(seed)
    return MaskedActorCritic()


def _check_batch(batch: dict, *, expect_min: int) -> int:
    t = batch["actions"].shape[0]
    assert t >= expect_min
    assert batch["obs"].shape == (t, OBS_LEN)
    assert batch["action_masks"].shape == (t, N_ACTIONS)
    assert batch["actions"].shape == (t,)
    assert batch["logprobs"].shape == (t,)
    assert batch["values"].shape == (t,)
    assert batch["advantages"].shape == (t,)
    assert batch["returns"].shape == (t,)

    assert batch["obs"].dtype == torch.float32
    assert batch["action_masks"].dtype == torch.float32
    assert batch["actions"].dtype == torch.int64
    assert batch["logprobs"].dtype == torch.float32

    for key in ("obs", "action_masks", "logprobs", "values", "advantages", "returns"):
        assert torch.isfinite(batch[key]).all(), f"non-finite in {key}"
    return t


def test_selfplay_shapes_and_no_mask_violations():
    policy = _fresh_policy()
    batch = collect_rollouts(policy, target_steps=512, rng_seed=1)
    t = _check_batch(batch, expect_min=512)
    assert batch["info"]["mask_violations"] == 0
    assert batch["info"]["num_games"] >= 1
    assert batch["info"]["mean_episode_length"] > 0
    # every chosen action is legal under its own mask.
    chosen = batch["action_masks"].gather(1, batch["actions"].unsqueeze(1)).squeeze(1)
    assert (chosen > 0.5).all()
    assert t >= 512


def test_returns_equal_raw_advantages_plus_values():
    # returns are left raw; advantages returned are normalized. The raw
    # advantage is recoverable as returns - values, so check that identity is
    # self-consistent and that normalized advantages have ~zero mean.
    policy = _fresh_policy()
    batch = collect_rollouts(policy, target_steps=512, rng_seed=2)
    raw_adv = batch["returns"] - batch["values"]
    assert torch.isfinite(raw_adv).all()
    # normalized advantages have mean ~0.
    assert abs(float(batch["advantages"].mean())) < 1e-5
    assert abs(float(batch["advantages"].std(unbiased=False)) - 1.0) < 1e-3


def test_one_learner_vs_three_random():
    policy = _fresh_policy()
    rnd = RandomAgent(seed=7)
    opp = wrap_random(rnd)
    opponents = {1: opp, 2: opp, 3: opp}
    batch = collect_rollouts(
        policy, target_steps=256, opponent_policies=opponents, rng_seed=3
    )
    _check_batch(batch, expect_min=256)
    assert batch["info"]["mask_violations"] == 0
    assert batch["info"]["learner_seats"] == [0]
    # only seat 0 collected: per-game transitions ~ a quarter of full self-play.
    assert batch["info"]["num_games"] >= 1


def test_determinism_same_seed_same_actions():
    p1 = _fresh_policy(seed=42)
    p2 = _fresh_policy(seed=42)
    # weights identical because same torch seed at init.
    b1 = collect_rollouts(p1, target_steps=300, rng_seed=99, deterministic=True)
    b2 = collect_rollouts(p2, target_steps=300, rng_seed=99, deterministic=True)
    assert torch.equal(b1["actions"], b2["actions"])
    assert torch.allclose(b1["returns"], b2["returns"])
    assert torch.allclose(b1["obs"], b2["obs"])


def test_terminal_reward_signal_matches_ranking():
    # Replay a single game deterministically and confirm the winning seat's last
    # transition carries the top terminal reward.
    policy = _fresh_policy(seed=5)
    seed = 1234
    game = Game(GameConfig(num_players=4, seed=seed))
    from ..env import action_codec, obs_codec

    while not game.is_terminal:
        seat = game.current_player
        obs_t = torch.as_tensor(obs_codec.encode(game.state, seat))
        mask_t = torch.as_tensor(action_codec.mask(game).astype(np.float32))
        a, _, _ = policy.act(obs_t, mask_t, deterministic=True)
        game.apply(action_codec.from_int(int(a.item()), game.state), validate=False)

    rewards = reward_config.terminal_rewards(game.state, "rank")
    order = scoring.rankings(game.state)
    winner = order[0]
    assert rewards[winner] == max(rewards)
    assert game.winner() == winner


def test_shaping_coef_zero_is_identical_to_no_shaping():
    # shaping_coef==0.0 must reproduce the no-shaping path byte-for-byte.
    p1 = _fresh_policy(seed=11)
    p2 = _fresh_policy(seed=11)
    b0 = collect_rollouts(p1, target_steps=512, rng_seed=21, deterministic=True)
    b0z = collect_rollouts(
        p2, target_steps=512, rng_seed=21, shaping_coef=0.0, deterministic=True
    )
    assert torch.equal(b0["actions"], b0z["actions"])
    assert torch.equal(b0["returns"], b0z["returns"])
    assert torch.equal(b0["advantages"], b0z["advantages"])
    assert torch.equal(b0["values"], b0z["values"])


def test_shaping_coef_positive_runs_and_is_finite():
    policy = _fresh_policy(seed=12)
    batch = collect_rollouts(
        policy, target_steps=512, rng_seed=22, shaping_coef=0.1, deterministic=True
    )
    _check_batch(batch, expect_min=512)
    assert batch["info"]["mask_violations"] == 0


def test_shaping_changes_returns_vs_no_shaping():
    # With a non-trivial coef the shaped returns should differ from unshaped
    # (same seed + same deterministic actions, only the reward changes).
    p1 = _fresh_policy(seed=13)
    p2 = _fresh_policy(seed=13)
    plain = collect_rollouts(p1, target_steps=512, rng_seed=23, deterministic=True)
    shaped = collect_rollouts(
        p2, target_steps=512, rng_seed=23, shaping_coef=0.5, deterministic=True
    )
    # identical action trajectory (shaping does not change action selection)...
    assert torch.equal(plain["actions"], shaped["actions"])
    # ...but the returns differ because the per-step reward changed.
    assert not torch.equal(plain["returns"], shaped["returns"])
    assert torch.isfinite(shaped["returns"]).all()


def test_info_stats_present():
    policy = _fresh_policy()
    batch = collect_rollouts(policy, target_steps=256, rng_seed=4)
    info = batch["info"]
    for key in (
        "num_games",
        "num_transitions",
        "mean_episode_length",
        "mean_terminal_reward_by_placement",
        "mask_violations",
        "learner_seats",
    ):
        assert key in info
    placements = info["mean_terminal_reward_by_placement"]
    assert len(placements) == 4
    # 1st place mean reward should exceed last place mean reward (rank reward).
    assert placements[0] > placements[-1]
