# Task 06: Reward Shaping and Engine Integration

## Status
not started

## Epic
agents-training

## Dependencies
- engine
- training config

## Overview
Add reward computation to the engine (`returns()`) supporting multiple reward modes plus optional dense shaping, and a `reward_config` module that selects/anneals the mode for training.

## Design References
- `design/05-agents-and-training.md`

## Files to Create/Modify
| File | Action | Changes |
|------|--------|---------|
| `puerto_rico/engine/...` (returns API) | Modify | Add `returns(reward_mode, shaping_coef=None)` |
| `puerto_rico/training/reward_config.py` | Create | Reward-mode selection + annealing schedule |

## Specification

### Engine `returns(reward_mode, shaping_coef=None) -> dict[seat, float]`
Terminal returns per seat by mode (4-player is general-sum):
- **`"rank"`** (default): zero-mean rank rewards `1st = +1`, `2nd = +1/3`, `3rd = -1/3`, `4th = -1`. Ties resolved by the game's tie-break, then split/assigned consistently so the vector sums to ~0.
- **`"win"`**: `+1` to the winner, `0` to everyone else.
- **`"vp_margin"`**: z-scored victory points across the 4 seats (mean 0, unit variance over the table).

### Optional dense shaping (`shaping_coef`)
- When `shaping_coef` is not `None`, add an end-of-round dense term: `shaping_coef * Δ(self_vp - mean(others_vp))` (the per-round change in the seat's VP advantage over the table mean).
- Shaping is additive to the chosen terminal mode and **annealed to 0** over training.

### `training/reward_config.py`
- Expose the available modes and a default (`"rank"`).
- Provide a `shaping_coef` schedule (start value + anneal-to-zero over a configurable horizon) consumed by the training loop (agents-task-07).

## Verification
- `returns("rank")` on a decided game yields the vector `[+1, +1/3, -1/3, -1]` mapped to seats by final placement (sums to ~0).
- `returns("win")` gives `+1` to winner, `0` otherwise.
- `returns("vp_margin")` is zero-mean across seats.
- The shaping schedule reaches `0` at/after the configured horizon.
