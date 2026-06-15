"""Shared ``Agent`` protocol that every concrete agent conforms to (design/05).

All agents consume the *same* masked observation dict the PettingZoo env emits
(:class:`~puerto_rico.env.pettingzoo_env.PuertoRicoAEC`), so they are
interchangeable in the arena, in evaluation, and in the UI.

The observation dict has the RLlib-standard masked-action shape::

    {"observation": float32[OBS_LEN], "action_mask": int8[N_ACTIONS]}

where ``action_mask[i] == 1`` means action id ``i`` is legal in the current
state. An agent's :meth:`Agent.act` must always return an id whose mask entry is
``1`` (the engine is the single source of truth for legality; agents never
reimplement rules).
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class Agent(Protocol):
    """Structural protocol for a Puerto Rico decision policy.

    Implemented structurally: any object exposing ``act`` and ``reset`` with
    these signatures is an ``Agent`` — no explicit subclassing required.
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
