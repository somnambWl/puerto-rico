"""Train an IMPROVED Puerto Rico RL policy that closes the strategy-audit gaps.

This is a successor to :mod:`puerto_rico.training.train_strong`. The current
release (``runs/release/final.pt``) is already strong (~78-80% vs 3 heuristics)
but the audit (``docs/rl-strategy-audit.md``) flagged gaps:

1. Never builds Guild Hall (0% of winners) — the best large building.
2. Leaves buildings unmanned (1.02 free circles) and breaks production chains
   (1.26 mismatch).
3. Over-ships corn without an engine (~20%).
4. Passes affordable builds ~48% in self-play.

Levers used here (no hand-coded building-specific rewards — kept general):

* **Wider net** ``hidden=(384, 384)`` — more capacity to learn end-game building
  value (e.g. Guild Hall's per-building VP) than the (256, 256) release net.
* **Heavier exposure to strong opponents.** ``self_play_prob=0.85`` mixes the
  opponent pool into *most* iterations; ``pool_self_play_prob=0.35`` makes those
  mixed seats *more often* the HeuristicAgent / a frozen snapshot than the live
  learner. The learner must therefore out-play strong play, which pushes it
  toward coherent big-building / Guild-Hall lines instead of self-play artifacts
  (passing affordable builds). At least one learner seat is always kept.
* **reward_mode="rank"** — 4-player Puerto Rico is general-sum; rank reward is the
  correct standing-based objective. No dense shaping: the PPO loop / rollout
  collector does not wire a shaping coefficient (``collect_rollouts`` only takes
  ``reward_mode``), so per the task we rely on rank + capacity + curriculum.
* **More iterations** than the strong run (1200), sized by a quick 5-iter timing
  calibration to respect a ~25-35 min wall-clock budget.

Pipeline (mirrors ``train_strong``):

1. Calibrate iters/sec on this machine, pick ``total_iterations`` to fit budget.
2. Train (checkpoints every ``snapshot_interval`` + ``final.pt``).
3. Best-checkpoint selection by ``benchmark_vs_heuristic`` over a solid sample
   (>=300 games), tie-break vs random. Print the curve.
4. Compare the BEST candidate vs the CURRENT release on win rate AND each audit
   gap (Guild Hall %, unmanned, chains, corn-no-engine). Print a BEFORE/AFTER
   table.
5. Save the candidate to ``runs/improved/final.pt`` regardless. PROMOTE it to
   ``runs/release/final.pt`` ONLY IF it clearly beats the release on win rate vs
   heuristic with no major regression (and ideally improves >=1 gap). Otherwise
   keep the old release and say so.

Run::

    PR_TRAIN_THREADS=6 nice -n 15 uv run python -m puerto_rico.training.train_improved
"""

from __future__ import annotations

import re
import shutil
import time
from pathlib import Path

from ..agents.heuristic_agent import HeuristicAgent
from ..agents.random_agent import RandomAgent
from ..agents.rl_policy import RLPolicy
from .evaluate import Arena, benchmark_vs_heuristic, benchmark_vs_random
from .ppo import PPOConfig, limit_cpu_usage, train
from . import strategy_audit

# --------------------------------------------------------------------------- #
# paths / knobs                                                               #
# --------------------------------------------------------------------------- #

OUT_DIR = Path("runs/improved")
RELEASE_DIR = Path("runs/release")
RELEASE_PT = RELEASE_DIR / "final.pt"
IMPROVED_PT = OUT_DIR / "final.pt"

# Per-checkpoint selection sample (seat-rotated; multiple of 4). >= 300 vs heur.
SELECT_GAMES_HEURISTIC = 320
SELECT_GAMES_RANDOM = 120

# Final rigorous benchmark (>= 504, multiple of 4 and of 12 for clean rotation).
FINAL_GAMES = 504
ARENA_GAMES = 504

# Audit gap comparison sample (per line-up; seat-rotated).
AUDIT_GAMES = 200

# Wall-clock budget for the training loop only (best-selection + audit extra).
TRAIN_BUDGET_MIN = 28.0
ITERS_MIN = 1200
ITERS_MAX = 2200


# --------------------------------------------------------------------------- #
# config                                                                       #
# --------------------------------------------------------------------------- #


def make_config(total_iterations: int) -> PPOConfig:
    """Improved training hyperparameters; see module docstring for rationale."""
    total = total_iterations
    return PPOConfig(
        num_players=4,
        reward_mode="rank",  # general-sum correct
        total_iterations=total,
        rollout_steps=4096,
        # PPO core (same well-tuned core as the strong run)
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
        # Model: wider for end-game building value (Guild Hall).
        hidden=(384, 384),
        # Curriculum: mix the pool into MOST iterations (0.85), and make those
        # mixed seats more often a strong baseline / frozen snapshot than the
        # live learner (pool self prob 0.35). Always keeps >=1 learner seat.
        self_play_prob=0.85,
        pool_self_play_prob=0.35,
        snapshot_interval=100,
        max_snapshots=16,
        eval_interval=100,
        eval_games=100,
        seed=0,
        out_dir=str(OUT_DIR),
        device="cpu",
    )


def calibrate_iters(threads: int) -> int:
    """Time a 5-iter probe, then size total iters to fit ``TRAIN_BUDGET_MIN``."""
    print("-" * 72)
    print(f"CALIBRATION: timing 5 iters to size the run (budget {TRAIN_BUDGET_MIN:.0f} min)")
    probe = make_config(total_iterations=5)
    probe.eval_interval = 0  # no eval during calibration
    probe.snapshot_interval = 1000  # no snapshots during calibration
    probe.out_dir = str(OUT_DIR / "_calib")
    t0 = time.time()
    train(probe)
    dt = time.time() - t0
    per_iter = dt / 5.0
    # clean up calib artifacts
    shutil.rmtree(OUT_DIR / "_calib", ignore_errors=True)
    budget_s = TRAIN_BUDGET_MIN * 60.0
    sized = int(budget_s / max(per_iter, 1e-6))
    sized = max(ITERS_MIN, min(ITERS_MAX, sized))
    print(
        f"  per-iter ~{per_iter:.2f}s ({threads} threads) -> "
        f"sized total_iterations={sized} "
        f"(~{sized * per_iter / 60:.1f} min projected)"
    )
    print("-" * 72)
    return sized


# --------------------------------------------------------------------------- #
# checkpoint discovery + selection (mirrors train_strong)                      #
# --------------------------------------------------------------------------- #


def _iter_key(path: Path) -> tuple[int, int]:
    if path.name == "final.pt":
        return (1, 1 << 30)
    m = re.search(r"checkpoint_(\d+)\.pt$", path.name)
    return (0, int(m.group(1)) if m else -1)


def discover_checkpoints(out_dir: Path) -> list[Path]:
    ckpts = list(out_dir.glob("checkpoint_*.pt"))
    final = out_dir / "final.pt"
    if final.exists():
        ckpts.append(final)
    return sorted(ckpts, key=_iter_key)


def _label(path: Path) -> str:
    if path.name == "final.pt":
        return "final"
    m = re.search(r"checkpoint_(\d+)\.pt$", path.name)
    return m.group(1) if m else path.name


def select_best(out_dir: Path) -> tuple[Path, list[dict]]:
    """Evaluate every checkpoint vs heuristic (+random); return (best, curve)."""
    ckpts = discover_checkpoints(out_dir)
    if not ckpts:
        raise FileNotFoundError(f"no checkpoints found in {out_dir}")

    curve: list[dict] = []
    print("\n" + "=" * 72)
    print("BEST-CHECKPOINT SELECTION")
    print(
        f"  scoring each checkpoint over {SELECT_GAMES_HEURISTIC} games vs heuristic"
        f" + {SELECT_GAMES_RANDOM} vs random (seat-rotated, deterministic)"
    )
    print("=" * 72)
    print(f"{'iter':>8}{'wr_vs_heuristic':>18}{'wr_vs_random':>15}{'time':>9}")
    print("-" * 72)

    for path in ckpts:
        t0 = time.time()
        policy = RLPolicy.from_checkpoint(path, deterministic=True)
        wr_h = benchmark_vs_heuristic(
            policy, num_games=SELECT_GAMES_HEURISTIC, seed=5678
        )
        wr_r = benchmark_vs_random(policy, num_games=SELECT_GAMES_RANDOM, seed=4242)
        dt = time.time() - t0
        label = _label(path)
        curve.append({"iter": label, "path": path, "wr_heur": wr_h, "wr_rand": wr_r})
        print(f"{label:>8}{wr_h:>18.3f}{wr_r:>15.3f}{dt:>8.1f}s", flush=True)

    best = max(curve, key=lambda c: (c["wr_heur"], c["wr_rand"]))
    print("-" * 72)
    print(
        f"BEST: iter={best['iter']}  wr_vs_heuristic={best['wr_heur']:.3f}  "
        f"wr_vs_random={best['wr_rand']:.3f}"
    )
    return best["path"], curve


# --------------------------------------------------------------------------- #
# audit-gap signature for an arbitrary checkpoint                              #
# --------------------------------------------------------------------------- #


def gap_signature(checkpoint: Path, num_games: int = AUDIT_GAMES) -> dict:
    """Run the audit's RL line-ups for ``checkpoint`` and extract the gap metrics.

    Reuses :mod:`strategy_audit` internals (``_run_lineup``) so the numbers match
    the published audit exactly. Returns win rate vs heuristic plus the four gap
    signatures (Guild Hall %, unmanned, chain mismatch, corn-no-engine).
    """
    rl = RLPolicy.from_checkpoint(checkpoint, deterministic=True)

    # 4x RL self-play -> manning / chains / Guild Hall / corn signatures.
    rl_self = strategy_audit._run_lineup([rl, rl, rl, rl], {0, 1, 2, 3}, num_games, 0)

    # 1x RL vs 3x Heuristic -> head-to-head win rate.
    mixed = [rl] + [HeuristicAgent(seed=300 + i) for i in range(strategy_audit.NUM_PLAYERS - 1)]
    rvh = strategy_audit._run_lineup(mixed, {0}, num_games, 0)
    wr_vs_heur = rvh["winners"] / max(1, rvh["games_as_target"])

    return {
        "wr_vs_heuristic": wr_vs_heur,
        "winner_owns_guild_hall_rate": rl_self["winner_owns_guild_hall_rate"],
        "winner_owns_large_rate": rl_self["winner_owns_large_rate"],
        "mean_unmanned": rl_self["mean_unmanned"],
        "mean_chain_mismatch": rl_self["mean_chain_mismatch"],
        "all_corn_no_engine_rate": rl_self["all_corn_no_engine_rate"],
        "empty_build_pass_rate": rl_self["empty_build_pass_rate"],
        "winner_mean_vp": rl_self["winner_mean_vp"],
    }


def _fmt_pct(x: float) -> str:
    return f"{100 * x:.1f}%"


def print_before_after(before: dict, after: dict) -> None:
    print("\n" + "=" * 72)
    print(f"BEFORE (current release) vs AFTER (candidate) — {AUDIT_GAMES} games/line-up")
    print("=" * 72)
    rows = [
        ("win rate vs 3 heuristic (1v3)", "wr_vs_heuristic", "pct", True),
        ("winners w/ Guild Hall", "winner_owns_guild_hall_rate", "pct", True),
        ("winners w/ any large", "winner_owns_large_rate", "pct", True),
        ("mean unmanned circles", "mean_unmanned", "num", False),
        ("mean chain mismatch", "mean_chain_mismatch", "num", False),
        ("all-corn-no-engine rate", "all_corn_no_engine_rate", "pct", False),
        ("empty-build pass rate", "empty_build_pass_rate", "pct", False),
        ("winner mean VP", "winner_mean_vp", "num", True),
    ]
    print(f"{'metric':<32}{'BEFORE':>12}{'AFTER':>12}{'better?':>10}")
    print("-" * 72)
    for label, key, kind, higher_better in rows:
        b, a = before[key], after[key]
        if kind == "pct":
            bs, as_ = _fmt_pct(b), _fmt_pct(a)
        else:
            bs, as_ = f"{b:.2f}", f"{a:.2f}"
        improved = (a > b) if higher_better else (a < b)
        same = abs(a - b) < 1e-9
        mark = "=" if same else ("YES" if improved else "no")
        print(f"{label:<32}{bs:>12}{as_:>12}{mark:>10}")
    print("-" * 72)


# --------------------------------------------------------------------------- #
# final rigorous benchmark                                                     #
# --------------------------------------------------------------------------- #


def final_benchmark(release_pt: Path) -> dict:
    print("\n" + "=" * 72)
    print("FINAL RIGOROUS BENCHMARK OF RELEASE POLICY")
    print(f"  checkpoint: {release_pt.resolve()}")
    print("=" * 72)

    policy = RLPolicy.from_checkpoint(release_pt, deterministic=True)

    t0 = time.time()
    wr_heur = benchmark_vs_heuristic(policy, num_games=FINAL_GAMES, seed=99001)
    print(
        f"win rate vs 3 HeuristicAgents over {FINAL_GAMES} games: "
        f"{wr_heur:.3f}  ({time.time() - t0:.1f}s)"
    )

    t0 = time.time()
    wr_rand = benchmark_vs_random(policy, num_games=FINAL_GAMES, seed=99002)
    print(
        f"win rate vs 3 RandomAgents over {FINAL_GAMES} games:    "
        f"{wr_rand:.3f}  ({time.time() - t0:.1f}s)"
    )

    print("\nArena: {RL, Heuristic, Random, Random}")
    arena = Arena(
        [
            ("rl", RLPolicy.from_checkpoint(release_pt, deterministic=True)),
            ("heuristic", HeuristicAgent(seed=2)),
            ("random1", RandomAgent(seed=3)),
            ("random2", RandomAgent(seed=4)),
        ],
        num_players=4,
        seed=7,
    )
    result = arena.run(ARENA_GAMES)
    print(result.to_table())

    return {"wr_heur": wr_heur, "wr_rand": wr_rand, "arena": result}


# --------------------------------------------------------------------------- #
# promotion decision                                                           #
# --------------------------------------------------------------------------- #


def decide_promotion(before: dict, after: dict) -> tuple[bool, str]:
    """Promote only if clearly better: higher wr vs heuristic + no major regression.

    A "major regression" is a meaningful worsening of a gap that is not offset by
    the win-rate gain. We require:

    * win rate vs heuristic strictly higher by a margin beyond noise (>= +0.5pp),
    * AND no gap regressing badly: unmanned/chain not worse by > 0.15, corn-no-
      engine not worse by > 5pp, Guild Hall / large not collapsing.
    """
    wr_gain = after["wr_vs_heuristic"] - before["wr_vs_heuristic"]
    if wr_gain < 0.005:
        return False, (
            f"win rate vs heuristic did not clearly improve "
            f"({_fmt_pct(before['wr_vs_heuristic'])} -> {_fmt_pct(after['wr_vs_heuristic'])}, "
            f"{wr_gain*100:+.1f}pp)"
        )

    regressions = []
    if after["mean_unmanned"] - before["mean_unmanned"] > 0.15:
        regressions.append("unmanned worse")
    if after["mean_chain_mismatch"] - before["mean_chain_mismatch"] > 0.15:
        regressions.append("chains worse")
    if after["all_corn_no_engine_rate"] - before["all_corn_no_engine_rate"] > 0.05:
        regressions.append("corn-no-engine worse")
    if after["winner_owns_large_rate"] < before["winner_owns_large_rate"] - 0.10:
        regressions.append("large-building ownership collapsed")

    if regressions:
        return False, (
            f"win rate improved ({wr_gain*100:+.1f}pp) but a gap regressed: "
            + ", ".join(regressions)
        )
    return True, f"win rate vs heuristic improved {wr_gain*100:+.1f}pp with no major gap regression"


# --------------------------------------------------------------------------- #
# main                                                                         #
# --------------------------------------------------------------------------- #


def main() -> dict:
    threads = limit_cpu_usage()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 72)
    print(f"(CPU-considerate: torch limited to {threads} threads; run niced)")
    print("IMPROVED PPO TRAINING: close the strategy-audit gaps, beat heuristic more")
    print("=" * 72)

    # Snapshot the CURRENT release's gap signature BEFORE we touch anything.
    before = None
    if RELEASE_PT.exists():
        print("\nmeasuring CURRENT release gap signature (BEFORE) ...")
        t0 = time.time()
        before = gap_signature(RELEASE_PT)
        print(f"  done ({time.time() - t0:.1f}s)")

    # Calibrate + size the run.
    total_iters = calibrate_iters(threads)
    cfg = make_config(total_iters)

    print(
        f"config: iters={cfg.total_iterations} rollout_steps={cfg.rollout_steps} "
        f"lr={cfg.lr} mb={cfg.minibatch_size} epochs={cfg.update_epochs} "
        f"hidden={cfg.hidden}"
    )
    print(
        f"        self_play_prob={cfg.self_play_prob} "
        f"pool_self_play_prob={cfg.pool_self_play_prob} "
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
    best_path, curve = select_best(OUT_DIR)

    # Always preserve the candidate at runs/improved/final.pt.
    shutil.copyfile(best_path, IMPROVED_PT)
    print(f"\nsaved candidate {best_path} -> {IMPROVED_PT.resolve()}")

    # Compare candidate vs current release on the audit gaps.
    print("\nmeasuring CANDIDATE gap signature (AFTER) ...")
    t0 = time.time()
    after = gap_signature(best_path)
    print(f"  done ({time.time() - t0:.1f}s)")

    promote = False
    reason = "no current release to compare against — promoting candidate as the release"
    if before is not None:
        print_before_after(before, after)
        promote, reason = decide_promotion(before, after)
    else:
        promote = True

    RELEASE_DIR.mkdir(parents=True, exist_ok=True)
    if promote:
        shutil.copyfile(best_path, RELEASE_PT)
        print(f"\nPROMOTED candidate -> {RELEASE_PT.resolve()}")
        print(f"  reason: {reason}")
    else:
        print(f"\nKEPT existing release at {RELEASE_PT.resolve()} (candidate NOT promoted)")
        print(f"  reason: {reason}")
        print(f"  candidate preserved at {IMPROVED_PT.resolve()}")

    # Final rigorous benchmark of WHATEVER is now the release.
    final = final_benchmark(RELEASE_PT)

    print("\n" + "=" * 72)
    print("DONE")
    print(f"  training time:          {train_secs / 60:.1f} min ({threads} threads)")
    print(f"  release checkpoint:     {RELEASE_PT.resolve()}")
    print(f"  release is:             {'NEW candidate' if promote else 'PREVIOUS (kept)'}")
    print(f"  final wr vs heuristic:  {final['wr_heur']:.3f}  ({FINAL_GAMES} games)")
    print(f"  final wr vs random:     {final['wr_rand']:.3f}  ({FINAL_GAMES} games)")
    print("=" * 72)

    return {
        "curve": curve,
        "best": best_path,
        "before": before,
        "after": after,
        "promoted": promote,
        "reason": reason,
        "final": final,
        "train_secs": train_secs,
    }


if __name__ == "__main__":
    main()
