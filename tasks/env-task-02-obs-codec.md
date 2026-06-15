# Task 02: ObsCodec — Flat Observation Encoder

## Status
done

## Epic
env

## Dependencies
- engine-core-task-07 (Game API: state access)
- buildings epic (complete)
- phases epic (complete)

## Overview
Encodes engine state into a flat, fixed-length `np.ndarray(OBS_LEN, float32)` from the
**current player's perspective**, normalized to roughly `[0, 1]`. The action mask is
delivered separately (Task 03) and is **not** part of the observation.

## Design References
- `design/04-rl-environment.md`

## Files to Create/Modify
| File | Action | Changes |
|------|--------|---------|
| `puerto_rico/env/obs_codec.py` | create | `ObsCodec` with `encode`, `describe`, frozen `OBS_LEN` |
| `puerto_rico/env/__init__.py` | modify | export `ObsCodec`, `OBS_LEN` |
| `tests/env/test_obs_codec.py` | create | length-constant, no-NaN, perspective-symmetry tests |

## Specification

`encode(state) -> np.ndarray(OBS_LEN, float32)`, current-player perspective (the observed
player is always written first, opponents follow in seating order). `OBS_LEN` is **frozen**
as a module constant.

Blocks (in order):

1. **Player blocks** — self first, then each opponent, identical layout per player:
   - doubloons
   - stored_colonists (San-Juan holding area)
   - vp_chips — **self only** (hidden info for opponents; encode 0 or omit consistently)
   - goods (5 kinds)
   - filled island (occupied plantation/quarry tile count)
   - empty circles (free island slots)
   - island tile-kind counts (6: quarry + 5 plantation kinds)
   - city per `BuildingId`: (owned?, occupied?) pair for each building type

2. **Shared board**:
   - role placards: per role (available?, doubloons-on-placard)
   - colonist_ship (count waiting)
   - colonist_supply (pool)
   - cargo ships: per ship (capacity, good one-hot + empty flag, current count)
   - trading_house multiset (5 goods)
   - goods_supply (5)
   - plantation faceup counts (6 tile kinds visible)
   - facedown plantation stack size
   - quarry_supply
   - vp_chips_remaining (general pool)
   - buildings_supply: per `BuildingId` remaining count

3. **Phase block**:
   - one-hot(Phase)
   - one-hot(active_role)
   - sub-state scalars (e.g. which sub-decision/step is pending)

Normalization: scale each field to roughly `[0, 1]` (divide by sensible caps —
max doubloons, supply sizes, capacities, etc.).

`describe() -> list[str]` — human-readable label per index, length `OBS_LEN`, for debugging.

## Verification

```
pytest tests/env/test_obs_codec.py -q
```

Expected:
- `OBS_LEN` constant: `encode(state).shape == (OBS_LEN,)` across many sampled states.
- `len(describe()) == OBS_LEN`.
- No NaNs / no infs in any encoded observation.
- Perspective symmetry: encoding from player p's perspective places p's own block first;
  rotating the observed player rotates the player blocks consistently (shared/phase blocks
  identical except for perspective-dependent fields).
