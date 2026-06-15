"""The per-phase FSM substate cursor (``PhaseState``).

``PhaseState`` is the finite-state-machine cursor for the active phase. It
records, within the active phase, the player order and where we are in it, plus
any per-player sub-state. ``state.phase`` says *which* phase we are in;
``state.phase_state`` says *where inside it*.

Owned by the **engine-phases** epic (design/02). The round/phase state machine
(``phases.py``) reads and mutates these fields; role-phase tasks (phases-02..08)
use ``order`` / ``order_pos`` and the per-role scratch fields
(``colonists_to_place``, ``captain_done``, ``sub``).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .enums import Role


@dataclass(slots=True)
class PhaseState:
    """FSM cursor for the active phase.

    Fields:
    - ``role_chooser``: during ROLE_SELECTION, the player index choosing next.
    - ``active_role``: the role currently being resolved (``None`` during
      ROLE_SELECTION).
    - ``order``: resolution order for the active role — the chooser first, then
      the remaining players clockwise.
    - ``order_pos``: index into ``order`` of the player whose action is pending.
    - ``colonists_to_place``: MAYOR scratch — colonists the current player still
      must place in the placement sub-phase.
    - ``captain_done``: CAPTAIN scratch — players who can no longer load.
    - ``sub``: transient per-role sub-decision state (e.g. a pending hacienda
      tile, captain goods-storage). ``None`` when no sub-state is active.

    All fields have benign defaults so a fresh ``PhaseState()`` is a valid
    ROLE_SELECTION cursor for player 0.
    """

    role_chooser: int = 0
    active_role: Role | None = None
    order: list[int] = field(default_factory=list)
    order_pos: int = 0
    colonists_to_place: int = 0
    captain_done: set[int] = field(default_factory=set)
    sub: dict | None = None
