# Task 05: Opponent Pool and Snapshotting

## Status
done

## Epic
agents-training

## Dependencies
- agents-task-03
- agents-task-01
- agents-task-02

## Overview
Implement a self-play opponent pool that holds frozen snapshots of `"main"`, plus `RandomAgent` and `HeuristicAgent`, and a callback that snapshots the learner every N iterations and assigns pool opponents to non-learner seats.

## Design References
- `design/05-agents-and-training.md`

## Files to Create/Modify
| File | Action | Changes |
|------|--------|---------|
| `puerto_rico/training/selfplay.py` | Create | `OpponentPool`, `snapshot_callback` |

## Specification

### `OpponentPool`
- Holds a set of selectable opponents identified by policy id:
  - Frozen snapshots of the `"main"` policy (weights captured at past iterations), each with metadata `{iter, elo}`.
  - The fixed baselines `RandomAgent` and `HeuristicAgent` (agents-task-01/02).
- API:
  - `add_snapshot(weights, *, iter, elo=None)` — store a frozen `"main"` snapshot with metadata.
  - `sample_opponents(n) -> list[policy_id]` — sample `n` non-learner opponents from the pool (snapshots + baselines), default toward `"main"` (current learner) but with probability draw from frozen/baseline opponents.
  - `policy_ids() -> list[str]` — all currently valid policy ids.
  - Bounded size: cap the number of stored snapshots (oldest/lowest-Elo evicted) per a `pool_size` setting.

### `snapshot_callback`
- A training callback that, every `snapshot_interval` iterations, captures the current `"main"` weights and calls `pool.add_snapshot(...)` with `iter` and (if available) `elo` metadata.
- Integrates with `policy_mapping_fn` (agents-task-03): with some probability, fill **1-3** non-learner seats from the pool; the remaining non-learner seats default to `"main"`. The learner seat always plays `"main"` (the live policy).

## Verification
- Over several training iterations, snapshots are created and added to the pool at the configured interval.
- `policy_ids()` always returns valid ids that the policy-mapping layer accepts (no unknown-policy errors during rollouts).
- Pool respects `pool_size` cap and always contains `RandomAgent` and `HeuristicAgent`.
