# Task 07: CAPTAIN Phase

## Status
done

## Epic
engine-phases

## Dependencies
- phases-task-01
- engine-core-task-07
- engine-core-task-02
- buildings-task-NN (soft: wharf, harbor, warehouse — stub the hooks if buildings epic not yet done)

## Overview
Implement the captain role: players repeatedly load goods onto cargo ships for victory points until no one can load, then resolve goods storage (keep 1 good plus warehouse capacity, discard the rest). Includes the VP-chip exhaustion end trigger.

## Design References
- `design/02-engine-phases-and-flow.md`
- `design/03-buildings-reference.md`
- `design/01-engine-core-and-state.md`

## Files to Create/Modify
| File | Action | Changes |
|------|--------|---------|
| `puerto_rico/engine/phases.py` | Modify | `captain_legal_actions()`, `captain_apply()`, `captain_last_duty()`, goods-storage sub-phase |
| `puerto_rico/engine/test_phases.py` | Modify | Captain phase tests |

## Specification
- Loading loop: continue while at least one player in `order` is not in `captain_done`. Advance through `order` (starting at chooser, clockwise); a player who cannot load is marked done (PASS) and skipped on future passes.
- Cargo-ship loading rules:
  - Each cargo ship holds goods of a SINGLE kind.
  - The same kind may not be loaded onto two different ships simultaneously (no duplicate kind across ships).
  - A ship that is already full cannot receive more.
  - A player CAN load a good kind iff there exists a ship that already holds that kind with free space, OR an empty ship exists AND that kind is not already on another ship.
  - A player who can load MUST load (loading is compulsory). They must load into the ship that takes the MOST of that kind (the most-filling legal ship). Document tie-break for ships of equal resulting fill (e.g. lowest ship index / largest-capacity ship first — pick one and document).
  - `LOAD(good)` is offered per loadable good kind the player holds.
- Wharf hook: a player may use their occupied wharf once per captain phase to `LOAD` all goods of one chosen kind directly to the supply (their own private ship). This counts as their load for that turn. (Stub if buildings not done.)
- `PASS` is legal ONLY when the player has no compulsory cargo-ship load available (cannot legally load any kind onto a shared ship). Wharf is optional and does not block PASS.
- VP scoring per load: `+1 VP per good loaded`; `+1` extra to the chooser on their FIRST load of the phase; `+1` per load if the loader owns an occupied harbor.
  - Decrement `vp_chips_remaining` accordingly. If it reaches 0, set `end_triggered = True` (VP-exhaustion end trigger — see `phases-task-09`). VP can continue to be awarded beyond the supply using the rules' large/small chip exchange — document that chips are tracked as a total and exhaustion is when the total hits 0.
- Goods storage sub-phase (after loading loop): each player may keep 1 good of one kind, PLUS warehouse capacity: small warehouse stores 1 kind (all of it), large warehouse stores 2 kinds, both/stacked store 3 kinds. All remaining goods are returned to the supply.
  - Emit a `CHOOSE` action when the storage selection is ambiguous (player must pick which kinds to keep); auto-resolve when there is only one legal way to keep.
- Last duty (chooser/end of phase): unload every FULL cargo ship's goods to the supply (full ships clear; partially filled ships keep their goods for the next captain phase).
- Edge cases: most-filling-ship rule can force a worse-for-the-player choice; the first-load chooser bonus applies only once; warehouse keeps ALL goods of the kept kind(s), the base "1 good" keeps a single unit.

## Verification
- `pytest puerto_rico/engine/test_phases.py -k captain`
  - Expected: single-kind-per-ship and no-duplicate-kind-across-ships enforced; must load into most-filling ship.
  - Expected: PASS only when no cargo load is possible.
  - Expected: VP +1/good, chooser +1 on first load, harbor +1/load; vp_chips_remaining hitting 0 sets end_triggered.
  - Expected: goods storage keeps 1 + warehouse capacity, rest to supply; full ships cleared in last duty.
