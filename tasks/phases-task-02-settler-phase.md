# Task 02: SETTLER Phase

## Status
not started

## Epic
engine-phases

## Dependencies
- phases-task-01
- engine-core-task-07
- engine-core-task-02
- buildings-task-NN (soft: hacienda, hospice, construction-hut — stub the hooks if buildings epic not yet done)

## Overview
Implement the settler role: each player in turn takes one plantation (or quarry) tile and places it on an empty island slot, with hacienda/hospice/construction-hut hooks.

## Design References
- `design/02-engine-phases-and-flow.md`
- `design/01-engine-core-and-state.md`

## Files to Create/Modify
| File | Action | Changes |
|------|--------|---------|
| `puerto_rico/engine/phases.py` | Modify | `settler_legal_actions()`, `settler_apply()`, `settler_last_duty()` |
| `puerto_rico/engine/test_phases.py` | Modify | Settler phase tests |

## Specification
- Resolution order: `order` starts at the chooser, clockwise.
- Legal actions for the acting player:
  - `TAKE_TILE` for each distinct face-up plantation currently available.
  - `TAKE_TILE(QUARRY)` only if the acting player is the chooser OR has an occupied construction hut. Non-choosers without an occupied construction hut may NOT take a quarry.
  - If the player's island is full (no empty slots), the only legal action is `PASS`.
- Auto-placement: the taken tile is placed automatically onto the lowest-index empty island slot (deterministic drop target — no separate placement action needed).
- Hacienda hook: if the acting player is the chooser (privilege) and owns an occupied hacienda, they first take an extra face-down tile from the stack and place it (auto lowest empty slot) BEFORE taking their chosen face-up tile. (If buildings epic not done, stub this hook to a no-op.)
- Hospice hook: if the player owns an occupied hospice, a free colonist from the supply is placed onto the newly placed tile (making it occupied immediately). (Stub if buildings not done.)
- Last duty (after all players have acted, performed by chooser/end of phase):
  1. Discard all remaining face-up plantation tiles.
  2. Draw `num_players + 1` plantation tiles face-up from the stack.
  3. If the draw stack is empty mid-draw, reshuffle the discard pile into a new face-down stack and continue drawing.
- Edge cases: quarry supply can be exhausted (then quarry not offered); hacienda extra tile and hospice colonist both come from supply and must be available (skip silently if exhausted, document choice).

## Verification
- `pytest puerto_rico/engine/test_phases.py -k settler`
  - Expected: non-chooser cannot take quarry without construction hut; chooser can.
  - Expected: tile lands on lowest empty slot; full island yields only PASS.
  - Expected: last duty refreshes face-up tiles to `num_players + 1`, reshuffling discard when stack empties.
  - Expected (if hooks implemented): hacienda gives chooser an extra face-down tile; hospice occupies the placed tile.
