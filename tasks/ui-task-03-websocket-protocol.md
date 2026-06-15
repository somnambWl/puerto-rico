# Task 03: WebSocket Protocol

## Status
done

## Epic
ui

## Dependencies
- ui-task-02
- ui-task-01

## Overview
Add a WebSocket endpoint that pushes the initial state on connect, accepts human
actions, runs the session step, and streams the resulting sequence of states
(including intermediate AI moves) back to the client with a short animation delay.

## Design References
- `design/06-ui.md`

## Files to Create/Modify
| File | Action | Changes |
|------|--------|---------|
| `puerto_rico/ui/backend/app.py` | modify | add `WS /games/{game_id}` route |
| `puerto_rico/ui/backend/test_websocket.py` | create | action-step protocol test |

## Specification

### `WS /games/{game_id}`
1. On connect: look up the session (close with an error if unknown), then send the
   current `StateMsg` (`session.state_view()`).
2. Receive loop: client sends `ActionMsg` `{ action_id }`.
   - Validate `action_id` is in the current legal actions. If not, send an error
     message and keep the connection open (do not mutate the game).
   - Call `session.human_step(action_id)` → list of `StateMsg` dicts.
   - Send them as a `SequenceMsg` `{ states: [...] }`. Additionally stream the
     intermediate AI states one at a time with a 100–200 ms delay between sends so
     the client can animate; the final state is the last element.
   - On terminal: the final `StateMsg` carries `terminal: true` and `result`.
3. Reconnect-safe: a new WS connection to the same `game_id` re-sends the current
   state on connect, so a dropped client recovers by reconnecting (state lives in
   the session, not the socket).

Message framing: JSON. Each frame is a discriminable object — include a `type`
field (`"state"`, `"sequence"`, `"error"`) so the client can route frames.

## Verification
`pytest puerto_rico/ui/backend/test_websocket.py` using FastAPI `TestClient`
websocket support:
- Create a game (heuristic opponent), open the WS, assert the first frame is a
  `state` (`StateMsg`).
- Send a valid `ActionMsg`; assert the response yields 2 or more `StateMsg` frames
  (the human result plus at least one AI move), arriving as a `sequence` and/or
  streamed states.
- Send an illegal `action_id`; assert an `error` frame and that a subsequent valid
  action still works (no desync).
