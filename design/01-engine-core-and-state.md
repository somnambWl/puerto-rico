# 01 — Engine Core & State Model

## Purpose

Define the data model (`GameState` and its parts), the `Action` protocol, the public engine
API, setup for the 2-player game, and serialization. This is the foundation; design/02 layers the
phase/turn state machine on top, and design/03 layers building effects.

Rules source of truth: `docs/puerto-rico-rules.md` (sections: Contents, Preparation, The Game for
Two, The Buildings).

## Package layout

```
puerto_rico/engine/
├── enums.py        Good, Role, BuildingId, Phase, TileType, DecisionType (IntEnums)
├── state.py        GameState, PlayerState, IslandSlot, CitySlot, CargoShip, RolePlacard
├── actions.py      Action dataclasses + the apply dispatch table
├── setup.py        new_game(config) -> GameState
├── phases.py       the round/phase state machine (design/02)
├── buildings.py    building catalog + effect hooks (design/03)
├── scoring.py      final scoring (design/02 §Game End)
├── game.py         thin public facade: Game class wrapping a GameState
└── serialize.py    to_dict / from_dict, and a public observation-free JSON view
```

`enums.py`, `state.py`, `actions.py`, `setup.py`, `serialize.py` are this document. The rest are
referenced here but specified in design/02–03.

## Enums (enums.py)

```python
class Good(IntEnum):    CORN=0; INDIGO=1; SUGAR=2; TOBACCO=3; COFFEE=4
class Role(IntEnum):    SETTLER=0; MAYOR=1; BUILDER=2; CRAFTSMAN=3; TRADER=4; CAPTAIN=5; PROSPECTOR=6
class TileType(IntEnum): EMPTY=0; QUARRY=1; CORN=2; INDIGO=3; SUGAR=4; TOBACCO=5; COFFEE=6
class Phase(IntEnum):   ROLE_SELECTION=0; SETTLER=1; MAYOR=2; BUILDER=3; CRAFTSMAN=4; TRADER=5; CAPTAIN=6; GAME_OVER=7
# BuildingId: one entry per distinct building; see design/03 for the full table.
```

Goods sold-price (trader) and trading rules live in design/02. The `Good`↔`TileType` mapping for
production (corn plantation → corn good, etc.) is a small helper in `buildings.py`.

## State model (state.py)

All dataclasses use `slots=True`. Counts are plain ints; collections are lists/dicts of ints. No
object references between players. The whole state must `clone()` cheaply (see §Cloning).

### IslandSlot
```python
@dataclass(slots=True)
class IslandSlot:
    tile: TileType = TileType.EMPTY     # QUARRY or a plantation kind, or EMPTY
    colonist: bool = False              # plantations/quarries hold exactly 0 or 1 colonist
```
A player's island is `list[IslandSlot]` of length 12. Position is irrelevant to rules (rulebook),
so order is just storage. An occupied production tile counts toward production only if its matching
production building has manned circles (see design/02 Craftsman).

### CitySlot
```python
@dataclass(slots=True)
class CitySlot:
    building: BuildingId | None = None  # None = empty
    colonists: int = 0                  # 0..capacity
    # capacity & is_large are looked up from the building spec, not stored here
```
A player's city is `list[CitySlot]` of length 12. A large building occupies **two adjacent** slots;
represent it as the building in the first slot and a sentinel `BuildingId.LARGE_CONT` in the second
(or track a `large_second_slot` set). Pick one representation and document it; the rest of the code
must treat large buildings as a single logical building occupying 2 spaces.

### CargoShip
```python
@dataclass(slots=True)
class CargoShip:
    capacity: int                       # 4, 5, 6, 7, or 8 depending on player count
    good: Good | None = None            # the single kind currently loaded, or None if empty
    count: int = 0                      # 0..capacity
```

### RolePlacard
```python
@dataclass(slots=True)
class RolePlacard:
    role: Role
    doubloons: int = 0                  # accumulated from unused rounds
    taken_by: int | None = None         # player idx this round, else None
```

### PlayerState
```python
@dataclass(slots=True)
class PlayerState:
    doubloons: int
    island: list[IslandSlot]            # len 12
    city:    list[CitySlot]             # len 12
    goods:   list[int]                  # len 5, indexed by Good, held on the windrose
    stored_colonists: int               # colonists on the windrose (not yet on a circle)
    vp_chips: int                       # secret; total VP value held in chips
    roles_taken_this_round: int = 0     # 2-player: each player takes 3 roles/round
```
Helper methods (pure, no mutation): `owns(building_id) -> bool`, `building_slot(building_id)`,
`occupied(building_id) -> bool` (building present AND colonists>0), `total_colonists() -> int`
(island + city + stored), `filled_island_spaces() -> int`, `empty_building_circles() -> int`.

### GameState
```python
@dataclass(slots=True)
class GameState:
    config: GameConfig
    rng: random.Random                  # seeded; the ONLY source of randomness
    players: list[PlayerState]
    governor: int                       # player idx holding the governor placard
    current_player: int                 # whose atomic decision is pending
    phase: Phase
    placards: list[RolePlacard]         # the role placards in play (7 for 2-player)
    colonist_ship: int                  # colonists currently on the ship
    colonist_supply: int                # colonists left in the general supply
    cargo_ships: list[CargoShip]
    trading_house: list[Good]           # 0..4 goods currently sold but not yet cleared
    goods_supply: list[int]             # len 5, indexed by Good
    plantation_faceup: list[TileType]   # the visible row (players+1 long when full)
    plantation_facedown: list[TileType] # shuffled draw stack (a flat list; pop from end)
    plantation_discard: list[TileType]
    quarry_supply: int
    vp_chips_remaining: int             # total VP value left in the chip pool
    buildings_supply: dict[BuildingId, int]  # how many of each building remain to be built
    phase_state: PhaseState             # the FSM cursor for the active phase (design/02)
    end_triggered: bool = False         # set when an end condition fires; game ends after round
```

`GameConfig`:
```python
@dataclass(slots=True, frozen=True)
class GameConfig:
    num_players: int = 4                # 4-player is the primary target; 2/3/5 supported
    seed: int | None = None
    ruleset: str = "base"               # only "base" for now
```

## Action protocol (actions.py)

An `Action` is a small immutable dataclass tagged by `DecisionType`. The set of fields used depends
on the type. Keep them flat and hashable (so RL can map them to integer ids; see design/04).

```python
class DecisionType(IntEnum):
    SELECT_ROLE=0      # choose a role placard
    TAKE_TILE=1        # settler: take a face-up plantation (or, via privilege/hut, a quarry)
    PLACE_COLONIST=2   # mayor: place one colonist on a specific circle (or store)
    BUILD=3            # builder: build one building (or pass)
    SELL=4             # trader: sell one good (or pass)
    LOAD=5             # captain: load a good kind onto a ship (or use wharf / pass when allowed)
    PASS=6             # decline an optional action
    CHOOSE=7           # generic building sub-choice (hacienda tile, warehouse keep, factory none, etc.)

@dataclass(slots=True, frozen=True)
class Action:
    type: DecisionType
    # union of optional fields; only those relevant to `type` are set:
    role: Role | None = None
    tile: TileType | None = None
    target: int | None = None          # slot index (island or city) or ship index
    good: Good | None = None
    building: BuildingId | None = None
    choice: int | None = None          # generic enumerated sub-choice id
```

> Why one flat `Action` instead of subclasses: it keeps `legal_actions()` cheap to build, makes the
> action→int mapping in design/04 simple, and avoids isinstance dispatch in the hot path. `apply`
> dispatches on `action.type`.

### Public engine API (game.py)

```python
class Game:
    def __init__(self, config: GameConfig): ...
    @property
    def state(self) -> GameState: ...
    @property
    def current_player(self) -> int: ...
    @property
    def is_terminal(self) -> bool: ...
    def legal_actions(self) -> list[Action]: ...      # never empty unless terminal
    def apply(self, action: Action) -> None: ...       # mutates in place; raises on illegal action
    def clone(self) -> "Game": ...
    def returns(self) -> list[float]: ...              # terminal payoffs per player (design/05 reward)
    def winner(self) -> int | None: ...                # tie-break by doubloons+goods
    def public_view(self, perspective: int|None=None) -> dict: ...  # serialize.py, for UI
```

`apply` must validate that `action` is in `legal_actions()` (at least in a debug mode) and raise
`IllegalAction` otherwise. In a fast mode this check can be skipped, trusting the env/agent.

## Cloning (§Cloning)

`clone()` must produce a fully independent state: deep-copy `players` (and their `island`/`city`
lists), `cargo_ships`, the plantation lists, `trading_house`, `goods_supply`, `buildings_supply`,
`phase_state`, and **fork the RNG** (`random.Random()` seeded from `rng.random()` or by copying its
internal `getstate()`/`setstate()`), so two clones diverge identically given identical actions only
if intended. Document the RNG-fork semantics: clones should reproduce the same draws unless reseeded.
Provide a fast path that avoids `copy.deepcopy` (manual field copies) because this is on the MCTS hot
path if AlphaZero is added later.

## Setup — base game (setup.py), 4-player primary

`new_game(config) -> GameState` builds the initial state from per-player-count constants. **4-player is
the implemented/tuned target**; the other counts are provided so the same code generalizes. Keep all
numbers in a `SETUP[num_players]` table of named constants so a ruleset change is data, not logic.

Per-player-count constants (base game):

| Constant | 2p | 3p | **4p** | 5p |
|---|---|---|---|---|
| starting doubloons (each) | 3 | 2 | **3** | 4 |
| VP chip pool | 65 | 75 | **100** | 126 |
| colonist supply | 40 | 55 | **75** | 95 |
| colonists on ship at start | 2 | 3 | **4** | 5 |
| cargo ship capacities | 4, 6 | 4,5,6 | **5,6,7** | 6,7,8 |
| role placards | 7 (−1 prospector) | 6 (−2 prospectors) | **7 (−1 prospector)** | 8 (all) |
| roles per player per round | 3 | 1 | **1** | 1 |
| face-up plantation row | 3 | 4 | **5** | 6 |
| plantation/quarry tiles removed | 3 of each | none | **none** | none |
| goods tokens removed | 2 of each | none | **none** | none |
| beige buildings on board (per kind) | 1 | 2 small / 1 large | **2 small / 1 large** | 2 small / 1 large |
| production buildings on board | 2 of each (12) | standard (20) | **standard (20)** | standard (20) |

For the **4-player game** specifically:

- 4 players, each: 3 doubloons, empty 12-slot island and city, empty goods, 0 stored colonists,
  0 vp_chips. Governor = player 0. Starting tiles (rulebook): players 0 & 1 → INDIGO, players 2 & 3 →
  CORN.
- **Plantation tiles:** full base counts (8 coffee, 9 tobacco, 10 corn, 11 sugar, 12 indigo) and 8
  quarries; **nothing removed**. Shuffle all plantations into `plantation_facedown` via `rng`; deal
  `num_players + 1 = 5` to `plantation_faceup`. `quarry_supply = 8`.
- **Buildings on board (`buildings_supply`):** 2 of each of the 12 small beige, 1 of each of the 5
  large beige, and the standard production counts (small indigo ×4, indigo plant ×3, small sugar ×4,
  sugar mill ×3, tobacco storage ×3, coffee roaster ×3 = 20). See design/03.
- **VP chips:** `vp_chips_remaining = 100`.
- **Colonists:** `colonist_supply = 75`; `colonist_ship = 4` (= num_players).
- **Cargo ships:** three ships, capacities 5, 6, 7.
- **Goods supply:** full base totals (Deluxe counts): corn 10, sugar 11, indigo 11, tobacco 9,
  coffee 9. Nothing removed.
- **Role placards:** 7 placards — all roles except one prospector, each with 0 doubloons,
  `taken_by=None`. (A round uses 4 of the 7; the 3 unused each gain a doubloon — see design/02.)
- `phase = ROLE_SELECTION`, `current_player = governor = 0`, `phase_state` initialized for role
  selection (design/02).

> **Edition note.** The two rulebooks differ slightly (see `docs/puerto-rico-rules.md` → Edition
> Differences): 5-player total VP is 122 (original) vs 126 (Deluxe), plus minor good-token counts.
> Use the **Deluxe** numbers (4-player VP = 100 is identical in both). Centralize all constants in the
> `SETUP` table so switching editions/player-counts is a data change, not a logic change.

## Serialization (serialize.py)

- `to_dict(state) -> dict` / `from_dict(d) -> GameState`: lossless round-trip (excluding RNG internal
  state, which is serialized via `rng.getstate()`), used for save/load and tests.
- `public_view(state, perspective=None) -> dict`: a UI-facing snapshot. If `perspective` is set, hide
  the other players' `vp_chips` (the only truly secret information) and the identity/order of
  `plantation_facedown` (counts only). Everything else in Puerto Rico is public.

## Acceptance criteria for this doc's milestone (M1)

- `new_game(GameConfig(seed=0))` produces a valid 4-player initial state matching the setup table.
- `legal_actions()` at the initial state returns the role-selection choices for player 0 (governor).
- A loop choosing random legal actions reaches a terminal state without raising (phases stubbed to
  no-ops are acceptable at M1; full behavior arrives in M2).
- `clone()` produces an independent state (mutating one does not affect the other), verified by a test.
- `to_dict`/`from_dict` round-trips to an equal state.
