"""Public engine facade — the :class:`Game` class.

``Game`` is the single public entry point that agents, the env, and the UI all
call. It wraps a :class:`GameState` and exposes legality (:meth:`legal_actions`),
application (:meth:`apply`), cloning (:meth:`clone`), and results
(:meth:`returns` / :meth:`winner`). Nothing outside the engine reimplements the
rules — this is the key-invariant boundary (see CLAUDE.md / design/00).

Phase dispatch
--------------
:meth:`legal_actions` and :meth:`apply` delegate to the round/phase state
machine in :mod:`phases` (``dispatch_legal_actions`` / ``dispatch_apply``). That
module owns role selection, the round/governor rotation, and the per-role
``ROLE_PHASES`` seam that the role tasks (phases-02..08) populate. This public
``Game`` surface stays identical regardless of which role phases are implemented.
"""

from __future__ import annotations

from . import scoring
from .actions import Action
from .enums import Phase
from .phases import dispatch_apply, dispatch_legal_actions
from .serialize import public_view as _serialize_public_view
from .setup import new_game
from .state import GameConfig, GameState


class IllegalAction(Exception):
    """Raised by :meth:`Game.apply` when the action is not currently legal."""


class Game:
    """Public facade wrapping a single :class:`GameState`.

    All rules legality flows through :meth:`legal_actions`; all state mutation
    flows through :meth:`apply`. Construct via a :class:`GameConfig`.
    """

    __slots__ = ("_state",)

    def __init__(self, config: GameConfig) -> None:
        self._state: GameState = new_game(config)

    # --- accessors ---------------------------------------------------------

    @property
    def state(self) -> GameState:
        """The underlying (mutable) :class:`GameState`."""
        return self._state

    @property
    def current_player(self) -> int:
        """Index of the player whose atomic decision is pending."""
        return self._state.current_player

    @property
    def is_terminal(self) -> bool:
        """``True`` once the game has ended (``phase == GAME_OVER``)."""
        return self._state.phase == Phase.GAME_OVER

    # --- core API ----------------------------------------------------------

    def legal_actions(self) -> list[Action]:
        """All legal actions for the current decision (empty iff terminal)."""
        return dispatch_legal_actions(self._state)

    def apply(self, action: Action, validate: bool = True) -> None:
        """Apply ``action`` in place.

        When ``validate`` is ``True`` (default), ``action`` must be in
        :meth:`legal_actions`; otherwise :class:`IllegalAction` is raised.
        ``validate=False`` skips the check for the rollout hot path, trusting
        the caller (env/agent) to only pass masked-legal actions.
        """
        if validate and action not in self.legal_actions():
            raise IllegalAction(f"illegal action {action!r} in phase {self._state.phase!r}")
        if self._state.phase == Phase.GAME_OVER:
            raise IllegalAction("no apply handler for phase Phase.GAME_OVER")
        dispatch_apply(self._state, action)

    def clone(self) -> "Game":
        """Return an independent copy wrapping ``state.clone()``."""
        new = Game.__new__(Game)
        new._state = self._state.clone()
        return new

    # --- results -----------------------------------------------------------

    def returns(self, reward_mode: str = "rank") -> list[float]:
        """Terminal payoffs, one per player; zeros if not terminal.

        The default ``reward_mode="rank"`` is a deterministic rank-based reward
        derived from :mod:`scoring`: 1st -> +1, 2nd -> +1/3, 3rd -> -1/3,
        4th -> -1 (evenly spaced over the standings). Genuinely-tied players
        (identical :func:`scoring.tiebreak_key`) share the average reward of the
        ranks they span, so the vector always sums to ~0.

        design/05 defines configurable ``reward_mode`` (rank / win / vp_margin);
        all modes are implemented in :mod:`puerto_rico.training.reward_config`,
        to which this method delegates. ``training`` depends only on
        :mod:`engine` (no env import), so there is no import cycle.
        """
        # Local import keeps the engine importable on its own and makes the
        # training -> engine dependency one-directional.
        from ..training import reward_config

        if not self.is_terminal:
            return [0.0] * len(self._state.players)
        return reward_config.terminal_rewards(self._state, reward_mode)

    def winner(self) -> int | None:
        """Winning player index, or ``None`` if not terminal.

        Tie-break (via :func:`scoring.rankings`): highest final score, then
        highest ``doubloons + total goods``, then lowest player index. Returns the
        sole top player.
        """
        if not self.is_terminal:
            return None
        return scoring.rankings(self._state)[0]

    # --- serialization -----------------------------------------------------

    def public_view(self, perspective: int | None = None) -> dict:
        """UI-facing snapshot; delegates to :func:`serialize.public_view`."""
        return _serialize_public_view(self._state, perspective)
