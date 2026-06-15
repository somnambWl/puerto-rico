# Task 07: React Action Prompt + Highlighting

## Status
not started

## Epic
ui

## Dependencies
- ui-task-05
- ui-task-04

## Overview
Render the legal actions as clickable buttons, send the chosen action over the WS,
disable input while the AI moves / animations play, and highlight the referenced
board element on hover.

## Design References
- `design/06-ui.md`

## Files to Create/Modify
| File | Action | Changes |
|------|--------|---------|
| `puerto_rico/ui/frontend/src/components/ActionPrompt.tsx` | create | action buttons |
| `puerto_rico/ui/frontend/src/components/Board.tsx` | modify | accept/apply highlight from hovered action |
| `puerto_rico/ui/frontend/src/App.tsx` | modify | wire prompt, disable-on-AI |

## Specification

### `ActionPrompt.tsx`
Props: `{ legalActions: LegalAction[]; onAction: (id: number) => void; disabled: boolean }`.
- Render one button per legal action using its `label`.
- On click: call `onAction(action.id)` (which sends `ActionMsg`), then immediately
  disable the prompt to prevent double-submit.
- On hover: derive the referenced board element from the action's `kind`/`detail`
  and signal it for highlighting (e.g. a plantation index → `highlightedPlantation`
  on `Board`; a building → highlight the building shelf entry; a ship → highlight the
  cargo ship).
- `disabled` hides/greys the buttons.

### App wiring
- Pass `currentState.legal_actions` to `ActionPrompt`.
- `disabled = isAnimating || currentState.to_move !== humanSeat || currentState.terminal`.
- Re-enable the prompt only when it is the human's turn and no animation is playing.

## Verification
`cd puerto_rico/ui/frontend && npm run dev`, manual check: legal-action buttons
appear on the human's turn, clicking one applies it and disables the prompt, the
prompt re-enables after the AI finishes, and hovering a button highlights the
correct board element. (Manual visual check — flag for human review.)
