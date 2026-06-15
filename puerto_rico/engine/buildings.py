"""Building catalog, timing-hook framework, and helper functions.

This module is the single source of truth for *building data and behavior*:

- ``Timing`` — the seven timing points at which buildings may inject behavior.
- ``BuildingSpec`` — the static (immutable) description of one building.
- ``CATALOG`` — every base-game building (23 entries; the ``LARGE_CONT``
  sentinel is NOT included).
- ``HANDLERS`` / ``register`` / ``fire`` — the hook framework. All
  building-specific behavior lives in handlers keyed by ``(BuildingId,
  Timing)``; ``phases.py`` only calls ``fire(...)`` and never branches on a
  ``BuildingId``.
- helper functions used by phases, handlers, and ``legal_actions()``.

Rules source: ``docs/puerto-rico-rules.md`` / ``design/03-buildings-reference.md``.

Handler contract
----------------
A handler is a plain function::

    handler(state, player_idx: int, ctx: Ctx) -> None | value

It mutates ``state`` and/or the documented mutable field(s) on ``ctx``. Most
return ``None``; some return a value (e.g. a price). A handler must be pure
w.r.t. anything other than its documented mutation target.

``ctx`` is a single flexible ``Ctx`` bag (extra attributes allowed). Which
fields each timing populates:

- ``TRADER_SELL_PRICE``: ``ctx.good`` (the good being sold, read-only) and
  ``ctx.price`` (mutable int the handler increments).
- ``SETTLER_PLACE``: ``ctx.tile`` / placement info for the tile being placed.
- ``CRAFTSMAN_PRODUCE``: ``ctx.kinds`` (set/list of distinct kinds produced
  this turn); handlers may add doubloons to ``state``.
- ``CAPTAIN_LOAD``: ``ctx.good`` / ``ctx.count`` / ``ctx.ship`` load info.
- ``CAPTAIN_STORAGE``: ``ctx.storage`` (storage-allowance accumulator).
- ``BUILDER_BUILD``: ``ctx.building`` (the building just built).
- ``SCORE_END``: ``ctx.vp`` (mutable VP accumulator).

Occupancy: ``fire()`` invokes handlers only for *occupied* buildings (>=1
colonist), EXCEPT for ``SCORE_END``, which is gated per-handler (large
buildings score base VP regardless; only the extra requires occupancy).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from typing import Callable

from .enums import BuildingId, Good, TileType


class Timing(IntEnum):
    """Timing points at which buildings may inject behavior."""

    SETTLER_PLACE = 0  # after this player places (or is about to place) a tile
    CRAFTSMAN_PRODUCE = 1  # after this player's production is computed
    TRADER_SELL_PRICE = 2  # adjust sale price / legality for this player's sale
    BUILDER_BUILD = 3  # when this player builds (cost adjust + post-build)
    CAPTAIN_LOAD = 4  # each time this player loads goods
    CAPTAIN_STORAGE = 5  # end-of-captain goods storage allowance
    SCORE_END = 6  # game-end extra VP


@dataclass(frozen=True, slots=True)
class BuildingSpec:
    """Static description of a single building."""

    id: BuildingId
    name: str
    cost: int
    column: int  # 1..4, the quarry-discount cap column on the board
    vp: int  # printed (base) VP
    capacity: int  # colonist circles (1..3); large buildings = 1
    is_large: bool
    is_production: bool
    produces: Good | None  # only set for production buildings
    timings: tuple[Timing, ...]  # which hooks this building implements


def _prod(
    id: BuildingId, name: str, cost: int, col: int, vp: int, cap: int, good: Good
) -> BuildingSpec:
    return BuildingSpec(
        id=id,
        name=name,
        cost=cost,
        column=col,
        vp=vp,
        capacity=cap,
        is_large=False,
        is_production=True,
        produces=good,
        timings=(),
    )


def _small(
    id: BuildingId,
    name: str,
    cost: int,
    col: int,
    vp: int,
    timings: tuple[Timing, ...],
) -> BuildingSpec:
    return BuildingSpec(
        id=id,
        name=name,
        cost=cost,
        column=col,
        vp=vp,
        capacity=1,
        is_large=False,
        is_production=False,
        produces=None,
        timings=timings,
    )


def _large(id: BuildingId, name: str) -> BuildingSpec:
    return BuildingSpec(
        id=id,
        name=name,
        cost=10,
        column=4,
        vp=4,
        capacity=1,
        is_large=True,
        is_production=False,
        produces=None,
        timings=(Timing.SCORE_END,),
    )


CATALOG: dict[BuildingId, BuildingSpec] = {
    # --- production buildings (no handlers; output computed in craftsman) ---
    BuildingId.SMALL_INDIGO: _prod(
        BuildingId.SMALL_INDIGO, "small indigo plant", 1, 1, 1, 1, Good.INDIGO
    ),
    BuildingId.INDIGO_PLANT: _prod(
        BuildingId.INDIGO_PLANT, "indigo plant", 3, 2, 2, 3, Good.INDIGO
    ),
    BuildingId.SMALL_SUGAR: _prod(
        BuildingId.SMALL_SUGAR, "small sugar mill", 2, 1, 1, 1, Good.SUGAR
    ),
    BuildingId.SUGAR_MILL: _prod(
        BuildingId.SUGAR_MILL, "sugar mill", 4, 2, 2, 3, Good.SUGAR
    ),
    BuildingId.TOBACCO_STORAGE: _prod(
        BuildingId.TOBACCO_STORAGE, "tobacco storage", 5, 3, 3, 3, Good.TOBACCO
    ),
    BuildingId.COFFEE_ROASTER: _prod(
        BuildingId.COFFEE_ROASTER, "coffee roaster", 6, 3, 3, 2, Good.COFFEE
    ),
    # --- small beige buildings ---
    BuildingId.SMALL_MARKET: _small(
        BuildingId.SMALL_MARKET, "small market", 1, 1, 1, (Timing.TRADER_SELL_PRICE,)
    ),
    BuildingId.HACIENDA: _small(
        BuildingId.HACIENDA, "hacienda", 2, 1, 1, (Timing.SETTLER_PLACE,)
    ),
    BuildingId.CONSTRUCTION_HUT: _small(
        BuildingId.CONSTRUCTION_HUT,
        "construction hut",
        2,
        1,
        1,
        (Timing.SETTLER_PLACE,),
    ),
    BuildingId.SMALL_WAREHOUSE: _small(
        BuildingId.SMALL_WAREHOUSE,
        "small warehouse",
        3,
        1,
        1,
        (Timing.CAPTAIN_STORAGE,),
    ),
    BuildingId.HOSPICE: _small(
        BuildingId.HOSPICE, "hospice", 4, 2, 2, (Timing.SETTLER_PLACE,)
    ),
    BuildingId.OFFICE: _small(
        BuildingId.OFFICE, "office", 5, 2, 2, (Timing.TRADER_SELL_PRICE,)
    ),
    BuildingId.LARGE_MARKET: _small(
        BuildingId.LARGE_MARKET, "large market", 5, 2, 2, (Timing.TRADER_SELL_PRICE,)
    ),
    BuildingId.LARGE_WAREHOUSE: _small(
        BuildingId.LARGE_WAREHOUSE,
        "large warehouse",
        6,
        2,
        2,
        (Timing.CAPTAIN_STORAGE,),
    ),
    BuildingId.FACTORY: _small(
        BuildingId.FACTORY, "factory", 7, 3, 3, (Timing.CRAFTSMAN_PRODUCE,)
    ),
    BuildingId.UNIVERSITY: _small(
        BuildingId.UNIVERSITY, "university", 8, 3, 3, (Timing.BUILDER_BUILD,)
    ),
    BuildingId.HARBOR: _small(
        BuildingId.HARBOR, "harbor", 8, 3, 3, (Timing.CAPTAIN_LOAD,)
    ),
    BuildingId.WHARF: _small(
        BuildingId.WHARF, "wharf", 9, 3, 3, (Timing.CAPTAIN_LOAD,)
    ),
    # --- large beige buildings ---
    BuildingId.GUILD_HALL: _large(BuildingId.GUILD_HALL, "guild hall"),
    BuildingId.RESIDENCE: _large(BuildingId.RESIDENCE, "residence"),
    BuildingId.FORTRESS: _large(BuildingId.FORTRESS, "fortress"),
    BuildingId.CUSTOMS_HOUSE: _large(BuildingId.CUSTOMS_HOUSE, "customs house"),
    BuildingId.CITY_HALL: _large(BuildingId.CITY_HALL, "city hall"),
}


# --------------------------------------------------------------------------- #
# Hook framework
# --------------------------------------------------------------------------- #

# A handler mutates state / ctx and may return a value (usually None).
Handler = Callable[["object", int, "Ctx"], "object | None"]

# Registry keyed by (building, timing). Empty here; populated by handler tasks.
HANDLERS: dict[tuple[BuildingId, Timing], Handler] = {}


@dataclass(slots=True)
class Ctx:
    """Flexible, mutable context bag passed to handlers.

    A single type carries the union of fields any timing needs; a given timing
    populates only the relevant ones (see the module docstring). Extra unused
    attributes are allowed and default to ``None``/0.
    """

    # TRADER_SELL_PRICE
    good: Good | None = None
    price: int = 0
    # SETTLER_PLACE
    tile: object | None = None
    # CRAFTSMAN_PRODUCE
    kinds: set | None = None
    # CAPTAIN_LOAD
    count: int = 0
    ship: object | None = None
    # CAPTAIN_STORAGE
    storage: int = 0
    # BUILDER_BUILD
    building: BuildingId | None = None
    # SCORE_END
    vp: int = 0
    # generic escape hatch for extra per-timing data
    extra: dict = field(default_factory=dict)


def register(building_id: BuildingId, timing: Timing) -> Callable[[Handler], Handler]:
    """Decorator registering ``fn`` as the handler for ``(building_id, timing)``.

    Used by the handler tasks (04-06) to attach behavior::

        @register(BuildingId.SMALL_MARKET, Timing.TRADER_SELL_PRICE)
        def _small_market(state, player_idx, ctx):
            ctx.price += 1
    """

    def deco(fn: Handler) -> Handler:
        HANDLERS[(building_id, timing)] = fn
        return fn

    return deco


def fire(timing: Timing, state, player_idx: int, ctx) -> None:
    """Invoke every registered handler for ``player_idx``'s buildings at ``timing``.

    Iterates the player's city in stable slot order. For each real building
    whose spec declares ``timing`` and which is *occupied* (>=1 colonist),
    looks up ``HANDLERS.get((building_id, timing))`` and calls it with
    ``(state, player_idx, ctx)``.

    ``SCORE_END`` is special: occupancy is NOT enforced here (large buildings
    score base VP unoccupied, and Task 06's handlers decide per-building whether
    the *extra* requires occupancy), so its handlers fire regardless of manning.

    Missing handlers are skipped silently (no error), making this a safe no-op
    dispatcher until the handler tasks populate ``HANDLERS``.
    """
    player = state.players[player_idx]
    for slot in player.city:
        bid = slot.building
        if bid is None or bid == BuildingId.LARGE_CONT:
            continue
        spec = CATALOG.get(bid)
        if spec is None or timing not in spec.timings:
            continue
        if timing != Timing.SCORE_END and slot.colonists <= 0:
            continue
        handler = HANDLERS.get((bid, timing))
        if handler is not None:
            handler(state, player_idx, ctx)


# --------------------------------------------------------------------------- #
# Helper functions
# --------------------------------------------------------------------------- #

_SMALL_PRODUCTION = frozenset({BuildingId.SMALL_INDIGO, BuildingId.SMALL_SUGAR})
_LARGE_PRODUCTION = frozenset(
    {
        BuildingId.INDIGO_PLANT,
        BuildingId.SUGAR_MILL,
        BuildingId.TOBACCO_STORAGE,
        BuildingId.COFFEE_ROASTER,
    }
)


def get_spec(building_id: BuildingId) -> BuildingSpec:
    """Return the spec for a real building.

    Raises ``KeyError`` for ``LARGE_CONT`` (a sentinel, not a real building).
    """
    return CATALOG[building_id]


def is_beige(building_id: BuildingId) -> bool:
    """True for all 17 non-production real buildings (12 small + 5 large).

    False for the 6 production buildings. Not valid for ``LARGE_CONT``
    (raises ``KeyError``).
    """
    return not CATALOG[building_id].is_production


def is_production(building_id: BuildingId) -> bool:
    """True for the 6 production buildings; False for beige."""
    return CATALOG[building_id].is_production


def production_size(building_id: BuildingId) -> str:
    """Return ``"small"`` or ``"large"`` for a production building.

    Raises ``ValueError`` for non-production ids (including beige and
    ``LARGE_CONT``).
    """
    if building_id in _SMALL_PRODUCTION:
        return "small"
    if building_id in _LARGE_PRODUCTION:
        return "large"
    raise ValueError(f"{building_id!r} is not a production building")


def can_sell(state, player_idx: int, good: Good) -> bool:
    """Whether ``player_idx`` may sell ``good`` to the trading house.

    Single source of truth for the trader duplicate-kind constraint (used by
    both the trader ``legal_actions()`` and the office ``TRADER_SELL_PRICE``
    handler). Rules:

    - The player must actually hold at least one of ``good``.
    - The trading house must not be full (4 goods).
    - By default a kind already present in the trading house may not be sold.
    - **Office exception:** an *occupied* office lifts the duplicate-kind
      constraint, so the player may sell a kind already in the house.
    """
    player = state.players[player_idx]
    if player.goods[good] <= 0:
        return False
    if len(state.trading_house) >= 4:
        return False
    if good in state.trading_house and not player.occupied(BuildingId.OFFICE):
        return False
    return True


# --------------------------------------------------------------------------- #
# Effect handlers (buildings-task-04: small beige economic buildings)
# --------------------------------------------------------------------------- #
#
# These attach the actual effects to the timing seams that phases.py already
# fires. Each is keyed by (BuildingId, Timing) and gated on occupancy by
# ``fire()`` (which skips unoccupied buildings for every timing except
# SCORE_END), so the handlers below do NOT re-check manning.
#
# OFFICE has NO handler: its only effect is *legality* (selling a kind already
# in the trading house), which is the single-source-of-truth ``can_sell()``
# above and is consulted directly by the trader phase. Adding a
# TRADER_SELL_PRICE office handler here would duplicate that logic, so we omit
# it deliberately.
#
# WHARF has NO handler: the captain phase implements the wharf shipment inline
# as a ``LOAD(choice=CAPTAIN_WHARF)`` action variant (a once-per-phase ship to
# the supply), not via a CAPTAIN_LOAD handler. The HARBOR handler below still
# fires for that wharf "load" because the phase fires CAPTAIN_LOAD for it too.


@register(BuildingId.SMALL_MARKET, Timing.TRADER_SELL_PRICE)
def _small_market(state, player_idx, ctx) -> None:
    """+1 doubloon on this player's sale (the phase already seeded base + chooser)."""
    ctx.price += 1


@register(BuildingId.LARGE_MARKET, Timing.TRADER_SELL_PRICE)
def _large_market(state, player_idx, ctx) -> None:
    """+2 doubloons on this player's sale; stacks additively with small market (+3)."""
    ctx.price += 2


#: Factory doubloon bonus indexed by the number of DISTINCT kinds produced.
_FACTORY_BONUS = {0: 0, 1: 0, 2: 1, 3: 2, 4: 3, 5: 5}


@register(BuildingId.FACTORY, Timing.CRAFTSMAN_PRODUCE)
def _factory(state, player_idx, ctx) -> None:
    """Pay bonus doubloons by the number of distinct kinds produced this turn.

    2 kinds -> +1, 3 -> +2, 4 -> +3, 5 -> +5 (0 or 1 -> +0). Reads the distinct
    kinds from ``ctx.kinds`` (the phase passes the set it just produced).
    """
    kinds = ctx.kinds or set()
    bonus = _FACTORY_BONUS.get(len(kinds), 0)
    if bonus:
        state.players[player_idx].doubloons += bonus


@register(BuildingId.HARBOR, Timing.CAPTAIN_LOAD)
def _harbor(state, player_idx, ctx) -> None:
    """+1 VP each time this player loads (cargo ship OR wharf).

    Routes the VP through the captain phase's ``award_captain_vp`` so the
    ``vp_chips_remaining`` pool decrements and the VP-exhaustion end trigger
    stays correct. Imported lazily to avoid the phases<->buildings import cycle
    (phases.py imports buildings at module load).
    """
    from . import phases

    phases.award_captain_vp(state, player_idx, 1)


@register(BuildingId.UNIVERSITY, Timing.BUILDER_BUILD)
def _university(state, player_idx, ctx) -> None:
    """Man the just-built building with one free colonist from the supply.

    Reads the new building's city slot from ``ctx.extra["slot"]``. Places exactly
    one colonist (even for a multi-circle building) if the supply has one and the
    building has free capacity. No-op when the supply is empty or the slot is
    already full.
    """
    if state.colonist_supply <= 0:
        return
    slot_idx = ctx.extra.get("slot")
    if slot_idx is None:
        return
    slot = state.players[player_idx].city[slot_idx]
    bid = slot.building
    if bid is None or bid == BuildingId.LARGE_CONT:
        return
    if slot.colonists >= CATALOG[bid].capacity:
        return
    slot.colonists += 1
    state.colonist_supply -= 1


def _best_held_kinds(player, n: int, exclude: set) -> list:
    """Up to ``n`` held good kinds with the highest counts, excluding ``exclude``.

    Greedy pick by (count desc, then Good value desc) for determinism. Used by the
    warehouse handlers to choose which WHOLE kinds to protect during storage.
    """
    candidates = sorted(
        (g for g in Good if player.goods[g] > 0 and g not in exclude),
        key=lambda g: (player.goods[g], int(g)),
        reverse=True,
    )
    return candidates[:n]


@register(BuildingId.SMALL_WAREHOUSE, Timing.CAPTAIN_STORAGE)
def _small_warehouse(state, player_idx, ctx) -> None:
    """Keep all goods of 1 chosen kind (beyond the windrose single good).

    Adds the best (highest-count) still-unprotected held kind to
    ``ctx.extra["keep_kinds"]``. Greedy-by-count picking is deterministic and,
    combined with the large warehouse, yields the top-N kinds regardless of which
    warehouse handler fires first.
    """
    keep_kinds = ctx.extra.setdefault("keep_kinds", set())
    keep_kinds.update(_best_held_kinds(state.players[player_idx], 1, keep_kinds))


@register(BuildingId.LARGE_WAREHOUSE, Timing.CAPTAIN_STORAGE)
def _large_warehouse(state, player_idx, ctx) -> None:
    """Keep all goods of 2 chosen kinds; stacks with small warehouse (-> 3 kinds)."""
    keep_kinds = ctx.extra.setdefault("keep_kinds", set())
    keep_kinds.update(_best_held_kinds(state.players[player_idx], 2, keep_kinds))


# --------------------------------------------------------------------------- #
# Effect handlers (buildings-task-05: small beige settler buildings)
# --------------------------------------------------------------------------- #
#
# These attach to Timing.SETTLER_PLACE, which phases.py fires TWICE for the
# acting player on a TAKE_TILE: once with ctx.extra["event"] == "pre_take"
# (before any tile is chosen; ctx.tile / ctx.extra["slot"] are None) and once
# with "post_place" (after the chosen tile is auto-placed; ctx.tile is the
# placed TileType and ctx.extra["slot"] is its island slot index). Both
# handlers are gated on occupancy by fire() and key off ctx.extra["event"], so
# they no-op on the event they don't care about.
#
# HACIENDA fires on "pre_take" for the *acting* player. Although the phase also
# passes ctx.extra["is_chooser"], the hacienda effect is NOT a chooser
# privilege: design/03 says "before taking a face-up tile, take an extra top
# face-down plantation and place it" with no chooser restriction, and in this
# engine each player acts only on their own settler turn (fire() already scopes
# to player_idx). So hacienda applies to whoever is taking the settler action,
# chooser or not — we deliberately ignore is_chooser.
#
# HOSPICE fires on "post_place" and mans the tile placed by the MAIN take (the
# post_place slot). Per design/03 the free colonist goes on "the newly placed
# tile"; the hacienda extra tile is placed during pre_take (a separate take) and
# is explicitly NOT manned by hospice (design/03: "If both hacienda and hospice
# are occupied ... the hospice colonist applies to the normal tile only, not the
# extra").
#
# CONSTRUCTION_HUT has NO handler: its only effect is *legality* (a quarry may be
# taken instead of a face-up plantation, for chooser and non-chooser alike),
# which the settler phase resolves directly via _can_take_quarry() consulting
# the player's occupied construction hut. Adding a SETTLER_PLACE handler would
# duplicate that legality rule, so we omit it deliberately — mirroring the
# OFFICE / WHARF omissions in buildings-task-04.


def _draw_facedown_plantation(state) -> TileType | None:
    """Pop the top face-down plantation, reshuffling discard if needed.

    Returns the drawn ``TileType`` or ``None`` when both the face-down stack and
    the discard are empty. Mirrors the reshuffle logic in
    ``settler_last_duty``: when ``plantation_facedown`` is empty, shuffle
    ``plantation_discard`` back into it via ``state.rng`` and draw from there.
    """
    if not state.plantation_facedown:
        if not state.plantation_discard:
            return None
        state.plantation_facedown = state.plantation_discard
        state.plantation_discard = []
        state.rng.shuffle(state.plantation_facedown)
    return state.plantation_facedown.pop()


@register(BuildingId.HACIENDA, Timing.SETTLER_PLACE)
def _hacienda(state, player_idx, ctx) -> None:
    """Pre-take: draw an extra face-down plantation onto the acting player's island.

    Fires only on the ``"pre_take"`` event (before the normal take). Draws the
    top face-down plantation (reshuffling the discard if the stack is empty) and
    places it on the player's lowest empty island slot. No-op when the island is
    full or no tile can be drawn. The extra tile is NOT quarry-swappable and is
    NOT manned by hospice (hospice fires on the later post_place event).
    """
    if ctx.extra.get("event") != "pre_take":
        return
    player = state.players[player_idx]
    slot_idx = None
    for i, slot in enumerate(player.island):
        if slot.tile == TileType.EMPTY:
            slot_idx = i
            break
    if slot_idx is None:
        return
    tile = _draw_facedown_plantation(state)
    if tile is None:
        return
    player.island[slot_idx].tile = tile


@register(BuildingId.HOSPICE, Timing.SETTLER_PLACE)
def _hospice(state, player_idx, ctx) -> None:
    """Post-place: man the just-placed (main-take) tile with a free colonist.

    Fires only on the ``"post_place"`` event. Reads the placed island slot from
    ctx.extra["slot"]; if that slot holds a tile and is not already manned and
    the colonist supply is non-empty, places one free colonist on it and
    decrements ``state.colonist_supply``. No-op otherwise. Only the main take's
    tile is manned — never the hacienda extra (which is placed at pre_take).
    """
    if ctx.extra.get("event") != "post_place":
        return
    if state.colonist_supply <= 0:
        return
    slot_idx = ctx.extra.get("slot")
    if slot_idx is None:
        return
    slot = state.players[player_idx].island[slot_idx]
    if slot.tile == TileType.EMPTY or slot.colonist:
        return
    slot.colonist = True
    state.colonist_supply -= 1


def owned_production_counts(player) -> dict[str, int]:
    """Count the player's owned production buildings, split by size.

    Counts buildings the player **owns** (occupied or not). Returns
    ``{"small": int, "large": int}``. Used by the guild hall ``SCORE_END``
    handler (Task 06).
    """
    small = 0
    large = 0
    for slot in player.city:
        bid = slot.building
        if bid in _SMALL_PRODUCTION:
            small += 1
        elif bid in _LARGE_PRODUCTION:
            large += 1
    return {"small": small, "large": large}


# --------------------------------------------------------------------------- #
# Effect handlers (buildings-task-06: large beige SCORE_END scoring)
# --------------------------------------------------------------------------- #
#
# Each large building's printed base 4 VP is counted unconditionally by
# scoring.py (it sums every owned building's printed vp). These handlers add
# ONLY the variable EXTRA, and ONLY when the building is occupied (>=1 colonist).
#
# fire() does NOT gate SCORE_END on occupancy (so the dispatch reaches an
# unoccupied large building), therefore EACH handler below first checks
# ``player.occupied(<its id>)`` and adds nothing when unmanned. The bonus is
# accumulated onto ``ctx.vp``.


@register(BuildingId.GUILD_HALL, Timing.SCORE_END)
def _guild_hall(state, player_idx, ctx) -> None:
    """+1 per small production building owned, +2 per large; occupied only.

    Counts owned production buildings regardless of their own occupancy
    (``owned_production_counts``). Adds nothing when the guild hall is unmanned.
    """
    player = state.players[player_idx]
    if not player.occupied(BuildingId.GUILD_HALL):
        return
    counts = owned_production_counts(player)
    ctx.vp += counts["small"] + 2 * counts["large"]


#: Residence extra VP keyed by filled island spaces (<=9 -> +4).
def _residence_bonus(filled: int) -> int:
    if filled <= 9:
        return 4
    if filled == 10:
        return 5
    if filled == 11:
        return 6
    return 7  # 12 (the island has 12 spaces, so this is the cap)


@register(BuildingId.RESIDENCE, Timing.SCORE_END)
def _residence(state, player_idx, ctx) -> None:
    """+4/5/6/7 for <=9 / 10 / 11 / 12 filled island spaces; occupied only.

    "Filled" = island spaces holding any tile (plantation or quarry), whether or
    not that tile carries a colonist. Adds nothing when the residence is unmanned.
    """
    player = state.players[player_idx]
    if not player.occupied(BuildingId.RESIDENCE):
        return
    ctx.vp += _residence_bonus(player.filled_island_spaces())


@register(BuildingId.FORTRESS, Timing.SCORE_END)
def _fortress(state, player_idx, ctx) -> None:
    """+1 per 3 colonists on the board (island + city + stored); occupied only.

    Floor division over ``total_colonists()``. Adds nothing when unmanned.
    """
    player = state.players[player_idx]
    if not player.occupied(BuildingId.FORTRESS):
        return
    ctx.vp += player.total_colonists() // 3


@register(BuildingId.CUSTOMS_HOUSE, Timing.SCORE_END)
def _customs_house(state, player_idx, ctx) -> None:
    """+1 per 4 VP CHIPS the player holds (printed building VP excluded); occupied only.

    Floor division over ``player.vp_chips`` (earned VP chips only). Adds nothing
    when unmanned.
    """
    player = state.players[player_idx]
    if not player.occupied(BuildingId.CUSTOMS_HOUSE):
        return
    ctx.vp += player.vp_chips // 4


@register(BuildingId.CITY_HALL, Timing.SCORE_END)
def _city_hall(state, player_idx, ctx) -> None:
    """+1 per beige (non-production) building owned, counting itself; occupied only.

    Beige = all non-production real buildings (12 small + 5 large), including the
    other large buildings and city hall itself. ``LARGE_CONT`` continuation slots
    are skipped. Adds nothing when city hall is unmanned.
    """
    player = state.players[player_idx]
    if not player.occupied(BuildingId.CITY_HALL):
        return
    bonus = 0
    for slot in player.city:
        bid = slot.building
        if bid is None or bid == BuildingId.LARGE_CONT:
            continue
        if not CATALOG[bid].is_production:
            bonus += 1
    ctx.vp += bonus
