"""Tests for the masked actor-critic network (PyTorch PPO).

The critical correctness properties verified here:
- masked logits push illegal actions to ~ -1e9 and leave legal ones unchanged;
- sampled / deterministic actions are ALWAYS legal (0 mask violations);
- log-probs and entropy are computed over the MASKED distribution (so a forced
  choice has ~0 entropy and several legal actions give > 0 entropy);
- single and batched inputs both work; a PPO-like backward pass is NaN-free.
"""

from __future__ import annotations

import torch

from puerto_rico.env.action_codec import N_ACTIONS
from puerto_rico.env.obs_codec import OBS_LEN
from puerto_rico.training.model import MaskedActorCritic


def _random_mask(batch: int, *, generator: torch.Generator) -> torch.Tensor:
    """Random 0/1 mask of shape (batch, N_ACTIONS) with >= 1 legal action each."""
    mask = (torch.rand(batch, N_ACTIONS, generator=generator) > 0.5).float()
    # Guarantee at least one legal action per row.
    forced = torch.randint(0, N_ACTIONS, (batch,), generator=generator)
    mask[torch.arange(batch), forced] = 1.0
    return mask


def _model() -> MaskedActorCritic:
    torch.manual_seed(0)
    return MaskedActorCritic()


def test_dims_match_codecs():
    m = _model()
    assert m.obs_dim == OBS_LEN
    assert m.n_actions == N_ACTIONS


def test_forward_shapes_and_masking():
    m = _model()
    g = torch.Generator().manual_seed(1)
    B = 16
    obs = torch.randn(B, OBS_LEN, generator=g)
    mask = _random_mask(B, generator=g)

    masked_logits, value = m.forward(obs, mask)
    assert masked_logits.shape == (B, N_ACTIONS)
    assert value.shape == (B,)

    # Recover raw logits to compare legal positions.
    features = m.torso(obs)
    raw = m.policy_head(features)

    illegal = mask < 0.5
    legal = ~illegal
    # Illegal positions are very negative.
    assert (masked_logits[illegal] <= -1e8).all()
    # Legal positions are unchanged from raw logits.
    assert torch.allclose(masked_logits[legal], raw[legal], atol=1e-4)


def test_act_always_legal_no_violations():
    m = _model()
    g = torch.Generator().manual_seed(2)
    total_violations = 0
    total_samples = 0
    for _ in range(50):
        B = 64
        obs = torch.randn(B, OBS_LEN, generator=g)
        mask = _random_mask(B, generator=g)
        action, logprob, value = m.act(obs, mask)

        assert action.shape == (B,)
        assert logprob.shape == (B,)
        assert value.shape == (B,)
        assert torch.isfinite(logprob).all()

        # Every sampled action must be legal.
        chosen_mask = mask.gather(1, action.unsqueeze(1)).squeeze(1)
        assert (chosen_mask == 1.0).all()
        total_violations += m.count_mask_violations(action, mask)
        total_samples += B

    assert total_samples > 3000
    assert total_violations == 0


def test_act_deterministic_is_legal_argmax():
    m = _model()
    g = torch.Generator().manual_seed(3)
    B = 32
    obs = torch.randn(B, OBS_LEN, generator=g)
    mask = _random_mask(B, generator=g)

    action, _, _ = m.act(obs, mask, deterministic=True)
    # Deterministic action is always legal.
    chosen_mask = mask.gather(1, action.unsqueeze(1)).squeeze(1)
    assert (chosen_mask == 1.0).all()
    assert m.count_mask_violations(action, mask) == 0

    # It must equal the argmax over legal raw logits.
    features = m.torso(obs)
    raw = m.policy_head(features)
    masked_for_argmax = raw.masked_fill(mask < 0.5, float("-inf"))
    expected = masked_for_argmax.argmax(dim=-1)
    assert torch.equal(action, expected)


def test_evaluate_matches_act_logprobs():
    m = _model()
    g = torch.Generator().manual_seed(4)
    B = 48
    obs = torch.randn(B, OBS_LEN, generator=g)
    mask = _random_mask(B, generator=g)

    action, act_logprob, act_value = m.act(obs, mask)
    eval_logprob, entropy, eval_value = m.evaluate_actions(obs, mask, action)

    assert torch.allclose(act_logprob, eval_logprob, atol=1e-5)
    assert torch.allclose(act_value, eval_value, atol=1e-5)
    assert torch.isfinite(entropy).all()
    assert (entropy >= -1e-6).all()


def test_entropy_zero_when_forced_choice():
    m = _model()
    g = torch.Generator().manual_seed(5)
    B = 8
    obs = torch.randn(B, OBS_LEN, generator=g)

    # Exactly one legal action per row -> forced choice -> ~0 entropy.
    mask = torch.zeros(B, N_ACTIONS)
    forced = torch.randint(0, N_ACTIONS, (B,), generator=g)
    mask[torch.arange(B), forced] = 1.0

    _, entropy, _ = m.evaluate_actions(obs, mask, forced)
    assert torch.isfinite(entropy).all()
    assert (entropy.abs() < 1e-3).all()


def test_entropy_positive_when_several_legal():
    m = _model()
    g = torch.Generator().manual_seed(6)
    B = 8
    obs = torch.randn(B, OBS_LEN, generator=g)

    # Make all actions legal -> entropy should be clearly positive.
    mask = torch.ones(B, N_ACTIONS)
    dummy_actions = torch.zeros(B, dtype=torch.long)
    _, entropy, _ = m.evaluate_actions(obs, mask, dummy_actions)
    assert (entropy > 0.5).all()


def test_single_unbatched_input():
    m = _model()
    g = torch.Generator().manual_seed(7)
    obs = torch.randn(OBS_LEN, generator=g)
    mask = _random_mask(1, generator=g).squeeze(0)

    logits, value = m.forward(obs, mask)
    assert logits.shape == (1, N_ACTIONS)
    assert value.shape == (1,)

    action, logprob, val = m.act(obs, mask)
    assert action.dim() == 0  # scalar
    assert logprob.dim() == 0
    assert val.dim() == 0
    assert mask[action.item()] == 1.0

    # evaluate_actions accepts a scalar action.
    lp, ent, v = m.evaluate_actions(obs, mask, action)
    assert lp.shape == (1,)
    assert ent.shape == (1,)
    assert v.shape == (1,)
    assert torch.allclose(lp.squeeze(0), logprob, atol=1e-5)


def test_gradient_sanity_ppo_like():
    m = _model()
    g = torch.Generator().manual_seed(8)
    B = 32
    obs = torch.randn(B, OBS_LEN, generator=g)
    mask = _random_mask(B, generator=g)

    action, old_logprob, _ = m.act(obs, mask)
    old_logprob = old_logprob.detach()

    opt = torch.optim.Adam(m.parameters(), lr=1e-3)
    before = [p.detach().clone() for p in m.parameters()]

    logprobs, entropy, value = m.evaluate_actions(obs, mask, action)
    advantages = torch.randn(B, generator=g)
    returns = torch.randn(B, generator=g)

    ratio = torch.exp(logprobs - old_logprob)
    pg_loss = -(ratio * advantages).mean()
    v_loss = ((value - returns) ** 2).mean()
    loss = pg_loss + 0.5 * v_loss - 0.01 * entropy.mean()

    assert torch.isfinite(loss)
    opt.zero_grad()
    loss.backward()

    # No NaN gradients.
    for p in m.parameters():
        assert p.grad is not None
        assert torch.isfinite(p.grad).all()
    opt.step()

    # At least one parameter changed.
    changed = any(
        not torch.allclose(b, p) for b, p in zip(before, m.parameters())
    )
    assert changed
