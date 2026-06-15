"""Core game-state data structures for the Puerto Rico engine.

This module defines the dataclasses that model the full game state: per-slot,
per-player, and global structures, plus read-only helper queries on
``PlayerState``. All mutation logic (setup, phase transitions, building
effects, cloning, serialization) belongs to other modules/epics.

Conventions:
- Every dataclass uses ``slots=True``; ``GameConfig`` is additionally frozen.
- Counts are plain ints; there are no cross-player object references.
- ``goods`` arrays are length 5, indexed by ``Good``.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from .enums import BuildingId, Good, Phase, Role, TileType
from .phase_state import PhaseState


@dataclass(slots=True)
class IslandSlot:
    """One island space: a single tile that may hold one colonist.

    A plantation/quarry tile holds exactly 0 or 1 colonist. ``EMPTY`` means no
    tile is placed here. Slot position carries no rules meaning; the list is
    just storage.
    """

    tile: TileType = TileType.EMPTY
    colonist: bool = False


@dataclass(slots=True)
class CitySlot:
    """One city space: a building and the colonists manning its circles.

    Large-building representation: a large building occupies two adjacent city
    slots. We store the real ``BuildingId`` in the FIRST slot and the sentinel
    ``BuildingId.LARGE_CONT`` in the SECOND (continuation) slot. This lets code
    iterate over ``city`` without double-counting a large building: real
    buildings are exactly the slots whose ``building`` is not ``None`` and not
    ``LARGE_CONT``. Per-building capacity / is-large are looked up from the
    building spec (buildings epic), not stored on the slot.
    """

    building: BuildingId | None = None
    colonists: int = 0


@dataclass(slots=True)
class CargoShip:
    """A shared cargo ship that holds a single good kind up to ``capacity``."""

    capacity: int
    good: Good | None = None
    count: int = 0


@dataclass(slots=True)
class RolePlacard:
    """A role placard, possibly carrying accumulated doubloons from skips."""

    role: Role
    doubloons: int = 0
    taken_by: int | None = None


@dataclass(slots=True)
class PlayerState:
    """All per-player state. Helper methods are pure read-only queries."""

    doubloons: int
    island: list[IslandSlot]  # len 12
    city: list[CitySlot]  # len 12
    goods: list[int]  # len 5, indexed by Good
    stored_colonists: int
    vp_chips: int
    roles_taken_this_round: int = 0

    # --- read-only helpers (no mutation) ---

    def owns(self, building_id: BuildingId) -> bool:
        """Whether the player has built ``building_id`` in their city."""
        return self.building_slot(building_id) is not None

    def building_slot(self, building_id: BuildingId) -> int | None:
        """Index of the city slot holding ``building_id``, or ``None``.

        Returns the first matching slot. ``LARGE_CONT`` continuation slots are
        never matched here because a real building is never queried as
        ``LARGE_CONT``.
        """
        for i, slot in enumerate(self.city):
            if slot.building == building_id:
                return i
        return None

    def occupied(self, building_id: BuildingId) -> bool:
        """Whether ``building_id`` is built AND has at least one colonist."""
        idx = self.building_slot(building_id)
        if idx is None:
            return False
        return self.city[idx].colonists > 0

    def total_colonists(self) -> int:
        """All colonists controlled by this player: island + city + stored."""
        island = sum(1 for s in self.island if s.colonist)
        city = sum(s.colonists for s in self.city)
        return island + city + self.stored_colonists

    def filled_island_spaces(self) -> int:
        """Count of island slots that hold a tile (non-``EMPTY``)."""
        return sum(1 for s in self.island if s.tile != TileType.EMPTY)

    def empty_building_circles(self) -> int:
        """Total unoccupied colonist circles across all built buildings.

        Sums ``capacity - colonists`` over every real building (skipping empty
        slots and ``LARGE_CONT`` continuation slots). Per-building capacity is
        looked up from the building spec via ``_building_capacity``.
        """
        total = 0
        for slot in self.city:
            if slot.building is None or slot.building == BuildingId.LARGE_CONT:
                continue
            total += _building_capacity(slot.building) - slot.colonists
        return total


def _building_capacity(building_id: BuildingId) -> int:
    """Colonist-circle capacity for a building, from the buildings catalog.

    Looks up the real capacity in ``buildings.CATALOG`` (design/03). ``buildings``
    is imported lazily here to keep ``state`` import-light and avoid any import
    ordering concerns (``buildings`` itself only depends on ``enums``).
    """
    from .buildings import CATALOG

    return CATALOG[building_id].capacity


@dataclass(slots=True, frozen=True)
class GameConfig:
    """Immutable game configuration."""

    num_players: int = 4
    seed: int | None = None
    ruleset: str = "base"
    # SAFETY VALVE until phases-09 end triggers exist: force GAME_OVER after this
    # many completed rounds so random playthroughs always terminate. The real
    # end conditions are colonist-shortage / 12th-building / VP-exhaustion
    # (design/02 §Game End); once those land this cap should never fire in a real
    # game. See phases.py:end_of_round.
    max_rounds: int = 50


@dataclass(slots=True)
class GameState:
    """The full mutable game state."""

    config: GameConfig
    rng: random.Random
    players: list[PlayerState]
    governor: int
    current_player: int
    phase: Phase
    placards: list[RolePlacard]
    colonist_ship: int
    colonist_supply: int
    cargo_ships: list[CargoShip]
    trading_house: list[Good]
    goods_supply: list[int]  # len 5
    plantation_faceup: list[TileType]
    plantation_facedown: list[TileType]
    plantation_discard: list[TileType]
    quarry_supply: int
    vp_chips_remaining: int
    buildings_supply: dict[BuildingId, int]
    phase_state: PhaseState
    end_triggered: bool = False
    # Number of FULLY COMPLETED rounds so far (incremented in end_of_round).
    # Used only by the max_rounds safety valve (see GameConfig.max_rounds).
    round_number: int = 0

    def clone(self) -> "GameState":
        """Return a fully independent deep copy for the simulation hot path.

        Mutating the clone never affects the original and vice versa. This is
        the copy used before ``apply()`` during tree search / RL rollouts, so
        it avoids ``copy.deepcopy`` on the whole state and reconstructs the
        mutable nested structures explicitly for speed.

        What is COPIED (independent in the clone):
        - ``players`` and, per player, the ``island`` (list of ``IslandSlot``),
          ``city`` (list of ``CitySlot``) and ``goods`` lists.
        - ``placards`` (list of ``RolePlacard``), ``cargo_ships`` (list of
          ``CargoShip``), ``trading_house``, ``goods_supply``,
          ``plantation_faceup`` / ``_facedown`` / ``_discard`` lists.
        - ``buildings_supply`` (fresh dict).
        - ``phase_state`` and its mutable fields (``order`` list,
          ``captain_done`` set, ``sub`` dict).
        - ``rng`` is FORKED: a fresh ``random.Random`` whose internal state is
          copied via ``getstate()``/``setstate()``. The clone's generator is a
          distinct object that currently produces the same sequence as the
          source; advancing one does not advance the other.

        What is SHARED by reference (safe because immutable / value types):
        - ``config`` (``GameConfig`` is frozen).
        - Enum members (``Good``, ``Role``, ``Phase``, ``TileType``,
          ``BuildingId``) and plain-int scalar fields, which are immutable.
        """
        # Fork the RNG: independent generator, currently identical sequence.
        rng = random.Random()
        rng.setstate(self.rng.getstate())

        players = [
            PlayerState(
                doubloons=p.doubloons,
                island=[IslandSlot(tile=s.tile, colonist=s.colonist) for s in p.island],
                city=[CitySlot(building=s.building, colonists=s.colonists) for s in p.city],
                goods=p.goods.copy(),
                stored_colonists=p.stored_colonists,
                vp_chips=p.vp_chips,
                roles_taken_this_round=p.roles_taken_this_round,
            )
            for p in self.players
        ]

        ps = self.phase_state
        phase_state = PhaseState(
            role_chooser=ps.role_chooser,
            active_role=ps.active_role,
            order=ps.order.copy(),
            order_pos=ps.order_pos,
            colonists_to_place=ps.colonists_to_place,
            captain_done=ps.captain_done.copy(),
            # Deep-copy sub's mutable values: captain stores ``wharf_used`` and
            # ``first_load_done`` sets, craftsman stores a ``chooser_kinds`` set.
            # A shallow ``dict(ps.sub)`` would leave these shared with the clone,
            # so mutating one corrupts the other (breaks MCTS/RL rollouts).
            sub=None
            if ps.sub is None
            else {
                k: (v.copy() if isinstance(v, (set, list, dict)) else v)
                for k, v in ps.sub.items()
            },
        )

        return GameState(
            config=self.config,  # frozen, safe to share
            rng=rng,
            players=players,
            governor=self.governor,
            current_player=self.current_player,
            phase=self.phase,
            placards=[
                RolePlacard(role=pl.role, doubloons=pl.doubloons, taken_by=pl.taken_by)
                for pl in self.placards
            ],
            colonist_ship=self.colonist_ship,
            colonist_supply=self.colonist_supply,
            cargo_ships=[
                CargoShip(capacity=c.capacity, good=c.good, count=c.count)
                for c in self.cargo_ships
            ],
            trading_house=self.trading_house.copy(),
            goods_supply=self.goods_supply.copy(),
            plantation_faceup=self.plantation_faceup.copy(),
            plantation_facedown=self.plantation_facedown.copy(),
            plantation_discard=self.plantation_discard.copy(),
            quarry_supply=self.quarry_supply,
            vp_chips_remaining=self.vp_chips_remaining,
            buildings_supply=dict(self.buildings_supply),
            phase_state=phase_state,
            end_triggered=self.end_triggered,
            round_number=self.round_number,
        )
