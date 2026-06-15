# Task 01: ActionCodec — Fixed-Size Discrete Action Space

## Status
done

## Epic
env

## Dependencies
- engine-core-task-07 (Game API: legal_actions/apply/current_player/is_terminal/returns)
- buildings epic (complete)
- phases epic (complete)

## Overview
A bidirectional codec mapping the engine's structured `Action` objects to/from a
fixed-size discrete action space (`N_ACTIONS`), and producing a boolean legality
mask from `state.legal_actions()`. This is the action interface RL agents train against.

## Design References
- `design/04-rl-environment.md`

## Files to Create/Modify
| File | Action | Changes |
|------|--------|---------|
| `puerto_rico/env/action_codec.py` | create | `ActionCodec` with `to_int`, `from_int`, `mask`, frozen `N_ACTIONS` |
| `puerto_rico/env/__init__.py` | create/modify | export `ActionCodec`, `N_ACTIONS` |
| `tests/env/test_action_codec.py` | create | roundtrip + mask legality tests |

## Specification

Fixed-size discrete space of roughly a few hundred ids. `N_ACTIONS` is **frozen**
(a module-level constant) once the layout is decided; never re-derive it per-state.

Action id layout (contiguous blocks, collapsed **by type, not by board slot**):

- `SELECT_ROLE` x7 — one id per role placard.
- `TAKE_TILE` x6 — QUARRY + 5 plantation kinds (Settler phase tile choice).
- `PLACE_COLONIST` x(6 tile categories + number-of-buildings + STORE) — collapsed by
  destination **type**, not by physical slot. The 6 tile categories cover plantation/quarry
  kinds; one id per `BuildingId` for building destinations; one `STORE` id for the
  San-Juan/colonist-store holding area.
- `BUILD` x(number of `BuildingId`) — one id per building type.
- `SELL` x5 — one id per good kind (Trader phase).
- `LOAD` x(5 goods x {ship0, ship1, WHARF}) = 15 — one id per (good, ship-target) pair.
- `PASS` x1 — single pass/decline id.
- Building `CHOOSE` sub-decisions — ids for buildings that require an extra in-phase choice
  (e.g. Hacienda/Discretionary-Hold style yes/no, Factory/University style follow-ups). One id
  per distinct sub-decision outcome.

Sum these block sizes to get `N_ACTIONS`. Document each block's offset in the module.

API:

- `to_int(action) -> int` — encode a structured engine `Action` to its id. Must be the
  inverse of `from_int` for every legal action.
- `from_int(i, state) -> Action` — decode an id to a structured `Action`, **using `state`**
  to resolve anything the flat id underdetermines: auto-placement target slot, the forced/only
  available ship for a LOAD when collapsed, the concrete tile slot for a TAKE_TILE, etc.
- `mask(state) -> np.ndarray[bool]` shape `(N_ACTIONS,)` — built by iterating
  `state.legal_actions()` and setting `to_int(a) = True`.

Mask contract (must hold for any reachable state):
- Number of `True` entries **exactly equals** `len(state.legal_actions())`.
- Every `True` id decodes via `from_int(i, state)` to an action present in
  `state.legal_actions()`.

The codec calls only the engine Game API (`legal_actions`); it does not reimplement rules.

## Verification

```
pytest tests/env/test_action_codec.py -q
```

Expected:
- Roundtrip: for a sampled set of states, `from_int(to_int(a), state) == a` for **all**
  `a in state.legal_actions()`.
- Mask legality count: `mask(state).sum() == len(state.legal_actions())` for every sampled state.
- Every `True` id in `mask(state)` decodes to a legal action.
- `N_ACTIONS` is constant across all states.
