# Task 05: React App Setup + Board

## Status
not started

## Epic
ui

## Dependencies
- ui-task-03 (WS protocol / message shapes)

## Overview
Scaffold the Vite + React + TypeScript frontend, define the shared message types,
build the WebSocket-driven `useGameState` hook, and render the shared `Board`
(non-player table state).

## Design References
- `design/06-ui.md`

## Files to Create/Modify
| File | Action | Changes |
|------|--------|---------|
| `puerto_rico/ui/frontend/package.json` | create | deps + scripts (vite, react, ts) |
| `puerto_rico/ui/frontend/vite.config.ts` | create | Vite config + dev proxy to backend |
| `puerto_rico/ui/frontend/src/types.ts` | create | `StateMsg`, `ActionMsg`, `SequenceMsg`, `LegalAction` |
| `puerto_rico/ui/frontend/src/hooks/useGameState.ts` | create | WS connection + state/animation queue |
| `puerto_rico/ui/frontend/src/components/Board.tsx` | create | shared board component |
| `puerto_rico/ui/frontend/src/App.tsx` | create | top-level wiring |

## Specification

### `types.ts`
Mirror the backend Pydantic models:
- `LegalAction = { id: number; label: string; kind: string; detail: Record<string, unknown> }`
- `StateMsg = { view: any; legal_actions: LegalAction[]; to_move: number; terminal: boolean; result?: any }`
- `ActionMsg = { action_id: number }`
- `SequenceMsg = { states: StateMsg[] }`

### `useGameState.ts`
- Opens the WS to `/games/{game_id}`; reconnect-safe (re-renders from the state frame
  sent on connect).
- Parses incoming frames by `type`: `state` → set current state; `sequence` → enqueue
  the `states` for animated playback (advance through the queue on a timer so the UI
  shows intermediate AI moves); `error` → expose an error string.
- Exposes: `currentState: StateMsg | null`, `isAnimating: boolean`,
  `sendAction(action_id: number): void`, `error?: string`.

### `Board.tsx`
Props: `{ view, highlightedPlantation?: number }`. Renders the shared table state
from `view`:
- Role placards (with doubloons sitting on them; highlight roles still available).
- Colonist ship (remaining colonists count).
- Cargo ships (each ship's capacity + current good/quantity).
- Trading house (goods currently in it).
- Supply stacks (remaining goods of each type).
- Face-up plantation row: 5 plantation tiles, each clickable; highlight the tile at
  `highlightedPlantation`.
- Victory-point chip pool (remaining).
- Buildings shelf (available buildings with cost / remaining count).

### `App.tsx`
Wire `useGameState` to `Board`, passing `currentState.view`. (Player boards, prompt,
log added in later tasks.)

## Verification
`cd puerto_rico/ui/frontend && npm install && npm run build` passes with no type
errors. `Board` renders given a sample `StateMsg.view` fixture.
