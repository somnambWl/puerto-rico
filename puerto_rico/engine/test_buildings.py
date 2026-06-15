"""Tests for the building catalog, hook framework, and helper functions.

Covers buildings-task-01 (catalog), -02 (hook framework), -03 (production
specs), and -08 (helper functions). Handler behavior (tasks 04-06) and the
full-catalog integration test (task 07) are out of scope here.
"""

import pytest

from .buildings import (
    CATALOG,
    HANDLERS,
    BuildingSpec,
    Ctx,
    Timing,
    can_sell,
    fire,
    get_spec,
    is_beige,
    is_production,
    owned_production_counts,
    production_size,
    register,
)
from .enums import BuildingId, Good
from .state import CitySlot, GameState, IslandSlot, PlayerState

PRODUCTION_IDS = [
    BuildingId.SMALL_INDIGO,
    BuildingId.INDIGO_PLANT,
    BuildingId.SMALL_SUGAR,
    BuildingId.SUGAR_MILL,
    BuildingId.TOBACCO_STORAGE,
    BuildingId.COFFEE_ROASTER,
]

SMALL_BEIGE_IDS = [
    BuildingId.SMALL_MARKET,
    BuildingId.HACIENDA,
    BuildingId.CONSTRUCTION_HUT,
    BuildingId.SMALL_WAREHOUSE,
    BuildingId.HOSPICE,
    BuildingId.OFFICE,
    BuildingId.LARGE_MARKET,
    BuildingId.LARGE_WAREHOUSE,
    BuildingId.FACTORY,
    BuildingId.UNIVERSITY,
    BuildingId.HARBOR,
    BuildingId.WHARF,
]

LARGE_BEIGE_IDS = [
    BuildingId.GUILD_HALL,
    BuildingId.RESIDENCE,
    BuildingId.FORTRESS,
    BuildingId.CUSTOMS_HOUSE,
    BuildingId.CITY_HALL,
]


# --------------------------------------------------------------------------- #
# Catalog completeness (task 01)
# --------------------------------------------------------------------------- #


def test_catalog_has_exactly_23_buildings():
    assert len(CATALOG) == 23
    assert len(PRODUCTION_IDS + SMALL_BEIGE_IDS + LARGE_BEIGE_IDS) == 23
    assert set(CATALOG) == set(PRODUCTION_IDS + SMALL_BEIGE_IDS + LARGE_BEIGE_IDS)


def test_large_cont_is_sentinel_not_in_catalog():
    assert hasattr(BuildingId, "LARGE_CONT")
    assert BuildingId.LARGE_CONT not in CATALOG
    # distinct from every real building value
    assert BuildingId.LARGE_CONT.value not in {b.value for b in CATALOG}


def test_every_spec_fully_populated_and_columns_in_range():
    for bid, spec in CATALOG.items():
        assert isinstance(spec, BuildingSpec)
        assert spec.id == bid
        assert isinstance(spec.name, str) and spec.name
        assert isinstance(spec.cost, int)
        assert 1 <= spec.column <= 4
        assert isinstance(spec.vp, int)
        assert 1 <= spec.capacity <= 3
        assert isinstance(spec.is_large, bool)
        assert isinstance(spec.is_production, bool)
        assert isinstance(spec.timings, tuple)
        if spec.is_production:
            assert spec.produces is not None
        else:
            assert spec.produces is None


def test_buildingspec_is_frozen():
    spec = CATALOG[BuildingId.SMALL_MARKET]
    with pytest.raises(Exception):
        spec.cost = 99


# --------------------------------------------------------------------------- #
# Production buildings (task 03)
# --------------------------------------------------------------------------- #

PRODUCTION_TABLE = {
    # id: (cost, column, vp, capacity, produces)
    BuildingId.SMALL_INDIGO: (1, 1, 1, 1, Good.INDIGO),
    BuildingId.INDIGO_PLANT: (3, 2, 2, 3, Good.INDIGO),
    BuildingId.SMALL_SUGAR: (2, 1, 1, 1, Good.SUGAR),
    BuildingId.SUGAR_MILL: (4, 2, 2, 3, Good.SUGAR),
    BuildingId.TOBACCO_STORAGE: (5, 3, 3, 3, Good.TOBACCO),
    BuildingId.COFFEE_ROASTER: (6, 3, 3, 2, Good.COFFEE),
}


@pytest.mark.parametrize("bid", PRODUCTION_IDS)
def test_production_spec_matches_table(bid):
    cost, col, vp, cap, good = PRODUCTION_TABLE[bid]
    spec = CATALOG[bid]
    assert (spec.cost, spec.column, spec.vp, spec.capacity, spec.produces) == (
        cost,
        col,
        vp,
        cap,
        good,
    )
    assert spec.is_production is True
    assert spec.is_large is False
    assert spec.timings == ()


def test_no_production_handlers_registered():
    for bid in PRODUCTION_IDS:
        for timing in Timing:
            assert (bid, timing) not in HANDLERS


def test_production_size_classification():
    assert production_size(BuildingId.SMALL_INDIGO) == "small"
    assert production_size(BuildingId.SMALL_SUGAR) == "small"
    for bid in [
        BuildingId.INDIGO_PLANT,
        BuildingId.SUGAR_MILL,
        BuildingId.TOBACCO_STORAGE,
        BuildingId.COFFEE_ROASTER,
    ]:
        assert production_size(bid) == "large"


# --------------------------------------------------------------------------- #
# Small + large beige specs (task 01)
# --------------------------------------------------------------------------- #

SMALL_BEIGE_TABLE = {
    # id: (cost, column, vp, timing)
    BuildingId.SMALL_MARKET: (1, 1, 1, Timing.TRADER_SELL_PRICE),
    BuildingId.HACIENDA: (2, 1, 1, Timing.SETTLER_PLACE),
    BuildingId.CONSTRUCTION_HUT: (2, 1, 1, Timing.SETTLER_PLACE),
    BuildingId.SMALL_WAREHOUSE: (3, 1, 1, Timing.CAPTAIN_STORAGE),
    BuildingId.HOSPICE: (4, 2, 2, Timing.SETTLER_PLACE),
    BuildingId.OFFICE: (5, 2, 2, Timing.TRADER_SELL_PRICE),
    BuildingId.LARGE_MARKET: (5, 2, 2, Timing.TRADER_SELL_PRICE),
    BuildingId.LARGE_WAREHOUSE: (6, 2, 2, Timing.CAPTAIN_STORAGE),
    BuildingId.FACTORY: (7, 3, 3, Timing.CRAFTSMAN_PRODUCE),
    BuildingId.UNIVERSITY: (8, 3, 3, Timing.BUILDER_BUILD),
    BuildingId.HARBOR: (8, 3, 3, Timing.CAPTAIN_LOAD),
    BuildingId.WHARF: (9, 3, 3, Timing.CAPTAIN_LOAD),
}


@pytest.mark.parametrize("bid", SMALL_BEIGE_IDS)
def test_small_beige_spec_matches_table(bid):
    cost, col, vp, timing = SMALL_BEIGE_TABLE[bid]
    spec = CATALOG[bid]
    assert (spec.cost, spec.column, spec.vp, spec.capacity) == (cost, col, vp, 1)
    assert spec.is_production is False
    assert spec.is_large is False
    assert spec.produces is None
    assert spec.timings == (timing,)


@pytest.mark.parametrize("bid", LARGE_BEIGE_IDS)
def test_large_beige_spec(bid):
    spec = CATALOG[bid]
    assert spec.cost == 10
    assert spec.column == 4
    assert spec.vp == 4
    assert spec.capacity == 1
    assert spec.is_large is True
    assert spec.is_production is False
    assert spec.produces is None
    assert spec.timings == (Timing.SCORE_END,)


# --------------------------------------------------------------------------- #
# Helpers (task 08)
# --------------------------------------------------------------------------- #


def test_get_spec_and_large_cont_raises():
    assert get_spec(BuildingId.OFFICE).name == "office"
    with pytest.raises(KeyError):
        get_spec(BuildingId.LARGE_CONT)


def test_is_beige_and_is_production():
    for bid in PRODUCTION_IDS:
        assert is_production(bid) is True
        assert is_beige(bid) is False
    for bid in SMALL_BEIGE_IDS + LARGE_BEIGE_IDS:
        assert is_production(bid) is False
        assert is_beige(bid) is True


def test_production_size_raises_for_beige():
    with pytest.raises(ValueError):
        production_size(BuildingId.OFFICE)


def _player_with(*buildings, goods=None) -> PlayerState:
    """A bare player owning the given buildings (1 colonist each by default)."""
    city = [CitySlot() for _ in range(12)]
    for i, b in enumerate(buildings):
        bid, colonists = b if isinstance(b, tuple) else (b, 1)
        city[i] = CitySlot(building=bid, colonists=colonists)
    return PlayerState(
        doubloons=0,
        island=[IslandSlot() for _ in range(12)],
        city=city,
        goods=goods if goods is not None else [0, 0, 0, 0, 0],
        stored_colonists=0,
        vp_chips=0,
    )


def test_owned_production_counts():
    p = _player_with(
        BuildingId.SMALL_INDIGO,
        BuildingId.SUGAR_MILL,
        BuildingId.COFFEE_ROASTER,
        BuildingId.OFFICE,  # beige, ignored
    )
    assert owned_production_counts(p) == {"small": 1, "large": 2}


def test_owned_production_counts_includes_unoccupied():
    p = _player_with(
        (BuildingId.SMALL_SUGAR, 0),  # owned but unmanned
        (BuildingId.INDIGO_PLANT, 0),
    )
    assert owned_production_counts(p) == {"small": 1, "large": 1}


class _MiniState:
    """Minimal state stub for can_sell tests."""

    def __init__(self, player: PlayerState, trading_house: list[Good]):
        self.players = [player]
        self.trading_house = trading_house


def test_can_sell_blocks_duplicate_kind_without_office():
    p = _player_with(goods=[0, 5, 0, 0, 0])  # holds indigo
    st = _MiniState(p, [Good.INDIGO])
    assert can_sell(st, 0, Good.INDIGO) is False


def test_can_sell_allows_duplicate_with_occupied_office():
    p = _player_with(BuildingId.OFFICE, goods=[0, 5, 0, 0, 0])
    st = _MiniState(p, [Good.INDIGO])
    assert can_sell(st, 0, Good.INDIGO) is True


def test_can_sell_office_must_be_occupied():
    p = _player_with((BuildingId.OFFICE, 0), goods=[0, 5, 0, 0, 0])
    st = _MiniState(p, [Good.INDIGO])
    assert can_sell(st, 0, Good.INDIGO) is False


def test_can_sell_requires_holding_good_and_room():
    # not held
    p = _player_with(goods=[0, 0, 0, 0, 0])
    assert can_sell(_MiniState(p, []), 0, Good.INDIGO) is False
    # full trading house
    p2 = _player_with(goods=[0, 5, 0, 0, 0])
    full = [Good.CORN, Good.SUGAR, Good.TOBACCO, Good.COFFEE]
    assert can_sell(_MiniState(p2, full), 0, Good.INDIGO) is False
    # held + room + new kind -> ok
    p3 = _player_with(goods=[0, 5, 0, 0, 0])
    assert can_sell(_MiniState(p3, [Good.CORN]), 0, Good.INDIGO) is True


# --------------------------------------------------------------------------- #
# Hook framework (task 02)
# --------------------------------------------------------------------------- #


def test_handlers_is_dict():
    assert isinstance(HANDLERS, dict)


def _fire_state(player: PlayerState) -> GameState:
    """Wrap a player in a GameState-shaped object for fire() (only .players used)."""

    class _S:
        pass

    s = _S()
    s.players = [player]
    return s  # type: ignore[return-value]


def test_fire_no_handler_is_noop_even_with_relevant_building():
    # Owns + occupies hacienda (declares SETTLER_PLACE) but no handler yet
    # (hacienda's SETTLER_PLACE handler lands in buildings-05).
    p = _player_with(BuildingId.HACIENDA, goods=[0, 0, 0, 0, 0])
    st = _fire_state(p)
    ctx = Ctx(price=2)
    fire(Timing.SETTLER_PLACE, st, 0, ctx)  # must not raise
    assert ctx.price == 2  # unchanged, no handler registered


def test_fire_invokes_registered_handler_once(monkeypatch):
    calls = []

    def handler(state, player_idx, ctx):
        calls.append(player_idx)
        ctx.price += 1

    monkeypatch.setitem(
        HANDLERS, (BuildingId.SMALL_MARKET, Timing.TRADER_SELL_PRICE), handler
    )
    p = _player_with(BuildingId.SMALL_MARKET)
    ctx = Ctx(good=Good.INDIGO, price=2)
    fire(Timing.TRADER_SELL_PRICE, _fire_state(p), 0, ctx)
    assert calls == [0]
    assert ctx.price == 3


def test_fire_skips_unoccupied_building(monkeypatch):
    called = []
    monkeypatch.setitem(
        HANDLERS,
        (BuildingId.SMALL_MARKET, Timing.TRADER_SELL_PRICE),
        lambda s, i, c: called.append(1),
    )
    p = _player_with((BuildingId.SMALL_MARKET, 0))  # unoccupied
    fire(Timing.TRADER_SELL_PRICE, _fire_state(p), 0, Ctx())
    assert called == []


def test_fire_skips_building_not_owned(monkeypatch):
    called = []
    monkeypatch.setitem(
        HANDLERS,
        (BuildingId.OFFICE, Timing.TRADER_SELL_PRICE),
        lambda s, i, c: called.append(1),
    )
    p = _player_with(BuildingId.SMALL_MARKET)  # does not own office
    fire(Timing.TRADER_SELL_PRICE, _fire_state(p), 0, Ctx())
    assert called == []


def test_register_decorator_inserts_and_dispatches(monkeypatch):
    # use a temporary key, then remove it to avoid polluting the registry
    key = (BuildingId.FACTORY, Timing.CRAFTSMAN_PRODUCE)
    monkeypatch.delitem(HANDLERS, key, raising=False)

    @register(BuildingId.FACTORY, Timing.CRAFTSMAN_PRODUCE)
    def _h(state, player_idx, ctx):
        ctx.price += 7

    try:
        assert HANDLERS[key] is _h
        p = _player_with(BuildingId.FACTORY)
        ctx = Ctx()
        fire(Timing.CRAFTSMAN_PRODUCE, _fire_state(p), 0, ctx)
        assert ctx.price == 7
    finally:
        HANDLERS.pop(key, None)
