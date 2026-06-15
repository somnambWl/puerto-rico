# Puerto Rico AI

A digital implementation of the board game Puerto Rico with a playable UI and a reinforcement-learning opponent. Personal-use project.

## Quick Start

### Setup
```bash
uv sync --extra dev
```

### Run tests
```bash
uv run pytest
```

### Train an RL agent
```bash
# Smoke test (quick, ~80% vs random): runs to `runs/smoke/final.pt`
uv run python -m puerto_rico.training.smoke_train

# Strong model (beat-heuristic target): runs to `runs/release/final.pt`
uv run python -m puerto_rico.training.train_strong
```

To limit CPU usage during training (keep the machine responsive), set `PR_TRAIN_THREADS`:
```bash
PR_TRAIN_THREADS=4 uv run python -m puerto_rico.training.train_strong
```

### Play in the browser
Start the backend (FastAPI + WebSocket server):
```bash
uv run uvicorn puerto_rico.ui.backend.app:app --reload
```

Start the frontend (React + TypeScript):
```bash
cd puerto_rico/ui/frontend
npm install
npm run dev
```

Open http://localhost:5173 in your browser. Create a new game, choose an opponent (heuristic or RL), and play.

## Architecture

The project follows a dependency chain: **Engine** → **Environment** → **Agents/Training** → **UI**.

- **Engine** (`puerto_rico/engine/`) — rules simulator, state model, action protocol, phase state machine.
- **Environment** (`puerto_rico/env/`) — PettingZoo AEC wrapper, action & observation encoders, legality masks.
- **Agents & Training** (`puerto_rico/agents/`, `puerto_rico/training/`) — baseline agents (random, heuristic), custom PyTorch PPO self-play with action masking.
- **UI** (`puerto_rico/ui/`) — FastAPI backend (game sessions, WebSocket), React frontend (board, action prompt, log).

For detailed design docs, see `design/` and `docs/`.

## Project Links

- **Rules reference:** `docs/puerto-rico-rules.md`
- **Architecture & design:** `design/00-overview-and-architecture.md`
- **RL strategy audit:** `docs/rl-strategy-audit.md`
- **Task tracker:** `tasks/README.md`
