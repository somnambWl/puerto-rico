"""Self-play rollout collector for the custom PyTorch PPO trainer (design/05).

This module plays full Puerto Rico games with a parameter-shared
:class:`~puerto_rico.training.model.MaskedActorCritic` policy and collects the
per-decision transitions the PPO update consumes, with GAE-Lambda advantages and
returns already computed.

Learner / opponent seat contract
--------------------------------
The game is seat-symmetric (the observation encoder writes the acting seat's
block first, design/04), so a single shared ``policy`` can drive every seat and
**every seat's decisions become learner training data** (full parameter
sharing). That is the default: ``opponent_policies is None`` -> pure self-play,
all seats collected.

When ``opponent_policies`` is supplied it maps *some* seats to fixed opponent
callables. Those seats are stepped through the environment by the opponent and
their decisions are **not** added to the learner batch (they are pure
environment dynamics). The remaining seats are the LEARNER seats, driven by
``policy`` and collected. Supports the two common cases directly:

- pure self-play (``opponent_policies=None``): collect all seats;
- 1 learner vs 3 fixed opponents: pass opponents for 3 of the 4 seats, the 4th
  is the learner and the only one collected.

Opponent callable contract
---------------------------
An opponent is any ``callable(game) -> int`` returning a *legal* discrete action
id (see :mod:`puerto_rico.env.action_codec`). ``game`` is the live engine
:class:`~puerto_rico.engine.game.Game`. Every baseline agent exposes the canonical
``act_id(game) -> int`` interface, so the adapters here are now thin shims over it
(:func:`wrap_heuristic`, :func:`wrap_random`), kept for backward-compatible imports.

Reward model
------------
Rewards are **terminal and general-sum** (design/05). Step rewards are 0; when a
game ends, :func:`~puerto_rico.training.reward_config.terminal_rewards` produces
one reward per seat, and that value is attached to the *last* learner transition
of that seat's trajectory. Intermediate shaping is intentionally left at 0.

GAE per (game, seat) trajectory
-------------------------------
Each seat's ordered sequence of decisions within a single game is one
trajectory. Because the reward is purely terminal and the episode truly ends at
game over, GAE-Lambda is computed within each (game, seat) trajectory with a
bootstrap value of 0 at the terminal step. ``returns = advantages + values``.

Advantage normalization
------------------------
Advantages are normalized to zero mean / unit std **across the whole returned
batch** at the end (PPO-standard). ``returns`` are left UN-normalized so the
value head regresses real returns; therefore ``returns == advantages_raw +
values`` holds for the raw (pre-normalization) advantages, not the normalized
ones returned. The raw advantages are recoverable as ``returns - values``.
"""

from __future__ import annotations

from typing import Callable, Mapping

import numpy as np
import torch

from ..engine.game import Game
from ..engine.state import GameConfig
from ..env import action_codec, obs_codec
from . import reward_config
from .model import MaskedActorCritic

# An opponent drives a seat: it receives the live Game and returns a legal id.
OpponentFn = Callable[[Game], int]


# --------------------------------------------------------------------------- #
# baseline-agent adapters                                                     #
# --------------------------------------------------------------------------- #


def wrap_heuristic(agent) -> OpponentFn:
    """Adapt a baseline agent to ``opp(game) -> int`` via its ``act_id(game)``.

    Backward-compatible shim: all baseline agents now expose the canonical
    ``act_id(game) -> int`` interface, so this routes through it (one mechanism).
    """

    return lambda game: int(agent.act_id(game))


def wrap_random(agent, *, perspective_is_current: bool = True) -> OpponentFn:
    """Adapt a ``RandomAgent`` to ``opp(game) -> int`` via its ``act_id(game)``.

    Backward-compatible shim: ``RandomAgent`` now exposes ``act_id(game)`` (it
    builds the obs dict internally and samples), so this routes through it — the
    same single mechanism used for every baseline.
    """

    return lambda game: int(agent.act_id(game))


# --------------------------------------------------------------------------- #
# trajectory bookkeeping                                                       #
# --------------------------------------------------------------------------- #


class _SeatTrajectory:
    """Accumulates one (game, seat) learner trajectory before GAE.

    ``shaping`` holds the per-step dense shaping reward (0 when no shaping is
    applied); it is added to the per-step reward vector before GAE.
    """

    __slots__ = ("obs", "masks", "actions", "logprobs", "values", "shaping")

    def __init__(self) -> None:
        self.obs: list[np.ndarray] = []
        self.masks: list[np.ndarray] = []
        self.actions: list[int] = []
        self.logprobs: list[float] = []
        self.values: list[float] = []
        self.shaping: list[float] = []

    def __len__(self) -> int:
        return len(self.actions)

    def add(self, obs, mask, action, logprob, value, shaping=0.0) -> None:
        self.obs.append(obs)
        self.masks.append(mask)
        self.actions.append(int(action))
        self.logprobs.append(float(logprob))
        self.values.append(float(value))
        self.shaping.append(float(shaping))


def _gae(
    values: np.ndarray,
    rewards: np.ndarray,
    gamma: float,
    gae_lambda: float,
) -> tuple[np.ndarray, np.ndarray]:
    """GAE-Lambda for ONE trajectory that ends at terminal (bootstrap 0).

    ``rewards`` is 0 everywhere except (typically) the final step. Returns
    ``(advantages, returns)`` with ``returns = advantages + values``.
    """
    t = len(values)
    adv = np.zeros(t, dtype=np.float64)
    last_gae = 0.0
    for i in reversed(range(t)):
        next_value = values[i + 1] if i + 1 < t else 0.0  # bootstrap 0 at end
        delta = rewards[i] + gamma * next_value - values[i]
        last_gae = delta + gamma * gae_lambda * last_gae
        adv[i] = last_gae
    returns = adv + values
    return adv, returns


# --------------------------------------------------------------------------- #
# rollout collection                                                           #
# --------------------------------------------------------------------------- #


def collect_rollouts(
    policy: MaskedActorCritic,
    *,
    num_players: int = 4,
    target_steps: int = 4096,
    opponent_policies: Mapping[int, OpponentFn] | None = None,
    gamma: float = 0.999,
    gae_lambda: float = 0.95,
    reward_mode: str = "rank",
    shaping_coef: float = 0.0,
    device: str = "cpu",
    rng_seed: int | None = None,
    deterministic: bool = False,
) -> dict[str, object]:
    """Play full games and collect learner transitions with GAE.

    See the module docstring for the learner/opponent seat contract, reward
    model, per-(game, seat) GAE, and the advantage-normalization choice.

    Parameters
    ----------
    policy:
        The shared :class:`MaskedActorCritic` driving every learner seat.
    num_players:
        Table size (default 4).
    target_steps:
        Minimum number of LEARNER transitions to collect; the last game always
        runs to completion, so the returned ``T`` is ``>= target_steps``.
    opponent_policies:
        Optional ``{seat: opp(game) -> int}``. Listed seats are driven by the
        opponent and NOT collected; remaining seats are learner seats. Seat ids
        here index seats *before* per-game rotation (i.e. fixed logical roles);
        seat rotation only changes engine seeds, not who is learner vs opponent.
    gamma, gae_lambda:
        GAE-Lambda discount / smoothing.
    reward_mode:
        Terminal reward mode (``"rank"`` default; see ``reward_config``).
    shaping_coef:
        Dense building-development shaping coefficient. When ``> 0``, each LEARNER
        transition's reward gets ``shaping_coef * Δ building_development_score``
        for that seat, where the delta is the change in the seat's
        :func:`reward_config.building_development_score` between its consecutive
        decision points (the first decision's delta is measured against the
        seat's score at the start of the game). This shaping reward is added to
        the transition reward BEFORE GAE so it shapes the advantage; the terminal
        rank reward is still added to the last transition as usual. Opponent
        seats are never affected. With ``shaping_coef == 0.0`` (default) the path
        is byte-identical to the no-shaping rollout. Expected to come from an
        annealed schedule (must reach 0 by end of training — design/05).
    device:
        Torch device for the returned tensors and policy inference.
    rng_seed:
        Base seed; per-game engine seeds are derived deterministically from it,
        so the same seed + same policy weights reproduces the rollout exactly.
    deterministic:
        If ``True``, the learner takes argmax actions (for eval-style rollouts).

    Returns
    -------
    dict with stacked torch tensors ``obs (T, OBS_LEN)``, ``action_masks
    (T, N_ACTIONS)``, ``actions (T,)``, ``logprobs (T,)``, ``values (T,)``,
    ``advantages (T,)`` (normalized), ``returns (T,)`` (raw), plus an ``info``
    dict of stats.
    """
    if opponent_policies is None:
        opponent_seats: set[int] = set()
    else:
        opponent_seats = set(opponent_policies.keys())
    learner_seats = [s for s in range(num_players) if s not in opponent_seats]
    if not learner_seats:
        raise ValueError("at least one seat must be a learner seat")

    base_seed = 0 if rng_seed is None else int(rng_seed)
    policy = policy.to(device)

    all_obs: list[np.ndarray] = []
    all_masks: list[np.ndarray] = []
    all_actions: list[int] = []
    all_logprobs: list[float] = []
    all_values: list[float] = []
    all_adv: list[np.ndarray] = []
    all_ret: list[np.ndarray] = []

    num_collected = 0
    num_games = 0
    episode_lengths: list[int] = []
    mask_violations = 0
    # mean terminal reward per FINAL placement (1st..last), accumulated.
    placement_reward_sum = np.zeros(num_players, dtype=np.float64)
    placement_count = 0

    while num_collected < target_steps:
        game_idx = num_games
        # Distinct engine seed per game (seat-rotation diversity comes free from
        # a fresh deal + which seat is governor each game).
        seed = base_seed * 1_000_003 + game_idx
        game = Game(GameConfig(num_players=num_players, seed=seed))

        # One learner trajectory per learner seat for this game.
        trajs: dict[int, _SeatTrajectory] = {s: _SeatTrajectory() for s in learner_seats}
        # Per-seat previous building-development score, for dense shaping. Only
        # touched when shaping_coef != 0 (keeps the no-shaping path identical).
        prev_dev: dict[int, float] = (
            {s: reward_config.building_development_score(game.state, s) for s in learner_seats}
            if shaping_coef != 0.0
            else {}
        )

        while not game.is_terminal:
            seat = game.current_player
            if seat in opponent_seats:
                action_id = int(opponent_policies[seat](game))
                action = action_codec.from_int(action_id, game.state)
                game.apply(action, validate=False)
                continue

            # learner seat decision
            obs_np = obs_codec.encode(game.state, seat)
            mask_np = action_codec.mask(game).astype(np.float32)
            obs_t = torch.as_tensor(obs_np, device=device)
            mask_t = torch.as_tensor(mask_np, device=device)
            action_t, logprob_t, value_t = policy.act(
                obs_t, mask_t, deterministic=deterministic
            )
            action_id = int(action_t.item())
            if mask_np[action_id] < 0.5:
                mask_violations += 1

            # dense building-development shaping at this seat's decision point.
            shaping_r = 0.0
            if shaping_coef != 0.0:
                dev_now = reward_config.building_development_score(game.state, seat)
                shaping_r = shaping_coef * (dev_now - prev_dev[seat])
                prev_dev[seat] = dev_now

            trajs[seat].add(
                obs_np,
                mask_np,
                action_id,
                float(logprob_t.item()),
                float(value_t.item()),
                shaping_r,
            )
            action = action_codec.from_int(action_id, game.state)
            game.apply(action, validate=False)

        # game over: terminal rewards per seat.
        rewards = reward_config.terminal_rewards(game.state, reward_mode)
        num_games += 1
        episode_lengths.append(sum(len(t) for t in trajs.values()))

        # placement-indexed reward stats (rank 0 == winner).
        from ..engine import scoring

        order = scoring.rankings(game.state)
        for place, seat_idx in enumerate(order):
            placement_reward_sum[place] += rewards[seat_idx]
        placement_count += 1

        # finalize each learner seat trajectory with GAE.
        for seat, traj in trajs.items():
            if len(traj) == 0:
                continue
            values = np.asarray(traj.values, dtype=np.float64)
            # Per-step shaping reward (all 0 when shaping_coef == 0) plus the
            # terminal rank reward on the last transition.
            rew = np.asarray(traj.shaping, dtype=np.float64)
            rew[-1] += rewards[seat]
            adv, ret = _gae(values, rew, gamma, gae_lambda)

            all_obs.extend(traj.obs)
            all_masks.extend(traj.masks)
            all_actions.extend(traj.actions)
            all_logprobs.extend(traj.logprobs)
            all_values.extend(traj.values)
            all_adv.append(adv)
            all_ret.append(ret)
            num_collected += len(traj)

    # stack everything.
    obs = torch.as_tensor(np.asarray(all_obs, dtype=np.float32), device=device)
    action_masks = torch.as_tensor(np.asarray(all_masks, dtype=np.float32), device=device)
    actions = torch.as_tensor(np.asarray(all_actions, dtype=np.int64), device=device)
    logprobs = torch.as_tensor(np.asarray(all_logprobs, dtype=np.float32), device=device)
    values = torch.as_tensor(np.asarray(all_values, dtype=np.float32), device=device)
    adv_np = np.concatenate(all_adv).astype(np.float32)
    ret_np = np.concatenate(all_ret).astype(np.float32)
    returns = torch.as_tensor(ret_np, device=device)

    # normalize advantages across the whole batch (returns left raw).
    adv_t = torch.as_tensor(adv_np, device=device)
    adv_mean = adv_t.mean()
    adv_std = adv_t.std(unbiased=False)
    advantages = (adv_t - adv_mean) / (adv_std + 1e-8)

    mean_placement_reward = (
        (placement_reward_sum / placement_count).tolist() if placement_count else []
    )

    info = {
        "num_games": num_games,
        "num_transitions": int(actions.shape[0]),
        "mean_episode_length": float(np.mean(episode_lengths)) if episode_lengths else 0.0,
        "mean_terminal_reward_by_placement": mean_placement_reward,
        "mask_violations": int(mask_violations),
        "reward_mode": reward_mode,
        "learner_seats": list(learner_seats),
    }

    return {
        "obs": obs,
        "action_masks": action_masks,
        "actions": actions,
        "logprobs": logprobs,
        "values": values,
        "advantages": advantages,
        "returns": returns,
        "info": info,
    }
