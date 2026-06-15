# Task 04: Small Beige Core Handlers (markets, warehouses, office, factory, university, wharf, harbor)

## Status
done

## Epic
buildings

## Dependencies
- buildings-task-01
- buildings-task-02

## Overview
Implement the trader/craftsman/builder/captain-phase handlers for the economic small beige buildings: small/large market, small/large warehouse, office, factory, university, wharf, and harbor.

## Design References
- `design/03-buildings-reference.md`
- `design/01-engine-core-and-state.md`

## Files to Create/Modify
| File | Action | Changes |
|------|--------|---------|
| `puerto_rico/engine/buildings.py` | Modify | Register handlers for the 8 buildings below |
| `puerto_rico/engine/test_buildings_core_handlers.py` | Create | Isolated per-handler tests |

## Specification
All handlers registered in `HANDLERS` via Task 02's `register`. Each fires only when its building is occupied (enforced by `fire()`).

### Small market — `(SMALL_MARKET, TRADER_SELL_PRICE)`
- Increment `ctx.price` by `+1` on this player's sale.

### Large market — `(LARGE_MARKET, TRADER_SELL_PRICE)`
- Increment `ctx.price` by `+2`. Stacks additively with small market (both occupied → +3 total). `fire()` iteration applies both handlers.

### Small warehouse — `(SMALL_WAREHOUSE, CAPTAIN_STORAGE)`
- Grant the player the ability to keep **all goods of 1 chosen kind** (beyond the 1 free good every player keeps). Model storage as protecting kinds: add +1 to the player's protected-kind allowance in `ctx`.

### Large warehouse — `(LARGE_WAREHOUSE, CAPTAIN_STORAGE)`
- Grant keeping **all goods of 2 chosen kinds**. Stacks with small warehouse (both → 3 protected kinds). Add +2 to the protected-kind allowance.
- Kept goods stay on the windrose (not consumed) and remain loadable in a future captain phase.

### Office — `(OFFICE, TRADER_SELL_PRICE)`
- Lifts the "may not sell a kind already in the trading house" restriction for this player. Office changes **legality**, not price.
- Single source of truth: implement via a `can_sell(state, player, good)` helper (defined in Task 08) that accounts for office; the trader `legal_actions()` and this handler both consult it. In this task, the office handler sets a flag/allowance on `ctx` indicating the duplicate-kind constraint is relaxed for this sale.

### Factory — `(FACTORY, CRAFTSMAN_PRODUCE)`
- Add doubloons by the number of **distinct kinds produced this craftsman turn** (quantity irrelevant, counts produced not held):
  - 0 or 1 distinct kinds → +0
  - 2 → +1
  - 3 → +2
  - 4 → +3
  - 5 → +5
- Read distinct-kind count from `ctx`; add the bonus to the player's doubloons.

### Wharf — `(WHARF, CAPTAIN_LOAD)`
- Once per captain phase, ship **all of one chosen kind** to the supply via an imaginary ship (capacity 11), scoring VP as normal. Optional. Mark wharf-used-this-phase on state so it cannot fire twice per phase.

### Harbor — `(HARBOR, CAPTAIN_LOAD)`
- `+1 VP` each time this player loads a cargo ship. Applies to every load, including the wharf "load." Increment the player's VP (or the captain-phase VP accumulator in `ctx`) by 1 per load event.

### University — `(UNIVERSITY, BUILDER_BUILD)`
- When this player builds a building, place a **free colonist from supply** on the just-built building (one colonist only, even for a multi-circle building). Read the built building from `ctx`; decrement supply and mark one of its circles occupied. No effect if supply is empty.

### Interactions
- Wharf and harbor can both apply in one captain phase; harbor's +1 applies to the wharf load too.
- Small + large market stack to +3; small + large warehouse stack to 3 protected kinds.

## Verification
Run `pytest puerto_rico/engine/test_buildings_core_handlers.py`.

Expected behavior (each in isolation):
- Small market alone: `ctx.price` increases by 1. Large market alone: +2. Both occupied: +3.
- Small warehouse: protected-kind allowance +1; large: +2; both: 3.
- Office: a duplicate-kind sale that would otherwise be illegal becomes allowed (flag/allowance set).
- Factory: 2 kinds → +1; 3 → +2; 4 → +3; 5 → +5; 1 kind → +0 doubloons.
- Wharf: fires at most once per captain phase; ships all of one kind to supply and scores VP.
- Harbor: +1 VP per load event (including the wharf load).
- University: building just built gains one free colonist from supply (one only, even multi-circle); no-op when supply empty.
