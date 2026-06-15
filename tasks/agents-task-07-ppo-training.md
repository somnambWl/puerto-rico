# Task 07: PPO Training Config and Loop

## Status
done (SUPERSEDED: implemented as custom PyTorch PPO)

## NOTE: Superseded
This task describes RLlib-based PPO training. The project was reworked to use **custom PyTorch PPO**.
The equivalent implementation is:
- **Training config:** `training/ppo.py` — `PPOConfig` dataclass (not `config.yaml`).
- **Training loop:** `training/ppo.py` — `train(cfg)` function with manual PPO update loop (not
  RLlib's `Trainer.train()`).
- **Checkpoint format:** plain `torch.save()` dict with codec versions and model state (not RLlib
  checkpoint directory).

See `conversation-notes.md` for the RL backend decision rationale.

## Epic
agents-training

## Dependencies
- agents-task-03
- agents-task-04
- agents-task-05
- agents-task-06
- agents-task-01
- agents-task-02

## Overview
Wire everything into a PPO self-play training entrypoint: config builder, training loop with checkpointing, and export of a lightweight inference artifact that loads without RLlib at serve time.

## Design References
- `design/05-agents-and-training.md`

## Files to Create/Modify
| File | Action | Changes |
|------|--------|---------|
| `puerto_rico/training/train.py` | Create | `get_ppo_config()`, `train()` |
| `puerto_rico/training/config.yaml` | Create | Default hyperparameters |

## Specification

### `get_ppo_config() -> PPOConfig`
Builds an RLlib PPO config that uses:
- The registered env (agents-task-03) and `policy_mapping_fn` with learner-seat rotation.
- The `MaskedActionModel` (agents-task-04).
- The `OpponentPool` + `snapshot_callback` (agents-task-05).
- The reward mode + shaping schedule (agents-task-06).

Exposed hyperparameters (defaults in `config.yaml`):
- `lr`, `gamma` (~0.999), `gae_lambda`, `clip_param`, `entropy_coef` (with decay schedule),
- `train_batch_size`, `sgd_minibatch_size`, `num_sgd_iter`,
- `fcnet_hiddens`,
- `snapshot_interval`, `pool_size`,
- `shaping_coef` + anneal horizon,
- `total_timesteps`.

### `train()`
- Runs the PPO loop to `total_timesteps`.
- Checkpoints the `"main"` policy regularly.
- Exports a **lightweight inference artifact**: torch weights + observation/action codec versions + minimal config, with **no RLlib dependency required to load it** (so the UI/`RLPolicy` can serve without RLlib).
- Logs metrics each iteration: episode length, win rate vs pool and vs `HeuristicAgent`, policy entropy, value loss, and **mask violations (must be 0)**.

## Verification
- `train()` runs for ~100 training steps without error.
- Checkpoints are created on disk at the configured interval.
- The exported lightweight artifact loads in a process where RLlib is **not** imported.
- Logged mask violations stay at 0.
