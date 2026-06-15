# Task 08: PROSPECTOR (inline in role selection)

## Status
done

## Epic
engine-phases

## Dependencies
- phases-task-01
- engine-core-task-07
- engine-core-task-02

## Overview
Implement the prospector role, which resolves immediately during role selection with no follow-up action: the chooser collects the placard's accumulated doubloons plus 1 from the supply, then control returns straight to ROLE_SELECTION.

## Design References
- `design/02-engine-phases-and-flow.md`
- `design/01-engine-core-and-state.md`

## Files to Create/Modify
| File | Action | Changes |
|------|--------|---------|
| `puerto_rico/engine/phases.py` | Modify | Handle `SELECT_ROLE(PROSPECTOR)` inline |
| `puerto_rico/engine/test_phases.py` | Modify | Prospector tests |

## Specification
- On `SELECT_ROLE(PROSPECTOR)`:
  1. Mark the prospector placard as taken (`taken_by = chooser`, increment chooser's `roles_taken_this_round`).
  2. Transfer any doubloons accumulated on the placard to the chooser (placard doubloon transfer — same as any taken role).
  3. The chooser gains an additional `+1` doubloon from the supply (prospector privilege).
  4. There is NO follow-up action / no resolution phase — immediately call `advance_role_chooser()` and return to ROLE_SELECTION.
- The prospector exists only in games with enough role placards (present in 3+ player setups). In a standard 4-player game there is one prospector; document that 2-player setups follow the configured placard set.
- Edge cases: the prospector never has an `active_role` resolution phase; `order`/`order_pos` are not used for it.

## Verification
- `pytest puerto_rico/engine/test_phases.py -k prospector`
  - Expected: chooser gains accumulated placard doubloons + 1; placard marked taken.
  - Expected: state returns directly to ROLE_SELECTION with the next chooser, no intermediate action requested.
