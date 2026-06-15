# Task 04: Action-Masking Model

## Status
not started

## Epic
agents-training

## Dependencies
- env-task-02 (action codec / mask)
- env-task-03 (PettingZoo wrapper)

## Overview
Implement a Torch RLlib model that applies the action mask to the policy logits so illegal actions are never sampled, and that excludes masked actions from the entropy term.

## Design References
- `design/05-agents-and-training.md`

## Files to Create/Modify
| File | Action | Changes |
|------|--------|---------|
| `puerto_rico/training/masked_model.py` | Create | `MaskedActionModel(TorchModelV2)` |

## Specification

### `MaskedActionModel(TorchModelV2, nn.Module)`
- MLP torso over the flat feature vector `obs["observation"]`; hidden layer sizes configurable via `model_config` (e.g. `fcnet_hiddens`, default reasonable like `[256, 256]`).
- Forward pass:
  - Compute raw `logits` from the torso (size = discrete action space).
  - Read `action_mask = obs["action_mask"]`.
  - Apply masking: `masked_logits = logits + (action_mask - 1) * 1e9` so illegal actions get logits `~ -1e9` and are effectively never sampled.
  - Return `masked_logits` as the model output.
- Value head: separate branch producing the state value; expose via `value_function()`.
- Entropy / policy head: ensure the action distribution and entropy are computed over the **masked** logits so masked actions contribute ~0 probability and do not inflate entropy.
- Track and log a **mask-violation counter** (number of times a sampled action had `mask==0`); this must stay **0**.

## Verification
- For sampled states, logits at masked positions are `~ -1e9` and sampled actions are always legal.
- A short training/rollout reports **0 mask violations**.
- Entropy is finite and computed only over legal actions (no NaNs/Infs from all-but-one masked states).
