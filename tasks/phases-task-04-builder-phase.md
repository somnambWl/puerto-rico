# Task 04: BUILDER Phase

## Status
not started

## Epic
engine-phases

## Dependencies
- phases-task-01
- engine-core-task-07
- engine-core-task-02
- buildings-task-NN (soft: buildings catalog, university — stub the hook if buildings epic not yet done)

## Overview
Implement the builder role: each player may buy one building, paying printed cost reduced by chooser privilege, occupied quarries, and hooks. Handles building-space limits and the 12-building end trigger.

## Design References
- `design/02-engine-phases-and-flow.md`
- `design/03-buildings-reference.md`
- `design/01-engine-core-and-state.md`

## Files to Create/Modify
| File | Action | Changes |
|------|--------|---------|
| `puerto_rico/engine/phases.py` | Modify | `builder_legal_actions()`, `builder_apply()`, `builder_last_duty()` |
| `puerto_rico/engine/test_phases.py` | Modify | Builder phase tests |

## Specification
- Cost computation for a building for the acting player:
  - `cost = printed_cost − (1 if chooser else 0) − min(occupied_quarries, cost_column) − other_hooks`, floored at 0.
  - `cost_column` is the building's quarry-discount cap (the max number of quarries that can apply to that building, per the buildings reference / production cost tier).
- `PASS` is always legal.
- `BUILD(building)` is legal iff ALL of:
  - The player can afford the computed cost (doubloons >= cost).
  - The building is still available in the supply (a copy remains).
  - The player does not already own that building (no duplicates per player).
  - There is room in the city: a building needs 1 empty building space; a large (1x2) building needs 2 adjacent empty spaces.
- Auto-placement: the new building occupies the lowest-index empty building space(s). A large building occupies 2 adjacent empty spaces — document the representation (e.g. the building records both space indices it spans).
- University hook: if the acting player owns an occupied university, one free colonist from the supply is placed onto the newly built building. (Stub if buildings not done.)
- End trigger: when any player builds such that they now occupy all 12 building spaces (the 12th space is filled), set `end_triggered = True` (builder end trigger — see `phases-task-09`).
- Edge cases: cost floors at 0 (free build still requires room and supply); a player with a full city can only PASS; quarry discount never exceeds the building's `cost_column`.

## Verification
- `pytest puerto_rico/engine/test_phases.py -k builder`
  - Expected: chooser pays 1 less; quarry discount capped by `cost_column`; cost floors at 0.
  - Expected: cannot build duplicate, unaffordable, out-of-supply, or no-room building; large needs 2 adjacent.
  - Expected: building the 12th space sets `end_triggered`.
  - Expected (if implemented): university occupies the new building.
