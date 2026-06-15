# Task 03: PettingZoo AEC Wrapper

## Status
done

## Epic
env

## Dependencies
- env-task-01 (ActionCodec)
- env-task-02 (ObsCodec)
- engine-core-task-07 (Game API: legal_actions/apply/current_player/is_terminal/returns)

## Overview
Wraps the engine in a PettingZoo AEC environment so multi-agent RL (self-play PPO) can
train against it. Uses `ActionCodec` for the discrete action space + mask and `ObsCodec`
for observations.

## Design References
- `design/04-rl-environment.md`
- `design/05-agents-and-training.md` (reward modes / shaping)

## Files to Create/Modify
| File | Action | Changes |
|------|--------|---------|
| `puerto_rico/env/pettingzoo_env.py` | create | `PuertoRicoAEC(AECEnv)` |
| `puerto_rico/env/__init__.py` | modify | export `PuertoRicoAEC` |
| `tests/env/test_pettingzoo_env.py` | create | api_test + determinism + reward consistency |

## Specification

`class PuertoRicoAEC(AECEnv)`:
- `metadata = {"name": "puerto_rico_v0", "is_parallelizable": False}`
- `__init__(self, config: dict)` — config keys: `num_players`, `seed`, `reward_mode`,
  `shaping_coef`. Build agent ids `["player_0", ..., "player_{n-1}"]`.
- Action space per agent: `Discrete(N_ACTIONS)`.
- Observation space per agent: `Dict({"observation": Box(OBS_LEN, float32),
  "action_mask": Box(N_ACTIONS, float32)})` (mask values in `{0,1}`, 1=legal).

Methods:
- `reset(self, seed=None, options=None) -> dict` — (re)seed the engine deterministically,
  set `agent_selection` to the engine's `current_player`, return initial per-agent dict.
- `observe(self, agent) -> {"observation": np.float32(OBS_LEN), "action_mask":
  np.float32(N_ACTIONS)}` — `action_mask` 1=legal, built from `ActionCodec.mask(state)`.
- `step(self, action: int)`:
  - Reject masked-illegal: if the chosen id is not legal in the current state, raise
    `ValueError`.
  - Decode via `ActionCodec.from_int(action, state)`, call `engine.apply`.
  - Advance `agent_selection` to engine's `current_player`.
  - On game over (`engine.is_terminal()`): set `terminations` True for all agents and set
    `rewards` from `engine.returns()` (per `reward_mode`); otherwise reward 0 (optional
    shaping per `design/05`, scaled by `shaping_coef`).

Determinism: identical `seed` + identical action sequence ⇒ identical trajectory.

## Verification

```
pytest tests/env/test_pettingzoo_env.py -q
```

Expected:
- `pettingzoo.test.api_test(PuertoRicoAEC({...}))` passes.
- Terminal rewards are consistent with final ranking from `engine.returns()`.
- Determinism: two runs with same seed + same actions produce identical observations,
  masks, and rewards.
- Stepping a masked-illegal action raises `ValueError`.
