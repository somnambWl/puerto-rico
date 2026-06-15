"""Shared pieces for the PPO training entry-point scripts (design/05).

``smoke_train.py``, ``train_strong.py`` and ``train_improved.py`` all do the same
post-training plumbing — discover the saved checkpoints, score each one to pick the
best, and run a final rigorous benchmark of the released policy. That boilerplate
lived (duplicated, occasionally drifting) in each script. It is consolidated here;
each script keeps only its own ``make_config()`` and script-specific logic
(``train_improved`` keeps its calibration + gap comparison; ``smoke`` keeps its
lighter flow).

Nothing here changes *what* the scripts do — it is a pure de-duplication. Sample
sizes are passed in as arguments so each script keeps its own numbers.
"""

from __future__ import annotations

import re
import time
from pathlib import Path

from ..agents.heuristic_agent import HeuristicAgent
from ..agents.random_agent import RandomAgent
from ..agents.rl_policy import RLPolicy
from .evaluate import Arena, benchmark_vs_heuristic, benchmark_vs_random


# --------------------------------------------------------------------------- #
# checkpoint discovery                                                         #
# --------------------------------------------------------------------------- #


def iter_key(path: Path) -> tuple[int, int]:
    """Sort key: ``(is_final, iteration)``. ``final.pt`` sorts last."""
    if path.name == "final.pt":
        return (1, 1 << 30)
    m = re.search(r"checkpoint_(\d+)\.pt$", path.name)
    return (0, int(m.group(1)) if m else -1)


def discover_checkpoints(out_dir: Path) -> list[Path]:
    """All ``checkpoint_*.pt`` + ``final.pt`` in ``out_dir``, in training order."""
    ckpts = list(out_dir.glob("checkpoint_*.pt"))
    final = out_dir / "final.pt"
    if final.exists():
        ckpts.append(final)
    return sorted(ckpts, key=iter_key)


def label(path: Path) -> str:
    """Short label for a checkpoint path (the iteration number, or ``"final"``)."""
    if path.name == "final.pt":
        return "final"
    m = re.search(r"checkpoint_(\d+)\.pt$", path.name)
    return m.group(1) if m else path.name


# --------------------------------------------------------------------------- #
# best-checkpoint selection                                                    #
# --------------------------------------------------------------------------- #


def select_best(
    out_dir: Path,
    *,
    select_games_heuristic: int,
    select_games_random: int,
    seed_heuristic: int = 5678,
    seed_random: int = 4242,
) -> tuple[Path, list[dict]]:
    """Evaluate every checkpoint vs heuristic (+random) and return ``(best, curve)``.

    Best = highest win rate vs heuristic; tie-break highest win rate vs random.
    Loads each checkpoint as a deterministic :class:`RLPolicy` and prints the
    per-checkpoint learning curve.
    """
    ckpts = discover_checkpoints(out_dir)
    if not ckpts:
        raise FileNotFoundError(f"no checkpoints found in {out_dir}")

    curve: list[dict] = []
    print("\n" + "=" * 72)
    print("BEST-CHECKPOINT SELECTION")
    print(
        f"  scoring each checkpoint over {select_games_heuristic} games vs heuristic"
        f" + {select_games_random} vs random (seat-rotated, deterministic)"
    )
    print("=" * 72)
    print(f"{'iter':>8}{'wr_vs_heuristic':>18}{'wr_vs_random':>15}{'time':>9}")
    print("-" * 72)

    for path in ckpts:
        t0 = time.time()
        policy = RLPolicy.from_checkpoint(path, deterministic=True)
        wr_h = benchmark_vs_heuristic(
            policy, num_games=select_games_heuristic, seed=seed_heuristic
        )
        wr_r = benchmark_vs_random(
            policy, num_games=select_games_random, seed=seed_random
        )
        dt = time.time() - t0
        lbl = label(path)
        curve.append({"iter": lbl, "path": path, "wr_heur": wr_h, "wr_rand": wr_r})
        print(f"{lbl:>8}{wr_h:>18.3f}{wr_r:>15.3f}{dt:>8.1f}s", flush=True)

    best = max(curve, key=lambda c: (c["wr_heur"], c["wr_rand"]))
    print("-" * 72)
    print(
        f"BEST: iter={best['iter']}  wr_vs_heuristic={best['wr_heur']:.3f}  "
        f"wr_vs_random={best['wr_rand']:.3f}"
    )
    return best["path"], curve


# --------------------------------------------------------------------------- #
# final rigorous benchmark                                                     #
# --------------------------------------------------------------------------- #


def final_benchmark(
    release_pt: Path,
    *,
    final_games: int,
    arena_games: int,
    seed_heuristic: int = 99001,
    seed_random: int = 99002,
    arena_seed: int = 7,
) -> dict:
    """Large-sample vs-heuristic / vs-random + an Arena with Elo of the release."""
    print("\n" + "=" * 72)
    print("FINAL RIGOROUS BENCHMARK OF RELEASE POLICY")
    print(f"  checkpoint: {release_pt.resolve()}")
    print("=" * 72)

    policy = RLPolicy.from_checkpoint(release_pt, deterministic=True)

    t0 = time.time()
    wr_heur = benchmark_vs_heuristic(policy, num_games=final_games, seed=seed_heuristic)
    print(
        f"win rate vs 3 HeuristicAgents over {final_games} games: "
        f"{wr_heur:.3f}  ({time.time() - t0:.1f}s)"
    )

    t0 = time.time()
    wr_rand = benchmark_vs_random(policy, num_games=final_games, seed=seed_random)
    print(
        f"win rate vs 3 RandomAgents over {final_games} games:    "
        f"{wr_rand:.3f}  ({time.time() - t0:.1f}s)"
    )

    # Arena: {RL, Heuristic, Random, Random}
    print("\nArena: {RL, Heuristic, Random, Random}")
    arena = Arena(
        [
            ("rl", RLPolicy.from_checkpoint(release_pt, deterministic=True)),
            ("heuristic", HeuristicAgent(seed=2)),
            ("random1", RandomAgent(seed=3)),
            ("random2", RandomAgent(seed=4)),
        ],
        num_players=4,
        seed=arena_seed,
    )
    result = arena.run(arena_games)
    print(result.to_table())

    return {"wr_heur": wr_heur, "wr_rand": wr_rand, "arena": result}
