"""PPO self-play trainer (pure PyTorch, no RLlib) — design/05.

This is the core training loop that turns the rollout collector
(:mod:`puerto_rico.training.rollout`), the masked actor-critic
(:mod:`puerto_rico.training.model`), and the self-play opponent pool
(:mod:`puerto_rico.training.opponent_pool`) into a trained policy checkpoint.

What ``train(cfg)`` does each iteration
---------------------------------------
1. (Optionally) sample an opponent assignment from the pool for some
   non-learner seats; by default it runs **full self-play**
   (``opponent_policies=None`` -> every seat is a learner and collected). With
   probability ``cfg.self_play_prob`` an iteration instead mixes 1-3 pool /
   baseline opponents into the table, leaving the rest as learner seats. Full
   self-play is the documented, correct default and still learns; pool mixing
   adds robustness against strategy cycling.
2. ``collect_rollouts`` plays full games and returns a flat batch of learner
   transitions with GAE-Lambda advantages (batch-normalized) and raw returns.
3. ``ppo_update`` runs the clipped-surrogate PPO update over ``update_epochs``
   passes of shuffled minibatches.
4. Entropy coefficient is annealed (optional linear decay to a floor).
5. Every ``snapshot_interval`` iterations the current weights are frozen into
   the opponent pool and a checkpoint is written.
6. Every ``eval_interval`` iterations the deterministic policy is benchmarked
   vs 3 RandomAgents and vs 3 HeuristicAgents (win rate, seat-rotated).

Checkpoint artifact schema (what agents-08 / the UI loads WITHOUT this trainer)
------------------------------------------------------------------------------
``torch.save`` of a plain dict::

    {
        "format":      "puerto_rico.rl_policy",   # artifact tag
        "version":     1,                          # schema version
        "codec":       {"obs_codec": int, "action_codec": int},
        "model_state": OrderedDict,                # MaskedActorCritic.state_dict()
        "obs_dim":     int,                        # == env.obs_codec.OBS_LEN
        "n_actions":   int,                        # == env.action_codec.N_ACTIONS
        "hidden":      list[int],                  # torso layer sizes
        "config":      dict,                       # PPOConfig as a dict
        "iteration":   int,                        # producing iteration (or "final")
    }

To rebuild for inference (no trainer import needed)::

    ckpt = torch.load(path, map_location="cpu", weights_only=False)
    net  = MaskedActorCritic(ckpt["obs_dim"], ckpt["n_actions"],
                             tuple(ckpt["hidden"]))
    net.load_state_dict(ckpt["model_state"])
    net.eval()
"""

from __future__ import annotations

import argparse
import dataclasses
import os
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import torch
from torch import nn

from ..agents.heuristic_agent import HeuristicAgent
from ..agents.random_agent import RandomAgent
from ..engine.game import Game
from ..engine.state import GameConfig
from ..env import action_codec
from ..env.action_codec import N_ACTIONS
from ..env.obs_codec import OBS_LEN
from .inference import policy_act_id
from .model import MaskedActorCritic
from .opponent_pool import OpponentPool
from .rollout import collect_rollouts, wrap_heuristic, wrap_random

# Codec version tags baked into the artifact so a loader can detect a mismatch
# between the encoding it expects and the one the policy was trained on.
OBS_CODEC_VERSION = 1
ACTION_CODEC_VERSION = 1
ARTIFACT_FORMAT = "puerto_rico.rl_policy"
ARTIFACT_VERSION = 1


def limit_cpu_usage(leave_free: int = 2) -> int:
    """Cap PyTorch's CPU thread pool so long training runs keep the machine usable.

    Uses at most ``cpu_count - leave_free`` threads (at least 1). Override with the
    ``PR_TRAIN_THREADS`` env var to set an explicit thread count. Call this from a
    training entry point BEFORE heavy work; it is a no-op for inference/tests.
    Tip: also run training niced, e.g. ``nice -n 10 uv run python -m ...``.
    """
    env = os.environ.get("PR_TRAIN_THREADS")
    if env:
        threads = max(1, int(env))
    else:
        cores = os.cpu_count() or 4
        threads = max(1, cores - max(0, leave_free))
    torch.set_num_threads(threads)
    return threads


# --------------------------------------------------------------------------- #
# config                                                                       #
# --------------------------------------------------------------------------- #


@dataclass
class PPOConfig:
    """Hyperparameters for the PPO self-play trainer (everything overridable)."""

    # game / env
    num_players: int = 4
    reward_mode: str = "rank"

    # training schedule
    total_iterations: int = 200
    rollout_steps: int = 4096  # min learner transitions collected per iteration

    # PPO core
    gamma: float = 0.999  # long episodes -> high discount (design/05)
    gae_lambda: float = 0.95
    clip: float = 0.2
    lr: float = 3e-4
    value_coef: float = 0.5
    max_grad_norm: float = 0.5
    update_epochs: int = 4
    minibatch_size: int = 512
    clip_value_loss: bool = True

    # entropy with optional linear decay to a floor
    entropy_coef: float = 0.01
    entropy_coef_final: float = 0.0
    entropy_anneal_iters: int = 0  # 0 -> no decay (constant entropy_coef)

    # model
    hidden: tuple[int, ...] = (256, 256)

    # self-play / opponent pool
    self_play_prob: float = 0.5
    # Per-seat probability that a *mixed* non-learner seat is the LIVE policy
    # ("self") rather than a frozen snapshot / baseline (heuristic|random). When
    # None it defaults to ``self_play_prob`` (legacy coupling). Set it LOWER than
    # ``self_play_prob`` to mix the pool often (high self_play_prob) while making
    # those mixed seats more often strong baselines / frozen snapshots — i.e.
    # heavier exposure to strong opponents without starving the learner of seats.
    pool_self_play_prob: float | None = None
    snapshot_interval: int = 20  # iters between freezing a snapshot + checkpoint
    max_snapshots: int = 10

    # evaluation
    eval_interval: int = 20
    eval_games: int = 100

    # misc
    seed: int = 0
    out_dir: str = "runs/ppo"
    device: str = "cpu"

    def as_dict(self) -> dict:
        """JSON/pickle-friendly dict (tuples become lists)."""
        d = dataclasses.asdict(self)
        d["hidden"] = list(self.hidden)
        return d


# --------------------------------------------------------------------------- #
# entropy schedule                                                             #
# --------------------------------------------------------------------------- #


def entropy_coef_at(cfg: PPOConfig, iteration: int) -> float:
    """Linearly anneal ``entropy_coef`` -> ``entropy_coef_final`` by ``anneal_iters``.

    ``iteration`` is 0-based. With ``entropy_anneal_iters <= 0`` the coefficient
    is constant. The result is clamped to the floor for any later iteration.
    """
    if cfg.entropy_anneal_iters <= 0:
        return cfg.entropy_coef
    frac = min(1.0, max(0.0, iteration / cfg.entropy_anneal_iters))
    return cfg.entropy_coef + frac * (cfg.entropy_coef_final - cfg.entropy_coef)


# --------------------------------------------------------------------------- #
# PPO update                                                                   #
# --------------------------------------------------------------------------- #


def ppo_update(
    policy: MaskedActorCritic,
    optimizer: torch.optim.Optimizer,
    batch: dict,
    cfg: PPOConfig,
    *,
    entropy_coef: float | None = None,
) -> dict:
    """Run a standard clipped-surrogate PPO update over ``batch``.

    For ``cfg.update_epochs`` passes, shuffle the transition indices and iterate
    ``cfg.minibatch_size`` minibatches. For each minibatch recompute
    logprob/entropy/value via :meth:`MaskedActorCritic.evaluate_actions`,
    form the probability ratio against the stored (old) logprobs, and minimize::

        L = policy_loss + value_coef * value_loss - entropy_coef * entropy

    where ``policy_loss`` is the clipped surrogate, ``value_loss`` is (optionally
    clipped) MSE to the raw returns, computed with the batch's already-normalized
    ``advantages``. Gradients are clipped to ``cfg.max_grad_norm``.

    Returns averaged metrics: ``policy_loss``, ``value_loss``, ``entropy``,
    ``approx_kl``, ``clip_frac``, ``mask_violations`` (always 0 here — actions
    came from the masked rollout).
    """
    ec = cfg.entropy_coef if entropy_coef is None else float(entropy_coef)
    device = next(policy.parameters()).device

    obs = batch["obs"].to(device)
    masks = batch["action_masks"].to(device)
    actions = batch["actions"].to(device)
    old_logprobs = batch["logprobs"].to(device)
    advantages = batch["advantages"].to(device)
    returns = batch["returns"].to(device)
    old_values = batch["values"].to(device)

    n = actions.shape[0]
    mb = min(cfg.minibatch_size, n)

    metrics = {
        "policy_loss": 0.0,
        "value_loss": 0.0,
        "entropy": 0.0,
        "approx_kl": 0.0,
        "clip_frac": 0.0,
    }
    n_updates = 0

    for _ in range(cfg.update_epochs):
        perm = torch.randperm(n, device=device)
        for start in range(0, n, mb):
            idx = perm[start : start + mb]
            mb_obs = obs[idx]
            mb_masks = masks[idx]
            mb_actions = actions[idx]
            mb_old_logp = old_logprobs[idx]
            mb_adv = advantages[idx]
            mb_ret = returns[idx]
            mb_old_val = old_values[idx]

            new_logp, entropy, value = policy.evaluate_actions(
                mb_obs, mb_masks, mb_actions
            )

            log_ratio = new_logp - mb_old_logp
            ratio = torch.exp(log_ratio)

            # clipped surrogate policy loss
            surr1 = ratio * mb_adv
            surr2 = torch.clamp(ratio, 1.0 - cfg.clip, 1.0 + cfg.clip) * mb_adv
            policy_loss = -torch.min(surr1, surr2).mean()

            # value loss (optionally clipped, PPO-style)
            if cfg.clip_value_loss:
                v_clipped = mb_old_val + torch.clamp(
                    value - mb_old_val, -cfg.clip, cfg.clip
                )
                v_loss_unclipped = (value - mb_ret) ** 2
                v_loss_clipped = (v_clipped - mb_ret) ** 2
                value_loss = 0.5 * torch.max(v_loss_unclipped, v_loss_clipped).mean()
            else:
                value_loss = 0.5 * ((value - mb_ret) ** 2).mean()

            entropy_mean = entropy.mean()
            loss = policy_loss + cfg.value_coef * value_loss - ec * entropy_mean

            optimizer.zero_grad(set_to_none=True)
            loss.backward()
            nn.utils.clip_grad_norm_(policy.parameters(), cfg.max_grad_norm)
            optimizer.step()

            with torch.no_grad():
                approx_kl = (-log_ratio).mean()  # k2 estimator: E[-log ratio]
                clip_frac = (
                    (torch.abs(ratio - 1.0) > cfg.clip).float().mean()
                )

            metrics["policy_loss"] += float(policy_loss.item())
            metrics["value_loss"] += float(value_loss.item())
            metrics["entropy"] += float(entropy_mean.item())
            metrics["approx_kl"] += float(approx_kl.item())
            metrics["clip_frac"] += float(clip_frac.item())
            n_updates += 1

    for k in metrics:
        metrics[k] /= max(1, n_updates)
    metrics["mask_violations"] = 0
    return metrics


# --------------------------------------------------------------------------- #
# evaluation                                                                   #
# --------------------------------------------------------------------------- #


def _policy_action(policy: MaskedActorCritic, game: Game, device: str) -> int:
    """Deterministic (argmax) legal action id for the current seat.

    Thin wrapper over the shared
    :func:`~puerto_rico.training.inference.policy_act_id` (deterministic).
    """
    return policy_act_id(policy, game, device=device, deterministic=True)


def evaluate_vs(
    policy: MaskedActorCritic,
    opponent_factory,
    num_games: int,
    num_players: int = 4,
    seed: int = 0,
    device: str = "cpu",
) -> float:
    """Win rate of the deterministic ``policy`` vs opponents, driving the engine.

    The learner occupies one seat (rotated across games so it is not
    governor/first-player biased) and ``opponent_factory()`` fills each of the
    other seats with a fresh ``opp(game) -> int`` callable (e.g. a wrapped
    RandomAgent / HeuristicAgent). Returns the fraction of games the learner
    wins outright (ties count as a loss for a conservative benchmark).
    """
    from ..engine import scoring

    policy = policy.to(device)
    policy.eval()
    wins = 0
    for g in range(num_games):
        learner_seat = g % num_players
        opp_fns = {
            s: opponent_factory()
            for s in range(num_players)
            if s != learner_seat
        }
        game = Game(
            GameConfig(num_players=num_players, seed=seed * 1_000_003 + g)
        )
        while not game.is_terminal:
            seat = game.current_player
            if seat == learner_seat:
                action_id = _policy_action(policy, game, device)
            else:
                action_id = int(opp_fns[seat](game))
            action = action_codec.from_int(action_id, game.state)
            game.apply(action, validate=False)
        winner = scoring.rankings(game.state)[0]
        if winner == learner_seat:
            wins += 1
    return wins / max(1, num_games)


def _random_factory(base_seed: int):
    counter = {"n": 0}

    def make():
        counter["n"] += 1
        return wrap_random(RandomAgent(seed=base_seed + counter["n"]))

    return make


def _heuristic_factory(base_seed: int):
    counter = {"n": 0}

    def make():
        counter["n"] += 1
        return wrap_heuristic(HeuristicAgent(seed=base_seed + counter["n"]))

    return make


# --------------------------------------------------------------------------- #
# checkpointing                                                                #
# --------------------------------------------------------------------------- #


def _build_artifact(policy: MaskedActorCritic, cfg: PPOConfig, iteration) -> dict:
    return {
        "format": ARTIFACT_FORMAT,
        "version": ARTIFACT_VERSION,
        "codec": {
            "obs_codec": OBS_CODEC_VERSION,
            "action_codec": ACTION_CODEC_VERSION,
        },
        "model_state": {
            k: v.detach().cpu().clone() for k, v in policy.state_dict().items()
        },
        "obs_dim": OBS_LEN,
        "n_actions": N_ACTIONS,
        "hidden": list(cfg.hidden),
        "config": cfg.as_dict(),
        "iteration": iteration,
    }


def save_checkpoint(
    policy: MaskedActorCritic, cfg: PPOConfig, iteration, path: Path
) -> Path:
    """Write the lightweight inference artifact to ``path`` via ``torch.save``."""
    path.parent.mkdir(parents=True, exist_ok=True)
    torch.save(_build_artifact(policy, cfg, iteration), path)
    return path


# --------------------------------------------------------------------------- #
# training loop                                                                #
# --------------------------------------------------------------------------- #


def _opponent_assignment(
    cfg: PPOConfig,
    pool: OpponentPool,
    policy: MaskedActorCritic,
    rng: np.random.Generator,
) -> dict | None:
    """Decide this iteration's opponent seats.

    Default is full self-play (``None``). With probability ``self_play_prob`` we
    instead reserve 1-3 non-learner seats and fill them from the pool (self /
    snapshot / baseline), keeping at least one learner seat.
    """
    if cfg.self_play_prob <= 0.0 or rng.random() >= cfg.self_play_prob:
        return None
    max_opp = max(1, cfg.num_players - 1)
    num_opp = int(rng.integers(1, max_opp + 1))  # 1..num_players-1
    # learner takes the low seats; opponents fill the top ones.
    opp_seats = list(range(cfg.num_players - num_opp, cfg.num_players))
    fns = pool.sample_opponents(
        num_opp, policy, self_play_prob=cfg.pool_self_play_prob, rng=rng
    )
    return dict(zip(opp_seats, fns))


def train(cfg: PPOConfig) -> str:
    """Run the PPO self-play loop and return the path to ``final.pt``."""
    torch.manual_seed(cfg.seed)
    # Seeding is explicit: the rollout/opponent RNGs are seeded ``np.random.Generator``
    # instances (no global ``np.random.*`` is used in the training path), so the
    # legacy global ``np.random.seed`` is intentionally omitted.
    rng = np.random.default_rng(cfg.seed)

    out_dir = Path(cfg.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    policy = MaskedActorCritic(OBS_LEN, N_ACTIONS, tuple(cfg.hidden)).to(cfg.device)
    optimizer = torch.optim.Adam(policy.parameters(), lr=cfg.lr)
    pool = OpponentPool(
        max_snapshots=cfg.max_snapshots,
        self_play_prob=(
            cfg.self_play_prob
            if cfg.pool_self_play_prob is None
            else cfg.pool_self_play_prob
        ),
    )

    final_path = out_dir / "final.pt"

    for it in range(cfg.total_iterations):
        t0 = time.time()
        opp = _opponent_assignment(cfg, pool, policy, rng)

        policy.train()
        batch = collect_rollouts(
            policy,
            num_players=cfg.num_players,
            target_steps=cfg.rollout_steps,
            opponent_policies=opp,
            gamma=cfg.gamma,
            gae_lambda=cfg.gae_lambda,
            reward_mode=cfg.reward_mode,
            device=cfg.device,
            rng_seed=cfg.seed + it,
        )

        ec = entropy_coef_at(cfg, it)
        metrics = ppo_update(policy, optimizer, batch, cfg, entropy_coef=ec)

        info = batch["info"]
        # snapshot + checkpoint
        if (it + 1) % cfg.snapshot_interval == 0:
            pool.add_snapshot(policy.state_dict(), it)
            save_checkpoint(policy, cfg, it, out_dir / f"checkpoint_{it}.pt")

        # eval
        wr_random = wr_heur = None
        if cfg.eval_interval > 0 and (it + 1) % cfg.eval_interval == 0:
            wr_random = evaluate_vs(
                policy,
                _random_factory(cfg.seed + 10_000 + it),
                cfg.eval_games,
                num_players=cfg.num_players,
                seed=cfg.seed + 20_000 + it,
                device=cfg.device,
            )
            wr_heur = evaluate_vs(
                policy,
                _heuristic_factory(cfg.seed + 30_000 + it),
                cfg.eval_games,
                num_players=cfg.num_players,
                seed=cfg.seed + 40_000 + it,
                device=cfg.device,
            )

        dt = time.time() - t0
        reward_by_place = info.get("mean_terminal_reward_by_placement", [])
        top_reward = reward_by_place[0] if reward_by_place else float("nan")
        wr_r = f"{wr_random:.2f}" if wr_random is not None else "--"
        wr_h = f"{wr_heur:.2f}" if wr_heur is not None else "--"
        print(
            f"iter {it:4d} | T={info['num_transitions']:5d} "
            f"games={info['num_games']:3d} len={info['mean_episode_length']:.0f} "
            f"r1st={top_reward:+.2f} | "
            f"pi={metrics['policy_loss']:+.3f} v={metrics['value_loss']:.3f} "
            f"H={metrics['entropy']:.3f} kl={metrics['approx_kl']:.4f} "
            f"clip={metrics['clip_frac']:.2f} ec={ec:.4f} | "
            f"wr_rand={wr_r} wr_heur={wr_h} mv={info['mask_violations']} "
            f"({dt:.1f}s)",
            flush=True,
        )

    save_checkpoint(policy, cfg, "final", final_path)
    return str(final_path)


# --------------------------------------------------------------------------- #
# CLI                                                                          #
# --------------------------------------------------------------------------- #


def _parse_args(argv=None) -> PPOConfig:
    p = argparse.ArgumentParser(description="PPO self-play trainer (PyTorch)")
    p.add_argument("--total-iterations", type=int, default=PPOConfig.total_iterations)
    p.add_argument("--rollout-steps", type=int, default=PPOConfig.rollout_steps)
    p.add_argument("--lr", type=float, default=PPOConfig.lr)
    p.add_argument("--gamma", type=float, default=PPOConfig.gamma)
    p.add_argument("--minibatch-size", type=int, default=PPOConfig.minibatch_size)
    p.add_argument("--update-epochs", type=int, default=PPOConfig.update_epochs)
    p.add_argument("--entropy-coef", type=float, default=PPOConfig.entropy_coef)
    p.add_argument("--self-play-prob", type=float, default=PPOConfig.self_play_prob)
    p.add_argument("--snapshot-interval", type=int, default=PPOConfig.snapshot_interval)
    p.add_argument("--eval-interval", type=int, default=PPOConfig.eval_interval)
    p.add_argument("--eval-games", type=int, default=PPOConfig.eval_games)
    p.add_argument("--num-players", type=int, default=PPOConfig.num_players)
    p.add_argument("--reward-mode", type=str, default=PPOConfig.reward_mode)
    p.add_argument("--seed", type=int, default=PPOConfig.seed)
    p.add_argument("--out-dir", type=str, default=PPOConfig.out_dir)
    p.add_argument("--device", type=str, default=PPOConfig.device)
    a = p.parse_args(argv)
    return PPOConfig(
        total_iterations=a.total_iterations,
        rollout_steps=a.rollout_steps,
        lr=a.lr,
        gamma=a.gamma,
        minibatch_size=a.minibatch_size,
        update_epochs=a.update_epochs,
        entropy_coef=a.entropy_coef,
        self_play_prob=a.self_play_prob,
        snapshot_interval=a.snapshot_interval,
        eval_interval=a.eval_interval,
        eval_games=a.eval_games,
        num_players=a.num_players,
        reward_mode=a.reward_mode,
        seed=a.seed,
        out_dir=a.out_dir,
        device=a.device,
    )


if __name__ == "__main__":
    cfg = _parse_args()
    path = train(cfg)
    print(f"final checkpoint: {path}")
