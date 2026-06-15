"""Tests for engine state data structures (engine-core-task-02)."""

import random

import pytest

from .enums import BuildingId, Good, Phase, Role, TileType
from .phase_state import PhaseState
from .state import (
    CargoShip,
    CitySlot,
    GameConfig,
    GameState,
    IslandSlot,
    PlayerState,
    RolePlacard,
)


def make_player() -> PlayerState:
    """A small hand-built fixture player.

    Island (12 slots): a CORN tile with a colonist, an empty QUARRY (tile but
    no colonist), and 10 EMPTY slots -> filled_island_spaces == 2.
    City (12 slots): SMALL_INDIGO with 1 colonist (occupied, full),
    SMALL_MARKET with 0 colonists (built, unmanned), and 10 empty slots.
    With capacity 1/building: empty_building_circles == 1 (the market).
    stored_colonists == 3.
    Colonists total: island 1 + city 1 + stored 3 == 5.
    """
    island = [IslandSlot() for _ in range(12)]
    island[0] = IslandSlot(tile=TileType.CORN, colonist=True)
    island[1] = IslandSlot(tile=TileType.QUARRY, colonist=False)

    city = [CitySlot() for _ in range(12)]
    city[0] = CitySlot(building=BuildingId.SMALL_INDIGO, colonists=1)
    city[1] = CitySlot(building=BuildingId.SMALL_MARKET, colonists=0)

    return PlayerState(
        doubloons=3,
        island=island,
        city=city,
        goods=[0, 0, 0, 0, 0],
        stored_colonists=3,
        vp_chips=0,
    )


def make_state() -> GameState:
    config = GameConfig(num_players=4, seed=42)
    return GameState(
        config=config,
        rng=random.Random(42),
        players=[make_player() for _ in range(4)],
        governor=0,
        current_player=0,
        phase=Phase.ROLE_SELECTION,
        placards=[RolePlacard(role=r) for r in Role],
        colonist_ship=4,
        colonist_supply=75,
        cargo_ships=[CargoShip(capacity=c) for c in (5, 6, 7)],
        trading_house=[],
        goods_supply=[10, 11, 11, 9, 9],
        plantation_faceup=[TileType.CORN],
        plantation_facedown=[TileType.INDIGO],
        plantation_discard=[],
        quarry_supply=8,
        vp_chips_remaining=100,
        buildings_supply={BuildingId.SMALL_MARKET: 2},
        phase_state=PhaseState(),
    )


# --- instantiation + slots ---


@pytest.mark.parametrize(
    "obj",
    [
        IslandSlot(),
        CitySlot(),
        CargoShip(capacity=5),
        RolePlacard(role=Role.SETTLER),
        make_player(),
        GameConfig(),
        make_state(),
        PhaseState(),
    ],
)
def test_has_slots(obj):
    assert hasattr(type(obj), "__slots__")
    # slotted dataclasses have no per-instance __dict__
    assert not hasattr(obj, "__dict__")


def test_all_instantiate():
    state = make_state()
    assert isinstance(state, GameState)
    assert len(state.players) == 4
    for p in state.players:
        assert len(p.island) == 12
        assert len(p.city) == 12
        assert len(p.goods) == 5
    assert len(state.goods_supply) == 5


def test_gameconfig_frozen():
    config = GameConfig()
    with pytest.raises(Exception):
        config.num_players = 2


# --- PlayerState helpers ---


def test_owns():
    p = make_player()
    assert p.owns(BuildingId.SMALL_INDIGO)
    assert p.owns(BuildingId.SMALL_MARKET)
    assert not p.owns(BuildingId.LARGE_CONT)


def test_building_slot():
    p = make_player()
    assert p.building_slot(BuildingId.SMALL_INDIGO) == 0
    assert p.building_slot(BuildingId.SMALL_MARKET) == 1
    assert p.building_slot(BuildingId.LARGE_CONT) is None


def test_occupied():
    p = make_player()
    assert p.occupied(BuildingId.SMALL_INDIGO)  # built + manned
    assert not p.occupied(BuildingId.SMALL_MARKET)  # built but unmanned
    assert not p.occupied(BuildingId.LARGE_CONT)  # not built


def test_total_colonists():
    p = make_player()
    # island 1 + city 1 + stored 3
    assert p.total_colonists() == 5


def test_filled_island_spaces():
    p = make_player()
    # CORN tile + QUARRY tile = 2 (EMPTY slots excluded)
    assert p.filled_island_spaces() == 2


def test_empty_building_circles():
    p = make_player()
    # indigo plant full (1/1), market empty (0/1) -> 1 empty circle
    assert p.empty_building_circles() == 1


# --- clone & immutability (engine-core-task-05) ---


def test_clone_player_goods_independent():
    s1 = make_state()
    s2 = s1.clone()

    s2.players[0].goods[Good.CORN] = 9
    assert s1.players[0].goods[Good.CORN] == 0

    s1.players[1].goods[Good.SUGAR] = 7
    assert s2.players[1].goods[Good.SUGAR] == 0


def test_clone_scalar_fields_independent():
    s1 = make_state()
    s2 = s1.clone()

    s2.players[0].doubloons = 99
    assert s1.players[0].doubloons == 3

    s2.governor = 3
    assert s1.governor == 0


def test_clone_island_and_city_slots_independent():
    s1 = make_state()
    s2 = s1.clone()

    # mutate clone's island slot
    s2.players[0].island[0].colonist = False
    s2.players[0].island[0].tile = TileType.SUGAR
    assert s1.players[0].island[0].colonist is True
    assert s1.players[0].island[0].tile == TileType.CORN

    # mutate clone's city slot
    s2.players[0].city[1].colonists = 5
    assert s1.players[0].city[1].colonists == 0


def test_clone_cargo_ships_and_placards_independent():
    s1 = make_state()
    s2 = s1.clone()

    s2.cargo_ships[0].good = Good.COFFEE
    s2.cargo_ships[0].count = 3
    assert s1.cargo_ships[0].good is None
    assert s1.cargo_ships[0].count == 0

    s2.placards[0].doubloons = 4
    s2.placards[0].taken_by = 2
    assert s1.placards[0].doubloons == 0
    assert s1.placards[0].taken_by is None


def test_clone_global_lists_and_supply_independent():
    s1 = make_state()
    s2 = s1.clone()

    s2.goods_supply[Good.CORN] = 0
    assert s1.goods_supply[Good.CORN] == 10

    s2.plantation_faceup.append(TileType.SUGAR)
    assert s1.plantation_faceup == [TileType.CORN]

    s2.buildings_supply[BuildingId.SMALL_MARKET] = 0
    assert s1.buildings_supply[BuildingId.SMALL_MARKET] == 2


def test_clone_phase_state_independent():
    s1 = make_state()
    s1.phase_state.order = [0, 1, 2, 3]
    s1.phase_state.sub = {"x": 1}
    s2 = s1.clone()

    s2.phase_state.captain_done.add(2)
    assert 2 not in s1.phase_state.captain_done

    s2.phase_state.order.append(99)
    assert s1.phase_state.order == [0, 1, 2, 3]

    s2.phase_state.sub["x"] = 42
    assert s1.phase_state.sub["x"] == 1


def test_clone_phase_state_sub_inner_sets_independent():
    """Regression: clone() must deep-copy the mutable VALUES inside sub.

    The captain phase stores ``wharf_used`` / ``first_load_done`` sets and the
    craftsman phase stores a ``chooser_kinds`` set in sub. A shallow
    ``dict(ps.sub)`` copies the outer dict but leaves these inner sets shared,
    so mutating the clone corrupts the original (silently breaks MCTS/RL
    rollouts that clone the state).
    """
    s1 = make_state()
    s1.phase_state.sub = {
        "wharf_used": {1},
        "first_load_done": set(),
        "chooser_kinds": {Good.CORN},
    }
    s2 = s1.clone()

    # The set objects must be distinct, not shared by reference.
    assert s2.phase_state.sub["wharf_used"] is not s1.phase_state.sub["wharf_used"]
    assert (
        s2.phase_state.sub["first_load_done"]
        is not s1.phase_state.sub["first_load_done"]
    )
    assert (
        s2.phase_state.sub["chooser_kinds"] is not s1.phase_state.sub["chooser_kinds"]
    )

    # Mutating the clone's inner sets must not touch the original.
    s2.phase_state.sub["wharf_used"].add(2)
    s2.phase_state.sub["first_load_done"].add(0)
    s2.phase_state.sub["chooser_kinds"].add(Good.SUGAR)

    assert s1.phase_state.sub["wharf_used"] == {1}
    assert s1.phase_state.sub["first_load_done"] == set()
    assert s1.phase_state.sub["chooser_kinds"] == {Good.CORN}


def test_clone_config_shared():
    s1 = make_state()
    s2 = s1.clone()
    # config is frozen/immutable -> shared by reference is intentional
    assert s2.config is s1.config


def test_clone_rng_forked_identical_then_diverges():
    s1 = make_state()
    s2 = s1.clone()

    # Distinct objects.
    assert s2.rng is not s1.rng

    # Forked identically: same next value at clone time.
    assert s2.rng.random() == s1.rng.random()

    # Independent: advancing one does not advance the other.
    s2.rng.random()
    s2.rng.random()
    # s1 is one draw behind s2 now; their next draws differ.
    assert s1.rng.random() != s2.rng.random()
