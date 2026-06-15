"""Real PPO smoke training run: train a policy that beats RandomAgents (task-10).

This is the manual, "actually train it" counterpart to the fast pytest in
``test_smoke_train.py``. It:

1. Builds a :class:`~puerto_rico.training.ppo.PPOConfig` sized to comfortably
   exceed an 80% win rate vs 3 ``RandomAgent``s within a few minutes of CPU wall
   clock (RandomAgent is extremely weak, so this is reachable in modest
   iterations).
2. Runs ``train(cfg)`` and writes the lightweight artifact to a **stable** path,
   ``runs/smoke/final.pt`` (NOT a temp dir — we keep this checkpoint so the fast
   test and the UI can load it).
3. Loads it back via :class:`~puerto_rico.agents.rl_policy.RLPolicy` (no trainer
   at serve time) and benchmarks it over seat-rotated games vs 3 RandomAgents and
   (for information) vs 3 HeuristicAgents.
4. Prints a clear final summary with the achieved win rates.

Design choices
--------------
* ``reward_mode="rank"`` — the documented multi-player reward (design/05).
* ``self_play_prob=0.5`` with snapshots — during rollouts the non-learner seats
  are a mix of the live policy, frozen snapshots, and the two baselines
  (random + heuristic). Because RandomAgent is one of the always-present
  baselines, the learner is **directly** exposed to (and optimized against) the
  exact opponent we benchmark, while self-play / snapshots keep it from
  collapsing to a single brittle line. This converges to a random-dominating
  policy faster than pure self-play.
* Entropy is annealed from 0.02 -> 0.0 over the run so early exploration is broad
  and late policy is decisive (helps the deterministic argmax benchmark).

Run::

    uv run python -m puerto_rico.training.smoke_train
"""

from __future__ import annotations

import time
from pathlib import Path

from ..agents.rl_policy import RLPolicy
from .evaluate import benchmark_vs_heuristic, benchmark_vs_random
from .ppo import PPOConfig, train

# Stable, kept location for the trained artifact.
OUT_DIR = Path("runs/smoke")
FINAL_PT = OUT_DIR / "final.pt"

# Benchmark sizes (seat-rotated). Multiples of 4 so every seat is covered evenly.
BENCH_GAMES_RANDOM = 240
BENCH_GAMES_HEURISTIC = 120
WIN_RATE_TARGET = 0.80


def make_config() -> PPOConfig:
    """The smoke-training hyperparameters (see module docstring for rationale)."""
    return PPOConfig(
        num_players=4,
        reward_mode="rank",
        # Schedule: many cheap iterations beat a few huge rollouts here.
        total_iterations=300,
        rollout_steps=2048,
        # PPO core
        lr=3e-4,
        gamma=0.999,
        gae_lambda=0.95,
        clip=0.2,
        update_epochs=4,
        minibatch_size=256,
        # Entropy: anneal broad -> decisive.
        entropy_coef=0.02,
        entropy_coef_final=0.0,
        entropy_anneal_iters=250,
        # Self-play mixed with baselines (random + heuristic) so we optimize
        # directly against the benchmark opponent.
        self_play_prob=0.5,
        snapshot_interval=25,
        max_snapshots=8,
        # In-loop eval just for the training curve (cheap, infrequent).
        eval_interval=50,
        eval_games=60,
        seed=0,
        out_dir=str(OUT_DIR),
        device="cpu",
    )


def main() -> float:
    """Train, checkpoint to ``runs/smoke/final.pt``, benchmark, and report.

    Returns the achieved win rate vs 3 RandomAgents.
    """
    from .ppo import limit_cpu_usage

    limit_cpu_usage()  # leave CPU headroom so the machine stays usable
    cfg = make_config()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 72)
    print("PPO SMOKE TRAINING (task-10): train a policy that beats RandomAgents")
    print("=" * 72)
    print(
        f"config: iters={cfg.total_iterations} rollout_steps={cfg.rollout_steps} "
        f"lr={cfg.lr} mb={cfg.minibatch_size} self_play_prob={cfg.self_play_prob} "
        f"reward={cfg.reward_mode}"
    )
    print(f"out_dir: {OUT_DIR.resolve()}")
    print("-" * 72)

    t0 = time.time()
    final_path = train(cfg)
    train_secs = time.time() - t0
    print("-" * 72)
    print(f"training done in {train_secs:.1f}s -> {final_path}")

    # Load via the lightweight inference path (no trainer import at serve time).
    policy = RLPolicy.from_checkpoint(final_path)

    print(f"benchmarking vs 3 RandomAgents over {BENCH_GAMES_RANDOM} seat-rotated games ...")
    t1 = time.time()
    wr_random = benchmark_vs_random(policy, num_games=BENCH_GAMES_RANDOM, seed=1234)
    print(f"  -> win rate vs random: {wr_random:.3f}  ({time.time() - t1:.1f}s)")

    print(f"benchmarking vs 3 HeuristicAgents over {BENCH_GAMES_HEURISTIC} games (info) ...")
    t2 = time.time()
    wr_heur = benchmark_vs_heuristic(policy, num_games=BENCH_GAMES_HEURISTIC, seed=5678)
    print(f"  -> win rate vs heuristic: {wr_heur:.3f}  ({time.time() - t2:.1f}s)")

    print("=" * 72)
    print("FINAL SUMMARY")
    print(f"  checkpoint:        {Path(final_path).resolve()}")
    print(f"  training time:     {train_secs:.1f}s")
    print(f"  win rate vs random:    {wr_random:.1%}  (target > {WIN_RATE_TARGET:.0%})")
    print(f"  win rate vs heuristic: {wr_heur:.1%}  (informational)")
    verdict = "PASS" if wr_random > WIN_RATE_TARGET else "BELOW TARGET"
    print(f"  verdict (>80% vs random): {verdict}")
    print("=" * 72)
    return wr_random


if __name__ == "__main__":
    main()
