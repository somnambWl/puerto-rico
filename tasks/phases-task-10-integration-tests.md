# Task 10: Integration and Full-Game Playthrough Tests

## Status
not started

## Epic
engine-phases

## Dependencies
- phases-task-01
- phases-task-02
- phases-task-03
- phases-task-04
- phases-task-05
- phases-task-06
- phases-task-07
- phases-task-08
- phases-task-09

## Overview
End-to-end tests that drive full games through the engine, verifying determinism, a rulebook worked example, randomized robustness, and global invariants.

## Design References
- `design/02-engine-phases-and-flow.md`
- `design/01-engine-core-and-state.md`

## Files to Create/Modify
| File | Action | Changes |
|------|--------|---------|
| `puerto_rico/engine/test_integration.py` | Create | Full-game integration tests |

## Specification
- Scripted deterministic game: with a fixed seed and a fixed scripted action sequence, the engine must reproduce an expected final score for each player (golden test — pin the expected scores).
- Rulebook captain worked example: reproduce the captain-phase example from `docs/puerto-rico-rules.md` step by step and assert the resulting VP, ship contents, and kept goods match the rulebook.
- Randomized robustness: run 100+ full games where each step picks a uniformly random action from `state.legal_actions()` with a fixed RNG. Each game must reach GAME_OVER without raising, and `legal_actions()` must never be empty before terminal.
- Invariant checks (asserted after every step in the random games):
  - All colonist counts (supply, ship, stored, placed) are >= 0 and conserved against the starting total.
  - Every cargo ship holds at most one good kind.
  - The trading house holds <= 4 goods.
  - No player's island spaces exceed 12 and no player's city building spaces exceed 12.
  - Total VP chips spent (awarded) <= 100 (the VP chip supply cap); `vp_chips_remaining` never negative.
- Edge cases: ensure reshuffles, end triggers, and round completion after a trigger are exercised at least once across the random suite.

## Verification
- `pytest puerto_rico/engine/test_integration.py`
  - Expected: scripted game reproduces pinned scores exactly.
  - Expected: captain worked example matches the rulebook.
  - Expected: 100+ random games all reach GAME_OVER with all invariants holding at every step.
