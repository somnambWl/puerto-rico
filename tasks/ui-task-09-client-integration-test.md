# Task 09: Automated Client Integration Test

## Status
done

## Epic
ui

## Dependencies
- ui-task-01
- ui-task-02
- ui-task-03

## Overview
An end-to-end backend test that drives a full game over the WebSocket against the
heuristic opponent, choosing random legal actions, and verifies there is no
desync and the final result is valid.

## Design References
- `design/06-ui.md`

## Files to Create/Modify
| File | Action | Changes |
|------|--------|---------|
| `puerto_rico/ui/backend/test_client.py` | create | full-game WS integration test |

## Specification

`test_client.py` using FastAPI `TestClient`:
1. `POST /games` with `{ opponent: "heuristic" }` (optionally a fixed `seed`); read
   `game_id` and initial `StateMsg`.
2. Open the WS; receive the initial state frame.
3. Loop until terminal:
   - From the current `StateMsg`, pick a random action from `legal_actions`.
   - Before sending, record the set of legal `action_id`s.
   - Send `ActionMsg { action_id }`; receive the resulting state(s).
   - Assert the chosen `action_id` was in the **prior** state's legal actions
     (i.e. the client and server never desynced).
   - Advance the current state to the last `StateMsg` received.
4. On terminal: assert `result` is present and valid — every seat has a score
   breakdown, and the winner has the maximum `total_vp`.

The test must complete a whole game without hanging (the auto-run AI guarantees the
next state is always the human's turn or terminal).

## Verification
`pytest puerto_rico/ui/backend/test_client.py` runs a complete game to terminal with
no desync assertion failures and a valid final result.
