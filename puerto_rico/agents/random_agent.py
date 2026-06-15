"""``RandomAgent`` — uniform sampling over the legal-action mask (design/05).

The sanity baseline and win-rate floor: it picks uniformly among the actions the
env marks legal (``action_mask == 1``). It never returns a masked-illegal id.
"""

from __future__ import annotations

import numpy as np

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

    def reset(self) -> None:
        """No per-episode state to clear."""
        return None
