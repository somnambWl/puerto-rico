# Task 09: Evaluation Harness

## Status
not started

## Epic
agents-training

## Dependencies
- agents-task-01
- agents-task-02
- agents-task-08

## Overview
Build an arena that plays many seat-rotated games between arbitrary agents, computes per-agent metrics and Elo, runs standard benchmarks, and audits for suspiciously strong results that may indicate engine bugs.

## Design References
- `design/05-agents-and-training.md`

## Files to Create/Modify
| File | Action | Changes |
|------|--------|---------|
| `puerto_rico/training/evaluate.py` | Create | `Arena`, `run_arena`, Elo + reporting |

## Specification

### `Arena` / `run_arena(agents, k=500, ...)`
- Plays `K` games (default `500`) among the provided agents, **rotating seats** so each agent occupies each seat roughly equally (removes seat-order bias).
- Per-agent metrics: win rate, mean placement, mean victory points.
- Deterministic given a seed (reproducible).

### Benchmarks
- Built-in benchmark configurations: candidate vs all-`RandomAgent`, candidate vs all-`HeuristicAgent`, and candidate vs past `RLPolicy` checkpoints (agents-task-08).

### Elo
- Compute an Elo table from arena results (pairwise/placement-based), reproducible across runs with the same seed and games.

### Sanity audit
- Flag "too good" results (e.g. a candidate winning at a rate that should be near-impossible against strong opponents) as **suspect — likely an engine bug**, surfaced clearly in the report.

### Reporting
- Produce a human-readable report (table) of win rates, mean placement, mean VP, and Elo.

## Verification
- `run_arena` completes for the default benchmarks.
- All-`RandomAgent` arena yields **~25%** win rate per seat.
- A `HeuristicAgent` vs 3 `RandomAgent`s yields **>50%** win rate.
- Elo table is **reproducible** for fixed seed + game set.
