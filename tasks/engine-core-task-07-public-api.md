# Task 07: Public API

## Status
not started

## Epic
engine-core

## Dependencies
- engine-core-task-01
- engine-core-task-02
- engine-core-task-03
- engine-core-task-04
- engine-core-task-05
- engine-core-task-06

## Overview
Provide the `Game` class — the single public entry point wrapping `GameState` — that agents, the env, and the UI all call for legality, application, cloning, and results.

## Design References
- `design/00-overview-and-architecture.md`
- `design/01-engine-core-and-state.md`
- `design/05-agents-and-training.md`

## Files to Create/Modify
| File | Action | Changes |
|------|--------|---------|
| `puerto_rico/engine/game.py` | Create | `Game` class + `IllegalAction` exception |
| `puerto_rico/engine/test_game.py` | Create | API behavior tests |

## Specification
In `puerto_rico/engine/game.py`:

`class Game` wrapping a `GameState`:
- `__init__(self, config: GameConfig)` — builds the initial state via `new_game(config)`.
- `state` — property/attribute exposing the underlying `GameState`.
- `current_player` — current player index.
- `is_terminal` — bool; True once the game has ended (`phase == GAME_OVER` / `end_triggered` resolved).
- `legal_actions() -> list[Action]` — all legal actions for the current decision.
- `apply(action) -> None` — validates that `action` is in `legal_actions()` and raises `IllegalAction` if not; then applies it. Validation must be **skippable in a fast mode** (e.g. a flag) for performance in rollouts.
- `clone() -> Game` — independent copy (delegates to `GameState.clone()`); cloned `Game`s do not cross-contaminate.
- `returns() -> list[float]` — terminal payoffs, one per player, per the reward definition in `design/05-agents-and-training.md`.
- `winner() -> int | None` — winning player index, with tie-break on doubloons + goods (per rules); `None` if not terminal or genuinely tied after tie-break.
- `public_view(perspective: int | None = None) -> dict` — delegates to `serialize.public_view`.

`IllegalAction` — custom exception raised by `apply` on an illegal action.

### Milestone 1 scope
- `legal_actions()` returns the available **role selections** when `phase == ROLE_SELECTION`.
- For other phases, `legal_actions()` may stub out to empty or a single `PASS` action (full phase logic is delivered by the engine-phases epic).

## Notes
This is the key-invariant boundary: nothing outside the engine reimplements rules; agents/UI call `legal_actions()` and `apply()`. Downstream epics (engine-phases, buildings, env, UI) build on this surface.

## Verification
Run `pytest puerto_rico/engine/test_game.py`.

Expected behavior:
- `Game(GameConfig(num_players=4))` constructs a valid initial state (`phase == ROLE_SELECTION`, `current_player == 0`, not terminal).
- `legal_actions()` returns role-selection `Action`s in `ROLE_SELECTION`.
- `apply()` with an action not in `legal_actions()` raises `IllegalAction`.
- `clone()` independence: applies on the clone do not affect the original.
- `is_terminal` is `False` at game start.
