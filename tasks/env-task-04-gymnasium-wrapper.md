# Task 04: Gymnasium Single-Agent Wrapper

## Status
not started

## Epic
env

## Dependencies
- env-task-03 (PettingZoo AEC wrapper)

## Overview
A single-agent `gym.Env` view over the AEC environment for player 0, with all other seats
driven by a supplied `opponent_policy`. Useful for single-agent RL libraries and quick
evaluation against a fixed opponent.

## Design References
- `design/04-rl-environment.md`
- `design/05-agents-and-training.md`

## Files to Create/Modify
| File | Action | Changes |
|------|--------|---------|
| `puerto_rico/env/gymnasium_wrapper.py` | create | `PuertoRicoSingle(gym.Env)` |
| `puerto_rico/env/__init__.py` | modify | export `PuertoRicoSingle` |
| `tests/env/test_gymnasium_wrapper.py` | create | gym API + opponent-policy invocation tests |

## Specification

`class PuertoRicoSingle(gym.Env)` wrapping `PuertoRicoAEC`:
- `__init__(self, config: dict, opponent_policy)` — `opponent_policy` is a callable
  `obs_dict -> int` returning a legal action id (it must respect the provided `action_mask`).
- `observation_space` / `action_space` mirror the AEC spaces for player 0
  (`Dict({"observation", "action_mask"})` and `Discrete(N_ACTIONS)`).
- `reset(self, *, seed=None, options=None) -> (obs_dict, info)` — reset the AEC env; if the
  first decision belongs to an opponent, run `opponent_policy` until it is player 0's turn (or
  game over), then return player 0's observation dict.
- `step(self, action_int) -> (obs, reward, terminated, truncated, info)`:
  - Apply player 0's action through the AEC env.
  - Loop: while it is not player 0's turn and the game is not over, query
    `opponent_policy(obs_dict_of_current_agent)` and step the AEC env.
  - Return player 0's observation dict, **cumulative** reward accrued to player 0 across the
    opponent loop, `terminated` (game over), `truncated` (False unless a step cap is added),
    and `info`.

## Verification

```
pytest tests/env/test_gymnasium_wrapper.py -q
```

Expected:
- Gym API compliance (spaces well-formed; `reset`/`step` return the gymnasium 2-tuple / 5-tuple
  contracts; optionally `gymnasium.utils.env_checker.check_env` with a masked random policy).
- `opponent_policy` is invoked for every non-player-0 decision and never for player-0 decisions.
- Terminal `terminated=True` with player-0 reward consistent with `engine.returns()`.
