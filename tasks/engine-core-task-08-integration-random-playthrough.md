# Task 08: Integration Test — Random Playthrough

## Status
done

## Epic
engine-core

## Dependencies
- engine-core-task-01
- engine-core-task-02
- engine-core-task-03
- engine-core-task-04
- engine-core-task-05
- engine-core-task-06
- engine-core-task-07

## Overview
An end-to-end integration test that plays a full game by selecting random legal moves until terminal, asserting the engine never dead-ends and never raises.

## Design References
- `design/00-overview-and-architecture.md`
- `design/01-engine-core-and-state.md`

## Files to Create/Modify
| File | Action | Changes |
|------|--------|---------|
| `puerto_rico/engine/test_integration.py` | Create | Random legal-move playthrough |

## Specification
In `puerto_rico/engine/test_integration.py`:

- For a set of fixed seeds, construct a `Game(GameConfig(num_players=4, seed=...))`.
- Loop until `game.is_terminal`:
  - Get `actions = game.legal_actions()`.
  - Assert that a **non-terminal** state always has at least one legal action (no dead-ends).
  - Pick a random action (use a seeded `random.Random` so the test itself is deterministic) and `game.apply(action)`.
  - Guard against infinite loops with a generous max-step cap; exceeding it fails the test.
- The full loop must run **without raising any exceptions**.
- After termination, `game.returns()` and `game.winner()` are callable without error.

### Milestone 1 note
Because phase logic beyond `ROLE_SELECTION` is stubbed at M1 (see engine-core-task-07), the playthrough may terminate quickly or cycle through stubbed `PASS` actions. The test must still hold the invariants (legal actions present while non-terminal, no exceptions). As the engine-phases epic lands, this test naturally exercises deeper play.

## Verification
Run `pytest puerto_rico/engine/test_integration.py`.

Expected behavior:
- Random legal-move games reach terminal (or the documented M1 stub end) without exceptions across all seeds.
- Every non-terminal state encountered had at least one legal action.
- `returns()` and `winner()` succeed at terminal.
