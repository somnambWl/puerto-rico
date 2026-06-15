# Task 11: Stretch — RL vs Heuristic Benchmark (M4)

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
- agents-task-10

## Overview
Milestone-4 stretch benchmark: a fully trained RL policy must be competitive with the heuristic baseline over a large seat-rotated sample.

## Design References
- `design/05-agents-and-training.md`

## Files to Create/Modify
| File | Action | Changes |
|------|--------|---------|
| `puerto_rico/training/evaluate.py` | Modify | Add the RL-vs-heuristic benchmark configuration |
| `puerto_rico/training/...` (benchmark entrypoint) | Create/Modify | Runner for the M4 benchmark + report |

## Specification
- Run **>= 500** games with **rotated seats**: trained `RLPolicy` (agents-task-08) vs **3 `HeuristicAgent`s** (agents-task-02), using the arena (agents-task-09).
- Target: RL win rate **>= 45%** (against 3 heuristics; random baseline would be 25%).
- Report **Elo**, **mean placement**, and **mean victory points** for the RL policy and the heuristic seats.

## Verification
- Benchmark runs >= 500 seat-rotated games and completes with a report.
- RL win rate vs 3 `HeuristicAgent`s is **>= 45%**.
- Report includes Elo, mean placement, and mean VP per agent.
