# Puerto Rico — Frontend

React + TypeScript (Vite) client for the Puerto Rico UI. It is a thin renderer:
all rules and legality live in the engine; the client only renders the server's
`view` + `legal_actions` and posts a chosen `action_id`.

## Run

1. Start the backend (from the repo root):

   ```bash
   uvicorn puerto_rico.ui.backend.app:app --reload --port 8000
   ```

2. Start the frontend dev server:

   ```bash
   cd puerto_rico/ui/frontend
   npm install
   npm run dev
   ```

   Vite serves on http://localhost:5173 and proxies `/games` + `/catalog`
   (REST) and `/ws` (WebSocket) to the backend on `:8000` (see `vite.config.ts`).

3. Open http://localhost:5173, pick an opponent + seat, and play.

## Build / type-check

```bash
npm run build      # tsc -b (type-check) + vite build
```

## Architecture

The client is a thin renderer: it draws the server's `view` + `legal_actions`
and posts a chosen `action_id`. It never re-derives rules.

Key files:

- `src/catalog.tsx` — Catalog context + `useBuildingInfo` / `useGoodInfo`
  hooks. `/catalog` is the single source of truth for building metadata (name,
  cost, VP, capacity, description); there is no hardcoded building table. When
  the catalog fetch fails, building lookups return null and the UI degrades to a
  generic "building N" label. One `CatalogProvider` wraps the whole app.
- `src/hooks/useGameState.ts` — WebSocket connection, the step-by-step playback
  animation queue, action send, and the reconnect/seed GET on mount.
- `src/hooks/useActionPreview.ts` — hover-to-preview: debounced POST
  `/games/{id}/preview`, AbortController cancellation, per-decision diff cache.
- `src/hooks/useLogEntries.ts` — derives the move Log from the playback feed.
- `src/preview.ts` — diffs a preview state against the current state into the
  human-perspective deltas shown in `PreviewPanel`.
- `src/components/PreviewPanel.tsx` — renders the preview diff lines.
- `src/components/PlaybackBar.tsx` — pause / step / skip / speed controls shown
  while the AI move sequence animates.
- `src/types.ts` — TS mirror of the backend wire protocol (`schemas.py`) and the
  engine `public_view` (`serialize.py`), plus display-name maps for the engine
  enums (goods / roles / tiles / phases). Building names are NOT duplicated here.
- `src/api.ts` — `createGame` / `getState` / `getCatalog` / `previewAction`.
- `src/components/` — `Board`, `PlayerBoard`, `ActionPrompt`, `Log`, `GameOver`,
  `Tooltip`.
- `src/App.tsx` — start screen + live game wiring (`GameView`).
