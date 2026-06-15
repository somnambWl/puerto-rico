"""Fast smoke test for the strategy audit (runs a handful of games).

Asserts the audit returns the expected metric shape and that numbers are finite
and in range. Does NOT assert specific strategy verdicts (those are reported,
not asserted). Skips if the release checkpoint is missing.
"""

from __future__ import annotations

import math
from pathlib import Path

import pytest

from puerto_rico.training import strategy_audit as sa


def _finite_in_range(x, lo=None, hi=None):
    assert isinstance(x, (int, float))
    assert not math.isnan(float(x))
    assert math.isfinite(float(x))
    if lo is not None:
        assert x >= lo - 1e-9
    if hi is not None:
        assert x <= hi + 1e-9


def test_run_audit_shape_and_ranges():
    audit = sa.run_audit(num_games=8, seed=0)

    assert set(audit.keys()) == {"agents", "rl_vs_heuristic", "meta"}
    assert audit["meta"]["num_games"] == 8

    # Heuristic and Random are always present (no checkpoint dependency).
    for name in ("Heuristic", "Random"):
        assert name in audit["agents"]

    if audit["meta"]["rl_available"]:
        assert "RL" in audit["agents"]
        assert audit["rl_vs_heuristic"] is not None
    else:
        assert "RL" not in audit["agents"]

    expected_keys = {
        "games_as_target",
        "winners",
        "winner_mean_vp",
        "winner_mean_vp_chips",
        "winner_mean_shipped",
        "winner_vp_hist",
        "wins_by_seat",
        "games_by_seat",
        "win_rate_by_seat",
        "winner_owns_large_rate",
        "winner_owns_guild_hall_rate",
        "role_total",
        "roles_by_third",
        "strong_build_rate",
        "trap_build_rate",
        "mean_unmanned",
        "mean_chain_mismatch",
        "mean_corn_acquire_frac",
        "all_corn_no_engine_rate",
        "empty_build_pass_rate",
        "ships_at_all_rate",
        "mean_first_ship_decision",
    }

    for name, m in audit["agents"].items():
        assert expected_keys <= set(m.keys()), name

        # rate metrics in [0, 1]
        for k in (
            "winner_owns_large_rate",
            "winner_owns_guild_hall_rate",
            "all_corn_no_engine_rate",
            "empty_build_pass_rate",
            "ships_at_all_rate",
            "mean_corn_acquire_frac",
        ):
            _finite_in_range(m[k], 0.0, 1.0001)

        for wr in m["win_rate_by_seat"]:
            _finite_in_range(wr, 0.0, 1.0001)
        assert len(m["win_rate_by_seat"]) == 4
        assert len(m["wins_by_seat"]) == 4
        assert sum(m["wins_by_seat"]) == m["winners"]

        _finite_in_range(m["mean_unmanned"], 0.0)
        _finite_in_range(m["mean_chain_mismatch"], 0.0)
        _finite_in_range(m["winner_mean_vp"], 0.0)

        # build-rate dicts populated and in range
        assert m["strong_build_rate"]
        for v in m["strong_build_rate"].values():
            _finite_in_range(v, 0.0, 1.0001)
        for v in m["trap_build_rate"].values():
            _finite_in_range(v, 0.0, 1.0001)

        # roles_by_third has all three thirds
        assert set(m["roles_by_third"].keys()) == {0, 1, 2}


def test_build_report_smoke(tmp_path):
    audit = sa.run_audit(num_games=8, seed=1)
    report = sa.build_report(audit)
    assert isinstance(report, str)
    assert "RL Strategy Audit" in report
    assert "VERDICT" in report
    # per-agent sections present
    assert "Heuristic" in report
    assert "Random" in report
