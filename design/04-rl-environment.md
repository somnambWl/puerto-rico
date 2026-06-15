# 04 — RL Environment (PettingZoo) & Encoders

## Purpose

Wrap the engine as a PettingZoo **AEC** (agent-environment-cycle) environment for turn-based,
single-current-player play, define the fixed-size **action space** with masking, and the tensor
**observation encoding**. The env is the only layer that imports both the engine and numpy.

## Why AEC

Puerto Rico is sequential: exactly one player decides at a time, decisions interleave (the follow
structure means players act out of a simple round-robin), and turn counts per player vary (captain).
PettingZoo's AEC API models precisely this: `agent_iter()`, `last()`, `step(action)`, per-agent
`observe()`. Do **not** use the Parallel API.

```
puerto_rico/env/
├── pettingzoo_env.py   PuertoRicoAEC(AECEnv)
├── action_codec.py     ActionCodec: Action <-> int, fixed-size space + mask
└── obs_codec.py        encode(state, perspective) -> np.ndarray
```

## Action space (action_codec.py)

RL needs a **fixed-size discrete** action space; the engine has a variable list of legal `Action`
objects. Bridge them with a canonical enumeration.

- Define a fixed, exhaustive list of all *possible* atomic actions across the game, each mapped to a
  stable integer id. The space is the union of:
  - `SELECT_ROLE` × 7 roles
  - `TAKE_TILE` × {QUARRY, the 5 plantation kinds} (placement auto-resolved per design/02 — no slot in
    the action)
  - `PLACE_COLONIST` × {one id per distinct circle *type*}. Because exact slot index is irrelevant for
    plantations/quarries, collapse placement targets to **categories**: "place on an empty
    {corn|indigo|sugar|tobacco|coffee|quarry} tile", "place on building {BuildingId}", and "STORE".
    This keeps the action set small and permutation-invariant. (~6 tile categories + #buildings + STORE.)
  - `BUILD` × (#distinct BuildingId)
  - `SELL` × 5 goods
  - `LOAD` × (5 goods × {ship0, ship1, WHARF}); ship/amount otherwise forced
  - `PASS` × 1
  - building `CHOOSE` sub-decisions × (small enumerated set: warehouse-protect kind, craftsman bonus
    good, storage keep) — enumerate each as its own ids.
- Total size is a few hundred ids (compute and freeze it). `ActionCodec` provides:
  - `to_int(action: Action) -> int`
  - `from_int(i: int, state) -> Action` (state needed to resolve auto-placement/forced ship)
  - `mask(state) -> np.ndarray[bool]` of length `n_actions`, True for ids whose decoded action is
    currently legal. Built directly from `state.legal_actions()` so the env never diverges from engine
    legality.

> The mask is the contract that makes a large fixed space safe: the policy only ever samples among
> True entries (masked softmax / `-inf` logits on False). See design/05 for the masked model.

## Observation space (obs_codec.py)

A flat `float32` vector (start simple; a structured/graph encoding is a later optimization). Encode
from the **current player's perspective** so the policy is symmetric. Concatenate:

1. **Self player block** and **each opponent block** (opponents in seating order starting after self):
   - doubloons (scaled), stored_colonists (scaled), vp_chips (self only; opponents' hidden → 0 or a
     "known-unknown" flag), per-good held counts (5), filled island spaces, empty building circles.
   - island summary: count of each tile kind (6) and how many of each are occupied.
   - city: for each BuildingId a 2-dim (owned?, occupied?) — fixed length = 2 × #buildings.
2. **Shared board block:** role placards (per role: available? doubloons-on-it), colonist_ship count,
   colonist_supply (scaled), per cargo ship (capacity, good one-hot(5)+empty, count), trading_house
   (count + which kinds present, multiset over 5), goods_supply (5, scaled), plantation_faceup (counts
   per kind, 6), plantation_facedown size (scaled), quarry_supply, vp_chips_remaining (scaled),
   buildings_supply (per BuildingId remaining count).
3. **Phase block:** one-hot(Phase), one-hot(active_role), current sub-state scalars
   (colonists_to_place, order position), and **the action mask is provided separately** by the env,
   not inside the observation (RLlib expects mask in the obs dict — see below).

Normalize counts to roughly [0,1] using known maxima (doubloons rarely exceed ~50; VP up to 65; etc.).
Keep the layout in one module with named offsets and a single `OBS_LEN` constant. Provide an
`describe()` that returns human-readable feature names for debugging.

### RLlib-compatible observation dict

Expose observations as:
```python
{"observation": np.ndarray(OBS_LEN, float32),
 "action_mask": np.ndarray(N_ACTIONS, float32)}   # 1.0 legal, 0.0 illegal
```
This is the standard masked-action format RLlib's models consume.

## Env behavior (pettingzoo_env.py)

```python
class PuertoRicoAEC(AECEnv):
    metadata = {"name": "puerto_rico_v0", "is_parallelizable": False}
    def __init__(self, config: dict): ...        # {num_players, seed, reward_mode, shaping_coef}
    def reset(self, seed=None, options=None): ...
    def observe(self, agent) -> dict: ...          # the obs dict above for that agent
    def step(self, action: int): ...               # decode via ActionCodec, engine.apply, advance
    def agent_selection: str                       # maps to engine.current_player
    # rewards: 0 every step except terminal (plus optional shaping, design/05)
```

Details:
- `agents = [f"player_{i}" for i in range(num_players)]` (4 by default). `agent_selection` follows
  `engine.current_player` exactly.
- On `step`, if the chosen int is masked-illegal, raise (in training, the masked policy prevents this;
  in eval against a buggy agent, surface it).
- Terminal: on `GAME_OVER`, set `terminations[a]=True` for all, fill `rewards` from `engine.returns()`.
- Determinism: pass `seed` to `engine` so episodes are reproducible.
- Provide a Gymnasium **single-agent** convenience wrapper too (`PuertoRicoSingle`) that fixes the
  opponents to a given policy, for quick PPO experiments and for the UI's "AI to move" calls.

## Tests / acceptance

- `pettingzoo.test.api_test(PuertoRicoAEC())` passes.
- `ActionCodec.from_int(ActionCodec.to_int(a), state) == a` for all `a in state.legal_actions()` across
  a random playthrough (round-trip).
- `mask(state)` has exactly `len(state.legal_actions())` True entries, all decoding to legal actions.
- `OBS_LEN` is constant across all states; no NaNs; values within expected ranges.
- A random-masked-policy self-play episode (4 seats) completes and assigns terminal rewards consistent
  with the final ranking (rank/VP-based; see design/05 — the rewards need not sum to zero).
