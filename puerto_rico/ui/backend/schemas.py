"""Pydantic wire-protocol models for the UI backend (design/06 — UI).

These are the JSON shapes exchanged with the browser over REST and WebSocket.
The frontend mirrors them in TypeScript, so the field names / types here are the
contract. Everything the UI displays is pre-computed server-side; the client is
a renderer.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


class ColonistTarget(BaseModel):
    """Where a PLACE_COLONIST action drops the colonist.

    ``kind`` is one of ``"city"`` (a city building slot), ``"island"`` (an
    island plantation/quarry slot), or ``"store"`` (keep remaining colonists in
    San Juan / storage — ends placement). ``index`` is the engine's raw slot
    index within the city or island; it is omitted for ``"store"``.
    """

    kind: Literal["city", "island", "store"]
    index: Optional[int] = None


class LegalActionMsg(BaseModel):
    """One legal action offered to the human, ready to render as a button.

    ``id`` is the env action-codec integer (the value the client echoes back in
    an :class:`ActionMsg`); ``label`` is the display string; ``kind`` is a coarse
    category for grouping (``"role"``/``"tile"``/``"build"``/``"colonist"``/
    ``"sell"``/``"ship"``/``"choose"``/``"pass"``).

    The remaining fields are *structured* targets decoded from the engine action
    so the frontend can map a board element directly to the action id (click to
    act / drag-and-drop). All default ``None`` and only the field(s) relevant to
    the action's kind are populated:

    * ``role`` — SELECT_ROLE: the ``Role`` enum value.
    * ``tile`` — TAKE_TILE: the ``TileType`` enum value (quarry or plantation).
    * ``building`` — BUILD: the ``BuildingId`` enum value.
    * ``good`` — SELL / LOAD / CHOOSE: the ``Good`` enum value.
    * ``ship`` — LOAD onto a cargo ship: the target ship index.
    * ``wharf`` — LOAD via the wharf (ship all of one good to the supply).
    * ``colonist_target`` — PLACE_COLONIST: the decoded :class:`ColonistTarget`.
    """

    id: int
    label: str
    kind: str
    role: Optional[int] = None
    tile: Optional[int] = None
    building: Optional[int] = None
    good: Optional[int] = None
    ship: Optional[int] = None
    wharf: bool = False
    colonist_target: Optional[ColonistTarget] = None


class StateMsg(BaseModel):
    """A full snapshot of the game from the human's perspective.

    ``view`` is the engine ``public_view`` dict (board + players, VP hidden for
    opponents). ``legal_actions`` is populated only when it is the human's turn
    (empty during AI turns). ``result`` is present only when ``terminal`` is
    true.

    ``preview`` marks a *hypothetical* frame produced by ``POST /games/{id}/
    preview``: the engine applied a single candidate human action to a throwaway
    clone (the real game is untouched) so the client can diff the current state
    against the result before committing. ``preview`` is ``False`` on every
    normal state frame; preview frames carry an empty ``legal_actions`` list.

    ``last_action_label`` / ``last_action_seat`` describe the action that
    *produced* this frame: during a human step the session attaches the
    human-readable label and the seat that moved to each streamed state, so the
    client log can show exactly what the human and each AI seat did. They are
    ``None`` on the initial connect/reset frame (no preceding action) and on
    preview frames.
    """

    view: dict
    legal_actions: list[LegalActionMsg]
    to_move: int
    to_move_is_human: bool
    terminal: bool
    result: Optional[dict] = None
    preview: bool = False
    last_action_label: Optional[str] = None
    last_action_seat: Optional[int] = None


class ActionMsg(BaseModel):
    """Client -> server: the chosen action id (must be a currently-legal id)."""

    action_id: int


class ActionBatchMsg(BaseModel):
    """Client -> server: an ordered batch of action ids applied as one step.

    Used for the human's Mayor placement: the human arranges every colonist in
    one editor and submits the whole sequence (N placements + a final store) at
    once. The session applies each id in order, validating each against the
    legal set *at that point* (no AI runs between them — they are the human's
    consecutive placements), then runs the AI to the next human turn. The
    response is a :class:`SequenceMsg` with one frame per applied action.
    """

    action_ids: list[int]


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
