"""Train a STRONG Puerto Rico RL policy and select the best checkpoint.

This is the "production" training run (vs the cheap ``smoke_train.py``). It trains
a policy on the **current** action space (``N_ACTIONS=92`` with explicit captain
ship + windrose decisions) long enough to play at a high level, then performs
**best-checkpoint selection** over every saved snapshot and promotes the winner to
the stable release path ``runs/release/final.pt`` (the path the UI and the fast
benchmark tests load).

Pipeline
--------
1. Train with a strong :class:`~puerto_rico.training.ppo.PPOConfig` (long run, rank
   reward, entropy annealed broad -> decisive, self-play mixed with frozen
   snapshots + heuristic/random baselines so the learner sees the heuristic during
   training). Checkpoints are written every ``snapshot_interval`` iters plus a
   ``final.pt`` at the end.
2. Evaluate EACH saved checkpoint (``checkpoint_*.pt`` + ``final.pt``) by loading
   it as an :class:`~puerto_rico.agents.rl_policy.RLPolicy` (deterministic) and
   running ``benchmark_vs_heuristic`` over a solid seat-rotated sample. Print the
   per-checkpoint learning curve.
3. Pick the checkpoint with the highest win rate vs the heuristic (tie-break: vs
   random) and copy it to ``runs/release/final.pt`` (overwriting the old, now
   dimension-incompatible artifact).
4. Run a rigorous final benchmark of the released policy: >=504 seat-rotated games
   vs 3 HeuristicAgents and vs 3 RandomAgents, plus an Arena of
   {RL, Heuristic, Random, Random} with the metrics + Elo table.

Run::

    uv run python -m puerto_rico.training.train_strong
"""

from __future__ import annotations

import shutil
import time
from pathlib import Path

from .ppo import PPOConfig, limit_cpu_usage, train
from .train_utils import final_benchmark, select_best

# --------------------------------------------------------------------------- #
# paths / knobs                                                               #
# --------------------------------------------------------------------------- #

OUT_DIR = Path("runs/strong")
RELEASE_DIR = Path("runs/release")
RELEASE_PT = RELEASE_DIR / "final.pt"

# Per-checkpoint selection sample (seat-rotated; multiple of 4).
SELECT_GAMES_HEURISTIC = 240
SELECT_GAMES_RANDOM = 120

# Final rigorous benchmark (>= 504, multiple of 4 and of 12 for clean rotation).
FINAL_GAMES = 504
ARENA_GAMES = 504


def make_config() -> PPOConfig:
    """Strong training hyperparameters (see module docstring for rationale).

    Calibrated at ~0.85s/iter (rollout_steps=4096, hidden=(256,256)) on this
    machine, so ~1200 iters is a ~17 minute wall-clock budget. In-loop eval every
    100 iters adds only ~7.5s each (negligible amortized).
    """
    total = 1200
    return PPOConfig(
        num_players=4,
        reward_mode="rank",
        total_iterations=total,
        rollout_steps=4096,
        # PPO core
        lr=2.5e-4,
        gamma=0.999,
        gae_lambda=0.95,
        clip=0.2,
        value_coef=0.5,
        max_grad_norm=0.5,
        update_epochs=4,
        minibatch_size=512,
        clip_value_loss=True,
        # Entropy: broad early exploration -> decisive late policy.
        entropy_coef=0.02,
        entropy_coef_final=0.0,
        entropy_anneal_iters=int(total * 0.8),  # anneal over ~80% of training
        # Model
        hidden=(256, 256),
        # Self-play mixed with frozen snapshots + heuristic/random baselines.
        # Higher self_play_prob -> the learner is more often exposed to pool /
        # baseline opponents (incl. the heuristic) during rollouts.
        self_play_prob=0.6,
        snapshot_interval=100,  # ~12 checkpoints over 1200 iters + final
        max_snapshots=16,
        # In-loop eval for the training curve (cheap, infrequent).
        eval_interval=100,
        eval_games=100,
        seed=0,
        out_dir=str(OUT_DIR),
        device="cpu",
    )


# --------------------------------------------------------------------------- #
# main                                                                         #
# --------------------------------------------------------------------------- #


def main() -> dict:
    threads = limit_cpu_usage()  # leave CPU headroom so the machine stays usable
    cfg = make_config()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 72)
    print(f"(CPU-considerate: torch limited to {threads} threads; run niced if desired)")
    print("STRONG PPO TRAINING (N_ACTIONS=92): beat the HeuristicAgent decisively")
    print("=" * 72)
    print(
        f"config: iters={cfg.total_iterations} rollout_steps={cfg.rollout_steps} "
        f"lr={cfg.lr} mb={cfg.minibatch_size} epochs={cfg.update_epochs} "
        f"hidden={cfg.hidden}"
    )
    print(
        f"        gamma={cfg.gamma} lambda={cfg.gae_lambda} clip={cfg.clip} "
        f"entropy={cfg.entropy_coef}->{cfg.entropy_coef_final} over "
        f"{cfg.entropy_anneal_iters} iters"
    )
    print(
        f"        self_play_prob={cfg.self_play_prob} "
        f"snapshot_interval={cfg.snapshot_interval} reward={cfg.reward_mode}"
    )
    print(f"out_dir: {OUT_DIR.resolve()}")
    print("-" * 72)

    t0 = time.time()
    final_path = train(cfg)
    train_secs = time.time() - t0
    print("-" * 72)
    print(f"training done in {train_secs / 60:.1f} min -> {final_path}")

    # Best-checkpoint selection.
    best_path, curve = select_best(
        OUT_DIR,
        select_games_heuristic=SELECT_GAMES_HEURISTIC,
        select_games_random=SELECT_GAMES_RANDOM,
    )

    # Promote the winner to the stable release path.
    RELEASE_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(best_path, RELEASE_PT)
    print(f"\npromoted {best_path} -> {RELEASE_PT.resolve()}")

    # Final rigorous benchmark of the released policy.
    final = final_benchmark(RELEASE_PT, final_games=FINAL_GAMES, arena_games=ARENA_GAMES)

    print("\n" + "=" * 72)
    print("DONE")
    print(f"  training time:          {train_secs / 60:.1f} min")
    print(f"  release checkpoint:     {RELEASE_PT.resolve()}")
    print(
        f"  final wr vs heuristic:  {final['wr_heur']:.3f}  "
        f"({FINAL_GAMES} games)"
    )
    print(
        f"  final wr vs random:     {final['wr_rand']:.3f}  "
        f"({FINAL_GAMES} games)"
    )
    decisive = final["wr_heur"] >= 0.40
    print(
        f"  decisively beats heuristic (>=0.40 in 4p general-sum): "
        f"{'YES' if decisive else 'NO'}"
    )
    print("=" * 72)

    return {"curve": curve, "best": best_path, "final": final, "train_secs": train_secs}


if __name__ == "__main__":
    main()
