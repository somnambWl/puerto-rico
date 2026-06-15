# Task 05: Small Beige Settler/Mayor Handlers (hacienda, construction hut, hospice)

## Status
done

## Epic
buildings

## Dependencies
- buildings-task-01
- buildings-task-02
- phases-task-02 (settler phase integration)

## Overview
Implement the settler-phase handlers that modify tile-taking and tile-placement: hacienda (extra face-down plantation), construction hut (take a quarry instead of a plantation), and hospice (free colonist on a placed normal tile), including their documented interactions.

## Design References
- `design/03-buildings-reference.md`
- `design/02-engine-phases-and-flow.md`
- `design/01-engine-core-and-state.md`

## Files to Create/Modify
| File | Action | Changes |
|------|--------|---------|
| `puerto_rico/engine/buildings.py` | Modify | Register the 3 SETTLER_PLACE handlers |
| `puerto_rico/engine/phases.py` | Modify | Call `fire(SETTLER_PLACE, ...)` at the correct seam; consult construction hut in settler `legal_actions()` |
| `puerto_rico/engine/test_buildings_settler_handlers.py` | Create | Per-handler + interaction tests |

## Specification
All three register handlers at `(BuildingId, Timing.SETTLER_PLACE)` and fire only when occupied.

### Hacienda — `(HACIENDA, SETTLER_PLACE)`
- Before the player takes their face-up tile, take an **extra top face-down plantation** from the face-down stack and place it immediately on the player's island.
- Ordering: **hacienda fires first** (adds the extra tile), then the normal take/place proceeds.
- The extra face-down tile is **not** quarry-swappable (construction hut does not apply to it).

### Construction hut — `(CONSTRUCTION_HUT, SETTLER_PLACE)`
- The player **may take a quarry** instead of a face-up plantation. This is the only way a non-chooser takes a quarry during settler.
- Surface this in settler `legal_actions()`: when the acting player has an occupied construction hut, "take quarry" is a legal tile choice (for both chooser and non-chooser turns).
- Record `construction_hut_active` (or equivalent) on state so `legal_actions()` can consult it without re-implementing rules.

### Hospice — `(HOSPICE, SETTLER_PLACE)`
- When the player places a tile, place a **free colonist from supply** on it (it becomes occupied).
- The hospice colonist applies to the **normal** tile only — **not** hacienda's extra face-down tile (rulebook).

### Interactions (must be tested)
- **Hacienda + construction hut:** the extra face-down hacienda tile is not quarry-swappable; a settler with a hacienda may take only one quarry (the normal take, via construction hut), not swap the extra tile.
- **Hacienda + hospice:** if both occupied and the player takes the extra hacienda tile, the hospice colonist applies to the normal tile only, not the extra.
- **Ordering:** hacienda fires before the normal take.

## Verification
Run `pytest puerto_rico/engine/test_buildings_settler_handlers.py`.

Expected behavior:
- Hacienda (occupied): player gains one extra face-down plantation placed on their island, before the normal take.
- Construction hut (occupied): "take quarry" appears in settler `legal_actions()` for the player, including on non-chooser turns; the player can place a quarry.
- Hospice (occupied): a free colonist is placed on the normally-taken tile (tile becomes occupied); supply decremented.
- Hacienda+construction hut: only one quarry obtainable; the extra hacienda tile cannot be swapped to a quarry.
- Hacienda+hospice: hospice colonist lands on the normal tile, not the extra hacienda tile.
