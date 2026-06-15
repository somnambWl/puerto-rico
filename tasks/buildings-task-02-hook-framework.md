# Task 02: Hook Framework (HANDLERS + fire dispatcher)

## Status
done

## Epic
buildings

## Dependencies
- buildings-task-01

## Overview
Build the timing-point hook framework: a `HANDLERS` registry keyed by `(BuildingId, Timing)` and a `fire(timing, state, player_idx, ctx)` dispatcher that `phases.py` calls so all building-specific behavior lives in handlers, never in the phase code.

## Design References
- `design/03-buildings-reference.md`
- `design/01-engine-core-and-state.md`

## Files to Create/Modify
| File | Action | Changes |
|------|--------|---------|
| `puerto_rico/engine/buildings.py` | Modify | `HANDLERS` dict, handler type alias, `register` decorator, `fire()` dispatcher, `Ctx` container |
| `puerto_rico/engine/test_buildings_hooks.py` | Create | Registry + dispatcher tests |

## Specification

### Handler registry
- `HANDLERS: dict[tuple[BuildingId, Timing], Callable]` — module-level dict, initially empty (Tasks 04–06 populate it).
- Provide a `register(building_id, timing)` decorator (or a `register(building_id, timing, fn)` function) that inserts into `HANDLERS`. Tasks 04–06 use this to attach handlers.

### Handler signature
```
handler(state, player_idx: int, ctx) -> None | value
```
- Handlers mutate `state` and/or the documented mutable field on `ctx`.
- Some handlers return a value (e.g. a price). Most return `None`.
- Keep handlers pure w.r.t. inputs other than the documented mutation target.

### Ctx container
A lightweight, timing-specific context object passed to handlers. Implement as a mutable dataclass (or simple attribute bag) carrying only the fields a given timing needs. Examples:
- `TRADER_SELL_PRICE`: `ctx.good` (the good being sold) and `ctx.price` (mutable int the handler increments).
- `SETTLER_PLACE`: the tile being placed / placement info.
- `CRAFTSMAN_PRODUCE`: the set/list of distinct kinds produced this turn.
- `CAPTAIN_LOAD`: load info (kind, count, ship).
- `CAPTAIN_STORAGE`: storage-allowance accumulator.
- `BUILDER_BUILD`: the building just built.
- `SCORE_END`: a mutable VP accumulator.

Define a single flexible `Ctx` type (extra unused attributes allowed) rather than one class per timing, unless a per-timing dataclass is clearly cleaner. Document which fields each timing populates.

### fire() dispatcher
```
fire(timing, state, player_idx, ctx) -> None
```
Behavior:
- Iterate the player's buildings that declare `timing` in their spec `timings`.
- For each such building, look up `HANDLERS.get((building_id, timing))`; if present, call it with `(state, player_idx, ctx)`.
- Occupancy requirement: handlers fire only for **occupied** buildings (≥1 colonist), **except** `SCORE_END` which Task 06 gates per-handler (large buildings score base VP regardless and only the extra requires occupancy). For non-SCORE_END timings, `fire()` skips unoccupied buildings.
- Safe on missing handler: if no entry exists in `HANDLERS` for a `(building_id, timing)` pair, skip silently (no error).
- Deterministic order: iterate buildings in a stable order (e.g. board slot order or ascending `BuildingId`) so stacking effects (small + large market/warehouse) are reproducible.

### Design rule (enforced by convention)
All building behavior lives in handlers. `phases.py` only calls `fire(...)`. Do not branch on `BuildingId` inside `phases.py`.

## Verification
Run `pytest puerto_rico/engine/test_buildings_hooks.py`.

Expected behavior:
- `HANDLERS` is a `dict` keyed by `(BuildingId, Timing)`.
- `fire()` with no registered handlers and any timing is a no-op (no exception), even when the player owns relevant buildings.
- Registering a dummy handler for an owned, occupied building causes `fire()` to invoke it exactly once and apply its mutation to `ctx`/`state`.
- `fire()` skips a handler whose building is owned but unoccupied (for a non-SCORE_END timing).
- A registered handler for a building the player does NOT own is never called.
