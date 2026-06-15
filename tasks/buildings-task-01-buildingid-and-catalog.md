# Task 01: BuildingId Enum + CATALOG

## Status
done

## Epic
buildings

## Dependencies
- engine-core-task-01

## Overview
Define the authoritative `BuildingId` enum (all 23 buildings + `LARGE_CONT` sentinel) and the static `CATALOG` of `BuildingSpec` records describing cost, column, VP, capacity, and type for every base-game building.

## Design References
- `design/03-buildings-reference.md`
- `design/01-engine-core-and-state.md`

## Files to Create/Modify
| File | Action | Changes |
|------|--------|---------|
| `puerto_rico/engine/enums.py` | Modify | Expand `BuildingId(IntEnum)` to the full 23 members + `LARGE_CONT` sentinel |
| `puerto_rico/engine/buildings.py` | Create | `Timing` enum, `BuildingSpec` dataclass, `CATALOG` dict, basic helpers |
| `puerto_rico/engine/test_buildings_catalog.py` | Create | Catalog completeness + value tests |

## Specification

### `BuildingId(IntEnum)` (in `enums.py`)
Replace the placeholder enum with all 23 real buildings plus the `LARGE_CONT` sentinel.

Production (6): `SMALL_INDIGO`, `INDIGO_PLANT`, `SMALL_SUGAR`, `SUGAR_MILL`, `TOBACCO_STORAGE`, `COFFEE_ROASTER`.

Small beige (12): `SMALL_MARKET`, `HACIENDA`, `CONSTRUCTION_HUT`, `SMALL_WAREHOUSE`, `HOSPICE`, `OFFICE`, `LARGE_MARKET`, `LARGE_WAREHOUSE`, `FACTORY`, `UNIVERSITY`, `HARBOR`, `WHARF`.

Large beige (5): `GUILD_HALL`, `RESIDENCE`, `FORTRESS`, `CUSTOMS_HOUSE`, `CITY_HALL`.

Sentinel (1): `LARGE_CONT` — not a real building; marks the continuation (second) slot of a large building on the board. Keep its value distinct and clearly out of the 0..22 building range.

Total real buildings = 23. Keep `LARGE_CONT` documented as a sentinel.

### `Timing(IntEnum)` (in `buildings.py`)
```
SETTLER_PLACE      = 0
CRAFTSMAN_PRODUCE  = 1
TRADER_SELL_PRICE  = 2
BUILDER_BUILD      = 3
CAPTAIN_LOAD       = 4
CAPTAIN_STORAGE    = 5
SCORE_END          = 6
```

### `BuildingSpec` dataclass (frozen, slots)
Fields:
- `id: BuildingId`
- `name: str`
- `cost: int`
- `column: int` — 1..4 (quarry-discount cap column on the board)
- `vp: int` — printed base VP
- `capacity: int` — colonist circles (1..3); large buildings = 1
- `is_large: bool`
- `is_production: bool`
- `produces: Good | None` — only set for production buildings
- `timings: tuple[Timing, ...]` — which hooks the building implements

### `CATALOG: dict[BuildingId, BuildingSpec]`
One entry per real building (23 entries; `LARGE_CONT` is NOT in the catalog).

Production buildings (`is_production=True`, `is_large=False`, `timings=()`):

| id | name | cost | col | vp | cap | produces |
|----|------|------|-----|----|-----|----------|
| SMALL_INDIGO | small indigo plant | 1 | 1 | 1 | 1 | INDIGO |
| INDIGO_PLANT | indigo plant | 3 | 2 | 2 | 3 | INDIGO |
| SMALL_SUGAR | small sugar mill | 2 | 1 | 1 | 1 | SUGAR |
| SUGAR_MILL | sugar mill | 4 | 2 | 2 | 3 | SUGAR |
| TOBACCO_STORAGE | tobacco storage | 5 | 3 | 3 | 3 | TOBACCO |
| COFFEE_ROASTER | coffee roaster | 6 | 3 | 3 | 2 | COFFEE |

Small beige buildings (`is_production=False`, `is_large=False`, `produces=None`):

| id | name | cost | col | vp | cap | timings |
|----|------|------|-----|----|-----|---------|
| SMALL_MARKET | small market | 1 | 1 | 1 | 1 | (TRADER_SELL_PRICE,) |
| HACIENDA | hacienda | 2 | 1 | 1 | 1 | (SETTLER_PLACE,) |
| CONSTRUCTION_HUT | construction hut | 2 | 1 | 1 | 1 | (SETTLER_PLACE,) |
| SMALL_WAREHOUSE | small warehouse | 3 | 1 | 1 | 1 | (CAPTAIN_STORAGE,) |
| HOSPICE | hospice | 4 | 2 | 2 | 1 | (SETTLER_PLACE,) |
| OFFICE | office | 5 | 2 | 2 | 1 | (TRADER_SELL_PRICE,) |
| LARGE_MARKET | large market | 5 | 2 | 2 | 1 | (TRADER_SELL_PRICE,) |
| LARGE_WAREHOUSE | large warehouse | 6 | 2 | 2 | 1 | (CAPTAIN_STORAGE,) |
| FACTORY | factory | 7 | 3 | 3 | 1 | (CRAFTSMAN_PRODUCE,) |
| UNIVERSITY | university | 8 | 3 | 3 | 1 | (BUILDER_BUILD,) |
| HARBOR | harbor | 8 | 3 | 3 | 1 | (CAPTAIN_LOAD,) |
| WHARF | wharf | 9 | 3 | 3 | 1 | (CAPTAIN_LOAD,) |

Large beige buildings (`is_production=False`, `is_large=True`, `produces=None`, `cost=10`, `column=4`, `vp=4`, `capacity=1`, `timings=(SCORE_END,)`):

| id | name |
|----|------|
| GUILD_HALL | guild hall |
| RESIDENCE | residence |
| FORTRESS | fortress |
| CUSTOMS_HOUSE | customs house |
| CITY_HALL | city hall |

### Minimal helpers (in `buildings.py`)
- `get_spec(building_id) -> BuildingSpec` — lookup in `CATALOG`.
- `is_beige(building_id) -> bool` — `not spec.is_production` (and not the sentinel).
- `is_production(building_id) -> bool` — `spec.is_production`.
- `production_size(building_id) -> "small" | "large"` — "small" for SMALL_INDIGO/SMALL_SUGAR, "large" for INDIGO_PLANT/SUGAR_MILL/TOBACCO_STORAGE/COFFEE_ROASTER; undefined/raise for non-production ids.

(Task 08 hardens/extends these helpers; this task only needs them present enough to support catalog tests.)

## Verification
Run `pytest puerto_rico/engine/test_buildings_catalog.py`.

Expected behavior:
- `len(CATALOG) == 23` and `LARGE_CONT not in CATALOG`.
- `BuildingId.LARGE_CONT` exists and is distinct from all 23 building ids.
- Every catalog entry's cost/column/vp/capacity/produces matches the tables above.
- All 6 production specs have `is_production=True` and `timings == ()`.
- All 5 large specs have `is_large=True`, `cost==10`, `column==4`, `vp==4`, `capacity==1`.
- `production_size(SMALL_INDIGO) == "small"`, `production_size(INDIGO_PLANT) == "large"`.
