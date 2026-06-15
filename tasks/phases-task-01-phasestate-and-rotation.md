# Task 01: PhaseState Cursor and Governor Rotation

## Status
not started

## Epic
engine-phases

## Dependencies
- engine-core-task-07
- engine-core-task-02

## Overview
Add the `PhaseState` cursor that tracks who is choosing/acting within a round, and implement the role-selection rotation including governor passing and end-of-round bookkeeping. This is the backbone every role phase plugs into.

## Design References
- `design/02-engine-phases-and-flow.md`
- `design/01-engine-core-and-state.md`

## Files to Create/Modify
| File | Action | Changes |
|------|--------|---------|
| `puerto_rico/engine/state.py` | Modify | Add `PhaseState` dataclass with cursor fields |
| `puerto_rico/engine/phases.py` | Create/Modify | `advance_role_chooser()` and round-end bookkeeping |
| `puerto_rico/engine/test_phases.py` | Create | Tests for rotation, governor pass, round end |

## Specification
- `PhaseState` dataclass fields:
  - `role_chooser`: player index currently selecting a role (during ROLE_SELECTION).
  - `active_role`: the role currently being resolved (None during ROLE_SELECTION).
  - `order`: list of player indices in resolution order for the active role (starts at chooser, clockwise).
  - `order_pos`: index into `order` of the player currently acting.
  - `colonists_to_place`: counter used by the mayor placement sub-phase.
  - `captain_done`: set/list of player indices that have finished loading in the captain phase.
  - `sub`: optional sub-phase tag (e.g. mayor placement, captain goods-storage) for phases that need an inner state.
- `roles_per_round`: number of roles each player takes per round = `3` if 2-player game else `1`. Derive from `num_players`.
- Round end condition: the round ends when every player's `roles_taken_this_round == roles_per_round`. (In a standard 4-player game that is after each player has taken exactly one role; the remaining unchosen placards just accrue doubloons.)
- `advance_role_chooser()`: after a chosen role fully resolves, advance `role_chooser` clockwise to the next player who still has roles left to take this round. If all players have hit `roles_per_round`, run end-of-round bookkeeping.
- Governor passes at round end: the governor marker moves clockwise by one player; the new governor becomes the first `role_chooser` of the next round.
- End-of-round bookkeeping (in order):
  1. Place 1 doubloon from the supply onto each role placard that was NOT taken this round.
  2. Reset `taken_by` on all placards (placards become available again).
  3. Reset `roles_taken_this_round` to 0 for all players.
  4. Pass governor (clockwise).
  5. Check end-of-game trigger (see `phases-task-09`): if `end_triggered` is set, the round that just completed was the last one — transition to GAME_OVER instead of starting a new round.
- Edge cases: do not advance past a player who has remaining roles; in 2-player, the same player may choose again later in the round (roles_per_round=3). Doubloons accrued on a placard stay until that placard is taken (transferred in the role-take / prospector logic of other tasks).

## Verification
- `pytest puerto_rico/engine/test_phases.py -k rotation`
  - Expected: 4-player round ends after 4 selections; governor advances by one; the 2 untaken placards each gain 1 doubloon; `taken_by`/`roles_taken_this_round` reset.
  - Expected: 2-player game lets each player take 3 roles before the round ends.
  - Expected: when `end_triggered` is set during a round, completing that round transitions to GAME_OVER rather than starting a new round.
