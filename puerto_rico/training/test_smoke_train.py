"""Fast smoke test for the trained policy artifact (task-10).

This test does **NOT** retrain — that is done by ``train_strong.py`` (the strong
release run) or ``smoke_train.py``, which take minutes. Instead it loads the kept
release checkpoint ``runs/release/final.pt`` (falling back to the older
``runs/smoke/final.pt``) via :class:`~puerto_rico.agents.rl_policy.RLPolicy` and
asserts the saved policy clearly dominates RandomAgents over a quick seat-rotated
benchmark.

The release checkpoint is trained on the current action space (``N_ACTIONS=92``)
by ``train_strong.py``. The bar here (> 0.6) is intentionally **looser** than the
strict numbers the manual run verifies: it proves the saved artifact loads and
learned, while staying fast and robust to benchmark-seed variance. If no
compatible checkpoint exists (a fresh clone that never ran training, or only an
older dimension-incompatible artifact), the test skips with a clear message rather
than failing.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ..agents.rl_policy import IncompatibleCheckpointError, RLPolicy
from .evaluate import benchmark_vs_random

# Prefer the stable release checkpoint; fall back to the smoke checkpoint.
RELEASE_PT = Path("runs/release/final.pt")
SMOKE_PT = Path("runs/smoke/final.pt")

BENCH_GAMES = 100
WIN_RATE_FLOOR = 0.60


def _checkpoint() -> Path | None:
    if RELEASE_PT.exists():
        return RELEASE_PT
    if SMOKE_PT.exists():
        return SMOKE_PT
    return None


def test_trained_policy_beats_random() -> None:
    ckpt = _checkpoint()
    if ckpt is None:
        pytest.skip(
            f"no trained checkpoint at {RELEASE_PT} or {SMOKE_PT}; run "
            "`uv run python -m puerto_rico.training.train_strong` first"
        )

    try:
        policy = RLPolicy.from_checkpoint(ckpt)
    except IncompatibleCheckpointError as exc:
        pytest.skip(
            f"checkpoint {ckpt} is dimension-incompatible with the current "
            f"codec ({exc}); the model must be retrained"
        )
    win_rate = benchmark_vs_random(policy, num_games=BENCH_GAMES, seed=4242)

    assert win_rate > WIN_RATE_FLOOR, (
        f"trained policy win rate vs random was {win_rate:.3f} "
        f"(<= {WIN_RATE_FLOOR}); checkpoint may be undertrained "
        f"(checkpoint: {ckpt})"
    )
