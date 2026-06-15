"""Self-play opponent pool for the custom PyTorch PPO trainer (design/05).

This module manages the set of opponents that fill the *non-learner* seats during
self-play rollouts. The contract it targets is the one
:func:`puerto_rico.training.rollout.collect_rollouts` already speaks: an opponent
is any ``callable(game: Game) -> int`` returning a *legal* discrete action id (see
:mod:`puerto_rico.env.action_codec`). Anything this module produces drops directly
into ``collect_rollouts(..., opponent_policies={seat: opp})``.

What the pool holds
-------------------
* The two fixed **baselines**, always present:
  :class:`~puerto_rico.agents.random_agent.RandomAgent` and
  :class:`~puerto_rico.agents.heuristic_agent.HeuristicAgent`. These are adapted
  to the opponent contract with :func:`rollout.wrap_random` / ``wrap_heuristic``.
* A bounded list of **frozen policy snapshots** — past ``MaskedActorCritic``
  weights captured during training, each tagged with its ``iteration`` and
  optional metadata (e.g. Elo). Snapshots are stored as deep-copied **CPU**
  ``state_dict``s so (a) later training never mutates them and (b) they are
  pickle-friendly and ride along in a checkpoint.

The frozen-policy opponent
--------------------------
:func:`make_snapshot_opponent` rebuilds a network from a stored ``state_dict``,
sets it to ``eval()``/``no_grad``, and returns a ``callable(game) -> int`` that
encodes the obs for ``game.current_player``, builds the mask, and returns a legal
action via the **same** ``obs_codec`` / ``action_codec`` path the rollout uses, so
the frozen opponent behaves exactly like the live learner did at snapshot time.
By default it **samples** (for behavioural diversity in the pool); pass
``deterministic=True`` for argmax.

How "self" is handled
---------------------
``sample_opponents`` is **self-contained**: it takes the *live* learner policy and,
for any "self" slot it draws, returns a live-policy opponent callable (a thin
wrapper around ``policy.act`` over the current weights). The trainer therefore does
not have to interpret sentinels — every element of the returned list is a ready
``callable(game) -> int``. (The live-policy wrapper closes over the live ``policy``
object, so its behaviour tracks the learner as training proceeds within an
iteration; opponents are re-sampled each iteration anyway.)

Sampling distribution (per non-learner seat, independently)
----------------------------------------------------------
With probability ``self_play_prob`` (default 0.5) the seat is **self** (live
policy). The remaining mass is split:

* if any snapshots exist: ``snapshot_share`` (default 0.7) of it goes to a frozen
  snapshot, biased toward recent ones (the latest gets half that share, the rest
  uniformly among older snapshots), and ``1 - snapshot_share`` goes to a baseline;
* if no snapshots exist yet: all of the non-self mass goes to the baselines.

Baselines are picked uniformly between random and heuristic. All probabilities are
configurable on the pool. The intent (design/05): *mostly* self / recent policy,
*sometimes* an older snapshot (defends against strategy collapse / cycling),
*sometimes* a baseline (keeps a floor of basic competence in the mix).
"""

from __future__ import annotations

import copy
import re
from collections import deque
from dataclasses import dataclass, field
from typing import Callable

import numpy as np
import torch

from ..agents.heuristic_agent import HeuristicAgent
from ..agents.random_agent import RandomAgent
from ..engine.game import Game
from ..env import action_codec, obs_codec
from .model import MaskedActorCritic
from .rollout import OpponentFn, wrap_heuristic, wrap_random

__all__ = [
    "Snapshot",
    "make_snapshot_opponent",
    "make_live_opponent",
    "OpponentPool",
]


# --------------------------------------------------------------------------- #
# snapshot record                                                             #
# --------------------------------------------------------------------------- #


@dataclass
class Snapshot:
    """One frozen ``MaskedActorCritic`` snapshot stored in the pool.

    ``state_dict`` is a deep-copied, CPU-resident, pickle-friendly mapping of the
    network weights at ``iteration``. ``metadata`` carries free-form tags (e.g.
    ``{"elo": 1042.0}``).
    """

    iteration: int
    state_dict: dict
    metadata: dict = field(default_factory=dict)


def _cpu_clone_state_dict(state_dict: dict) -> dict:
    """Deep-copy a state_dict onto CPU, detached, so it never aliases live weights."""
    return {k: v.detach().to("cpu").clone() for k, v in state_dict.items()}


def _factory_for_state_dict(state_dict: dict) -> Callable[[], MaskedActorCritic]:
    """Build a ``MaskedActorCritic`` factory matching ``state_dict``'s shapes.

    Infers ``obs_dim``, the ``hidden`` tuple and ``n_actions`` from the saved
    ``torso.*.weight`` / ``policy_head.weight`` tensors so snapshots from a
    non-default (e.g. wider/deeper) network rebuild correctly. The torso is an
    ``nn.Sequential`` of ``Linear`` layers at even indices (0, 2, 4, ...).
    """
    torso_idxs = sorted(
        int(m.group(1))
        for k in state_dict
        if (m := re.match(r"torso\.(\d+)\.weight$", k))
    )
    hidden = tuple(int(state_dict[f"torso.{i}.weight"].shape[0]) for i in torso_idxs)
    obs_dim = int(state_dict[f"torso.{torso_idxs[0]}.weight"].shape[1])
    n_actions = int(state_dict["policy_head.weight"].shape[0])
    return lambda: MaskedActorCritic(obs_dim, n_actions, hidden)


# --------------------------------------------------------------------------- #
# opponent wrappers                                                           #
# --------------------------------------------------------------------------- #


def _policy_opponent(policy: MaskedActorCritic, *, deterministic: bool) -> OpponentFn:
    """Build a ``callable(game) -> int`` from a (ready) ``MaskedActorCritic``.

    Uses the same obs/action codec path as :func:`rollout.collect_rollouts`, so the
    opponent's behaviour is consistent with how the learner is rolled out.
    """

    def _fn(game: Game) -> int:
        seat = game.current_player
        obs_np = obs_codec.encode(game.state, seat)
        mask_np = action_codec.mask(game).astype(np.float32)
        obs_t = torch.as_tensor(obs_np)
        mask_t = torch.as_tensor(mask_np)
        action_t, _, _ = policy.act(obs_t, mask_t, deterministic=deterministic)
        return int(action_t.item())

    return _fn


def make_snapshot_opponent(
    state_dict: dict,
    *,
    deterministic: bool = False,
    model_factory: Callable[[], MaskedActorCritic] | None = None,
) -> OpponentFn:
    """Build a frozen-policy opponent callable from a stored ``state_dict``.

    The network is rebuilt (default :class:`MaskedActorCritic`), loaded with the
    snapshot weights, moved to CPU and set to ``eval()``. Inference runs under
    ``no_grad`` (``MaskedActorCritic.act`` is already ``@torch.no_grad``). Returns
    a ``callable(game) -> int`` returning a legal action id.

    Parameters
    ----------
    deterministic:
        ``False`` (default) samples from the masked policy (diversity); ``True``
        takes the argmax.
    model_factory:
        Optional builder for the network shell (must match the snapshot's shapes).
        Defaults to a plain ``MaskedActorCritic()``.
    """
    net = (model_factory or MaskedActorCritic)()
    net.load_state_dict(state_dict)
    net.to("cpu")
    net.eval()
    return _policy_opponent(net, deterministic=deterministic)


def make_live_opponent(
    policy: MaskedActorCritic, *, deterministic: bool = False
) -> OpponentFn:
    """Build an opponent callable backed by the *live* learner ``policy``.

    Unlike :func:`make_snapshot_opponent` this does **not** copy weights: it closes
    over the live policy object, so a "self" seat plays the current learner. Used by
    :meth:`OpponentPool.sample_opponents` for self slots.
    """
    return _policy_opponent(policy, deterministic=deterministic)


# --------------------------------------------------------------------------- #
# the pool                                                                     #
# --------------------------------------------------------------------------- #


class OpponentPool:
    """Bounded self-play opponent pool: baselines + frozen policy snapshots.

    Parameters
    ----------
    max_snapshots:
        Cap on stored frozen snapshots. When exceeded the **oldest** snapshot is
        evicted (FIFO); :meth:`add_snapshot` returns the evicted :class:`Snapshot`.
    self_play_prob:
        Per-seat probability that a sampled opponent is *self* (the live policy).
    snapshot_share:
        Of the non-self probability mass, the fraction routed to frozen snapshots
        when any exist (the remainder goes to a baseline). Ignored (treated as 0)
        when the pool has no snapshots.
    latest_snapshot_bias:
        Within the snapshot mass, the probability of picking the *latest* snapshot
        (vs. a uniform older one). Recency bias keeps self-play near the current
        frontier while still revisiting history.
    deterministic_opponents:
        If ``True``, snapshot/live opponents take argmax; default ``False``
        (sample) for behavioural diversity.
    random_seed / heuristic_seed:
        Seeds for the always-present baseline agents.
    """

    def __init__(
        self,
        *,
        max_snapshots: int = 10,
        self_play_prob: float = 0.5,
        snapshot_share: float = 0.7,
        latest_snapshot_bias: float = 0.5,
        deterministic_opponents: bool = False,
        random_seed: int | None = 0,
        heuristic_seed: int | None = 0,
    ) -> None:
        if max_snapshots < 1:
            raise ValueError("max_snapshots must be >= 1")
        self.max_snapshots = int(max_snapshots)
        self.self_play_prob = float(self_play_prob)
        self.snapshot_share = float(snapshot_share)
        self.latest_snapshot_bias = float(latest_snapshot_bias)
        self.deterministic_opponents = bool(deterministic_opponents)

        self._snapshots: deque[Snapshot] = deque()

        # Always-present baselines, adapted to the opponent contract.
        self._random_agent = RandomAgent(seed=random_seed)
        self._heuristic_agent = HeuristicAgent(seed=heuristic_seed)
        self._random_opp = wrap_random(self._random_agent)
        self._heuristic_opp = wrap_heuristic(self._heuristic_agent)

    # ----- size / inspection ------------------------------------------- #

    def __len__(self) -> int:
        """Number of stored frozen snapshots (baselines are not counted)."""
        return len(self._snapshots)

    @property
    def snapshots(self) -> list[Snapshot]:
        """Stored snapshots, oldest first (a copy of the internal order)."""
        return list(self._snapshots)

    def latest(self) -> Snapshot | None:
        """Most recently added snapshot, or ``None`` if none stored yet."""
        return self._snapshots[-1] if self._snapshots else None

    # ----- mutation ----------------------------------------------------- #

    def add_snapshot(
        self,
        state_dict: dict,
        iteration: int,
        metadata: dict | None = None,
    ) -> Snapshot | None:
        """Store a deep CPU copy of ``state_dict`` and enforce the size cap.

        The weights are detached and cloned to CPU so subsequent training never
        mutates the stored snapshot. Returns the evicted :class:`Snapshot` when the
        cap forced one out (FIFO, oldest first), else ``None``.
        """
        snap = Snapshot(
            iteration=int(iteration),
            state_dict=_cpu_clone_state_dict(state_dict),
            metadata=dict(metadata or {}),
        )
        self._snapshots.append(snap)
        if len(self._snapshots) > self.max_snapshots:
            return self._snapshots.popleft()
        return None

    # ----- opponent builders ------------------------------------------- #

    def baseline_opponents(self) -> dict[str, OpponentFn]:
        """The always-present baseline opponents, by name."""
        return {"random": self._random_opp, "heuristic": self._heuristic_opp}

    def snapshot_opponent(self, snap: Snapshot) -> OpponentFn:
        """Build a frozen-policy opponent callable for ``snap``.

        The network shell is rebuilt to match the snapshot's *actual* layer
        shapes (read from its ``state_dict``) so snapshots from a non-default
        (e.g. wider) :class:`MaskedActorCritic` load correctly.
        """
        factory = _factory_for_state_dict(snap.state_dict)
        return make_snapshot_opponent(
            snap.state_dict,
            deterministic=self.deterministic_opponents,
            model_factory=factory,
        )

    # ----- sampling ----------------------------------------------------- #

    def sample_opponents(
        self,
        num_seats: int,
        policy: MaskedActorCritic,
        *,
        self_play_prob: float | None = None,
        rng: np.random.Generator | None = None,
    ) -> list[OpponentFn]:
        """Return ``num_seats`` opponent callables to fill the non-learner seats.

        Each seat is drawn independently from the distribution documented at module
        level. "self" slots are materialised against the live ``policy`` (no
        sentinels). Every element is a ready ``callable(game) -> int``.

        Parameters
        ----------
        num_seats:
            How many non-learner seats to fill.
        policy:
            The live learner policy, used for "self" slots.
        self_play_prob:
            Override the pool's default per-seat self probability for this call.
        rng:
            Optional ``numpy`` generator for reproducible sampling.
        """
        if num_seats < 0:
            raise ValueError("num_seats must be >= 0")
        gen = rng if rng is not None else np.random.default_rng()
        p_self = self.self_play_prob if self_play_prob is None else float(self_play_prob)

        out: list[OpponentFn] = []
        for _ in range(num_seats):
            out.append(self._sample_one(policy, p_self, gen))
        return out

    def _sample_one(
        self, policy: MaskedActorCritic, p_self: float, gen: np.random.Generator
    ) -> OpponentFn:
        # 1) self vs. not-self
        if gen.random() < p_self:
            return make_live_opponent(
                policy, deterministic=self.deterministic_opponents
            )

        # 2) snapshot vs. baseline (snapshots only if any exist)
        use_snapshot = len(self._snapshots) > 0 and gen.random() < self.snapshot_share
        if use_snapshot:
            snap = self._sample_snapshot(gen)
            return self.snapshot_opponent(snap)

        # 3) baseline: uniform between random and heuristic
        if gen.random() < 0.5:
            return self._random_opp
        return self._heuristic_opp

    def _sample_snapshot(self, gen: np.random.Generator) -> Snapshot:
        """Pick a snapshot: latest with ``latest_snapshot_bias``, else uniform older."""
        snaps = self._snapshots
        if len(snaps) == 1:
            return snaps[-1]
        if gen.random() < self.latest_snapshot_bias:
            return snaps[-1]
        # uniform among the older snapshots (all but the latest)
        idx = int(gen.integers(len(snaps) - 1))
        return snaps[idx]
