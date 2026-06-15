"""Pydantic wire-protocol models for the UI backend (design/06 — UI).

These are the JSON shapes exchanged with the browser over REST and WebSocket.
The frontend mirrors them in TypeScript, so the field names / types here are the
contract. Everything the UI displays is pre-computed server-side; the client is
a renderer.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


class LegalActionMsg(BaseModel):
    """One legal action offered to the human, ready to render as a button.

    ``id`` is the env action-codec integer (the value the client echoes back in
    an :class:`ActionMsg`); ``label`` is the display string; ``kind`` is a coarse
    category for grouping (``"role"``/``"tile"``/``"build"``/``"colonist"``/
    ``"sell"``/``"ship"``/``"choose"``/``"pass"``).
    """

    id: int
    label: str
    kind: str


class StateMsg(BaseModel):
    """A full snapshot of the game from the human's perspective.

    ``view`` is the engine ``public_view`` dict (board + players, VP hidden for
    opponents). ``legal_actions`` is populated only when it is the human's turn
    (empty during AI turns). ``result`` is present only when ``terminal`` is
    true.
    """

    view: dict
    legal_actions: list[LegalActionMsg]
    to_move: int
    to_move_is_human: bool
    terminal: bool
    result: Optional[dict] = None


class ActionMsg(BaseModel):
    """Client -> server: the chosen action id (must be a currently-legal id)."""

    action_id: int


class SequenceMsg(BaseModel):
    """Server -> client: the ordered states produced by one human action plus
    every AI response that followed, so the frontend can animate the turn."""

    states: list[StateMsg]


class NewGameMsg(BaseModel):
    """POST /games body: how to set up a new game."""

    seed: Optional[int] = None
    human_seat: int = 0
    opponent: Literal["heuristic", "rl"] = "heuristic"
    difficulty: Optional[str] = None


class NewGameResponse(BaseModel):
    """POST /games response: the new game id and its initial state."""

    game_id: str
    state: StateMsg


class ErrorMsg(BaseModel):
    """Server -> client (WebSocket): a non-fatal error (e.g. illegal action)."""

    type: Literal["error"] = "error"
    message: str
