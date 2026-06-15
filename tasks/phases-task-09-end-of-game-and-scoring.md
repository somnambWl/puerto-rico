# Task 09: End-of-Game Detection and Final Scoring

## Status
done

## Epic
engine-phases

## Dependencies
- phases-task-02
- phases-task-03
- phases-task-04
- phases-task-05
- phases-task-06
- phases-task-07
- phases-task-08
- buildings-task-NN (soft: large-building scoring hooks — stub the hooks if buildings epic not yet done)

## Overview
Centralize the three end-of-game triggers, finish the current round, transition to GAME_OVER, and compute final scores (VP chips + building VP + large-building bonuses) with tie-breaking and winner determination.

## Design References
- `design/02-engine-phases-and-flow.md`
- `design/03-buildings-reference.md`
- `design/01-engine-core-and-state.md`

## Files to Create/Modify
| File | Action | Changes |
|------|--------|---------|
| `puerto_rico/engine/phases.py` | Modify | `check_end_triggered()` integration |
| `puerto_rico/engine/scoring.py` | Create/Modify | `final_score()` |
| `puerto_rico/engine/game.py` | Modify | `is_terminal()`, `legal_actions()`, `returns()`, `winner()` |
| `puerto_rico/engine/test_phases.py` | Modify | End-game + scoring tests |

## Specification
- Three end triggers (all set `end_triggered = True`; the game does NOT stop immediately):
  1. Mayor: ship-refill cannot meet the required colonist count (colonist shortage) — see `phases-task-03`.
  2. Builder: a player fills the 12th building space — see `phases-task-04`.
  3. Captain: the last VP chip is taken (`vp_chips_remaining` reaches 0) — see `phases-task-07`.
- After a trigger, the CURRENT round is played out to completion (every player finishes their role this round). Then `phase = GAME_OVER`. (Round-end check from `phases-task-01` performs this transition.)
- `final_score(player)` =
  - `vp_chips` collected during the game, PLUS
  - printed VP of every building the player owns (regardless of occupied), PLUS
  - large-building bonuses, awarded ONLY if the large building is fully occupied (manned):
    - Guild Hall: +1 per small production building owned, +2 per large production building owned (small production = indigo small / sugar small; large production = the 1x2 production buildings).
    - Residence: +4/+5/+6/+7 VP for occupying <=9 / 10 / 11 / 12 island spaces respectively.
    - Fortress: +1 per 3 colonists the player has (total colonists on the player's board, floor division by 3).
    - Customs House: +1 per 4 VP chips the player collected (floor division by 4).
    - City Hall: +1 per beige (civic/violet purple non-production? use rules' definition) building the player owns — count the buildings the rules designate; document the exact category used.
- Tie-break for final ranking: most (doubloons + remaining goods) wins the tie; if still tied, the lower player index wins. `winner()` returns the single winner after tie-break.
- `game.py`:
  - `is_terminal()` -> True iff `phase == GAME_OVER`.
  - `legal_actions()` -> empty when terminal.
  - `returns()` -> per-player final scores (and/or normalized rewards as the RL layer needs — at minimum expose raw scores).
  - `winner()` -> index of the winning player applying tie-break.

## Verification
- `pytest puerto_rico/engine/test_phases.py -k endgame`
  - Expected: each of the 3 triggers sets `end_triggered`; the current round still completes before GAME_OVER.
  - Expected: `final_score` sums VP chips + building VP + each large-building bonus with correct occupied gating.
  - Expected: tie-break resolves by doubloons+goods then lower index; `winner()` matches.
  - Expected: `is_terminal()`/`legal_actions()`/`returns()` consistent at GAME_OVER.
