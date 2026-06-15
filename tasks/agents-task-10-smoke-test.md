# Task 10: Training Smoke Test

## Status
not started

## Epic
agents-training

## Dependencies
- agents-task-01
- agents-task-02
- agents-task-03
- agents-task-04
- agents-task-05
- agents-task-06
- agents-task-07
- agents-task-08
- agents-task-09

## Overview
An end-to-end smoke test that trains `"main"` briefly against random opponents and verifies it learns to dominate them, validating the whole training + inference + eval pipeline.

## Design References
- `design/05-agents-and-training.md`

## Files to Create/Modify
| File | Action | Changes |
|------|--------|---------|
| `puerto_rico/training/smoke_test.py` | Create | Pytest-runnable smoke test |

## Specification
- Train the shared `"main"` policy for approximately **200K timesteps** against **3 `RandomAgent`s** (using the agents-task-07 training loop).
- Export the lightweight artifact and load it via `RLPolicy` (agents-task-08, no RLlib at serve).
- Evaluate with the arena (agents-task-09): **200 games**, seats rotated, trained policy vs 3 `RandomAgent`s.
- Assertions:
  - Trained-agent win rate **> 80%**.
  - **0** mask violations throughout training and evaluation.
- Keep total runtime within the pytest budget below.

## Verification
- `pytest puerto_rico/training/smoke_test.py` completes in **< 10 minutes**.
- Reported win rate vs 3 RandomAgents is **> 80%** with **0** mask violations.
