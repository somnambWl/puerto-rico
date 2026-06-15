"""Tests for the buildings-task-04 effect handlers (small beige economic buildings).

Covers, in isolation, the handlers registered in ``buildings.py`` and the timing
seams ``phases.py`` already fires:

- SMALL_MARKET / LARGE_MARKET @ TRADER_SELL_PRICE (price +1 / +2, stack +3).
- FACTORY @ CRAFTSMAN_PRODUCE (doubloons by distinct kinds: 2->1,3->2,4->3,5->5).
- HARBOR @ CAPTAIN_LOAD (+1 VP per load, decrements vp_chips_remaining, can
  trigger exhaustion).
- UNIVERSITY @ BUILDER_BUILD (free colonist from supply onto the new building).
- SMALL_WAREHOUSE / LARGE_WAREHOUSE @ CAPTAIN_STORAGE (protect 1 / 2 / 3 whole
  kinds), exercised through the real ``_store_goods_for_player`` integration path.
- OFFICE: confirms NO TRADER_SELL_PRICE handler is registered (legality lives in
  ``can_sell``); WHARF: confirms NO CAPTAIN_LOAD handler (wharf is an inline
  action variant in the captain phase).
"""

from __future__ import annotations

import random

from .buildings import HANDLERS, Ctx, Timing, fire
from .enums import BuildingId, Good, TileType
from .phases import _store_goods_for_player, award_captain_vp
from .state import CitySlot, IslandSlot, PlayerState


# --------------------------------------------------------------------------- #
# helpers (a bare player + a minimal state shaped for fire()/handlers)
# --------------------------------------------------------------------------- #


def _player_with(*built, goods=None) -> PlayerState:
    """A bare player owning ``built`` buildings (1 colonist each by default).

    Each entry is a ``BuildingId`` or a ``(BuildingId, colonists)`` tuple.
    """
    city = [CitySlot() for _ in range(12)]
    for i, b in enumerate(built):
        bid, colonists = b if isinstance(b, tuple) else (b, 1)
        city[i] = CitySlot(building=bid, colonists=colonists)
    return PlayerState(
        doubloons=0,
        island=[IslandSlot() for _ in range(12)],
        city=city,
        goods=list(goods) if goods is not None else [0, 0, 0, 0, 0],
        stored_colonists=0,
        vp_chips=0,
    )


class _State:
    """Minimal state stub carrying only the fields the handlers touch."""

    def __init__(self, player: PlayerState, **kw):
        self.players = [player]
        self.colonist_supply = kw.get("colonist_supply", 0)
        self.vp_chips_remaining = kw.get("vp_chips_remaining", 0)
        self.goods_supply = kw.get("goods_supply", [0, 0, 0, 0, 0])
        self.end_triggered = False
        self.plantation_facedown = kw.get("plantation_facedown", [])
        self.plantation_discard = kw.get("plantation_discard", [])
        self.rng = kw.get("rng", random.Random(0))


# --------------------------------------------------------------------------- #
# Markets @ TRADER_SELL_PRICE
# --------------------------------------------------------------------------- #


def test_small_market_adds_one():
    p = _player_with(BuildingId.SMALL_MARKET)
    ctx = Ctx(good=Good.INDIGO, price=2)  # base indigo + chooser already seeded
    fire(Timing.TRADER_SELL_PRICE, _State(p), 0, ctx)
    assert ctx.price == 3


def test_large_market_adds_two():
    p = _player_with(BuildingId.LARGE_MARKET)
    ctx = Ctx(good=Good.SUGAR, price=2)
    fire(Timing.TRADER_SELL_PRICE, _State(p), 0, ctx)
    assert ctx.price == 4


def test_small_and_large_market_stack_to_three():
    p = _player_with(BuildingId.SMALL_MARKET, BuildingId.LARGE_MARKET)
    ctx = Ctx(good=Good.COFFEE, price=4)
    fire(Timing.TRADER_SELL_PRICE, _State(p), 0, ctx)
    assert ctx.price == 7  # 4 + 1 + 2


def test_unoccupied_market_does_not_fire():
    p = _player_with((BuildingId.SMALL_MARKET, 0))
    ctx = Ctx(good=Good.INDIGO, price=1)
    fire(Timing.TRADER_SELL_PRICE, _State(p), 0, ctx)
    assert ctx.price == 1


# --------------------------------------------------------------------------- #
# Factory @ CRAFTSMAN_PRODUCE
# --------------------------------------------------------------------------- #


def _factory_bonus_for(kinds: set) -> int:
    p = _player_with(BuildingId.FACTORY)
    st = _State(p)
    ctx = Ctx()
    ctx.kinds = kinds
    fire(Timing.CRAFTSMAN_PRODUCE, st, 0, ctx)
    return p.doubloons


def test_factory_bonus_by_distinct_kinds():
    assert _factory_bonus_for(set()) == 0
    assert _factory_bonus_for({Good.CORN}) == 0
    assert _factory_bonus_for({Good.CORN, Good.INDIGO}) == 1
    assert _factory_bonus_for({Good.CORN, Good.INDIGO, Good.SUGAR}) == 2
    assert _factory_bonus_for({Good.CORN, Good.INDIGO, Good.SUGAR, Good.TOBACCO}) == 3
    assert (
        _factory_bonus_for(
            {Good.CORN, Good.INDIGO, Good.SUGAR, Good.TOBACCO, Good.COFFEE}
        )
        == 5
    )


def test_unoccupied_factory_pays_nothing():
    p = _player_with((BuildingId.FACTORY, 0))
    st = _State(p)
    ctx = Ctx()
    ctx.kinds = {Good.CORN, Good.INDIGO, Good.SUGAR}
    fire(Timing.CRAFTSMAN_PRODUCE, st, 0, ctx)
    assert p.doubloons == 0


# --------------------------------------------------------------------------- #
# Harbor @ CAPTAIN_LOAD
# --------------------------------------------------------------------------- #


def _captain_load_ctx() -> Ctx:
    ctx = Ctx(good=Good.SUGAR)
    ctx.count = 2
    ctx.ship = None
    ctx.extra = {"first": False}
    return ctx


def test_harbor_awards_one_vp_per_load_and_decrements_pool():
    p = _player_with(BuildingId.HARBOR)
    st = _State(p, vp_chips_remaining=10)
    fire(Timing.CAPTAIN_LOAD, st, 0, _captain_load_ctx())
    assert p.vp_chips == 1
    assert st.vp_chips_remaining == 9
    # Independent of count loaded (harbor is +1 per LOAD event, not per good).
    fire(Timing.CAPTAIN_LOAD, st, 0, _captain_load_ctx())
    assert p.vp_chips == 2
    assert st.vp_chips_remaining == 8


def test_harbor_exhausts_pool_and_triggers_end():
    p = _player_with(BuildingId.HARBOR)
    st = _State(p, vp_chips_remaining=1)
    fire(Timing.CAPTAIN_LOAD, st, 0, _captain_load_ctx())
    assert p.vp_chips == 1
    assert st.vp_chips_remaining == 0
    assert st.end_triggered is True


def test_harbor_routes_through_award_captain_vp():
    # award_captain_vp clamps to the remaining pool: a 1-VP harbor award when the
    # pool is empty grants nothing and leaves end_triggered set.
    p = _player_with(BuildingId.HARBOR)
    st = _State(p, vp_chips_remaining=0)
    award_captain_vp(st, 0, 0)  # sanity: shares the captain-phase accountant
    fire(Timing.CAPTAIN_LOAD, st, 0, _captain_load_ctx())
    assert p.vp_chips == 0
    assert st.vp_chips_remaining == 0


# --------------------------------------------------------------------------- #
# University @ BUILDER_BUILD
# --------------------------------------------------------------------------- #


def test_university_mans_the_just_built_building():
    # University in slot 0, a freshly-built (unmanned) office in slot 1.
    p = _player_with(BuildingId.UNIVERSITY, (BuildingId.OFFICE, 0))
    st = _State(p, colonist_supply=5)
    ctx = Ctx(building=BuildingId.OFFICE)
    ctx.extra = {"slot": 1}
    fire(Timing.BUILDER_BUILD, st, 0, ctx)
    assert p.city[1].colonists == 1
    assert st.colonist_supply == 4


def test_university_noop_when_supply_empty():
    p = _player_with(BuildingId.UNIVERSITY, (BuildingId.OFFICE, 0))
    st = _State(p, colonist_supply=0)
    ctx = Ctx(building=BuildingId.OFFICE)
    ctx.extra = {"slot": 1}
    fire(Timing.BUILDER_BUILD, st, 0, ctx)
    assert p.city[1].colonists == 0
    assert st.colonist_supply == 0


def test_university_places_only_one_colonist_on_multi_circle():
    # A 3-circle production building: university adds exactly one colonist.
    p = _player_with(BuildingId.UNIVERSITY, (BuildingId.INDIGO_PLANT, 0))
    st = _State(p, colonist_supply=5)
    ctx = Ctx(building=BuildingId.INDIGO_PLANT)
    ctx.extra = {"slot": 1}
    fire(Timing.BUILDER_BUILD, st, 0, ctx)
    assert p.city[1].colonists == 1
    assert st.colonist_supply == 4


def test_university_noop_when_unoccupied():
    p = _player_with((BuildingId.UNIVERSITY, 0), (BuildingId.OFFICE, 0))
    st = _State(p, colonist_supply=5)
    ctx = Ctx(building=BuildingId.OFFICE)
    ctx.extra = {"slot": 1}
    fire(Timing.BUILDER_BUILD, st, 0, ctx)
    assert p.city[1].colonists == 0
    assert st.colonist_supply == 5


# --------------------------------------------------------------------------- #
# Warehouses @ CAPTAIN_STORAGE (through the real storage path)
# --------------------------------------------------------------------------- #


def _store_state(player: PlayerState):
    st = _State(player, goods_supply=[0, 0, 0, 0, 0])
    return st


def test_small_warehouse_protects_one_whole_kind():
    p = _player_with(BuildingId.SMALL_WAREHOUSE, goods=[2, 0, 4, 0, 0])
    st = _store_state(p)
    _store_goods_for_player(st, 0)
    # sugar (4) protected; corn keeps 1 on windrose, the other returns to supply.
    assert p.goods[Good.SUGAR] == 4
    assert p.goods[Good.CORN] == 1
    assert st.goods_supply[Good.CORN] == 1


def test_large_warehouse_protects_two_kinds():
    p = _player_with(BuildingId.LARGE_WAREHOUSE, goods=[5, 0, 3, 2, 0])
    st = _store_state(p)
    _store_goods_for_player(st, 0)
    # corn (5) + sugar (3) protected; tobacco (2) keeps 1 windrose, 1 to supply.
    assert p.goods[Good.CORN] == 5
    assert p.goods[Good.SUGAR] == 3
    assert p.goods[Good.TOBACCO] == 1
    assert st.goods_supply[Good.TOBACCO] == 1


def test_warehouses_stack_to_three_kinds():
    p = _player_with(
        BuildingId.SMALL_WAREHOUSE,
        BuildingId.LARGE_WAREHOUSE,
        goods=[5, 4, 3, 2, 0],
    )
    st = _store_state(p)
    _store_goods_for_player(st, 0)
    # Top 3 (corn 5, indigo 4, sugar 3) fully protected; tobacco (2) -> 1 windrose.
    assert p.goods[Good.CORN] == 5
    assert p.goods[Good.INDIGO] == 4
    assert p.goods[Good.SUGAR] == 3
    assert p.goods[Good.TOBACCO] == 1
    assert st.goods_supply[Good.TOBACCO] == 1


def test_unoccupied_warehouse_protects_nothing():
    # Only occupied tiles function (rulebook): an unmanned warehouse is inert.
    p = _player_with((BuildingId.SMALL_WAREHOUSE, 0), goods=[0, 0, 4, 0, 0])
    st = _store_state(p)
    _store_goods_for_player(st, 0)
    assert p.goods[Good.SUGAR] == 1  # only the windrose single survives
    assert st.goods_supply[Good.SUGAR] == 3


# --------------------------------------------------------------------------- #
# Office / Wharf: deliberate absence of handlers
# --------------------------------------------------------------------------- #


def test_office_has_no_trader_sell_price_handler():
    # Office legality lives in can_sell(); no price/legality handler duplicates it.
    assert (BuildingId.OFFICE, Timing.TRADER_SELL_PRICE) not in HANDLERS


def test_wharf_has_no_captain_load_handler():
    # Wharf is an inline LOAD(choice=CAPTAIN_WHARF) action variant in the captain
    # phase, not a CAPTAIN_LOAD handler.
    assert (BuildingId.WHARF, Timing.CAPTAIN_LOAD) not in HANDLERS


# --------------------------------------------------------------------------- #
# Settler handlers @ SETTLER_PLACE (hacienda, hospice; construction hut = none)
# --------------------------------------------------------------------------- #


def _pre_ctx(is_chooser: bool = False) -> Ctx:
    ctx = Ctx(tile=None)
    ctx.extra = {"event": "pre_take", "is_chooser": is_chooser, "slot": None}
    return ctx


def _post_ctx(tile: TileType, slot: int, is_chooser: bool = False) -> Ctx:
    ctx = Ctx(tile=tile)
    ctx.extra = {"event": "post_place", "is_chooser": is_chooser, "slot": slot}
    return ctx


def test_hacienda_draws_extra_facedown_tile_on_pre_take():
    p = _player_with(BuildingId.HACIENDA)
    st = _State(p, plantation_facedown=[TileType.CORN, TileType.TOBACCO])
    fire(Timing.SETTLER_PLACE, st, 0, _pre_ctx())
    # Top of stack (last element) drawn onto lowest empty island slot.
    assert p.island[0].tile == TileType.TOBACCO
    assert p.island[0].colonist is False  # hacienda does not man the tile
    assert st.plantation_facedown == [TileType.CORN]


def test_hacienda_applies_regardless_of_is_chooser():
    # Hacienda is NOT a chooser privilege: it fires for the acting non-chooser.
    p = _player_with(BuildingId.HACIENDA)
    st = _State(p, plantation_facedown=[TileType.INDIGO])
    fire(Timing.SETTLER_PLACE, st, 0, _pre_ctx(is_chooser=False))
    assert p.island[0].tile == TileType.INDIGO


def test_hacienda_noop_on_post_place_event():
    p = _player_with(BuildingId.HACIENDA)
    st = _State(p, plantation_facedown=[TileType.CORN])
    # post_place must not draw an extra tile (hacienda is a pre_take effect).
    p.island[0].tile = TileType.SUGAR  # simulate the main take already placed
    fire(Timing.SETTLER_PLACE, st, 0, _post_ctx(TileType.SUGAR, 0))
    assert p.island[1].tile == TileType.EMPTY
    assert st.plantation_facedown == [TileType.CORN]


def test_hacienda_reshuffles_discard_when_facedown_empty():
    p = _player_with(BuildingId.HACIENDA)
    st = _State(
        p,
        plantation_facedown=[],
        plantation_discard=[TileType.COFFEE, TileType.COFFEE],
        rng=random.Random(0),
    )
    fire(Timing.SETTLER_PLACE, st, 0, _pre_ctx())
    assert p.island[0].tile == TileType.COFFEE
    assert st.plantation_discard == []
    assert len(st.plantation_facedown) == 1  # one drawn from the reshuffled stack


def test_hacienda_noop_when_both_stacks_empty():
    p = _player_with(BuildingId.HACIENDA)
    st = _State(p, plantation_facedown=[], plantation_discard=[])
    fire(Timing.SETTLER_PLACE, st, 0, _pre_ctx())
    assert p.island[0].tile == TileType.EMPTY


def test_hacienda_noop_when_island_full():
    p = _player_with(BuildingId.HACIENDA)
    for s in p.island:
        s.tile = TileType.CORN
    st = _State(p, plantation_facedown=[TileType.TOBACCO])
    fire(Timing.SETTLER_PLACE, st, 0, _pre_ctx())
    # Nothing drawn; the stack is untouched.
    assert st.plantation_facedown == [TileType.TOBACCO]


def test_hacienda_unoccupied_does_nothing():
    p = _player_with((BuildingId.HACIENDA, 0))
    st = _State(p, plantation_facedown=[TileType.CORN])
    fire(Timing.SETTLER_PLACE, st, 0, _pre_ctx())
    assert p.island[0].tile == TileType.EMPTY
    assert st.plantation_facedown == [TileType.CORN]


def test_hospice_mans_the_placed_tile():
    p = _player_with(BuildingId.HOSPICE)
    p.island[0].tile = TileType.CORN  # the main take already placed here
    st = _State(p, colonist_supply=5)
    fire(Timing.SETTLER_PLACE, st, 0, _post_ctx(TileType.CORN, 0))
    assert p.island[0].colonist is True
    assert st.colonist_supply == 4


def test_hospice_noop_when_supply_empty():
    p = _player_with(BuildingId.HOSPICE)
    p.island[0].tile = TileType.CORN
    st = _State(p, colonist_supply=0)
    fire(Timing.SETTLER_PLACE, st, 0, _post_ctx(TileType.CORN, 0))
    assert p.island[0].colonist is False
    assert st.colonist_supply == 0


def test_hospice_noop_on_pre_take_event():
    p = _player_with(BuildingId.HOSPICE)
    st = _State(p, colonist_supply=5)
    fire(Timing.SETTLER_PLACE, st, 0, _pre_ctx())
    assert st.colonist_supply == 5


def test_hospice_unoccupied_does_not_man():
    p = _player_with((BuildingId.HOSPICE, 0))
    p.island[0].tile = TileType.CORN
    st = _State(p, colonist_supply=5)
    fire(Timing.SETTLER_PLACE, st, 0, _post_ctx(TileType.CORN, 0))
    assert p.island[0].colonist is False
    assert st.colonist_supply == 5


def test_hacienda_plus_hospice_hospice_mans_only_the_main_tile():
    # Both occupied. Simulate the real phase sequence: hacienda pre_take draws an
    # extra tile (slot 0), then the main take places at slot 1, then hospice
    # post_place mans slot 1 only — NOT the hacienda extra at slot 0.
    p = _player_with(BuildingId.HACIENDA, BuildingId.HOSPICE)
    st = _State(p, colonist_supply=5, plantation_facedown=[TileType.TOBACCO])

    # pre_take: hacienda draws the extra onto the lowest empty slot (0).
    fire(Timing.SETTLER_PLACE, st, 0, _pre_ctx())
    assert p.island[0].tile == TileType.TOBACCO
    assert p.island[0].colonist is False

    # main take placed at slot 1 (lowest empty after the hacienda extra).
    p.island[1].tile = TileType.CORN
    # post_place mans slot 1 only.
    fire(Timing.SETTLER_PLACE, st, 0, _post_ctx(TileType.CORN, 1))
    assert p.island[1].colonist is True  # main tile manned
    assert p.island[0].colonist is False  # hacienda extra NOT manned
    assert st.colonist_supply == 4


def test_construction_hut_has_no_settler_place_handler():
    # Construction hut's effect is pure legality (take a quarry instead of a
    # plantation), resolved in-phase by settler's _can_take_quarry(); no
    # SETTLER_PLACE handler duplicates it. See test_settler.py
    # ::test_non_chooser_with_construction_hut_can_take_quarry for the phase-level
    # legality coverage.
    assert (BuildingId.CONSTRUCTION_HUT, Timing.SETTLER_PLACE) not in HANDLERS


# --------------------------------------------------------------------------- #
# Large beige SCORE_END handlers (buildings-task-06)
# --------------------------------------------------------------------------- #
#
# Each handler adds ONLY the variable extra and ONLY when the large building is
# occupied. The base 4 printed VP is counted by scoring.py, not here.


def _score_end_bonus(player: PlayerState) -> int:
    """Fire SCORE_END for a single player and return the accumulated ctx.vp."""
    ctx = Ctx()
    ctx.vp = 0
    fire(Timing.SCORE_END, _State(player), 0, ctx)
    return ctx.vp


def _island_player(*built, tiles=0, colonist_tiles=0, stored=0, vp_chips=0):
    """A player owning ``built`` buildings with ``tiles`` filled island spaces.

    ``colonist_tiles`` of those island tiles also carry a colonist. ``built``
    entries are BuildingId or (BuildingId, colonists).
    """
    city = [CitySlot() for _ in range(12)]
    for i, b in enumerate(built):
        bid, colonists = b if isinstance(b, tuple) else (b, 1)
        city[i] = CitySlot(building=bid, colonists=colonists)
    island = [IslandSlot() for _ in range(12)]
    for i in range(tiles):
        island[i] = IslandSlot(
            tile=TileType.CORN, colonist=(i < colonist_tiles)
        )
    return PlayerState(
        doubloons=0,
        island=island,
        city=city,
        goods=[0, 0, 0, 0, 0],
        stored_colonists=stored,
        vp_chips=vp_chips,
    )


# --- guild hall -------------------------------------------------------------

def test_guild_hall_small_and_large_mix():
    # 2 small + 1 large production owned -> 2*1 + 1*2 = 4
    p = _player_with(
        BuildingId.GUILD_HALL,
        BuildingId.SMALL_INDIGO,
        BuildingId.SMALL_SUGAR,
        BuildingId.SUGAR_MILL,
    )
    assert _score_end_bonus(p) == 4


def test_guild_hall_counts_production_regardless_of_occupancy():
    # production buildings unmanned (0 colonists) still count; guild hall manned
    p = _player_with(
        BuildingId.GUILD_HALL,
        (BuildingId.INDIGO_PLANT, 0),
        (BuildingId.COFFEE_ROASTER, 0),
    )
    assert _score_end_bonus(p) == 4  # 2 large * 2


def test_guild_hall_unoccupied_adds_zero():
    p = _player_with(
        (BuildingId.GUILD_HALL, 0),
        BuildingId.SMALL_INDIGO,
        BuildingId.SUGAR_MILL,
    )
    assert _score_end_bonus(p) == 0


# --- residence --------------------------------------------------------------

def test_residence_brackets():
    for tiles, expected in [(0, 4), (9, 4), (10, 5), (11, 6), (12, 7)]:
        p = _island_player(BuildingId.RESIDENCE, tiles=tiles)
        assert _score_end_bonus(p) == expected, tiles


def test_residence_counts_unoccupied_tiles():
    # 11 tiles placed, none carry a colonist -> still +6
    p = _island_player(BuildingId.RESIDENCE, tiles=11, colonist_tiles=0)
    assert _score_end_bonus(p) == 6


def test_residence_unoccupied_adds_zero():
    p = _island_player((BuildingId.RESIDENCE, 0), tiles=12)
    assert _score_end_bonus(p) == 0


# --- fortress ---------------------------------------------------------------

def test_fortress_colonists_floor_div():
    # 1 city colonist (fortress) + 3 island + 3 stored = 7 -> 7//3 = 2
    p = _island_player(BuildingId.FORTRESS, tiles=3, colonist_tiles=3, stored=3)
    assert _score_end_bonus(p) == 2


def test_fortress_only_city_colonist():
    # just the manning colonist on the fortress -> 1//3 = 0
    p = _island_player(BuildingId.FORTRESS)
    assert _score_end_bonus(p) == 0


def test_fortress_six_colonists():
    # fortress(1) + 2 island manned + 3 stored = 6 -> 2
    p = _island_player(BuildingId.FORTRESS, tiles=2, colonist_tiles=2, stored=3)
    assert _score_end_bonus(p) == 2


def test_fortress_unoccupied_adds_zero():
    p = _island_player((BuildingId.FORTRESS, 0), tiles=9, colonist_tiles=9, stored=9)
    assert _score_end_bonus(p) == 0


# --- customs house ----------------------------------------------------------

def test_customs_house_vp_chips_floor_div():
    p = _island_player(BuildingId.CUSTOMS_HOUSE, vp_chips=9)
    assert _score_end_bonus(p) == 2  # 9 // 4


def test_customs_house_zero_chips():
    p = _island_player(BuildingId.CUSTOMS_HOUSE, vp_chips=3)
    assert _score_end_bonus(p) == 0  # 3 // 4


def test_customs_house_unoccupied_adds_zero():
    p = _island_player((BuildingId.CUSTOMS_HOUSE, 0), vp_chips=99)
    assert _score_end_bonus(p) == 0


# --- city hall --------------------------------------------------------------

def test_city_hall_counts_beige_including_itself():
    # beige owned: city hall, small market, hospice, office = 4;
    # production (indigo plant) is NOT beige. The 3 small beige buildings have no
    # SCORE_END handler, so the bonus isolates city hall's own beige count.
    p = _player_with(
        BuildingId.CITY_HALL,
        BuildingId.SMALL_MARKET,
        BuildingId.HOSPICE,
        BuildingId.OFFICE,
        BuildingId.INDIGO_PLANT,
    )
    assert _score_end_bonus(p) == 4


def test_city_hall_alone_counts_itself():
    p = _player_with(BuildingId.CITY_HALL)
    assert _score_end_bonus(p) == 1


def test_city_hall_counts_other_large_beige_buildings():
    # city hall + residence (both large beige) -> city hall counts 2. Call the
    # handler directly so the residence's own SCORE_END bonus doesn't pollute ctx.
    from .buildings import _city_hall

    p = _player_with(BuildingId.CITY_HALL, BuildingId.RESIDENCE)
    ctx = Ctx()
    ctx.vp = 0
    _city_hall(_State(p), 0, ctx)
    assert ctx.vp == 2


def test_city_hall_unoccupied_adds_zero():
    p = _player_with(
        (BuildingId.CITY_HALL, 0),
        BuildingId.SMALL_MARKET,
        BuildingId.HOSPICE,
    )
    assert _score_end_bonus(p) == 0


# --- integration via scoring.final_score ------------------------------------

def test_final_score_base_four_plus_bonus_when_occupied():
    from . import scoring

    # occupied customs house + 8 vp chips: base 4 (printed) + 2 (8//4) + 8 chips
    p = _island_player(BuildingId.CUSTOMS_HOUSE, vp_chips=8)
    assert scoring.final_score(_State(p), 0) == 8 + 4 + 2


def test_final_score_base_four_only_when_unoccupied():
    from . import scoring

    # unoccupied customs house: base 4 printed counts, bonus is 0
    p = _island_player((BuildingId.CUSTOMS_HOUSE, 0), vp_chips=8)
    assert scoring.final_score(_State(p), 0) == 8 + 4
