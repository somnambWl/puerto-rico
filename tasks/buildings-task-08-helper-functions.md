# Task 08: Helper Functions

## Status
done

## Epic
buildings

## Dependencies
- buildings-task-01

## Overview
Provide the shared building helper functions used by handlers, phases, and `legal_actions()`: classification helpers, plus `can_sell` (office-aware) and `owned_production_counts` (for guild hall).

## Design References
- `design/03-buildings-reference.md`
- `design/01-engine-core-and-state.md`

## Files to Create/Modify
| File | Action | Changes |
|------|--------|---------|
| `puerto_rico/engine/buildings.py` | Modify | Finalize/harden helper functions |
| `puerto_rico/engine/test_buildings_helpers.py` | Create | Helper-function unit tests |

## Specification

### Classification helpers
- `get_spec(building_id) -> BuildingSpec` — `CATALOG[building_id]`; raises/KeyErrors on `LARGE_CONT`.
- `is_beige(building_id) -> bool` — True for all non-production real buildings (12 small + 5 large); False for production; not valid for `LARGE_CONT`.
- `is_production(building_id) -> bool` — `get_spec(building_id).is_production`.
- `production_size(building_id) -> "small" | "large"` — "small" for SMALL_INDIGO, SMALL_SUGAR; "large" for INDIGO_PLANT, SUGAR_MILL, TOBACCO_STORAGE, COFFEE_ROASTER; raises for non-production ids.

### `can_sell(state, player, good) -> bool`
- Single source of truth for trader sale legality re: the duplicate-kind constraint.
- Default rule: a good may not be sold if a good of that kind is already in the trading house.
- **Office exception:** if the player has an **occupied** office, the duplicate-kind constraint is lifted (the player may sell a kind already present).
- Used by both the trader `legal_actions()` and the office `TRADER_SELL_PRICE` handler so the rule lives in one place.
- (Should also respect other base sale legality such as trading house full / player has the good — keep consistent with design/02; the office-specific part is the focus here.)

### `owned_production_counts(player) -> {"small": int, "large": int}`
- Count production buildings the player **owns** (occupied or not), split by `production_size`.
- "small" = owned SMALL_INDIGO / SMALL_SUGAR; "large" = owned INDIGO_PLANT / SUGAR_MILL / TOBACCO_STORAGE / COFFEE_ROASTER.
- Used by the guild hall SCORE_END handler (Task 06).

## Verification
Run `pytest puerto_rico/engine/test_buildings_helpers.py`.

Expected behavior:
- `is_beige` True for all 17 beige ids, False for all 6 production ids.
- `is_production` True for the 6 production ids, False for beige.
- `production_size` returns "small"/"large" correctly and raises for a beige id.
- `can_sell`: returns False for a duplicate kind without office; returns True for the same case when the player has an occupied office.
- `owned_production_counts`: counts owned small/large production buildings correctly (e.g. owning SMALL_INDIGO + SUGAR_MILL + COFFEE_ROASTER → {small:1, large:2}).
