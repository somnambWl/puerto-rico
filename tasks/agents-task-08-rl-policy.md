# Task 08: RLPolicy Inference Wrapper

## Status
done

## Epic
agents-training

## Dependencies
- env codecs (env-task-01/02)
- agents-task-07
- agents-task-01

## Overview
Implement `RLPolicy`, an `Agent` that loads the lightweight inference artifact (no RLlib at serve time) and performs masked inference for play in the UI and evaluation.

## Design References
- `design/05-agents-and-training.md`

## Files to Create/Modify
| File | Action | Changes |
|------|--------|---------|
| `puerto_rico/agents/rl_policy.py` | Create | `RLPolicy(Agent)` |
| `puerto_rico/agents/__init__.py` | Modify | Export `RLPolicy` |

## Specification

### `RLPolicy(Agent)`
- Constructor: `RLPolicy(artifact_path, *, deterministic=False, device="cpu")`.
  - Loads the lightweight artifact from agents-task-07 (torch weights + codec versions + minimal config) **without importing RLlib**.
  - Validates the artifact's codec versions against the installed env codecs; error clearly on mismatch.
  - Moves weights to `device`.
- `act(obs, *, rng=None) -> int`:
  - Runs the torso/forward to produce logits, applies the action mask (`logits + (mask-1)*1e9`) identically to training (agents-task-04).
  - **Deterministic** mode: return `argmax` over masked logits.
  - **Stochastic** mode: sample from the masked softmax using `rng` if provided, else internal RNG.
  - Always returns a legal action (`mask==1`).
- `reset()`: no-op (stateless inference) unless recurrent state is later added.

## Verification
- Loads the artifact in a process without RLlib imported.
- Returns a legal action for 100 sampled states (0 mask violations).
- Inference latency `< 100 ms` per action on CPU.
- Deterministic mode is reproducible; stochastic mode respects the passed `rng`.
