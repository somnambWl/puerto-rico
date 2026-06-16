"""Reward modes + optional dense shaping for self-play training (design/05).

4-player Puerto Rico is **general-sum** — there is no single opponent to be ±1
against — so the default terminal reward is standing-based (``rank``), not a
zero-sum win/lose. This module is the single place training selects a reward
mode and (optionally) anneals a dense shaping coefficient to zero.

Reward modes (see :data:`MODES`):

- **``"rank"`` (default):** map final placement to evenly-spaced, zero-mean
  rewards from ``+1`` (1st) down to ``−1`` (last). For 4 players that is
  ``[+1, +1/3, −1/3, −1]``. Genuinely-tied players (identical
  :func:`scoring.tiebreak_key`) share the averaged reward of the ranks they
  span, so the vector always sums to ~0. This matches and reuses the historical
  ``Game.returns()`` rank logic.
- **``"win"``:** ``+1`` to the winner, ``0`` to everyone else. Sparser; ablation
  only. Ties on the full tie-break key are split *evenly* among the tied top
  players (so the total awarded stays ``+1``) — in practice the
  ``-player_idx`` discriminator in ``tiebreak_key`` makes the order total, so
  there is a unique winner, but the split keeps the contract well-defined.
- **``"vp_margin"``:** z-scored final VP across the table (mean 0, unit std). If
  every player has the same VP (std == 0) returns all zeros. Smoothest signal —
  use for early bootstrapping, then switch to ``rank``.

Dense shaping (:class:`ShapingSchedule` + :func:`round_shaping`) is additive to
the terminal mode and **must anneal to 0** by the end of training so it cannot
distort the standing-based objective. It is pure/optional and applied at the end
of each round.

This module depends only on :mod:`puerto_rico.engine.scoring` (no env import),
so the env can call :func:`terminal_rewards` without an import cycle.
"""

from __future__ import annotations

from ..engine import scoring
from ..engine.state import GameState

#: Canonical reward-mode identifiers and the training default.
RANK = "rank"
WIN = "win"
VP_MARGIN = "vp_margin"
MODES: tuple[str, ...] = (RANK, WIN, VP_MARGIN)
DEFAULT_MODE: str = RANK


def _rank_rewards(state: GameState) -> list[float]:
    """Zero-mean, evenly-spaced rank rewards (1st → +1 ... last → −1).

    Mirrors the historical ``Game.returns()`` logic: rank best-first via
    :func:`scoring.rankings`, assign targets evenly spaced from ``+1`` to
    ``−1``, and let any genuinely-tied players share the averaged target of the
    ranks they span. The vector sums to ~0.
    """
    n = len(state.players)
    if n == 1:
        return [0.0]

    targets = [1.0 - 2.0 * i / (n - 1) for i in range(n)]
    order = scoring.rankings(state)
    rewards = [0.0] * n
    i = 0
    while i < n:
        j = i
        key_i = scoring.tiebreak_key(state, order[i])
        while j + 1 < n and scoring.tiebreak_key(state, order[j + 1]) == key_i:
            j += 1
        avg = sum(targets[i : j + 1]) / (j - i + 1)
        for k in range(i, j + 1):
            rewards[order[k]] = avg
        i = j + 1
    return rewards


def _win_rewards(state: GameState) -> list[float]:
    """``+1`` to the winner(s), ``0`` otherwise; split evenly if tied at top."""
    n = len(state.players)
    if n == 1:
        return [0.0]
    order = scoring.rankings(state)
    top_key = scoring.tiebreak_key(state, order[0])
    winners = [p for p in order if scoring.tiebreak_key(state, p) == top_key]
    share = 1.0 / len(winners)
    rewards = [0.0] * n
    for p in winners:
        rewards[p] = share
    return rewards


def _vp_margin_rewards(state: GameState) -> list[float]:
    """Z-scored final VP across the table (mean 0, unit std; zeros if std==0)."""
    scores = [float(s) for s in scoring.final_scores(state)]
    n = len(scores)
    if n == 0:
        return []
    mean = sum(scores) / n
    var = sum((s - mean) ** 2 for s in scores) / n
    std = var ** 0.5
    if std == 0.0:
        return [0.0] * n
    return [(s - mean) / std for s in scores]


def terminal_rewards(state: GameState, mode: str = DEFAULT_MODE) -> list[float]:
    """Terminal per-seat rewards for ``mode``; zeros if ``state`` is not terminal.

    ``mode`` is one of :data:`MODES`. Non-terminal states (or an empty table)
    return all zeros. See the module docstring for each mode's exact formula and
    tie handling.
    """
    from ..engine.enums import Phase

    n = len(state.players)
    if state.phase != Phase.GAME_OVER:
        return [0.0] * n

    if mode == RANK:
        return _rank_rewards(state)
    if mode == WIN:
        return _win_rewards(state)
    if mode == VP_MARGIN:
        return _vp_margin_rewards(state)
    raise ValueError(f"unknown reward_mode {mode!r}; expected one of {MODES}")


class ShapingSchedule:
    """Linear anneal of a dense-shaping coefficient from ``coef0`` to 0.

    ``coef(step)`` is ``coef0`` at ``step == 0``, decreases linearly, and is
    clamped to ``0`` at/after ``horizon`` (and for any ``step > horizon``). The
    coefficient must reach 0 by the end of training so shaping cannot distort the
    standing-based terminal objective (design/05).
    """

    __slots__ = ("coef0", "horizon")

    def __init__(self, coef0: float, horizon: int) -> None:
        if horizon <= 0:
            raise ValueError("horizon must be positive")
        self.coef0 = float(coef0)
        self.horizon = int(horizon)

    def coef(self, step: int) -> float:
        """Annealed coefficient at ``step`` (clamped to ``[0, coef0]``)."""
        if step <= 0:
            return self.coef0
        if step >= self.horizon:
            return 0.0
        return self.coef0 * (1.0 - step / self.horizon)


def _vp_advantage(state: GameState, player_idx: int) -> float:
    """``self_vp − mean(other players' vp)`` from :func:`scoring.final_score`."""
    scores = scoring.final_scores(state)
    n = len(scores)
    if n <= 1:
        return float(scores[player_idx]) if n == 1 else 0.0
    others_mean = (sum(scores) - scores[player_idx]) / (n - 1)
    return float(scores[player_idx]) - others_mean


def round_shaping(
    prev_state: GameState,
    new_state: GameState,
    player_idx: int,
    coef: float,
) -> float:
    """Dense end-of-round shaping: ``coef * Δ(self_vp − mean(others_vp))``.

    Pure helper — the per-round change in ``player_idx``'s VP advantage over the
    table mean, scaled by ``coef``. ``coef`` is expected to come from a
    :class:`ShapingSchedule` and **must anneal to 0** by the end of training.
    """
    if coef == 0.0:
        return 0.0
    delta = _vp_advantage(new_state, player_idx) - _vp_advantage(prev_state, player_idx)
    return coef * delta


def building_development_score(state: GameState, seat: int) -> float:
    """Building-derived VP potential for ``seat`` (the "engine" signal).

    Defined as the player's final score MINUS its VP chips::

        building_development_score = scoring.final_score(state, seat) - vp_chips
                                   = printed building VP + occupied large bonuses

    This is exactly the VP a player earns from *acquiring AND manning* buildings
    (especially the large buildings, whose SCORE_END bonus only counts when
    occupied) — the engine the pure-corn-shipping rush skips entirely. It rises
    when the player buys a (scoring) building and rises further when a large
    building's slots are occupied at game end.

    Used as a **potential-based-ish dense shaping signal** by the rollout
    collector: the per-decision change ``Δ building_development_score`` is scaled
    by an annealed coefficient and added to that step's reward before GAE. Like
    all shaping here it MUST anneal to 0 by the end of training so the final
    policy is fine-tuned purely on the standing-based terminal objective
    (design/05). It is measured at the acting seat's decision points, so it acts
    as a difference-of-potentials nudge rather than a permanent reward bias.
    """
    return float(scoring.final_score(state, seat)) - float(
        state.players[seat].vp_chips
    )
