"""Shared masked-policy inference helper for the trainer / serving paths.

Every place that needs "given a live ``Game``, what discrete action id does this
``MaskedActorCritic`` pick?" was repeating the same five lines: encode the obs for
the acting seat, build the legality mask, wrap both in tensors, run
:meth:`~puerto_rico.training.model.MaskedActorCritic.act` under ``no_grad``, and
return the chosen ``int``. That snippet lived (subtly inconsistently) in the
rollout collector, the opponent pool, the PPO eval loop, and the serving
``RLPolicy``.

:func:`policy_act_id` is the single implementation. ``MaskedActorCritic.act`` is
already ``@torch.no_grad``, so no extra guard is needed; the mask guarantees the
returned id is legal (illegal logits are pushed to ``~ -inf`` before sampling /
argmax).
"""

from __future__ import annotations

import numpy as np
import torch

from ..env import action_codec, obs_codec
from .model import MaskedActorCritic


def policy_act_id(
    policy: MaskedActorCritic,
    game,
    *,
    device: str = "cpu",
    deterministic: bool = False,
) -> int:
    """Return a legal discrete action id for ``game.current_player``.

    Encodes the observation for the acting seat, builds the legality mask
    (``action_codec.mask`` calls ``game.legal_actions()``, so the live ``Game`` is
    passed), runs a masked forward pass, and returns the chosen action id. The id
    is always legal because the policy's distribution is built from masked logits.

    Parameters
    ----------
    policy:
        The :class:`MaskedActorCritic` to query.
    game:
        The live engine :class:`~puerto_rico.engine.game.Game`.
    device:
        Torch device for the obs/mask tensors and inference.
    deterministic:
        ``True`` -> argmax over masked logits (reproducible); ``False`` (default)
        -> sample from the masked distribution.
    """
    seat = game.current_player
    obs_np = obs_codec.encode(game.state, seat)
    mask_np = action_codec.mask(game).astype(np.float32)
    obs_t = torch.as_tensor(obs_np, device=device)
    mask_t = torch.as_tensor(mask_np, device=device)
    action_t, _, _ = policy.act(obs_t, mask_t, deterministic=deterministic)
    return int(action_t.item())
