# Task 03: RLlib Env Registration and Policy Mapping

## Status
done (SUPERSEDED: implemented as custom PyTorch PPO)

## NOTE: Superseded
This task describes RLlib integration. The project was reworked to use **custom PyTorch PPO** instead.
The equivalent implementation is:
- **Rollout collection:** `training/rollout.py` — `collect_rollouts(cfg)` runs parallel episodes and
  collects GAE-Lambda advantages; no RLlib wrapper needed.
- **Policy mapping:** implicit in the rollout collector — all learner seats run the same network weights;
  non-learner seats are sampled from `OpponentPool` with `self_play_prob`.

See `conversation-notes.md` for the RL backend decision rationale.

## Epic
agents-training

## Dependencies
- env-task-03 (PettingZoo wrapper)

## Overview
Register the Puerto Rico PettingZoo env with RLlib and define the policy-mapping function: a single shared `"main"` policy controls all 4 seats (parameter sharing, seat-symmetric), with the learner seat rotated each episode.

## Design References
- `design/05-agents-and-training.md`

## Files to Create/Modify
| File | Action | Changes |
|------|--------|---------|
| `puerto_rico/training/__init__.py` | Create/Modify | Package marker |
| `puerto_rico/training/env_factory.py` | Create | `register_env()`, `policy_mapping_fn`, env-creator |

## Specification

### Env creator + registration (`training/env_factory.py`)
- A creator function `env_creator(config) -> MultiAgentEnv` that wraps the PettingZoo AEC env (from `env-task-03`) into the RLlib multi-agent interface (e.g. via `PettingZooEnv` / `ParallelPettingZooEnv` as appropriate to the wrapper's API).
- `register_env(name: str = "puerto_rico") -> str`: registers `env_creator` under `name` with RLlib's `tune.register_env`; returns the registered name. Idempotent (safe to call repeatedly).

### Policy mapping
- `policy_mapping_fn(agent_id, episode, **kwargs) -> str`: returns the policy id for a given seat/agent.
- Default behavior: all seats map to `"main"` (single shared, seat-symmetric policy, full parameter sharing).
- Support a learner-seat-rotation hook so that across episodes the seat designated as the active learner rotates (0->1->2->3->...). The rotation must keep the env seat-symmetric (observations already encoded relative to the acting seat by the codec). This rotation point is also the seam where non-learner seats can later be mapped to opponent-pool policies (agents-task-05).

## Verification
- `register_env()` returns the name and the env can be created by RLlib without error.
- A short 4-player rollout under RLlib produces valid `(obs, action, reward, done, info)` tuples for all seats, with `obs` containing `observation` and `action_mask`.
- `policy_mapping_fn` returns `"main"` for every seat by default.
