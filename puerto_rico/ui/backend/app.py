"""FastAPI backend for the Puerto Rico UI (design/06 — UI).

Exposes the authoritative engine to the browser:

* ``POST /games`` — create a game vs. a chosen opponent, return the initial state.
* ``GET  /games/{game_id}`` — current state (reconnect / refresh, read-only).
* ``WS   /ws/games/{game_id}`` — push state, accept human actions, stream the
  resulting animation sequence.

Sessions live in an in-memory dict (single-process, personal-use). The browser
never holds rules: it sends a chosen ``action_id`` and renders the returned
``StateMsg``.
"""

from __future__ import annotations

import logging
import random
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from puerto_rico.agents.heuristic_agent import HeuristicAgent
from puerto_rico.engine.game import Game
from puerto_rico.engine.state import GameConfig

from .catalog import CATALOG_RESPONSE
from .schemas import ErrorMsg, NewGameMsg, NewGameResponse, SequenceMsg, StateMsg
from .session import GameSession

logger = logging.getLogger("puerto_rico.ui.backend")

#: Default RL checkpoint used for ``opponent == "rl"``.
DEFAULT_RL_CHECKPOINT = "runs/release/final.pt"

#: Delay (seconds) between streamed AI states so the client can animate.
AI_STREAM_DELAY = 0.12


def _build_ai(opponent: str, difficulty: str | None):
    """Construct the agent driving all non-human seats.

    ``"heuristic"`` -> :class:`HeuristicAgent`. ``"rl"`` -> :class:`RLPolicy`
    loaded from the release checkpoint, falling back to a heuristic agent (with a
    warning) if the checkpoint is missing or fails to load, so the server never
    fails to create a game.
    """
    if opponent == "rl":
        ckpt = Path(DEFAULT_RL_CHECKPOINT)
        if not ckpt.exists():
            logger.warning(
                "RL checkpoint %s not found; falling back to HeuristicAgent",
                ckpt,
            )
            return HeuristicAgent()
        try:
            # Imported lazily so a torch-free environment can still serve the
            # heuristic opponent.
            from puerto_rico.agents.rl_policy import RLPolicy

            return RLPolicy(str(ckpt))
        except Exception as exc:  # pragma: no cover - defensive fallback
            logger.warning(
                "failed to load RL checkpoint %s (%s); falling back to "
                "HeuristicAgent",
                ckpt,
                exc,
            )
            return HeuristicAgent()
    return HeuristicAgent()


def create_app() -> FastAPI:
    """Build the FastAPI application (factory; also bound to module ``app``)."""
    app = FastAPI(title="Puerto Rico UI backend")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "*",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    sessions: dict[str, GameSession] = {}
    app.state.sessions = sessions

    def _get_session(game_id: str) -> GameSession:
        session = sessions.get(game_id)
        if session is None:
            raise HTTPException(status_code=404, detail="game not found")
        return session

    @app.post("/games", response_model=NewGameResponse)
    def create_game(body: NewGameMsg) -> NewGameResponse:
        seed = body.seed if body.seed is not None else random.randrange(2**31)
        config = GameConfig(num_players=4, seed=seed)
        game = Game(config)
        ai = _build_ai(body.opponent, body.difficulty)
        session = GameSession(game, human_seat=body.human_seat, ai=ai)

        # If the game does not start on the human, advance the AI to the human's
        # first decision (or to a terminal state, defensively).
        session.run_ai_until_human()

        game_id = uuid.uuid4().hex
        sessions[game_id] = session
        return NewGameResponse(game_id=game_id, state=session.state_view())

    @app.get("/games/{game_id}", response_model=StateMsg)
    def get_game(game_id: str) -> StateMsg:
        return _get_session(game_id).state_view()

    @app.get("/catalog")
    def get_catalog() -> dict:
        """Static building catalog + good base values (no game needed)."""
        return CATALOG_RESPONSE

    @app.post("/games/{game_id}/preview", response_model=StateMsg)
    def preview_game(game_id: str, body: dict) -> StateMsg:
        """Apply ``action_id`` to a *clone* and return the hypothetical state.

        The real game is never mutated and no AI is run — this is a what-if frame
        (``preview=True``) the client diffs against the current state. ``404`` for
        an unknown game; ``400`` for a missing/non-integer ``action_id`` or an
        action that is not currently legal.
        """
        session = _get_session(game_id)
        action_id = body.get("action_id") if isinstance(body, dict) else None
        if action_id is None:
            raise HTTPException(status_code=400, detail="missing action_id")
        try:
            return session.preview_action(int(action_id))
        except (TypeError, ValueError, KeyError) as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @app.websocket("/ws/games/{game_id}")
    async def ws_game(websocket: WebSocket, game_id: str) -> None:
        await websocket.accept()
        session = sessions.get(game_id)
        if session is None:
            await websocket.send_json(
                ErrorMsg(message="game not found").model_dump()
            )
            await websocket.close()
            return

        # On connect: send the current state (reconnect-safe — pulled from the
        # session, not the socket).
        await websocket.send_json(_state_frame(session.state_view()))

        try:
            while True:
                msg = await websocket.receive_json()
                action_id = msg.get("action_id") if isinstance(msg, dict) else None
                if action_id is None:
                    await websocket.send_json(
                        ErrorMsg(message="missing action_id").model_dump()
                    )
                    continue
                try:
                    states = session.human_step(int(action_id))
                except (ValueError, KeyError) as exc:
                    # Invalid / illegal action: report, keep the socket open,
                    # do not mutate the game.
                    await websocket.send_json(
                        ErrorMsg(message=str(exc)).model_dump()
                    )
                    continue

                await _send_sequence(websocket, states)
        except WebSocketDisconnect:
            return

    return app


def _state_frame(state: StateMsg) -> dict:
    """Wrap a :class:`StateMsg` in a discriminable ``"state"`` frame."""
    frame = state.model_dump()
    frame["type"] = "state"
    return frame


async def _send_sequence(websocket: WebSocket, states: list[StateMsg]) -> None:
    """Send the animation sequence: a ``"sequence"`` frame, then stream each state.

    The single ``sequence`` frame carries the full ordered list (clients that
    prefer to animate locally can use it directly). The per-state ``"state"``
    frames are then streamed with a short delay so a simpler client can animate
    by just rendering each frame as it arrives.
    """
    import asyncio

    await websocket.send_json(SequenceMsg(states=states).model_dump() | {"type": "sequence"})
    for i, state in enumerate(states):
        await websocket.send_json(_state_frame(state))
        if i < len(states) - 1:
            await asyncio.sleep(AI_STREAM_DELAY)


app = create_app()
