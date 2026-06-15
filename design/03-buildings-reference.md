# 03 — Buildings Reference & Hook Model

## Purpose

Define every base-game building (cost, VP, capacity, effect) and the **hook interface** through which
buildings inject behavior into the phases. The hook model keeps `phases.py` clean and makes the two
expansions addable later without touching core flow.

Rules source: `docs/puerto-rico-rules.md` (The Buildings, production buildings, beige buildings, large
buildings).

## Hook model (buildings.py)

A building is described by a static spec plus a set of **effect handlers** keyed by timing point. The
engine, at each timing point, iterates the current player's *occupied* buildings (occupancy required
except for end-game VP) and invokes any handler for that point.

```python
class Timing(IntEnum):
    SETTLER_PLACE      = 0   # after this player places (or is about to place) an island tile
    CRAFTSMAN_PRODUCE  = 1   # after this player's production is computed
    TRADER_SELL_PRICE  = 2   # adjust sale price / legality for this player's sale
    BUILDER_BUILD      = 3   # when this player builds (cost adjust + post-build effect)
    CAPTAIN_LOAD       = 4   # each time this player loads goods
    CAPTAIN_STORAGE    = 5   # end-of-captain goods storage allowance
    SCORE_END          = 6   # game-end extra VP

@dataclass(frozen=True, slots=True)
class BuildingSpec:
    id: BuildingId
    name: str
    cost: int
    column: int               # 1..4, the quarry-discount cap column on the board
    vp: int                   # printed (base) VP
    capacity: int             # colonist circles (1..3); large buildings per rules
    is_large: bool
    is_production: bool
    produces: Good | None     # for production buildings
    timings: tuple[Timing,...] # which hooks this building implements
```

Handlers are plain functions `handler(state, player_idx, ctx) -> None/return value` registered per
`(BuildingId, Timing)`. `ctx` carries timing-specific data (e.g. the good being sold, the tile being
placed, a mutable price). Keep handlers pure w.r.t. inputs other than the documented mutation target.

Design rule: **all building-specific behavior lives in handlers**, never in `phases.py`. `phases.py`
only calls "fire(timing, state, player, ctx)". This is the seam the expansions plug into.

## Production buildings

Two of each are on the board in the 2-player setup. Production output is computed in the craftsman
phase (design/02): `output(kind) = min(manned circles of the matching building, occupied plantations
of that kind, supply)`. Corn needs no building.

| id | name | cost | col | VP | circles | produces |
|----|------|------|-----|----|---------|----------|
| SMALL_INDIGO | small indigo plant | 1 | 1 | 1 | 1 | INDIGO |
| INDIGO_PLANT | indigo plant | 3 | 2 | 2 | 3 | INDIGO |
| SMALL_SUGAR  | small sugar mill | 2 | 1 | 1 | 1 | SUGAR |
| SUGAR_MILL   | sugar mill | 4 | 2 | 2 | 3 | SUGAR |
| TOBACCO_STORAGE | tobacco storage | 5 | 3 | 3 | 3 | TOBACCO |
| COFFEE_ROASTER  | coffee roaster | 6 | 3 | 3 | 2 | COFFEE |

(No corn production building exists.)

## Small beige buildings (1 of each in 2-player)

| id | name | cost | col | VP | circles | timing | effect |
|----|------|------|-----|----|---------|--------|--------|
| SMALL_MARKET | small market | 1 | 1 | 1 | 1 | TRADER_SELL_PRICE | +1 doubloon on your sale |
| HACIENDA | hacienda | 2 | 1 | 1 | 1 | SETTLER_PLACE | before taking a face-up tile, take an extra top face-down plantation and place it |
| CONSTRUCTION_HUT | construction hut | 2 | 1 | 1 | 1 | SETTLER_PLACE | may take a quarry instead of a face-up plantation (also for non-chooser turns) |
| SMALL_WAREHOUSE | small warehouse | 3 | 1 | 1 | 1 | CAPTAIN_STORAGE | keep all goods of 1 chosen kind (beyond the 1 free) |
| HOSPICE | hospice | 4 | 2 | 2 | 1 | SETTLER_PLACE | when you place a tile, place a free colonist (from supply) on it |
| OFFICE | office | 5 | 2 | 2 | 1 | TRADER_SELL_PRICE | may sell a kind already in the trading house |
| LARGE_MARKET | large market | 5 | 2 | 2 | 1 | TRADER_SELL_PRICE | +2 doubloons on your sale (stacks with small market → +3) |
| LARGE_WAREHOUSE | large warehouse | 6 | 2 | 2 | 1 | CAPTAIN_STORAGE | keep all goods of 2 chosen kinds (stack with small → 3) |
| FACTORY | factory | 7 | 3 | 3 | 1 | CRAFTSMAN_PRODUCE | +doubloons by # distinct kinds produced: 2→1,3→2,4→3,5→5 |
| UNIVERSITY | university | 8 | 3 | 3 | 1 | BUILDER_BUILD | place a free colonist on the building you just built (one, even for multi-circle) |
| HARBOR | harbor | 8 | 3 | 3 | 1 | CAPTAIN_LOAD | +1 VP each time you load a cargo ship |
| WHARF | wharf | 9 | 3 | 3 | 1 | CAPTAIN_LOAD | once/phase, ship all of one kind to the supply via an imaginary ship (cap 11), scoring VP as normal |

### Building-specific notes & edge cases

- **Hacienda + construction hut interaction:** if a player has both occupied, taking the extra
  face-down tile (hacienda) forbids substituting a quarry for it; a settler with a hacienda may take
  only one quarry. Encode in the SETTLER_PLACE handler ordering: hacienda fires first (adds a tile),
  then the normal take.
- **Construction hut for non-choosers:** the only way a non-chooser takes a quarry in the settler
  phase. Reflect this in `legal_actions()` for settler turns by consulting the player's occupied
  construction hut.
- **Hospice:** the free colonist is placed on the newly placed tile (it becomes occupied). If both
  hacienda and hospice are occupied and the player takes the extra hacienda tile, the hospice colonist
  applies to the **normal** tile only, not the extra (rulebook).
- **Office:** modifies *legality* of a sale, not just price. The TRADER_SELL_PRICE handler must be able
  to relax the different-kind constraint when building `legal_actions()` for trader turns — so the
  trader legality check itself queries this. Keep one source: a helper `can_sell(state, player, good)`
  that accounts for office.
- **Factory:** counts distinct kinds *produced this craftsman turn*, not held; quantity irrelevant.
- **Wharf vs harbor:** both can apply in one captain phase. Wharf is optional and once-per-phase;
  harbor's +1 applies to every load including the wharf "load." See design/02 captain rules for the
  mandatory-load interaction (a player must load a cargo ship if able; wharf is the exception).
- **Warehouses:** "kept" goods stay on the player's windrose; they are not consumed. They still must be
  loaded in a future captain phase if loadable. Model storage as choosing which kinds to protect.

## Large beige buildings (1 of each)

Each occupies two adjacent city slots, counts as one building, and scores base VP unoccupied. The
SCORE_END extra applies only when occupied (≥1 colonist). Capacity = 1 circle each.

| id | name | cost | col | base VP | SCORE_END extra (if occupied) |
|----|------|------|-----|---------|-------------------------------|
| GUILD_HALL | guild hall | 10 | 4 | 4 | +1 per small production bldg, +2 per large production bldg (owned, occ. or not) |
| RESIDENCE | residence | 10 | 4 | 4 | +4/5/6/7 for ≤9 / 10 / 11 / 12 filled island spaces |
| FORTRESS | fortress | 10 | 4 | 4 | +1 per 3 colonists on the board (island+city+stored) |
| CUSTOMS_HOUSE | customs house | 10 | 4 | 4 | +1 per 4 VP chips (building VP excluded) |
| CITY_HALL | city hall | 10 | 4 | 4 | +1 per beige building owned (counts itself) |

Notes:
- "Beige building" = all non-production buildings (the 12 small + 5 large). City hall counts itself
  and the other large buildings.
- Guild hall: "small production building" = small indigo plant, small sugar mill; "large production
  building" = indigo plant, sugar mill, tobacco storage, coffee roaster.

## BuildingId enum & the catalog

Define `BuildingId(IntEnum)` with one member per row above (production + small + large), plus
`LARGE_CONT` sentinel for the second slot of a large building (design/01). Build a single
`CATALOG: dict[BuildingId, BuildingSpec]` and a `HANDLERS: dict[(BuildingId, Timing), Callable]`.
Provide helpers: `is_beige(id)`, `is_production(id)`, `production_size(id) -> "small"|"large"`.

## Acceptance criteria

- Each building has: a spec entry, correct cost/VP/capacity, and (where applicable) a handler with a
  unit test asserting its effect in isolation (e.g. factory with 3 kinds → +2 doubloons; residence with
  11 filled spaces → +6 VP; office allows a duplicate-kind sale).
- A "build every building, occupy all, score" integration test reproduces hand-computed end VP.
- The hacienda+construction-hut and hospice+hacienda interactions each have a dedicated test.
