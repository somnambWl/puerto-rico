# Task 02: FastAPI App + Session Manager

## Status
not started

## Epic
ui

## Dependencies
- ui-task-01
- engine (Game)
- agents-task-02 (HeuristicAgent)
- agents-task-08 (RLPolicy)

## Overview
Create the FastAPI application with REST endpoints to create and reconnect to games,
holding live `GameSession` objects in an in-memory session manager.

## Design References
- `design/06-ui.md`

## Files to Create/Modify
| File | Action | Changes |
|------|--------|---------|
| `puerto_rico/ui/backend/app.py` | create | FastAPI app, sessions dict, REST routes |
| `puerto_rico/ui/backend/test_app.py` | create | create + reconnect tests |

## Specification

### Session manager
Module-level `sessions: dict[str, GameSession]`. `game_id` = a generated UUID string.

### Opponent construction
- `opponent == "heuristic"` → `HeuristicAgent()` (from agents-task-02).
- `opponent == "rl"` → `RLPolicy(checkpoint, difficulty)` (from agents-task-08).
  `difficulty` selects which checkpoint / strength; pass it through.

### `POST /games`
Request body:
```
{ "seed": Optional[int], "human_seat": Optional[int] = 0,
  "opponent": "heuristic" | "rl", "difficulty": Optional[str] }
```
Behavior: build a new 4-player `Game` (seeded if `seed` given), build the opponent
agent, create a `GameSession`, store under a new `game_id`. If the human is not the
first to move, advance the AI until it is the human's turn (reuse the session's
auto-run logic).

Response:
```
{ "game_id": str, "state": StateMsg }
```
where `state` is `session.state_view()`.

### `GET /games/{game_id}`
Return the current `StateMsg` (`session.state_view()`). 404 if `game_id` unknown.
This is the reconnect path — it must return whatever the current state is without
mutating the game.

## Verification
`pytest puerto_rico/ui/backend/test_app.py` using FastAPI `TestClient`:
- `POST /games` with `{seed, opponent:"heuristic"}` → 200, response has `game_id`
  and a `state` with `StateMsg` keys.
- `GET /games/{game_id}` → 200, returns a `StateMsg`; calling it twice returns the
  same `to_move` (no mutation).
- `GET /games/unknown` → 404.
