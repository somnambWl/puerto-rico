# Task 02: State Data Structures

## Status
done

## Epic
engine-core

## Dependencies
- engine-core-task-01

## Overview
Define the dataclasses that model the full game state: per-slot, per-player, and global game structures, plus read-only helper methods on `PlayerState`.

## Design References
- `design/00-overview-and-architecture.md`
- `design/01-engine-core-and-state.md`

## Files to Create/Modify
| File | Action | Changes |
|------|--------|---------|
| `puerto_rico/engine/state.py` | Create | Define all state dataclasses + helpers |
| `puerto_rico/engine/test_state.py` | Create | Instantiation + helper tests |

## Specification
All dataclasses use `slots=True`. Imports come from `puerto_rico/engine/enums.py`.

### Slot-level structures
- `IslandSlot`: `tile: TileType = TileType.EMPTY`, `colonist: bool = False`
- `CitySlot`: `building: BuildingId | None = None`, `colonists: int = 0`
- `CargoShip`: `capacity: int`, `good: Good | None = None`, `count: int = 0`
- `RolePlacard`: `role: Role`, `doubloons: int = 0`, `taken_by: int | None = None`

### PlayerState
Fields:
- `doubloons: int`
- `island: list[IslandSlot]` — length 12
- `city: list[CitySlot]` — length 12
- `goods: list[int]` — length 5, indexed by `Good`
- `stored_colonists: int`
- `vp_chips: int`
- `roles_taken_this_round: int = 0`

Read-only helper methods (no mutation):
- `owns(...)` — query ownership of tile/building
- `building_slot(...)` — locate a building's city slot
- `occupied(...)` — whether a slot is occupied
- `total_colonists(...)` — sum of colonists on island + city + stored
- `filled_island_spaces(...)` — count of non-empty island slots
- `empty_building_circles(...)` — count of unoccupied colonist circles across built buildings

(Exact signatures left to the implementer; they must be pure read-only queries over `PlayerState`.)

### GameConfig
`@dataclass(slots=True, frozen=True)`:
- `num_players: int = 4`
- `seed: int | None = None`
- `ruleset: str = "base"`

### GameState
`@dataclass(slots=True)` holding the full mutable game:
- `config: GameConfig`
- `rng: random.Random`
- `players: list[PlayerState]`
- `governor: int`
- `current_player: int`
- `phase: Phase`
- `placards: list[RolePlacard]`
- `colonist_ship: int`
- `colonist_supply: int`
- `cargo_ships: list[CargoShip]`
- `trading_house: list[Good]`
- `goods_supply: list[int]` — length 5
- `plantation_faceup: list[TileType]`
- `plantation_facedown: list[TileType]`
- `plantation_discard: list[TileType]`
- `quarry_supply: int`
- `vp_chips_remaining: int`
- `buildings_supply: dict[BuildingId, int]`
- `phase_state: PhaseState` — stub type for this milestone (a placeholder dataclass; full per-phase substate is defined in the engine-phases epic)
- `end_triggered: bool = False`

### Large buildings
Large buildings occupy two adjacent city slots. Document the chosen representation in the module: recommended approach is to store the real `BuildingId` in the first slot and `BuildingId.LARGE_CONT` (sentinel from task 01) in the second slot, so iteration over `city` never double-counts a large building.

## Notes
Downstream epics (engine-phases, buildings) build directly on these structures. Keep helpers minimal and read-only here; mutation logic belongs to later phase/building tasks.

## Verification
Run `pytest puerto_rico/engine/test_state.py`.

Expected behavior:
- A `GameState` (and all nested dataclasses) can be instantiated.
- `island` and `city` lists are present and length 12; `goods` and `goods_supply` length 5.
- `PlayerState` helpers return correct values on small hand-built fixtures (e.g. `total_colonists`, `filled_island_spaces`, `empty_building_circles`).
