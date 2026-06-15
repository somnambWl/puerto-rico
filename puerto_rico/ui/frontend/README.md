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

   Vite serves on http://localhost:5173 and proxies `/games` (REST) and `/ws`
   (WebSocket) to the backend on `:8000` (see `vite.config.ts`).

3. Open http://localhost:5173, pick an opponent + seat, and play.

## Build / type-check

```bash
npm run build      # tsc -b (type-check) + vite build
```

## Layout

- `src/types.ts` — TS mirror of the backend wire protocol (`schemas.py`) and the
  engine `public_view` (`serialize.py`), plus display-name maps from the engine
  enums + buildings CATALOG.
- `src/api.ts` — `createGame` / `getState` (REST).
- `src/hooks/useGameState.ts` — WebSocket connection, animation queue, actions.
- `src/components/` — `Board`, `PlayerBoard`, `ActionPrompt`, `Log`, `GameOver`.
- `src/App.tsx` — start screen + live game wiring.
