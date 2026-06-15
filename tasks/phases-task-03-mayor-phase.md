# Task 03: MAYOR Phase

## Status
done

## Epic
engine-phases

## Dependencies
- phases-task-01
- engine-core-task-07
- engine-core-task-02

## Overview
Implement the mayor role: distribute colonists from the colonist ship (chooser gets the privilege colonist from supply), then a placement sub-phase where each player assigns their stored colonists to building/plantation circles.

## Design References
- `design/02-engine-phases-and-flow.md`
- `design/01-engine-core-and-state.md`

## Files to Create/Modify
| File | Action | Changes |
|------|--------|---------|
| `puerto_rico/engine/phases.py` | Modify | `mayor_legal_actions()`, `mayor_apply()`, `mayor_last_duty()` and placement sub-phase |
| `puerto_rico/engine/test_phases.py` | Modify | Mayor phase tests |

## Specification
- Distribution step (automatic, no player actions):
  - The chooser first takes 1 colonist from the supply (mayor privilege) into their `stored_colonists`.
  - Then colonists are drawn from the colonist ship one at a time, going around the table starting at the chooser, clockwise, until the ship is empty. Each drawn colonist goes to that player's `stored_colonists`.
- Placement sub-phase (uses `PhaseState.sub`): for each player in `order` (starting at chooser, clockwise):
  - First, lift ALL of that player's placed colonists back into `stored_colonists` (colonists are freely redistributable each mayor phase).
  - Then the player issues `PLACE_COLONIST(target=circle)` actions, one per still-stored colonist, each onto an empty building or plantation circle.
  - `PLACE_COLONIST(target=STORE)` is only legal when there are NO empty circles remaining on that player's board (excess colonists stay in storage).
- `colonists_to_place` cursor tracks remaining stored colonists for the current player during placement.
- Last duty (after all placements, by chooser/end of phase):
  - Refill the colonist ship from the supply: place enough colonists to fill ALL currently empty building circles across all players, but at least `num_players`.
  - If the supply has insufficient colonists to meet that count, place what remains and set `end_triggered = True` (colonist-shortage end trigger — see `phases-task-09`).
- Edge cases: a player with more stored colonists than empty circles keeps the excess in storage; supply can be exactly emptied; ship refill count = `max(num_players, total_empty_circles)` clamped by supply.

## Verification
- `pytest puerto_rico/engine/test_phases.py -k mayor`
  - Expected: chooser receives the privilege colonist plus their share from the ship.
  - Expected: placement lifts existing colonists first; STORE only legal when board full.
  - Expected: ship refills to `max(num_players, empty_circles)`; supply shortage sets `end_triggered`.
