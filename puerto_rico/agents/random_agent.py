"""``RandomAgent`` — uniform sampling over the legal-action mask (design/05).

The sanity baseline and win-rate floor: it picks uniformly among the actions the
env marks legal (``action_mask == 1``). It never returns a masked-illegal id.

Interfaces
----------
``RandomAgent`` is the canonical **obs-based** agent: :meth:`act` consumes the env
observation dict (``{"observation", "action_mask"}``) the way the PettingZoo env
emits it. For parity with the game-based agents (HeuristicAgent / RLPolicy) it
also exposes :meth:`act_id` ``(game) -> int``, which builds that obs dict from the
live :class:`~puerto_rico.engine.game.Game` and dispatches to :meth:`act`, so the
arena / UI / opponent-pool can treat all three baselines uniformly via
``act_id(game)``.
"""

from __future__ import annotations

import numpy as np

from ..env import action_codec, obs_codec
from .base import Agent


class RandomAgent(Agent):
    """Samples uniformly among legal actions in the observation's mask.

    Parameters
    ----------
    seed:
        Optional seed for the agent's internal ``numpy.random.Generator``. A
        fixed seed makes the agent's choices reproducible across runs (given the
        same sequence of observations). A per-call ``rng`` passed to :meth:`act`
        overrides the internal generator for that call.
    """

    def __init__(self, seed: int | None = None) -> None:
        self._rng = np.random.default_rng(seed)

    def act(self, obs: dict, *, rng=None) -> int:
        mask = np.asarray(obs["action_mask"])
        legal = np.flatnonzero(mask == 1)
        if legal.size == 0:
            raise ValueError(
                "RandomAgent received an empty action mask; the engine should "
                "never present a state with no legal actions"
            )
        generator = rng if rng is not None else self._rng
        return int(generator.choice(legal))

    def act_id(self, game) -> int:
        """Return a uniform-random legal action id for ``game.current_player``.

        Builds the same masked observation dict the env emits (``obs_codec.encode``
        + ``action_codec.mask`` for the acting seat) and dispatches to :meth:`act`,
        so the random agent presents the game-based ``act_id(game)`` interface used
        by the arena / opponent pool while reusing its one sampling code path.
        """
        seat = game.current_player
        obs = obs_codec.encode(game.state, seat)
        mask = action_codec.mask(game).astype(np.float32)
        return self.act({"observation": obs, "action_mask": mask})

    def reset(self) -> None:
        """No per-episode state to clear."""
        return None
