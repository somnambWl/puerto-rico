"""Train a STRONG *and* VARIED Puerto Rico RL policy via dense reward shaping.

Successor to :mod:`puerto_rico.training.train_strong` /
:mod:`puerto_rico.training.train_improved`. On the (now correct) building supply,
plain self-play converges to a pure **corn-shipping rush**: it wins ~96% vs the
heuristic but almost never builds an engine (the audit's "all-corn-no-engine"
~77%, large-building winners ~8%). We want a policy that is BOTH strong AND
builds a production / building engine (large buildings, Guild Hall).

Lever (design/05): a small, ANNEALED dense shaping reward for *developing a
building engine*. At each learner decision the step reward gets
``shaping_coef * Δ building_development_score`` (printed building VP + occupied
large-building bonuses — exactly the VP the corn rush skips). The coefficient is
small relative to the ±1 terminal rank reward (so it nudges, not dominates) and
anneals to 0 over the first ~65% of training, so the final third fine-tunes the
varied behavior on the **pure rank objective** — no permanent distortion.

Two further anti-monoculture levers:

* heavy opponent diversity (``self_play_prob=0.7``, ``pool_self_play_prob=0.3``)
  so the learner is often facing frozen snapshots / the heuristic rather than
  cloning a single corn-rush line;
* entropy annealed broad -> decisive (0.02 -> 0 over 80%).

Pipeline:

1. Train (checkpoints every 100 iters + ``final.pt``) into ``runs/shaped``.
2. Best-checkpoint selection by win rate vs the heuristic (``select_best``).
3. For the top-few checkpoints, run the strategy audit's RL self-play line-up and
   print a clear VARIETY-vs-STRENGTH table: ``wr_vs_heuristic``,
   ``large-bldg-winner %``, ``corn-no-engine %`` (+ Guild Hall %, winner VP).
4. Save the selected best to ``runs/shaped/final.pt`` and PRINT the comparison.
   It does NOT auto-overwrite ``runs/release`` — the operator promotes manually
   after reviewing the table (a policy that is strong AND varied).

Run::

    PR_TRAIN_THREADS=6 nice -n 15 uv run python -m puerto_rico.training.train_shaped
"""

from __future__ import annotations

import shutil
import time
from pathlib import Path

from ..agents.heuristic_agent import HeuristicAgent
from ..agents.rl_policy import RLPolicy
from . import strategy_audit
from .ppo import PPOConfig, limit_cpu_usage, train
from .train_utils import discover_checkpoints, label, select_best

# --------------------------------------------------------------------------- #
# paths / knobs                                                               #
# --------------------------------------------------------------------------- #

OUT_DIR = Path("runs/shaped")
SHAPED_PT = OUT_DIR / "final.pt"

# Per-checkpoint selection sample (seat-rotated; multiple of 4).
SELECT_GAMES_HEURISTIC = 320
SELECT_GAMES_RANDOM = 120

# How many of the top-by-win-rate checkpoints to deep-audit for variety.
TOP_K_AUDIT = 4
# Audit sample per checkpoint (RL self-play line-up; seat-rotated).
AUDIT_GAMES = 200

TOTAL_ITERATIONS = 1500


# --------------------------------------------------------------------------- #
# config                                                                       #
# --------------------------------------------------------------------------- #


def make_config() -> PPOConfig:
    """Shaped training hyperparameters; see module docstring for rationale.

    Shaping: ``shaping_coef0=0.10`` (small vs the ±1 rank reward — a few VP of
    building development moves the per-step reward by ~0.1-0.5, a nudge not a
    dominator) annealed to 0 over ~65% of training, so the last third trains on
    pure rank and fine-tunes the varied behavior.
    """
    total = TOTAL_ITERATIONS
    return PPOConfig(
        num_players=4,
        reward_mode="rank",  # general-sum correct; shaping is additive + annealed
        total_iterations=total,
        rollout_steps=4096,
        # PPO core (same well-tuned core as the strong/improved runs)
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
        entropy_anneal_iters=int(total * 0.8),
        # Dense building-development shaping, annealed to 0 over ~65% of training.
        shaping_coef0=0.10,
        shaping_anneal_iters=int(total * 0.65),
        # Model: 256x256 trains faster and is enough capacity here.
        hidden=(256, 256),
        # Opponent diversity to discourage the corn monoculture: mix the pool into
        # most iterations (0.7), and make those mixed seats *more often* a strong
        # baseline / frozen snapshot than the live learner (pool self prob 0.3).
        self_play_prob=0.7,
        pool_self_play_prob=0.3,
        snapshot_interval=100,
        max_snapshots=16,
        eval_interval=100,
        eval_games=100,
        seed=0,
        out_dir=str(OUT_DIR),
        device="cpu",
    )


# --------------------------------------------------------------------------- #
# per-checkpoint variety + strength signature                                 #
# --------------------------------------------------------------------------- #


def variety_signature(checkpoint: Path, num_games: int = AUDIT_GAMES) -> dict:
    """Audit a checkpoint for the key strength + variety gap metrics.

    Reuses :func:`strategy_audit.run_lineup` so the numbers match the published
    audit exactly. Returns win rate vs 3 heuristics plus the variety signatures
    that the corn rush fails (large-building winners up, corn-no-engine down).
    """
    rl = RLPolicy.from_checkpoint(checkpoint, deterministic=True)

    # 4x RL self-play -> variety signatures (large buildings / Guild Hall / corn).
    rl_self = strategy_audit.run_lineup([rl, rl, rl, rl], {0, 1, 2, 3}, num_games, 0)

    # 1x RL vs 3x Heuristic -> head-to-head strength.
    mixed = [rl] + [
        HeuristicAgent(seed=300 + i) for i in range(strategy_audit.NUM_PLAYERS - 1)
    ]
    rvh = strategy_audit.run_lineup(mixed, {0}, num_games, 0)
    wr_vs_heur = rvh["winners"] / max(1, rvh["games_as_target"])

    return {
        "wr_vs_heuristic": wr_vs_heur,
        "winner_owns_large_rate": rl_self["winner_owns_large_rate"],
        "winner_owns_guild_hall_rate": rl_self["winner_owns_guild_hall_rate"],
        "all_corn_no_engine_rate": rl_self["all_corn_no_engine_rate"],
        "winner_mean_vp": rl_self["winner_mean_vp"],
    }


def _pct(x: float) -> str:
    return f"{100 * x:.1f}%"


def print_variety_table(rows: list[tuple[str, dict]]) -> None:
    """Print the per-checkpoint strength-vs-variety table for operator review."""
    print("\n" + "=" * 78)
    print(f"VARIETY vs STRENGTH — top {len(rows)} checkpoints ({AUDIT_GAMES} games each)")
    print("  pick one that is BOTH strong (high wr) AND varied (high large%, low corn%)")
    print("=" * 78)
    print(
        f"{'ckpt':>8}{'wr_vs_heur':>12}{'large_win%':>12}"
        f"{'guildhall%':>12}{'corn_no_eng%':>14}{'winnerVP':>10}"
    )
    print("-" * 78)
    for lbl, sig in rows:
        print(
            f"{lbl:>8}"
            f"{_pct(sig['wr_vs_heuristic']):>12}"
            f"{_pct(sig['winner_owns_large_rate']):>12}"
            f"{_pct(sig['winner_owns_guild_hall_rate']):>12}"
            f"{_pct(sig['all_corn_no_engine_rate']):>14}"
            f"{sig['winner_mean_vp']:>10.1f}",
            flush=True,
        )
    print("-" * 78)


# --------------------------------------------------------------------------- #
# main                                                                         #
# --------------------------------------------------------------------------- #


def main() -> dict:
    threads = limit_cpu_usage()  # leave CPU headroom so the machine stays usable
    cfg = make_config()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 78)
    print(f"(CPU-considerate: torch limited to {threads} threads; run niced if desired)")
    print("SHAPED PPO TRAINING: strong AND varied (anneal a building-engine reward)")
    print("=" * 78)
    print(
        f"config: iters={cfg.total_iterations} rollout_steps={cfg.rollout_steps} "
        f"lr={cfg.lr} mb={cfg.minibatch_size} epochs={cfg.update_epochs} "
        f"hidden={cfg.hidden}"
    )
    print(
        f"        entropy={cfg.entropy_coef}->{cfg.entropy_coef_final} over "
        f"{cfg.entropy_anneal_iters} iters | "
        f"shaping_coef0={cfg.shaping_coef0} -> 0 over {cfg.shaping_anneal_iters} iters"
    )
    print(
        f"        self_play_prob={cfg.self_play_prob} "
        f"pool_self_play_prob={cfg.pool_self_play_prob} reward={cfg.reward_mode}"
    )
    print(f"out_dir: {OUT_DIR.resolve()}")
    print("-" * 78)

    t0 = time.time()
    final_path = train(cfg)
    train_secs = time.time() - t0
    print("-" * 78)
    print(f"training done in {train_secs / 60:.1f} min -> {final_path}")

    # Best-checkpoint selection (by win rate vs heuristic; tie-break vs random).
    best_path, curve = select_best(
        OUT_DIR,
        select_games_heuristic=SELECT_GAMES_HEURISTIC,
        select_games_random=SELECT_GAMES_RANDOM,
    )

    # Deep-audit the top-few by win rate for variety, so the operator can pick one
    # that is BOTH strong AND varied.
    ranked = sorted(curve, key=lambda c: (c["wr_heur"], c["wr_rand"]), reverse=True)
    top = ranked[:TOP_K_AUDIT]
    print(f"\nauditing top {len(top)} checkpoints for variety ...")
    table_rows: list[tuple[str, dict]] = []
    for c in top:
        t1 = time.time()
        sig = variety_signature(c["path"])
        table_rows.append((str(c["iter"]), sig))
        print(f"  audited iter={c['iter']} ({time.time() - t1:.1f}s)", flush=True)
    print_variety_table(table_rows)

    # Save the best-by-win-rate to runs/shaped/final.pt. DO NOT touch runs/release;
    # the operator promotes manually after reviewing the variety table above.
    shutil.copyfile(best_path, SHAPED_PT)
    print(f"\nsaved best (by wr vs heuristic) {label(best_path)} -> {SHAPED_PT.resolve()}")
    print(
        "NOTE: runs/release NOT modified. Review the VARIETY vs STRENGTH table and "
        "promote your chosen checkpoint manually, e.g.:\n"
        f"  cp runs/shaped/checkpoint_<iter>.pt runs/release/final.pt"
    )

    print("\n" + "=" * 78)
    print("DONE")
    print(f"  training time:      {train_secs / 60:.1f} min ({threads} threads)")
    print(f"  shaped checkpoint:  {SHAPED_PT.resolve()}")
    print(f"  checkpoints:        {len(discover_checkpoints(OUT_DIR))} in {OUT_DIR}")
    print("=" * 78)

    return {
        "curve": curve,
        "best": best_path,
        "variety_table": table_rows,
        "train_secs": train_secs,
    }


if __name__ == "__main__":
    main()
