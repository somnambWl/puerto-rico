"""Shared ``Agent`` protocol that every concrete agent conforms to (design/05).

Two interchangeable interfaces
------------------------------
Concrete agents expose **two** decision entry points, and the arena / evaluation /
UI / opponent pool all drive agents through the *game-based* one:

* ``act_id(game) -> int`` — the **canonical** interface. Given the live engine
  :class:`~puerto_rico.engine.game.Game` (it is ``game.current_player``'s turn),
  return a legal discrete action id. Every baseline (``RandomAgent``,
  ``HeuristicAgent``, ``RLPolicy``) implements this, so callers can treat them
  uniformly as ``callable(game) -> int`` (see
  :func:`puerto_rico.training.evaluate.make_player`).
* ``act(obs, *, rng=None) -> int`` — the **env-facing** interface. Consumes the
  masked observation dict the PettingZoo env emits
  (:class:`~puerto_rico.env.pettingzoo_env.PuertoRicoAEC`)::

      {"observation": float32[OBS_LEN], "action_mask": int8[N_ACTIONS]}

  where ``action_mask[i] == 1`` means action id ``i`` is legal. ``RandomAgent`` is
  the canonical obs-based agent (its ``act_id`` builds the obs dict and calls
  ``act``); the game-based agents take a ``Game`` directly.

Either way the engine is the single source of truth for legality — every returned
id is legal and agents never reimplement rules.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class Agent(Protocol):
    """Structural protocol for a Puerto Rico decision policy.

    Implemented structurally: any object exposing ``act`` and ``reset`` with
    these signatures is an ``Agent`` — no explicit subclassing required. The
    canonical game-based ``act_id(game) -> int`` interface is documented at module
    level and implemented by every concrete agent.
    """

    def act(self, obs: dict, *, rng=None) -> int:
        """Choose a legal action id for the given observation.

        Parameters
        ----------
        obs:
            The env observation dict, containing at least
            ``obs["action_mask"]`` (a 0/1 array over the discrete action space,
            indexed by action id) and ``obs["observation"]`` (the encoded
            feature vector).
        rng:
            Optional ``numpy.random.Generator`` for any stochastic choice. When
            ``None`` the agent falls back to its own internal RNG.

        Returns
        -------
        int
            An action id whose ``obs["action_mask"]`` entry is ``1``.
        """
        ...

    def reset(self) -> None:
        """Clear any per-episode internal state. A no-op is acceptable."""
        ...
