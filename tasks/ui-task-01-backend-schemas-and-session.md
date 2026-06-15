# Task 01: Backend Schemas + Session Model

## Status
not started

## Epic
ui

## Dependencies
- engine (Game, public_view, legal_actions, scoring)
- agents-task-02 (HeuristicAgent)
- agents-task-08 (RLPolicy)

## Overview
Define the Pydantic message schemas exchanged with the frontend and a `GameSession`
object that drives a single game, applies the human action, and auto-runs the AI
opponents until it is the human's turn again (or the game ends).

## Design References
- `design/06-ui.md`

## Files to Create/Modify
| File | Action | Changes |
|------|--------|---------|
| `puerto_rico/ui/backend/schemas.py` | create | Pydantic message models |
| `puerto_rico/ui/backend/session.py` | create | `GameSession` model |
| `puerto_rico/ui/backend/test_session.py` | create | construction + step tests |

## Specification

### `schemas.py`
Pydantic models (v2 style):

- `LegalAction`: `{ id: int, label: str, kind: str, detail: dict }`
  - `id` = engine action int; `kind` = action category (e.g. `role`, `build`,
    `ship`, `select_plantation`, `store`, `trade`); `detail` = structured payload
    used by the frontend for highlighting; `label` = human-readable string.
- `StateMsg`: `{ view: dict, legal_actions: list[LegalAction], to_move: int,
  terminal: bool, result: Optional[dict] }`
  - `view` = engine `public_view` dict.
  - `to_move` = seat index whose turn it is.
  - `result` present only when `terminal` is true; shape from scoring (see task 08).
- `ActionMsg`: `{ action_id: int }` (client → server).
- `SequenceMsg`: `{ states: list[StateMsg] }` — ordered sequence of intermediate
  states produced by one human action plus the AI responses that follow.

### `session.py`
`GameSession(game, human_seat: int, ai)`:
- `game` = engine `Game` instance.
- `human_seat` = seat index controlled by the human.
- `ai` = an agent object exposing `act(game) -> int` (HeuristicAgent or RLPolicy).
  All non-human seats are driven by this single `ai`.

Methods:
- `state_view() -> dict` → a `StateMsg`-shaped dict:
  `{ view: game.public_view(), legal_actions: [...], to_move, terminal, result? }`.
  Build each legal action via the labeling module (task 04); until task 04 exists,
  use a placeholder label = `str(action_id)`.
- `human_step(action_int) -> list[dict]`:
  1. Apply the human action to the game.
  2. Append the resulting `state_view()` to a list.
  3. While the game is not terminal and `to_move != human_seat`: query `ai.act(game)`,
     apply it, append `state_view()`.
  4. Return the ordered list of `StateMsg`-shaped dicts (one per applied action).

The session never mutates anything except its own `game`. It must raise/return a
clear error if `action_int` is not in the current legal actions.

## Verification
`pytest puerto_rico/ui/backend/test_session.py`:
- Construct a `GameSession` from a fresh 4-player `Game` with a stub AI that always
  returns the first legal action. Assert `state_view()` has the documented keys and
  `to_move` is an int.
- Call `human_step(first_legal_action)`; assert the return is a non-empty list of
  dicts, each with `StateMsg` keys, and that the final element either is terminal or
  has `to_move == human_seat`.
