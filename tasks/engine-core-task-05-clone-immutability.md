# Task 05: Clone & Immutability

## Status
done

## Epic
engine-core

## Dependencies
- engine-core-task-01
- engine-core-task-02

## Overview
Add `GameState.clone()` returning an independent deep copy suitable for the simulation hot path (tree search / RL rollouts), with a correctly forked RNG.

## Design References
- `design/00-overview-and-architecture.md`
- `design/01-engine-core-and-state.md`

## Files to Create/Modify
| File | Action | Changes |
|------|--------|---------|
| `puerto_rico/engine/state.py` | Modify | Add `GameState.clone()` |
| `puerto_rico/engine/test_state.py` | Modify | Add clone-independence tests |

## Specification
`GameState.clone() -> GameState`:
- Deep-copies all mutable fields (players and their nested `island`/`city`/`goods` lists, `placards`, `cargo_ships`, `trading_house`, all plantation lists, `buildings_supply`, `phase_state`, etc.) so that mutating the clone never affects the original and vice versa.
- Forks the RNG by reading the source RNG state via `getstate()` and applying it to a fresh `random.Random` via `setstate()` — the clone's `rng` must be an independent generator that currently produces the same sequence as the source at clone time.
- **Avoid `copy.deepcopy` on the hot path.** Construct new dataclass instances / lists explicitly for performance. Frozen value types (`GameConfig`, `RolePlacard` if treated as immutable, enum members) may be shared by reference.

## Notes
- `IslandSlot`, `CitySlot`, `CargoShip` are mutable (`slots=True`, not frozen) and must be reconstructed per-clone.
- Document which fields are safe to share (immutable) vs. which are copied.

## Verification
Run `pytest puerto_rico/engine/test_state.py`.

Expected behavior (clone independence):
- After `s2 = s1.clone()`, mutating a player's `goods`, `doubloons`, an `island`/`city` slot, or a cargo ship on `s2` leaves `s1` unchanged (and vice versa).
- `s2.rng` is a distinct object from `s1.rng` but produces the same next values immediately after cloning; advancing one RNG does not advance the other.
- Diverging sequences of applies on `s1` vs `s2` do not cross-contaminate.
