# Task 01: RandomAgent and Agent Protocol

## Status
not started

## Epic
agents-training

## Dependencies
- env-task-01 (observation codec)
- env-task-02 (action codec)
- env-task-03 (PettingZoo wrapper)
- engine

## Overview
Define the shared `Agent` protocol and implement a `RandomAgent` that samples uniformly among legal actions. This is the foundation all other agents conform to.

## Design References
- `design/05-agents-and-training.md`

## Files to Create/Modify
| File | Action | Changes |
|------|--------|---------|
| `puerto_rico/agents/__init__.py` | Create/Modify | Export `Agent`, `RandomAgent` |
| `puerto_rico/agents/base.py` | Create | `Agent` protocol |
| `puerto_rico/agents/random_agent.py` | Create | `RandomAgent` implementation |

## Specification

### `Agent` protocol (`agents/base.py`)
- Method `act(self, obs, *, rng=None) -> int`
  - `obs` is the env observation dict containing at least `obs["observation"]` and `obs["action_mask"]` (a 0/1 array over the discrete action space, indexed by action id).
  - Returns a single integer action id whose `action_mask` entry is `1`.
  - `rng` is an optional `numpy.random.Generator` used for any stochastic choice; when `None`, the agent falls back to its own internal RNG.
- Method `reset(self) -> None`
  - Clears any per-episode internal state. Default no-op acceptable.
- Define as a `typing.Protocol` (runtime-checkable) so all concrete agents type-check structurally.

### `RandomAgent` (`agents/random_agent.py`)
- Constructor accepts optional `seed: int | None` to build an internal `numpy.random.Generator`.
- `act(obs, *, rng=None)`:
  - Read `mask = obs["action_mask"]`.
  - Compute `legal = indices where mask == 1`.
  - Raise a clear error if `legal` is empty (engine should never present an empty mask).
  - Sample one index uniformly from `legal` using `rng` if provided, else the internal generator.
  - Return the chosen action id as a Python `int`.
- `reset()` is a no-op (no per-episode state).

## Verification
- `python -c "from puerto_rico.agents import Agent, RandomAgent"` imports cleanly.
- Run a full 4-player game (`env-task-03` wrapper) with 4 `RandomAgent`s to terminal: **0 action-mask violations** (every returned action has `mask==1`).
- Over >=200 games of 4 RandomAgents with rotating seats, each seat wins **~25%** (within sampling noise).
