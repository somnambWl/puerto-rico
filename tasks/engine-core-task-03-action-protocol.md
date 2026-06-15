# Task 03: Action Protocol

## Status
done

## Epic
engine-core

## Dependencies
- engine-core-task-01

## Overview
Define the single flat, immutable, hashable `Action` dataclass that represents every player decision, dispatched on `action.type` inside `apply()`.

## Design References
- `design/00-overview-and-architecture.md`
- `design/01-engine-core-and-state.md`

## Files to Create/Modify
| File | Action | Changes |
|------|--------|---------|
| `puerto_rico/engine/actions.py` | Create | Define `Action` dataclass |
| `puerto_rico/engine/test_actions.py` | Create | Hashability / frozen / int-mapping tests |

## Specification
In `puerto_rico/engine/actions.py`:

`@dataclass(slots=True, frozen=True)`
`Action`:
- `type: DecisionType`
- `role: Role | None = None`
- `tile: TileType | None = None`
- `target: int | None = None`
- `good: Good | None = None`
- `building: BuildingId | None = None`
- `choice: int | None = None`

Design constraints:
- **Flat**: one dataclass for all decision kinds (no subclasses). Fields not relevant to a given `DecisionType` stay `None`.
- **Immutable**: `frozen=True`.
- **Hashable**: must be usable as a dict key and as a set member — this enables a stable `Action`→int mapping for the RL action space.
- Dispatch happens later in `apply()` on `action.type` (this task only defines the protocol type, not the dispatch logic).

## Notes
Downstream epics (engine-phases, buildings) construct `Action` instances and rely on the dispatch-on-`type` convention. Keep this type pure data.

## Verification
Run `pytest puerto_rico/engine/test_actions.py`.

Expected behavior:
- `Action` instances are hashable (`hash(a)` works; two equal actions hash equal; usable in a `set` / dict).
- `Action` is frozen (assigning to a field raises `FrozenInstanceError`).
- A collection of distinct `Action`s can be mapped to unique ints (e.g. via `enumerate(sorted_or_listed_actions)`), confirming they are stable, distinguishable values.
