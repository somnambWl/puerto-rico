"""The flat, immutable action protocol for the Puerto Rico engine.

An :class:`Action` is a single small dataclass that represents *every* kind of
atomic player decision. There are deliberately **no subclasses**: the action is
tagged by its :class:`~puerto_rico.engine.enums.DecisionType` in the ``type``
field, and ``apply()`` dispatches on ``action.type``. The remaining fields form
a flat union — only the fields relevant to a given ``type`` are set; all others
stay ``None``.

Design rationale:

* **Flat** — one dataclass keeps ``legal_actions()`` cheap to build and avoids
  ``isinstance`` dispatch in the hot path.
* **Immutable** (``frozen=True``) — actions are pure values that can be freely
  shared, cached, and stored.
* **Hashable** — frozen dataclasses are hashable by value, so an ``Action`` can
  be a dict key or set member. This enables a stable ``Action``→int mapping for
  the RL action space (see design/04).

Convenience ``@staticmethod`` constructors are provided for readability at the
many construction sites downstream; they are thin wrappers that only set the
fields relevant to each decision kind.
"""

from __future__ import annotations

from dataclasses import dataclass

from .enums import BuildingId, DecisionType, Good, Role, TileType


@dataclass(slots=True, frozen=True)
class Action:
    """A single atomic player decision, tagged by ``type``.

    Only the fields relevant to ``type`` are populated; the rest stay ``None``.
    Equality and hashing are by value (all fields), so distinct decisions are
    distinct values.
    """

    type: DecisionType
    role: Role | None = None
    tile: TileType | None = None
    target: int | None = None
    good: Good | None = None
    building: BuildingId | None = None
    choice: int | None = None

    # --- convenience constructors -------------------------------------------

    @staticmethod
    def select_role(role: Role) -> "Action":
        """Role selection: choose a role placard."""
        return Action(DecisionType.SELECT_ROLE, role=role)

    @staticmethod
    def take_tile(tile: TileType) -> "Action":
        """Settler: take a plantation (or quarry) tile of the given kind."""
        return Action(DecisionType.TAKE_TILE, tile=tile)

    @staticmethod
    def place_colonist(target: int) -> "Action":
        """Mayor: place one colonist on the circle at slot index ``target``."""
        return Action(DecisionType.PLACE_COLONIST, target=target)

    @staticmethod
    def build(building: BuildingId) -> "Action":
        """Builder: build one building."""
        return Action(DecisionType.BUILD, building=building)

    @staticmethod
    def sell(good: Good) -> "Action":
        """Trader: sell one good to the trading house."""
        return Action(DecisionType.SELL, good=good)

    @staticmethod
    def load(good: Good, target: int | None = None) -> "Action":
        """Captain: load a good kind onto a ship (``target`` = ship index)."""
        return Action(DecisionType.LOAD, good=good, target=target)

    @staticmethod
    def choose(choice: int) -> "Action":
        """Generic enumerated building sub-choice."""
        return Action(DecisionType.CHOOSE, choice=choice)

    @staticmethod
    def passing() -> "Action":
        """Decline an optional action."""
        return Action(DecisionType.PASS)
