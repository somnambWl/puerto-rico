# Task 06: React PlayerBoard x4

## Status
not started

## Epic
ui

## Dependencies
- ui-task-05

## Overview
Render each player's personal board (island plantations, city buildings, doubloons,
goods, stored colonists, VP), with the human board enlarged and the three AI boards
compact in a sidebar.

## Design References
- `design/06-ui.md`

## Files to Create/Modify
| File | Action | Changes |
|------|--------|---------|
| `puerto_rico/ui/frontend/src/components/PlayerBoard.tsx` | create | per-player board |
| `puerto_rico/ui/frontend/src/App.tsx` | modify | lay out 4 player boards |

## Specification

### `PlayerBoard.tsx`
Props: `{ playerView, playerIndex, isHuman, perspectiveName }`.
Render from `playerView`:
- **Island**: 12 plantation/quarry slots; each occupied slot shows its tile type and
  a colonist dot when staffed.
- **City**: 12 building slots; large buildings span 2 slots; show colonist dots on
  staffed building slots.
- **Doubloons** count.
- **Goods inventory** (corn/indigo/sugar/tobacco/coffee quantities).
- **Stored colonists** (the player's "San Juan" colonist supply).
- **Victory points**: shown for the human; rendered as `"?"` for AI players (hidden
  information).
- Label the board with `perspectiveName`.

### `App.tsx` layout
- Human's `PlayerBoard` occupies ~60% of the viewport (primary area).
- The three AI `PlayerBoard`s render compact in a sidebar.
- Highlight the board whose seat equals `currentState.to_move`.

## Verification
`cd puerto_rico/ui/frontend && npm run dev` and visually confirm: four player boards
render, human board is large with visible VP, AI boards are compact with `"?"` VP,
colonist dots appear on staffed slots. (Visual check — flag for human review.)
