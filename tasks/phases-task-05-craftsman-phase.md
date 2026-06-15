# Task 05: CRAFTSMAN Phase

## Status
not started

## Epic
engine-phases

## Dependencies
- phases-task-01
- engine-core-task-07
- engine-core-task-02
- buildings-task-NN (soft: factory, production buildings — stub the hooks if buildings epic not yet done)

## Overview
Implement the craftsman role: every player produces goods deterministically based on manned production capacity and occupied plantations; the chooser gets one extra good of choice. Includes the factory doubloon bonus.

## Design References
- `design/02-engine-phases-and-flow.md`
- `design/03-buildings-reference.md`
- `design/01-engine-core-and-state.md`

## Files to Create/Modify
| File | Action | Changes |
|------|--------|---------|
| `puerto_rico/engine/phases.py` | Modify | `craftsman_legal_actions()`, `craftsman_apply()`, `craftsman_last_duty()` |
| `puerto_rico/engine/test_phases.py` | Modify | Craftsman phase tests |

## Specification
- Production is deterministic for every player (no player choice except the chooser privilege good):
  - For each good kind, `output = min(manned_production_circles_for_kind, occupied_plantations_of_kind, goods_supply_for_kind)`.
  - Corn requires NO production building — its output is just `min(occupied_corn_plantations, corn_supply)`.
  - For non-corn goods (indigo, sugar, tobacco, coffee), output is capped by occupied production-building circles of the matching kind (small/large production buildings).
  - Add produced goods to each player's stored goods and decrement the corresponding goods supply.
- Factory hook (per player, after that player's production): bonus doubloons based on the number of DISTINCT good kinds produced this craftsman phase:
  - 2 kinds -> +1, 3 kinds -> +2, 4 kinds -> +3, 5 kinds -> +5. (1 or 0 kinds -> +0.)
  - (Stub if buildings epic not done.)
- Chooser privilege (after all production): the chooser may `CHOOSE` 1 extra good of any kind that was produced this phase, provided that good's supply still has at least 1 remaining. `PASS` if no eligible good (nothing produced this phase, or all eligible supplies empty).
- Edge cases: supply caps can reduce output (distribute deterministically — produce in a fixed kind order until supply runs out); the privilege good must be a kind actually produced AND still in supply.

## Verification
- `pytest puerto_rico/engine/test_phases.py -k craftsman`
  - Expected: output = min(manned circles, occupied plantations, supply); corn needs no building.
  - Expected: goods supply decremented; production stops when a supply is exhausted.
  - Expected: chooser gets exactly one extra produced-kind good (or PASS if none eligible).
  - Expected (if implemented): factory pays 1/2/3/5 doubloons for 2/3/4/5 distinct kinds.
