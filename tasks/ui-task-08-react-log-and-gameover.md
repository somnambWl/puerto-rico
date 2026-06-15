# Task 08: React Log + Game-Over

## Status
not started

## Epic
ui

## Dependencies
- ui-task-05
- ui-task-03

## Overview
Add a chronological action log and a game-over modal showing final scores, derived
from the streamed states and the terminal `result`.

## Design References
- `design/06-ui.md`

## Files to Create/Modify
| File | Action | Changes |
|------|--------|---------|
| `puerto_rico/ui/frontend/src/components/Log.tsx` | create | chronological action log |
| `puerto_rico/ui/frontend/src/components/GameOver.tsx` | create | final-score modal |
| `puerto_rico/ui/frontend/src/App.tsx` | modify | integrate log + game-over |

## Specification

### `Log.tsx`
- Append one entry per applied action as states stream in, formatted
  `"{player}: {action_label}"`.
- Newest entries visible; the panel scrolls (auto-scroll to latest).
- Source the player + label from each `StateMsg` as it is consumed from the
  animation queue (the action that produced that state).

### `GameOver.tsx`
- Renders when `currentState.terminal` is true, reading `currentState.result`.
- Show each player's final score breakdown:
  `{ total_vp, chips, buildings_vp, large_building_bonus }`.
- Sort players by `total_vp` descending; highlight the winner.

### App integration
- Mount `Log` alongside the board.
- Mount `GameOver` as a modal overlay when terminal.

## Verification
`cd puerto_rico/ui/frontend && npm run dev`, play a full game against the heuristic
opponent: the log fills with `"{player}: {action}"` entries in order and scrolls,
and on game end the modal shows sorted final scores with the winner highlighted.
(Visual / full-game check — flag for human review.)
