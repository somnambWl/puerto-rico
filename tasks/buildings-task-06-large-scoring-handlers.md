# Task 06: Large Beige Scoring Handlers (SCORE_END)

## Status
not started

## Epic
buildings

## Dependencies
- buildings-task-01
- buildings-task-02
- buildings-task-03

## Overview
Implement the end-game `SCORE_END` handlers for the five large beige buildings. Each scores its base 4 VP regardless of occupancy; the variable extra applies **only when the building is occupied** (≥1 colonist).

## Design References
- `design/03-buildings-reference.md`
- `design/01-engine-core-and-state.md`

## Files to Create/Modify
| File | Action | Changes |
|------|--------|---------|
| `puerto_rico/engine/buildings.py` | Modify | Register the 5 SCORE_END handlers |
| `puerto_rico/engine/test_buildings_scoring_handlers.py` | Create | Per-building scoring + occupancy tests |

## Specification
Each handler registered at `(BuildingId, Timing.SCORE_END)`. Base VP (4 each) is counted by normal end-game building VP scoring regardless of occupancy; these handlers add **only the extra**, and **only if the building is occupied**. Each handler must early-return 0 / add nothing when its building is unoccupied. Add the computed extra to the player's end VP (via `ctx` accumulator).

### Guild hall — `(GUILD_HALL, SCORE_END)`
- `+1` per **small** production building owned, `+2` per **large** production building owned (owned whether occupied or not).
- Small production = SMALL_INDIGO, SMALL_SUGAR. Large production = INDIGO_PLANT, SUGAR_MILL, TOBACCO_STORAGE, COFFEE_ROASTER.
- Use `owned_production_counts(player) -> {small, large}` helper (Task 08).

### Residence — `(RESIDENCE, SCORE_END)`
- Extra VP by number of **filled island spaces** (occupied plantation/quarry tiles):
  - ≤9 filled → +4
  - 10 → +5
  - 11 → +6
  - 12 → +7

### Fortress — `(FORTRESS, SCORE_END)`
- `+1` per **3 colonists on the board**, counting island + city + stored colonists (floor division).

### Customs house — `(CUSTOMS_HOUSE, SCORE_END)`
- `+1` per **4 VP chips** the player holds (building/printed VP excluded — only earned VP chips), floor division.

### City hall — `(CITY_HALL, SCORE_END)`
- `+1` per **beige building owned** (counts itself). Beige = all non-production buildings (the 12 small + 5 large).

## Verification
Run `pytest puerto_rico/engine/test_buildings_scoring_handlers.py`.

Expected behavior (each in isolation, building occupied unless noted):
- Guild hall with e.g. 2 small + 1 large production building → +(2*1 + 1*2) = +4.
- Residence with 11 filled island spaces → +6; with 9 or fewer → +4; with 12 → +7.
- Fortress with 7 colonists on board → +2 (7//3).
- Customs house with 9 VP chips → +2 (9//4).
- City hall with 4 beige buildings owned (including itself) → +4.
- For every large building: when **unoccupied**, the SCORE_END handler adds **0** extra (base 4 still counted elsewhere).
