"""Tests for engine setup / initialization (``new_game``)."""

from __future__ import annotations

from .enums import BuildingId, Good, Phase, Role, TileType
from .setup import building_supply_for, new_game
from .state import GameConfig


def test_4player_initial_state() -> None:
    state = new_game(GameConfig(num_players=4, seed=0))

    # Player count and per-player doubloons.
    assert len(state.players) == 4
    for p in state.players:
        assert p.doubloons == 3
        assert p.stored_colonists == 0
        assert p.vp_chips == 0
        assert len(p.island) == 12
        assert len(p.city) == 12
        assert p.goods == [0, 0, 0, 0, 0]
        # No buildings, no colonists placed yet.
        assert all(c.building is None and c.colonists == 0 for c in p.city)

    # Supplies and pools.
    assert state.vp_chips_remaining == 100
    assert state.colonist_supply == 75
    assert state.colonist_ship == 4
    assert state.quarry_supply == 8

    # Cargo ship capacities.
    assert [c.capacity for c in state.cargo_ships] == [5, 6, 7]
    assert all(c.good is None and c.count == 0 for c in state.cargo_ships)

    # Role placards: 7, one per Role, unclaimed with 0 doubloons.
    assert len(state.placards) == 7
    assert {pl.role for pl in state.placards} == set(Role)
    assert all(pl.taken_by is None and pl.doubloons == 0 for pl in state.placards)

    # Face-up plantation row: 5 tiles.
    assert len(state.plantation_faceup) == 5

    # Plantation deck: full base counts (8+9+10+11+12 = 50), minus 5 dealt
    # face-up, all from the same deck; starting tiles do NOT come from the deck.
    all_deck = state.plantation_faceup + state.plantation_facedown
    assert len(all_deck) == 50
    assert len(state.plantation_facedown) == 45
    assert state.plantation_discard == []
    expected = {
        TileType.COFFEE: 8,
        TileType.TOBACCO: 9,
        TileType.CORN: 10,
        TileType.SUGAR: 11,
        TileType.INDIGO: 12,
    }
    for tile, count in expected.items():
        assert all_deck.count(tile) == count

    # Goods supply, indexed by Good.
    assert state.goods_supply[Good.CORN] == 10
    assert state.goods_supply[Good.SUGAR] == 11
    assert state.goods_supply[Good.INDIGO] == 11
    assert state.goods_supply[Good.TOBACCO] == 9
    assert state.goods_supply[Good.COFFEE] == 9

    # Building supply (3-5p standard counts): 2 of each small violet, 1 of each
    # large violet, interim production counts.
    bs = state.buildings_supply
    assert bs[BuildingId.HOSPICE] == 2
    assert bs[BuildingId.HARBOR] == 2
    assert bs[BuildingId.GUILD_HALL] == 1
    assert bs[BuildingId.CITY_HALL] == 1
    assert bs[BuildingId.SMALL_INDIGO] == 4
    assert bs[BuildingId.SUGAR_MILL] == 3

    # Trading house empty.
    assert state.trading_house == []

    # Starting island tiles: players 0,1 -> INDIGO; players 2,3 -> CORN.
    def starting_tiles(p) -> list[TileType]:
        return [sl.tile for sl in p.island if sl.tile != TileType.EMPTY]

    assert starting_tiles(state.players[0]) == [TileType.INDIGO]
    assert starting_tiles(state.players[1]) == [TileType.INDIGO]
    assert starting_tiles(state.players[2]) == [TileType.CORN]
    assert starting_tiles(state.players[3]) == [TileType.CORN]
    # Starting tiles carry no colonist at game start.
    for p in state.players:
        assert all(not sl.colonist for sl in p.island)

    # Turn/phase cursor.
    assert state.governor == 0
    assert state.current_player == 0
    assert state.phase == Phase.ROLE_SELECTION
    assert state.end_triggered is False


def test_determinism_same_seed_identical_faceup() -> None:
    a = new_game(GameConfig(num_players=4, seed=42))
    b = new_game(GameConfig(num_players=4, seed=42))
    assert a.plantation_faceup == b.plantation_faceup
    assert a.plantation_facedown == b.plantation_facedown


def test_building_supply_for_2player_reduced() -> None:
    # 2-player variant: 1 of each beige (small AND large), 2 of each production.
    supply = building_supply_for(2)
    assert supply[BuildingId.HOSPICE] == 1
    assert supply[BuildingId.GUILD_HALL] == 1
    assert supply[BuildingId.SMALL_INDIGO] == 2
    assert supply[BuildingId.SUGAR_MILL] == 2
    # And new_game(2p) uses it.
    state = new_game(GameConfig(num_players=2, seed=0))
    assert state.buildings_supply[BuildingId.HOSPICE] == 1


def test_determinism_different_seeds_generally_differ() -> None:
    rows = [
        new_game(GameConfig(num_players=4, seed=s)).plantation_faceup
        for s in range(8)
    ]
    # With 8 distinct seeds, at least one face-up row should differ from seed 0.
    assert any(row != rows[0] for row in rows[1:])
