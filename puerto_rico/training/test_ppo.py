"""Tests for the PyTorch PPO self-play trainer (training/ppo.py).

Kept FAST: tiny configs, few iterations, short rollouts.
"""

from __future__ import annotations

import torch

from ..env.action_codec import N_ACTIONS
from ..env.obs_codec import OBS_LEN
from .model import MaskedActorCritic
from .ppo import (
    ARTIFACT_FORMAT,
    PPOConfig,
    entropy_coef_at,
    evaluate_vs,
    ppo_update,
    shaping_coef_at,
    train,
)
from .ppo import _random_factory  # eval helper
from .rollout import collect_rollouts


def _fresh_policy(seed: int = 0) -> MaskedActorCritic:
    torch.manual_seed(seed)
    return MaskedActorCritic()


def _params_snapshot(policy):
    return [p.detach().clone() for p in policy.parameters()]


def test_ppo_update_runs():
    policy = _fresh_policy()
    cfg = PPOConfig(minibatch_size=128, update_epochs=2)
    optimizer = torch.optim.Adam(policy.parameters(), lr=cfg.lr)

    batch = collect_rollouts(policy, target_steps=512, rng_seed=1)
    before = _params_snapshot(policy)

    metrics = ppo_update(policy, optimizer, batch, cfg)

    # finite metrics
    for k in ("policy_loss", "value_loss", "entropy", "approx_kl", "clip_frac"):
        assert k in metrics
        v = metrics[k]
        assert v == v and abs(v) < 1e6, f"{k} not finite: {v}"
    assert metrics["mask_violations"] == 0

    # params changed
    after = _params_snapshot(policy)
    changed = any(not torch.allclose(b, a) for b, a in zip(before, after))
    assert changed, "ppo_update did not change any parameters"


def test_entropy_anneal():
    cfg = PPOConfig(entropy_coef=0.02, entropy_coef_final=0.0, entropy_anneal_iters=10)
    assert entropy_coef_at(cfg, 0) == 0.02
    assert entropy_coef_at(cfg, 10) == 0.0
    mid = entropy_coef_at(cfg, 5)
    assert 0.0 < mid < 0.02
    # no decay when anneal_iters == 0
    cfg2 = PPOConfig(entropy_coef=0.02, entropy_anneal_iters=0)
    assert entropy_coef_at(cfg2, 100) == 0.02


def test_shaping_anneal():
    cfg = PPOConfig(shaping_coef0=0.1, shaping_anneal_iters=10)
    assert shaping_coef_at(cfg, 0) == 0.1
    assert shaping_coef_at(cfg, 10) == 0.0
    assert shaping_coef_at(cfg, 20) == 0.0  # clamped to 0 past the horizon
    mid = shaping_coef_at(cfg, 5)
    assert 0.0 < mid < 0.1
    # no decay when anneal_iters == 0 -> constant coef0
    cfg2 = PPOConfig(shaping_coef0=0.1, shaping_anneal_iters=0)
    assert shaping_coef_at(cfg2, 100) == 0.1
    # default disables shaping entirely
    assert shaping_coef_at(PPOConfig(), 0) == 0.0


def test_train_smoke_with_shaping(tmp_path):
    cfg = PPOConfig(
        total_iterations=2,
        rollout_steps=512,
        minibatch_size=128,
        update_epochs=2,
        eval_interval=0,
        snapshot_interval=2,
        self_play_prob=0.0,
        shaping_coef0=0.1,
        shaping_anneal_iters=2,
        out_dir=str(tmp_path),
        seed=0,
    )
    final = train(cfg)
    assert final == str(tmp_path / "final.pt")
    assert (tmp_path / "final.pt").exists()


def test_evaluate_vs_runs():
    policy = _fresh_policy()
    wr = evaluate_vs(
        policy, _random_factory(123), num_games=6, num_players=4, seed=7
    )
    assert 0.0 <= wr <= 1.0


def _smoke_cfg(out_dir) -> PPOConfig:
    return PPOConfig(
        total_iterations=2,
        rollout_steps=512,
        minibatch_size=128,
        update_epochs=2,
        eval_interval=1,
        eval_games=20,
        snapshot_interval=1,
        self_play_prob=0.0,  # full self-play keeps the smoke test deterministic & fast
        out_dir=str(out_dir),
        seed=0,
    )


def test_train_smoke(tmp_path):
    cfg = _smoke_cfg(tmp_path)
    final = train(cfg)

    final_path = tmp_path / "final.pt"
    assert final == str(final_path)
    assert final_path.exists()

    ckpt = torch.load(final_path, map_location="cpu", weights_only=False)
    assert ckpt["format"] == ARTIFACT_FORMAT
    assert ckpt["obs_dim"] == OBS_LEN
    assert ckpt["n_actions"] == N_ACTIONS
    assert ckpt["hidden"] == list(cfg.hidden)
    assert "model_state" in ckpt
    assert "config" in ckpt
    assert ckpt["iteration"] == "final"
    # a per-snapshot checkpoint was also written (snapshot_interval=1)
    assert (tmp_path / "checkpoint_0.pt").exists()


def test_checkpoint_roundtrip(tmp_path):
    cfg = _smoke_cfg(tmp_path)
    train(cfg)
    ckpt = torch.load(tmp_path / "final.pt", map_location="cpu", weights_only=False)

    net = MaskedActorCritic(
        ckpt["obs_dim"], ckpt["n_actions"], tuple(ckpt["hidden"])
    )
    net.load_state_dict(ckpt["model_state"])
    net.eval()

    obs = torch.zeros(OBS_LEN)
    mask = torch.zeros(N_ACTIONS)
    mask[0] = 1.0
    mask[5] = 1.0
    action, logprob, value = net.act(obs, mask, deterministic=True)
    assert int(action.item()) in (0, 5)
    assert torch.isfinite(logprob)
    assert torch.isfinite(value)


def test_determinism(tmp_path):
    """Same seed -> same iter-1 update metrics (within tolerance)."""

    def run_one():
        torch.manual_seed(0)
        policy = MaskedActorCritic()  # deterministic init
        optimizer = torch.optim.Adam(policy.parameters(), lr=3e-4)
        cfg = PPOConfig(minibatch_size=128, update_epochs=2, seed=0)
        # re-seed so the sampling inside collect_rollouts is reproducible
        torch.manual_seed(0)
        batch = collect_rollouts(
            policy, target_steps=512, rng_seed=0, deterministic=False
        )
        torch.manual_seed(0)
        return ppo_update(policy, optimizer, batch, cfg)

    m1 = run_one()
    m2 = run_one()
    for k in ("policy_loss", "value_loss", "entropy"):
        assert abs(m1[k] - m2[k]) < 1e-4, f"{k} differs: {m1[k]} vs {m2[k]}"
