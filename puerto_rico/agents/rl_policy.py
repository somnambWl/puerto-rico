"""``RLPolicy`` — load a trained PPO checkpoint and play, no trainer at serve time.

This is the **inference** counterpart to :mod:`puerto_rico.training.ppo`. It loads
the lightweight checkpoint artifact that the trainer writes (a plain ``torch.save``
dict, schema documented in ``ppo.py``) and runs masked forward passes to pick a
legal action. Crucially it imports **only** the model
(:class:`~puerto_rico.training.model.MaskedActorCritic`) and the env codecs — never
``puerto_rico.training.ppo`` — so serving (the UI, the eval arena) does not pull in
the rollout collector, the optimizer, or any of the training loop.

Interface
---------
``RLPolicy`` deliberately mirrors
:class:`~puerto_rico.agents.heuristic_agent.HeuristicAgent`: it is **state/game
based**, not obs-dict based. The primary entry points are

* :meth:`act` ``(game) -> Action`` — the chosen engine action for
  ``game.current_player``, and
* :meth:`act_id` ``(game) -> int`` — the same choice as a discrete action id.

so the UI session and the evaluation arena can treat a ``HeuristicAgent`` and an
``RLPolicy`` interchangeably.

The mask guarantees legality: the network builds its action distribution from
**masked** logits (illegal ids pushed to ``~ -inf``), so the returned action is
always in ``game.legal_actions()``.

Determinism
-----------
``deterministic=True`` (the default) takes the argmax over masked logits — the same
state always yields the same action. ``deterministic=False`` samples from the masked
softmax (still always legal). The mode can be overridden per call via the
``deterministic=`` kwarg on :meth:`act` / :meth:`act_id`.
"""

from __future__ import annotations

from pathlib import Path

import torch

from ..engine.actions import Action
from ..env import action_codec, obs_codec
from ..training.inference import policy_act_id  # codec+model only — NOT the loop
from ..training.model import MaskedActorCritic  # model only — NOT the trainer loop

# Mirrors the constants the trainer bakes into the artifact (ppo.py). Kept local so
# this module never imports the training loop.
_ARTIFACT_FORMAT = "puerto_rico.rl_policy"
_SUPPORTED_VERSIONS = frozenset({1})


class IncompatibleCheckpointError(ValueError):
    """A checkpoint is structurally valid but its codec dims differ from installed.

    Raised when ``obs_dim`` / ``n_actions`` baked into the artifact no longer match
    the currently installed ``obs_codec.OBS_LEN`` / ``action_codec.N_ACTIONS`` — i.e.
    the net was trained against a different observation/action encoding and would be
    dimension-incompatible if loaded. It subclasses ``ValueError`` for backward
    compatibility, but callers/tests can catch it specifically to *skip* (the model
    must be retrained) rather than treat it as a hard failure.
    """


class RLPolicy:
    """A trained PPO policy that plays from a saved checkpoint (no RLlib/trainer).

    Parameters
    ----------
    checkpoint_path:
        Path to a ``torch.save`` artifact written by the PPO trainer (e.g.
        ``runs/ppo/final.pt``). Schema: a dict with ``format``, ``version``,
        ``codec``, ``model_state``, ``obs_dim``, ``n_actions``, ``hidden``,
        ``config``, ``iteration``.
    device:
        Torch device to load and run on (default ``"cpu"``; inference is a tiny MLP).
    deterministic:
        Default inference mode. ``True`` -> argmax (reproducible); ``False`` ->
        sample. Overridable per call.
    """

    def __init__(
        self,
        checkpoint_path: str | Path,
        *,
        device: str = "cpu",
        deterministic: bool = True,
    ) -> None:
        self.checkpoint_path = str(checkpoint_path)
        self.device = torch.device(device)
        self.deterministic = bool(deterministic)

        ckpt = torch.load(
            self.checkpoint_path, map_location=self.device, weights_only=False
        )
        self._validate(ckpt)

        self.obs_dim = int(ckpt["obs_dim"])
        self.n_actions = int(ckpt["n_actions"])
        self.hidden = tuple(int(h) for h in ckpt["hidden"])
        self.codec = dict(ckpt.get("codec", {}))
        self.iteration = ckpt.get("iteration")

        net = MaskedActorCritic(self.obs_dim, self.n_actions, self.hidden)
        net.load_state_dict(ckpt["model_state"])
        net.to(self.device).eval()
        self.policy = net

    # ------------------------------------------------------------------ #
    # construction helpers                                               #
    # ------------------------------------------------------------------ #

    @classmethod
    def from_checkpoint(
        cls,
        path: str | Path,
        *,
        device: str = "cpu",
        deterministic: bool = True,
    ) -> RLPolicy:
        """Factory: build an :class:`RLPolicy` from a checkpoint path."""
        return cls(path, device=device, deterministic=deterministic)

    @staticmethod
    def _validate(ckpt: object) -> None:
        if not isinstance(ckpt, dict):
            raise ValueError(
                f"checkpoint is not a dict (got {type(ckpt).__name__}); "
                "not an RLPolicy artifact"
            )
        fmt = ckpt.get("format")
        if fmt != _ARTIFACT_FORMAT:
            raise ValueError(
                f"unexpected artifact format {fmt!r}; expected {_ARTIFACT_FORMAT!r}"
            )
        ver = ckpt.get("version")
        if ver not in _SUPPORTED_VERSIONS:
            raise ValueError(
                f"unsupported artifact version {ver!r}; "
                f"supported: {sorted(_SUPPORTED_VERSIONS)}"
            )
        for key in ("model_state", "obs_dim", "n_actions", "hidden"):
            if key not in ckpt:
                raise ValueError(f"checkpoint missing required key {key!r}")
        # Guard against an obs/action codec that differs from what is installed —
        # the encoding the net learned must match what we feed it at serve time.
        if obs_codec.OBS_LEN != int(ckpt["obs_dim"]):
            raise IncompatibleCheckpointError(
                f"obs_dim mismatch: artifact={ckpt['obs_dim']} "
                f"installed OBS_LEN={obs_codec.OBS_LEN}; retrain the model"
            )
        if action_codec.N_ACTIONS != int(ckpt["n_actions"]):
            raise IncompatibleCheckpointError(
                f"n_actions mismatch: artifact={ckpt['n_actions']} "
                f"installed N_ACTIONS={action_codec.N_ACTIONS}; retrain the model"
            )

    # ------------------------------------------------------------------ #
    # inference                                                          #
    # ------------------------------------------------------------------ #

    def _action_id(self, game, deterministic: bool) -> int:
        """Masked forward pass -> a legal discrete action id for the current seat.

        Delegates to the shared :func:`~puerto_rico.training.inference.policy_act_id`
        helper (encode obs -> build mask -> masked ``act`` -> int), the same path
        the trainer / opponent pool use, so behaviour is identical everywhere.
        """
        return policy_act_id(
            self.policy, game, device=str(self.device), deterministic=deterministic
        )

    def act_id(self, game, *, deterministic: bool | None = None) -> int:
        """Return the discrete action id the policy chooses for ``game``.

        ``deterministic`` overrides the instance default for this call.
        """
        det = self.deterministic if deterministic is None else bool(deterministic)
        return self._action_id(game, det)

    def act(self, game, *, deterministic: bool | None = None) -> Action:
        """Return the legal :class:`Action` the policy chooses for ``game``.

        The action is guaranteed legal (``in game.legal_actions()``) because the
        network samples/argmaxes over the masked action distribution.
        """
        action_id = self.act_id(game, deterministic=deterministic)
        return action_codec.from_int(action_id, game.state)

    def reset(self) -> None:
        """No per-episode state (stateless feed-forward inference)."""
        return None
