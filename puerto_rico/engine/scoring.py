"""Final scoring at GAME_OVER (design/02 §Final Scoring, design/03 large buildings).

This module is the single source of truth for end-of-game scoring. ``game.py``
delegates :meth:`Game.returns` / :meth:`Game.winner` here; nothing else
reimplements the totals.

A player's final score is::

    final_score = vp_chips
                + printed VP of every building owned (occupied or not)
                + SCORE_END large-building bonuses

The printed-VP term counts each large building's base 4 VP exactly once (the
``LARGE_CONT`` continuation slot is skipped). Production buildings and small
beige buildings each contribute their catalog ``vp``.

SCORE_END ctx contract
----------------------
The large-building bonuses are delegated to building handlers (buildings-06) via
``buildings.fire(Timing.SCORE_END, state, player_idx, ctx)``. The contract:

- ``ctx.vp`` (mutable int): the bonus accumulator. Each registered SCORE_END
  handler ADDS its building's extra VP to ``ctx.vp``. We seed it at 0 and add
  the result onto the base. (The ``Ctx`` field is named ``vp``; this is the
  "final_vp"/"bonus" accumulator the task refers to.)
- Occupancy: ``buildings.fire`` does NOT gate SCORE_END on occupancy (large
  buildings score their base 4 unoccupied). Per design/03 (line 108-109) and
  docs/puerto-rico-rules.md (line 221): "A building scores its printed VP even
  when unoccupied ... The large buildings' extra scoring applies only when
  occupied." So the BASE 4 is added here unconditionally (it is just the
  building's printed ``vp``), and each SCORE_END handler is responsible for
  gating its own EXTRA on occupancy.

Until the buildings-06 handlers register, ``fire`` is a no-op for SCORE_END, so
the bonus term is 0 and ``final_score`` reduces to vp_chips + printed VP. That
is acceptable for M1 — the base printed VP (including each large building's 4)
still counts.
"""

from __future__ import annotations

from . import buildings
from .buildings import Ctx, Timing
from .enums import BuildingId
from .state import GameState


def _printed_building_vp(player) -> int:
    """Sum of catalog printed VP over every real building the player owns.

    Skips empty slots and ``LARGE_CONT`` continuation slots, so each large
    building's base 4 VP is counted exactly once.
    """
    total = 0
    for slot in player.city:
        bid = slot.building
        if bid is None or bid == BuildingId.LARGE_CONT:
            continue
        total += buildings.CATALOG[bid].vp
    return total


def _score_end_bonus(state: GameState, player_idx: int) -> int:
    """Large-building SCORE_END bonus for one player (0 until buildings-06).

    Fires ``Timing.SCORE_END`` with a fresh ``Ctx`` whose ``vp`` accumulator the
    handlers increment. Occupancy gating is per-handler (see module docstring);
    ``fire`` itself does not enforce it for SCORE_END.
    """
    ctx = Ctx()
    ctx.vp = 0
    buildings.fire(Timing.SCORE_END, state, player_idx, ctx)
    return ctx.vp


def final_score(state: GameState, player_idx: int) -> int:
    """Final VP for one player: vp_chips + printed building VP + SCORE_END bonus."""
    player = state.players[player_idx]
    base = player.vp_chips + _printed_building_vp(player)
    return base + _score_end_bonus(state, player_idx)


def final_scores(state: GameState) -> list[int]:
    """Final VP for every player, in seat order."""
    return [final_score(state, i) for i in range(len(state.players))]


def tiebreak_key(state: GameState, player_idx: int) -> tuple[int, int, int]:
    """Sortable ranking key for ``player_idx`` (higher is better).

    Components, in priority order:
    1. ``final_score`` — total VP (the rules' primary winner test).
    2. ``doubloons + total goods held`` — the rules' tie-break (1 good = 1
       doubloon).
    3. ``-player_idx`` — deterministic final tie-break: the LOWER seat index wins
       (negated so "higher key" still means "wins").
    """
    p = state.players[player_idx]
    score = final_score(state, player_idx)
    wealth = p.doubloons + sum(p.goods)
    return (score, wealth, -player_idx)


def rankings(state: GameState) -> list[int]:
    """Player indices ordered best-to-worst by :func:`tiebreak_key` (descending)."""
    n = len(state.players)
    return sorted(range(n), key=lambda p: tiebreak_key(state, p), reverse=True)
