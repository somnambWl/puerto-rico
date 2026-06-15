"""Fast M4 benchmark test: the release RL policy vs the baselines (task-11).

This test does **NOT** retrain. It loads the kept release checkpoint
``runs/release/final.pt`` (falling back to ``runs/smoke/final.pt``) via
:class:`~puerto_rico.agents.rl_policy.RLPolicy` and asserts the saved policy is
competitive with 3 ``HeuristicAgent``s and clearly dominates 3 ``RandomAgent``s
over quick seat-rotated benchmarks.

The release checkpoint is trained on the current action space (``N_ACTIONS=92``)
by ``train_strong.py``, which also reports the strict, large-sample numbers
(>= 504 games). This pytest uses a smaller ``~120``-game sample and slightly
**looser floors** (heuristic >= 0.45, random >= 0.70) purely to stay fast and
robust to benchmark-seed variance while still proving the artifact loads and is
strong. If no checkpoint exists (a fresh clone that never ran training) the test
skips with a clear message rather than failing.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ..agents.rl_policy import IncompatibleCheckpointError, RLPolicy
from .evaluate import benchmark_vs_heuristic, benchmark_vs_random

# Prefer the stable release checkpoint; fall back to the smoke checkpoint.
RELEASE_PT = Path("runs/release/final.pt")
SMOKE_PT = Path("runs/smoke/final.pt")

BENCH_GAMES = 120  # multiple of 4 so every seat is covered evenly
HEURISTIC_FLOOR = 0.45  # M4 headline; trained release comfortably exceeds this
RANDOM_FLOOR = 0.70


def _checkpoint() -> Path | None:
    if RELEASE_PT.exists():
        return RELEASE_PT
    if SMOKE_PT.exists():
        return SMOKE_PT
    return None


def _load_or_skip(ckpt: Path | None) -> RLPolicy:
    """Load the checkpoint, skipping if absent or codec-incompatible (needs retrain)."""
    if ckpt is None:
        pytest.skip(
            f"no trained checkpoint at {RELEASE_PT} or {SMOKE_PT}; run "
            "`uv run python -m puerto_rico.training.smoke_train` first"
        )
    try:
        return RLPolicy.from_checkpoint(ckpt)
    except IncompatibleCheckpointError as exc:
        pytest.skip(
            f"checkpoint {ckpt} is dimension-incompatible with the current codec "
            f"({exc}); the model must be retrained (task E4)"
        )


def test_release_policy_competitive_vs_heuristic() -> None:
    ckpt = _checkpoint()
    policy = _load_or_skip(ckpt)
    win_rate = benchmark_vs_heuristic(policy, num_games=BENCH_GAMES, seed=5678)

    assert win_rate >= HEURISTIC_FLOOR, (
        f"trained policy win rate vs 3 heuristics was {win_rate:.3f} "
        f"(< {HEURISTIC_FLOOR}); checkpoint may be undertrained "
        f"(checkpoint: {ckpt})"
    )


def test_release_policy_dominates_random() -> None:
    ckpt = _checkpoint()
    policy = _load_or_skip(ckpt)
    win_rate = benchmark_vs_random(policy, num_games=BENCH_GAMES, seed=4242)

    assert win_rate >= RANDOM_FLOOR, (
        f"trained policy win rate vs 3 randoms was {win_rate:.3f} "
        f"(< {RANDOM_FLOOR}); checkpoint may be undertrained "
        f"(checkpoint: {ckpt})"
    )
