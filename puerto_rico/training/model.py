"""Masked actor-critic network for custom PyTorch PPO (design/05).

A shared MLP torso reads the flat observation vector (``OBS_LEN`` features) and
feeds a policy head producing ``N_ACTIONS`` logits and a scalar value head. The
**single most important correctness detail** is action masking: before any
sampling, entropy, or log-prob computation, illegal actions are pushed to
``~ -inf`` so they can never be selected and never inflate entropy.

Masking formula (applied to raw logits, ``action_mask`` is 0/1 float)::

    masked_logits = logits + (action_mask - 1) * 1e9

Legal positions (mask == 1) add ``0`` and are unchanged; illegal positions
(mask == 0) add ``-1e9``, so ``softmax`` assigns them ~0 probability. Because the
``Categorical`` distribution is built from these *masked* logits, both the sampled
action and the distribution entropy are computed over the masked distribution —
illegal actions contribute ~0 to entropy and are never sampled.

Inputs may be single (unbatched) or batched; a leading batch dim is added when
missing so every public method returns batched tensors consistently.
"""

from __future__ import annotations

import torch
from torch import Tensor, nn
from torch.distributions import Categorical

from ..env.action_codec import N_ACTIONS
from ..env.obs_codec import OBS_LEN

# Large finite penalty added to illegal logits. Finite (not -inf) so masked
# softmax stays numerically safe even when many actions are illegal.
_NEG_INF = 1e9


def _orthogonal_init(layer: nn.Linear, gain: float) -> nn.Linear:
    nn.init.orthogonal_(layer.weight, gain=gain)
    nn.init.zeros_(layer.bias)
    return layer


class MaskedActorCritic(nn.Module):
    """Shared-torso actor-critic with hard action masking on the policy head."""

    def __init__(
        self,
        obs_dim: int = OBS_LEN,
        n_actions: int = N_ACTIONS,
        hidden: tuple[int, ...] = (256, 256),
    ) -> None:
        super().__init__()
        self.obs_dim = obs_dim
        self.n_actions = n_actions

        layers: list[nn.Module] = []
        last = obs_dim
        for h in hidden:
            layers.append(_orthogonal_init(nn.Linear(last, h), gain=2.0**0.5))
            layers.append(nn.Tanh())
            last = h
        self.torso = nn.Sequential(*layers)

        # Small policy gain keeps the initial policy close to uniform; value
        # head uses gain 1.0 (standard for actor-critic init).
        self.policy_head = _orthogonal_init(nn.Linear(last, n_actions), gain=0.01)
        self.value_head = _orthogonal_init(nn.Linear(last, 1), gain=1.0)

    # ------------------------------------------------------------------ #
    # internals                                                          #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _ensure_batched(t: Tensor, width: int) -> tuple[Tensor, bool]:
        """Add a leading batch dim if ``t`` is 1-D. Returns (tensor, was_single)."""
        if t.dim() == 1:
            return t.unsqueeze(0), True
        return t, False

    def _masked_dist(self, logits: Tensor, action_mask: Tensor) -> Categorical:
        """Build a Categorical over masked logits (mask == 0 -> ~ -inf)."""
        masked = logits + (action_mask - 1.0) * _NEG_INF
        return Categorical(logits=masked)

    # ------------------------------------------------------------------ #
    # forward / inference                                                #
    # ------------------------------------------------------------------ #

    def forward(self, obs: Tensor, action_mask: Tensor) -> tuple[Tensor, Tensor]:
        """Return ``(masked_logits, value)``.

        ``masked_logits`` has shape ``(B, n_actions)`` with illegal positions at
        ``~ -1e9`` and legal positions equal to the raw torso logits. ``value``
        has shape ``(B,)``.
        """
        obs, _ = self._ensure_batched(obs, self.obs_dim)
        action_mask, _ = self._ensure_batched(action_mask, self.n_actions)

        obs = obs.to(dtype=torch.float32)
        action_mask = action_mask.to(dtype=torch.float32)

        features = self.torso(obs)
        logits = self.policy_head(features)
        value = self.value_head(features).squeeze(-1)

        masked_logits = logits + (action_mask - 1.0) * _NEG_INF
        return masked_logits, value

    @torch.no_grad()
    def act(
        self,
        obs: Tensor,
        action_mask: Tensor,
        *,
        deterministic: bool = False,
    ) -> tuple[Tensor, Tensor, Tensor]:
        """Sample (or argmax) a legal action.

        Returns ``(action, logprob, value)``. ``action`` is a long tensor of
        shape ``(B,)`` (or scalar for single input); the chosen action is always
        legal because the distribution is built from masked logits. ``logprob`` is
        the log-prob of the chosen action under the masked distribution.
        """
        single = obs.dim() == 1
        obs_b, _ = self._ensure_batched(obs, self.obs_dim)
        mask_b, _ = self._ensure_batched(action_mask, self.n_actions)

        obs_b = obs_b.to(dtype=torch.float32)
        mask_b = mask_b.to(dtype=torch.float32)

        features = self.torso(obs_b)
        logits = self.policy_head(features)
        value = self.value_head(features).squeeze(-1)

        dist = self._masked_dist(logits, mask_b)
        if deterministic:
            # argmax over masked logits == argmax over masked probs; illegal
            # positions sit at ~ -1e9 so they can never win the argmax.
            action = dist.logits.argmax(dim=-1)
        else:
            action = dist.sample()
        logprob = dist.log_prob(action)

        if single:
            return action.squeeze(0), logprob.squeeze(0), value.squeeze(0)
        return action, logprob, value

    # ------------------------------------------------------------------ #
    # PPO update                                                         #
    # ------------------------------------------------------------------ #

    def evaluate_actions(
        self,
        obs: Tensor,
        action_mask: Tensor,
        actions: Tensor,
    ) -> tuple[Tensor, Tensor, Tensor]:
        """Recompute log-probs / entropy / value for a PPO update.

        Everything is computed over the **masked** distribution: ``logprobs`` are
        the log-probs of ``actions`` under masked logits, ``entropy`` is the
        entropy of the masked distribution (illegal actions contribute ~0), and
        ``value`` is the state value. Returns batched tensors of shape ``(B,)``.
        """
        obs_b, _ = self._ensure_batched(obs, self.obs_dim)
        mask_b, _ = self._ensure_batched(action_mask, self.n_actions)
        if actions.dim() == 0:
            actions = actions.unsqueeze(0)

        obs_b = obs_b.to(dtype=torch.float32)
        mask_b = mask_b.to(dtype=torch.float32)

        features = self.torso(obs_b)
        logits = self.policy_head(features)
        value = self.value_head(features).squeeze(-1)

        dist = self._masked_dist(logits, mask_b)
        logprobs = dist.log_prob(actions)
        entropy = dist.entropy()
        return logprobs, entropy, value

    # ------------------------------------------------------------------ #
    # diagnostics                                                        #
    # ------------------------------------------------------------------ #

    @staticmethod
    def count_mask_violations(actions: Tensor, action_mask: Tensor) -> int:
        """Number of ``actions`` whose chosen id has ``mask == 0`` (must be 0)."""
        if action_mask.dim() == 1:
            action_mask = action_mask.unsqueeze(0)
        if actions.dim() == 0:
            actions = actions.unsqueeze(0)
        chosen = action_mask.gather(1, actions.long().unsqueeze(1)).squeeze(1)
        return int((chosen < 0.5).sum().item())
