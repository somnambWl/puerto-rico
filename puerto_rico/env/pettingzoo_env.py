"""PettingZoo **AEC** wrapper around the Puerto Rico engine (design/04).

This is the only layer that imports both the engine and the RL codecs. It turns
the engine's turn-based, single-decision-at-a-time flow into the PettingZoo
agent-environment-cycle contract so multi-agent self-play PPO can train on it.

Design notes
------------
- Agents are ``["player_0", ..., "player_{n-1}"]`` and ``agent_selection`` follows
  the engine's ``current_player`` exactly (one player decides at a time).
- Observations use the RLlib-standard masked-action dict::

      {"observation": float32[OBS_LEN], "action_mask": float32[N_ACTIONS]}

  with ``action_mask`` 1.0 == legal, built from :func:`action_codec.mask`.
- Rewards are 0 every step until the game ends; on ``GAME_OVER`` every agent gets
  its terminal payoff from
  :func:`training.reward_config.terminal_rewards` for the configured
  ``reward_mode`` (default ``"rank"``, matching :meth:`Game.returns`). The dense
  ``shaping_coef`` hook is still 0 by default — full per-round shaping
  integration lands with the training loop (agents-task-07).
- Determinism comes from the engine seed passed through ``GameConfig``.
"""

from __future__ import annotations

import numpy as np
from gymnasium.spaces import Box, Dict as DictSpace, Discrete
from pettingzoo.utils.env import AECEnv

from ..engine.game import Game
from ..engine.state import GameConfig
from ..training import reward_config
from . import action_codec, obs_codec

#: Mask dtype — kept identical in the declared space and in :meth:`observe`.
#: ``int8`` (not float32) so the mask can be fed straight into
#: ``Discrete.sample(mask)``, which Gymnasium requires to be int8; this is what
#: PettingZoo's ``api_test`` does with the ``action_mask`` in the obs dict.
#: Values are still {0, 1} as design/04 specifies.
_MASK_DTYPE = np.int8


class PuertoRicoAEC(AECEnv):
    """AEC environment wrapping one :class:`~puerto_rico.engine.game.Game`."""

    metadata = {"name": "puerto_rico_v0", "is_parallelizable": False}

    def __init__(self, config: dict | None = None) -> None:
        super().__init__()
        config = dict(config or {})
        self.num_players: int = int(config.get("num_players", 4))
        self.seed: int | None = config.get("seed", None)
        self.reward_mode: str = config.get("reward_mode", "rank")
        self.shaping_coef: float = float(config.get("shaping_coef", 0.0))

        self.possible_agents: list[str] = [
            f"player_{i}" for i in range(self.num_players)
        ]
        self.agents: list[str] = list(self.possible_agents)

        obs_space = DictSpace(
            {
                "observation": Box(
                    low=0.0,
                    high=1.0,
                    shape=(obs_codec.OBS_LEN,),
                    dtype=np.float32,
                ),
                "action_mask": Box(
                    low=0.0,
                    high=1.0,
                    shape=(action_codec.N_ACTIONS,),
                    dtype=_MASK_DTYPE,
                ),
            }
        )
        act_space = Discrete(action_codec.N_ACTIONS)
        self.observation_spaces = {a: obs_space for a in self.possible_agents}
        self.action_spaces = {a: act_space for a in self.possible_agents}

        self.game: Game | None = None

    # --- PettingZoo space accessors ---------------------------------------- #

    def observation_space(self, agent: str):
        return self.observation_spaces[agent]

    def action_space(self, agent: str):
        return self.action_spaces[agent]

    # --- helpers ----------------------------------------------------------- #

    @staticmethod
    def _seat(agent: str) -> int:
        return int(agent.split("_")[1])

    def _sync_selection(self) -> None:
        """Point ``agent_selection`` at the engine's current decider."""
        self.agent_selection = f"player_{self.game.current_player}"

    # --- core AEC API ------------------------------------------------------ #

    def reset(self, seed=None, options=None):
        if seed is not None:
            self.seed = seed
        self.game = Game(GameConfig(num_players=self.num_players, seed=self.seed))

        self.agents = list(self.possible_agents)
        self.rewards = {a: 0.0 for a in self.agents}
        self._cumulative_rewards = {a: 0.0 for a in self.agents}
        self.terminations = {a: False for a in self.agents}
        self.truncations = {a: False for a in self.agents}
        self.infos = {a: {} for a in self.agents}

        self._sync_selection()
        # PettingZoo AEC `reset` returns None.
        return None

    def observe(self, agent: str) -> dict:
        perspective = self._seat(agent)
        # obs_codec works on the raw GameState; action_codec works on the Game
        # facade (it calls .legal_actions()).
        observation = obs_codec.encode(self.game.state, perspective)
        action_mask = action_codec.mask(self.game).astype(_MASK_DTYPE)
        return {"observation": observation, "action_mask": action_mask}

    def step(self, action: int) -> None:
        agent = self.agent_selection

        # Dead-step convention: a terminated/truncated agent's step is a no-op
        # that just advances the cursor (PettingZoo standard helper).
        if self.terminations[agent] or self.truncations[agent]:
            self._was_dead_step(action)
            return

        # Reward delivered this step accrues to the agent that just acted; clear
        # the prior step's per-agent rewards first (PettingZoo bookkeeping).
        self._cumulative_rewards[agent] = 0.0

        # Reject masked-illegal ids: training masks should prevent this, eval
        # surfaces agent bugs here.
        legal_mask = action_codec.mask(self.game)
        if not (0 <= int(action) < action_codec.N_ACTIONS) or not legal_mask[int(action)]:
            raise ValueError(
                f"illegal action id {action!r} for {agent} "
                f"(not set in the legality mask)"
            )

        act = action_codec.from_int(int(action), self.game.state)
        self.game.apply(act, validate=False)

        # Default: no per-step reward. Dense end-of-round shaping (scaled by
        # self.shaping_coef via reward_config.round_shaping) is left as a stub
        # here — it is wired into the training loop (agents-task-07), not the raw
        # env. Terminal rewards below honor self.reward_mode.
        self.rewards = {a: 0.0 for a in self.agents}

        if self.game.is_terminal:
            returns = reward_config.terminal_rewards(self.game.state, self.reward_mode)
            for a in self.agents:
                self.rewards[a] = float(returns[self._seat(a)])
                self.terminations[a] = True

        # Advance to the engine's next decider, then fold step rewards into the
        # cumulative totals that `last()` reports.
        self._sync_selection()
        self._accumulate_rewards()

    # --- rendering / teardown ---------------------------------------------- #

    def render(self) -> None:
        if self.game is None:
            return None
        # Lightweight text snapshot via the engine's public view.
        return self.game.public_view()

    def close(self) -> None:
        return None


def raw_env(**kwargs) -> PuertoRicoAEC:
    """Construct the raw AEC env (PettingZoo naming convention)."""
    return PuertoRicoAEC(config=kwargs or None)


def env(**kwargs) -> PuertoRicoAEC:
    """Factory returning a ready-to-use :class:`PuertoRicoAEC`."""
    return raw_env(**kwargs)
