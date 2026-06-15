"""``GameSession`` — drives one game: human action in, AI auto-run, states out.

One session owns one authoritative :class:`Game` plus a single AI agent that
plays **all** non-human seats (3 of 4 in a 4-player game). The human picks a
legal action; the session applies it and then steps the AI for every following
non-human seat until it is the human's turn again or the game ends, capturing a
snapshot after each applied action so the frontend can animate the sequence.

The session is the only thing that mutates its game; it never touches anything
else. All legality flows through the engine (``game.legal_actions``) — the
session never reimplements a rule.
"""

from __future__ import annotations

from puerto_rico.engine import scoring
from puerto_rico.engine.enums import DecisionType
from puerto_rico.engine.phases import (
    CAPTAIN_WHARF,
    ISLAND_TARGET_OFFSET,
    MAYOR_STORE,
)
from puerto_rico.env import action_codec

from . import labels
from .schemas import ColonistTarget, LegalActionMsg, StateMsg


def _structured_fields(action) -> dict:
    """Decode an engine ``Action`` into the structured ``LegalActionMsg`` fields.

    Returns only the keys relevant to the action's :class:`DecisionType`; the
    rest stay at their schema defaults. This lets the frontend map a board
    element straight to the action id (click-to-act / drag-and-drop) without
    parsing the human-readable label.
    """
    t = action.type
    if t == DecisionType.SELECT_ROLE:
        return {"role": int(action.role)}
    if t == DecisionType.TAKE_TILE:
        return {"tile": int(action.tile)}
    if t == DecisionType.BUILD:
        return {"building": int(action.building)}
    if t == DecisionType.SELL:
        return {"good": int(action.good)}
    if t == DecisionType.CHOOSE:
        return {"good": int(action.good)} if action.good is not None else {}
    if t == DecisionType.LOAD:
        out: dict = {"good": int(action.good)}
        if action.choice == CAPTAIN_WHARF:
            out["wharf"] = True
        elif action.target is not None:
            out["ship"] = int(action.target)
        return out
    if t == DecisionType.PLACE_COLONIST:
        target = action.target
        if target == MAYOR_STORE:
            ct = ColonistTarget(kind="store")
        elif target >= ISLAND_TARGET_OFFSET:
            ct = ColonistTarget(kind="island", index=target - ISLAND_TARGET_OFFSET)
        else:
            ct = ColonistTarget(kind="city", index=int(target))
        return {"colonist_target": ct}
    return {}


def _jsonable(obj):
    """Recursively convert sets (and set-valued sub-state) to sorted lists.

    The engine ``public_view`` can carry Python ``set`` values inside the
    phase-specific ``sub`` dict (e.g. the captain's ``wharf_used``). Those are
    not JSON-serializable, so we normalize them before they reach the wire.
    """
    if isinstance(obj, set):
        try:
            return sorted(obj)
        except TypeError:
            return list(obj)
    if isinstance(obj, dict):
        return {k: _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(v) for v in obj]
    return obj


class GameSession:
    """One live game = one :class:`Game` + one AI agent + the human's seat.

    Parameters
    ----------
    game:
        The authoritative engine :class:`Game`.
    human_seat:
        Seat index controlled by the human.
    ai:
        A game-based agent exposing ``act(game) -> Action`` (a
        :class:`HeuristicAgent` or :class:`RLPolicy`). It drives every non-human
        seat.
    """

    def __init__(self, game, human_seat: int, ai) -> None:
        self.game = game
        self.human_seat = int(human_seat)
        self.ai = ai

    # ------------------------------------------------------------------ #
    # snapshot                                                           #
    # ------------------------------------------------------------------ #

    def legal_action_ids(self) -> set[int]:
        """The set of action ids legal for the *current* decision.

        Always computed from ``game.legal_actions()`` so it can never diverge
        from engine legality.
        """
        return {action_codec.to_int(a) for a in self.game.legal_actions()}

    def _legal_action_msgs(self) -> list[LegalActionMsg]:
        """Legal actions as wire messages — only meaningful on the human's turn.

        Returns an empty list when it is an AI seat's turn (the human has no
        decision to make) or when the game is terminal.
        """
        game = self.game
        if game.is_terminal or game.current_player != self.human_seat:
            return []
        out: list[LegalActionMsg] = []
        for action in game.legal_actions():
            out.append(
                LegalActionMsg(
                    id=action_codec.to_int(action),
                    label=labels.label_action(action, game),
                    kind=labels.label_action_kind(action),
                    **_structured_fields(action),
                )
            )
        return out

    def _result_for(self, game) -> dict | None:
        """Final-score breakdown when ``game`` is terminal, else ``None``.

        Per-player ``final_score`` plus its components (vp chips, building VP,
        large-building bonus) and the overall winner. Mirrors ``scoring.py`` so
        the game-over screen matches the engine exactly. Works for the live game
        or a preview clone (used by :meth:`preview_action`).
        """
        if not game.is_terminal:
            return None
        state = game.state
        scores = scoring.final_scores(state)
        ranking = scoring.rankings(state)
        players = []
        for i, p in enumerate(state.players):
            chips = p.vp_chips
            total = scores[i]
            # building VP + large-building bonus = everything above the chips.
            building_vp = total - chips
            players.append(
                {
                    "seat": i,
                    "final_score": total,
                    "vp_chips": chips,
                    "building_vp": building_vp,
                    "doubloons": p.doubloons,
                    "goods": list(p.goods),
                }
            )
        return {
            "scores": scores,
            "ranking": ranking,
            "winner": game.winner(),
            "players": players,
        }

    def state_view(
        self,
        last_action_label: str | None = None,
        last_action_seat: int | None = None,
    ) -> StateMsg:
        """A :class:`StateMsg` snapshot from the human's perspective.

        ``last_action_label`` / ``last_action_seat`` describe the action that
        produced this frame (the label is computed by the caller *before*
        applying, so the game state matched the actor's turn). They default to
        ``None`` for the initial connect/reset frame, which has no predecessor.
        """
        game = self.game
        return StateMsg(
            view=_jsonable(game.public_view(perspective=self.human_seat)),
            legal_actions=self._legal_action_msgs(),
            to_move=game.current_player,
            to_move_is_human=(game.current_player == self.human_seat),
            terminal=game.is_terminal,
            result=self._result_for(game),
            last_action_label=last_action_label,
            last_action_seat=last_action_seat,
        )

    def preview_action(self, action_id: int) -> StateMsg:
        """A hypothetical :class:`StateMsg`: ``action_id`` applied to a *clone*.

        Validates ``action_id`` against the current legal set (raising
        ``ValueError`` if it is not legal right now), clones the authoritative
        game, applies the single decoded human action to the clone, and returns a
        :class:`StateMsg` built from the **clone's** ``public_view`` — leaving
        ``self.game`` completely untouched. No AI is run; only the one human
        action is applied. The returned frame has ``preview=True`` and an empty
        ``legal_actions`` list (it is a what-if, not a turn).
        """
        game = self.game
        if game.is_terminal:
            raise ValueError("game is already over")
        if game.current_player != self.human_seat:
            raise ValueError("not the human's turn")
        if action_id not in self.legal_action_ids():
            raise ValueError(f"action {action_id} is not currently legal")

        clone = game.clone()
        action = action_codec.from_int(action_id, clone.state)
        clone.apply(action, validate=False)

        result = None
        if clone.is_terminal:
            result = self._result_for(clone)
        return StateMsg(
            view=_jsonable(clone.public_view(perspective=self.human_seat)),
            legal_actions=[],
            to_move=clone.current_player,
            to_move_is_human=(clone.current_player == self.human_seat),
            terminal=clone.is_terminal,
            result=result,
            preview=True,
        )

    # ------------------------------------------------------------------ #
    # stepping                                                           #
    # ------------------------------------------------------------------ #

    def ai_step_once(self) -> StateMsg:
        """Apply one AI action for the current (non-human) seat; return the state.

        The action's label and the acting seat are captured *before* the apply
        (so ``game`` still reflects the actor's turn) and attached to the
        resulting frame, so the client log shows what the AI actually did.
        """
        game = self.game
        action = self.ai.act(game)
        seat = game.current_player
        label = labels.label_action(action, game)
        game.apply(action)
        return self.state_view(last_action_label=label, last_action_seat=seat)

    def run_ai_until_human(self) -> list[StateMsg]:
        """Auto-run the AI for every non-human seat until the human's turn / end.

        Returns one :class:`StateMsg` per AI action applied (possibly empty).
        """
        states: list[StateMsg] = []
        game = self.game
        while not game.is_terminal and game.current_player != self.human_seat:
            states.append(self.ai_step_once())
        return states

    def human_step(self, action_id: int) -> list[StateMsg]:
        """Apply the human's ``action_id`` then auto-run the AI to the next human turn.

        Validates ``action_id`` against the current legal set (raising
        ``ValueError`` if not legal), applies it, then steps every following AI
        seat. Returns the ordered list of snapshots: one after the human action,
        then one after each AI action — the animation sequence.
        """
        game = self.game
        if game.is_terminal:
            raise ValueError("game is already over")
        if game.current_player != self.human_seat:
            raise ValueError("not the human's turn")
        if action_id not in self.legal_action_ids():
            raise ValueError(f"action {action_id} is not currently legal")

        action = action_codec.from_int(action_id, game.state)
        # Label + seat captured before the apply, while the game still reflects
        # the human's turn, so the produced frame records what the human did.
        seat = game.current_player
        label = labels.label_action(action, game)
        game.apply(action)

        states: list[StateMsg] = [
            self.state_view(last_action_label=label, last_action_seat=seat)
        ]
        states.extend(self.run_ai_until_human())
        return states
