"""Gymnasium single-agent wrapper over :class:`PuertoRicoAEC` (env-task-04).

A single *learner* (``learner_seat``, default 0) plays the AEC env while every
other seat is driven by a fixed ``opponent_policy``. This collapses the
multi-agent AEC into the standard single-agent ``gymnasium.Env`` contract so
single-agent PPO libraries can train on it, and so the UI can call a fixed
opponent to compute "AI to move".

Design notes
------------
- ``observation_space`` / ``action_space`` mirror the AEC's *per-agent* spaces:
  ``Dict({"observation": Box, "action_mask": Box})`` and ``Discrete(N_ACTIONS)``.
- ``reset`` resets the AEC, then runs the opponent loop until it is the learner's
  turn or the game is over; it returns the learner's observation dict.
- ``step`` applies the learner's action, then drives every non-learner turn via
  ``opponent_policy`` until control returns to the learner or the game ends. The
  reward is the learner's reward accumulated since its previous action; on
  termination it is the learner's final return.

Reading the learner's terminal reward despite AEC pruning
---------------------------------------------------------
PettingZoo's AEC prunes terminated agents from ``agents`` / ``rewards`` once they
take their dead-step, and at termination the ``agent_selection`` need not be the
learner. So we never rely on the AEC reward bookkeeping at the end. Instead, the
underlying engine is the source of truth: when ``game.is_terminal`` we read
``game.returns()[learner_seat]`` directly. Per-step (non-terminal) rewards are
read from the AEC's ``rewards`` dict, which is keyed by agent and accumulated
each step before any pruning would remove it.

Determinism
-----------
The engine seed is threaded through to the AEC. The default opponent uses a
seeded ``numpy`` rng (derived from the same seed) so episodes are reproducible.
"""

from __future__ import annotations

from typing import Callable

import gymnasium
import numpy as np
from gymnasium.spaces import Discrete

from . import action_codec
from .pettingzoo_env import PuertoRicoAEC

#: Type of an opponent policy: maps an AEC observation dict to a legal action id.
OpponentPolicy = Callable[[dict], int]


class PuertoRicoSingle(gymnasium.Env):
    """Single-agent Gymnasium view over :class:`PuertoRicoAEC`.

    One seat (``learner_seat``) is controlled by the caller via :meth:`step`; all
    other seats are played by ``opponent_policy`` (a uniform-random legal policy
    by default).
    """

    metadata = {"render_modes": ["ansi"], "name": "puerto_rico_single_v0"}

    def __init__(
        self,
        config: dict | None = None,
        opponent_policy: OpponentPolicy | None = None,
    ) -> None:
        super().__init__()
        config = dict(config or {})
        self.learner_seat: int = int(config.pop("learner_seat", 0))

        # The AEC takes the remaining engine/reward config keys verbatim.
        self._aec = PuertoRicoAEC(config)
        self.learner_agent: str = f"player_{self.learner_seat}"
        if self.learner_seat < 0 or self.learner_seat >= self._aec.num_players:
            raise ValueError(
                f"learner_seat {self.learner_seat} out of range for "
                f"{self._aec.num_players} players"
            )

        # Mirror the AEC's per-agent spaces for the learner seat.
        self.observation_space = self._aec.observation_space(self.learner_agent)
        self.action_space = Discrete(action_codec.N_ACTIONS)

        # rng for the default random opponent + the user-supplied policy.
        self._opponent_policy: OpponentPolicy = (
            opponent_policy if opponent_policy is not None else self._random_policy
        )
        self._rng = np.random.default_rng(config.get("seed", None))

    # --- default opponent --------------------------------------------------- #

    def _random_policy(self, obs: dict) -> int:
        """Uniform-random over the legal actions in ``obs['action_mask']``."""
        legal = np.where(np.asarray(obs["action_mask"]) != 0)[0]
        return int(self._rng.choice(legal))

    # --- internal helpers --------------------------------------------------- #

    def _is_terminal(self) -> bool:
        return self._aec.game.is_terminal

    def _current_agent(self) -> str:
        return self._aec.agent_selection

    def _learner_obs(self) -> dict:
        return self._aec.observe(self.learner_agent)

    def _terminal_obs(self) -> dict:
        """A terminal observation: last learner view with an all-zero mask.

        On termination there is no legal action, so the mask is zeroed (the
        Gymnasium contract only requires a valid observation, not a usable one).
        """
        obs = self._learner_obs()
        obs["action_mask"] = np.zeros_like(obs["action_mask"])
        return obs

    def _run_opponents(self) -> None:
        """Drive opponent seats until it is the learner's turn or game over."""
        while not self._is_terminal() and self._current_agent() != self.learner_agent:
            agent = self._current_agent()
            obs = self._aec.observe(agent)
            action = int(self._opponent_policy(obs))
            self._aec.step(action)

    # --- Gymnasium API ------------------------------------------------------ #

    def reset(self, seed=None, options=None):  # noqa: D401
        super().reset(seed=seed)
        if seed is not None:
            # Re-seed both the engine (via AEC) and the opponent rng.
            self._rng = np.random.default_rng(seed)
        self._aec.reset(seed=seed)

        # If an opponent opens the game, play through to the learner's turn.
        self._run_opponents()

        if self._is_terminal():
            # Degenerate (should not happen): return a terminal obs immediately.
            return self._terminal_obs(), {}
        return self._learner_obs(), {}

    def step(self, action: int):
        if self._is_terminal():
            raise RuntimeError("step() called on a terminated episode; call reset()")
        if self._current_agent() != self.learner_agent:
            raise RuntimeError(
                "internal error: not the learner's turn at step() entry"
            )

        # Apply the learner's action (AEC validates against the mask and raises
        # on illegal ids).
        self._aec.step(int(action))

        # Drive opponents until control returns to the learner or the game ends.
        self._run_opponents()

        if self._is_terminal():
            # Final return read straight from the engine — independent of AEC
            # agent pruning / which seat is agent_selection at the end.
            reward = float(self._aec.game.returns()[self.learner_seat])
            return self._terminal_obs(), reward, True, False, {}

        # Non-terminal: per-step reward accrued to the learner since its last
        # action. The AEC zeroes non-terminal rewards, so this is 0.0 today, but
        # reading it keeps the wrapper correct if shaping is wired in later.
        reward = float(self._aec.rewards.get(self.learner_agent, 0.0))
        return self._learner_obs(), reward, False, False, {}

    # --- rendering / teardown ---------------------------------------------- #

    def render(self):
        return self._aec.render()

    def close(self):
        return self._aec.close()
