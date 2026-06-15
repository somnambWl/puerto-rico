# Task 01: Define Enums

## Status
not started

## Epic
engine-core

## Dependencies
- None

## Overview
Define the core enumerations used throughout the engine: goods, roles, tile types, phases, decision types, and a placeholder building-id enum. These are the foundational value types every downstream module imports.

## Design References
- `design/00-overview-and-architecture.md`
- `design/01-engine-core-and-state.md`

## Files to Create/Modify
| File | Action | Changes |
|------|--------|---------|
| `puerto_rico/engine/enums.py` | Create | Define all core enums |
| `puerto_rico/engine/test_enums.py` | Create | Unit tests for enum members |

## Specification
All enums live in `puerto_rico/engine/enums.py`.

- `Good(IntEnum)`: `CORN=0, INDIGO=1, SUGAR=2, TOBACCO=3, COFFEE=4`
- `Role(IntEnum)`: `SETTLER=0, MAYOR=1, BUILDER=2, CRAFTSMAN=3, TRADER=4, CAPTAIN=5, PROSPECTOR=6`
- `TileType(IntEnum)`: `EMPTY=0, QUARRY=1, CORN=2, INDIGO=3, SUGAR=4, TOBACCO=5, COFFEE=6`
- `Phase(IntEnum)`: `ROLE_SELECTION=0, SETTLER=1, MAYOR=2, BUILDER=3, CRAFTSMAN=4, TRADER=5, CAPTAIN=6, GAME_OVER=7`
- `DecisionType(IntEnum)`: `SELECT_ROLE=0, TAKE_TILE=1, PLACE_COLONIST=2, BUILD=3, SELL=4, LOAD=5, PASS=6, CHOOSE=7`
- `BuildingId(IntEnum)`: placeholder enum for this milestone. Must include a `LARGE_CONT` sentinel value used to mark the second slot occupied by a large (two-slot) building. The full building table is defined in `design/03-buildings-reference.md`; downstream epics (buildings) will expand this enum. Provide enough placeholder members to compile and be referenced by `state.py` and `setup.py`, but the authoritative catalog is deferred.

Use `IntEnum` so values are directly usable as array indices and in the RL action-int mapping. Members must be hashable and have unique values.

## Specification Notes
- `Good` values double as indices into the length-5 goods arrays used elsewhere (`goods`, `goods_supply`).
- Keep the `LARGE_CONT` sentinel clearly documented as "not a real building — marks the continuation slot of a large building."

## Verification
Run `pytest puerto_rico/engine/test_enums.py`.

Expected behavior:
- All enum members are hashable (usable as dict keys / set members).
- Within each enum, all values are unique.
- `Good`, `Role`, `TileType`, `Phase`, `DecisionType` have exactly the members and integer values listed above.
- `BuildingId.LARGE_CONT` exists.
