"""Tests for the BUILDER phase (phases-task-04).

Covers: cost computation (chooser privilege, quarry discount capped by the
building column, floor at 0, affordability gating), legality (no duplicates, no
out-of-supply, large-building 2-adjacent-slot requirement, PASS always legal),
apply (pay cost, decrement supply, lowest-slot placement, large LARGE_CONT
sentinel), the 12th-building end trigger, and that the BUILDER_BUILD hook fires.
"""

from __future__ import annotations

from puerto_rico.engine import buildings
from puerto_rico.engine.actions import Action
from puerto_rico.engine.buildings import Timing
from puerto_rico.engine.enums import BuildingId, DecisionType, Phase, Role, TileType
from puerto_rico.engine.game import Game
from puerto_rico.engine.phases import _build_cost
from puerto_rico.engine.state import GameConfig


def _new_game(num_players: int = 4, seed: int = 0) -> Game:
    return Game(GameConfig(num_players=num_players, seed=seed))


def _enter_builder(g: Game) -> None:
    """Select BUILDER so the engine enters Phase.BUILDER at the chooser's turn."""
    g.apply(Action.select_role(Role.BUILDER))
    assert g.state.phase == Phase.BUILDER


def _give_quarries(player, n: int, occupied: int) -> None:
    """Place ``n`` quarry tiles on the island, ``occupied`` of them manned."""
    for i in range(n):
        player.island[i].tile = TileType.QUARRY
        player.island[i].colonist = i < occupied


def _clear_city(player) -> None:
    for slot in player.city:
        slot.building = None
        slot.colonists = 0


# --------------------------------------------------------------------------- #
# cost                                                                         #
# --------------------------------------------------------------------------- #


def test_chooser_privilege_reduces_cost_by_one():
    g = _new_game()
    _enter_builder(g)
    chooser = g.state.phase_state.role_chooser
    other = (chooser + 1) % 4
    # OFFICE: printed cost 5, no quarries.
    assert _build_cost(g.state, chooser, BuildingId.OFFICE) == 4
    assert _build_cost(g.state, other, BuildingId.OFFICE) == 5


def test_quarry_discount_capped_by_column():
    g = _new_game()
    _enter_builder(g)
    other = (g.state.phase_state.role_chooser + 1) % 4
    p = g.state.players[other]
    _give_quarries(p, n=3, occupied=3)
    # CONSTRUCTION_HUT cost 2, column 1 -> discount capped at 1 -> cost 1.
    assert _build_cost(g.state, other, BuildingId.CONSTRUCTION_HUT) == 1
    # OFFICE cost 5, column 2 -> discount capped at 2 -> cost 3.
    assert _build_cost(g.state, other, BuildingId.OFFICE) == 3
    # HARBOR cost 8, column 3 -> 3 occupied quarries -> cost 5.
    assert _build_cost(g.state, other, BuildingId.HARBOR) == 5


def test_only_occupied_quarries_discount():
    g = _new_game()
    _enter_builder(g)
    other = (g.state.phase_state.role_chooser + 1) % 4
    p = g.state.players[other]
    _give_quarries(p, n=3, occupied=1)  # 3 quarries, only 1 manned
    # OFFICE cost 5, column 2, but only 1 occupied quarry -> cost 4.
    assert _build_cost(g.state, other, BuildingId.OFFICE) == 4


def test_cost_floors_at_zero():
    g = _new_game()
    _enter_builder(g)
    chooser = g.state.phase_state.role_chooser
    p = g.state.players[chooser]
    _give_quarries(p, n=4, occupied=4)
    # SMALL_INDIGO cost 1, column 1; chooser -1 and 1 quarry -> floors at 0.
    assert _build_cost(g.state, chooser, BuildingId.SMALL_INDIGO) == 0


def test_affordability_gates_legal_actions():
    g = _new_game()
    _enter_builder(g)
    chooser = g.state.phase_state.role_chooser
    p = g.state.players[chooser]
    p.doubloons = 0  # can only afford things that cost 0
    builds = {a.building for a in g.legal_actions() if a.type == DecisionType.BUILD}
    for bid in builds:
        assert _build_cost(g.state, chooser, bid) == 0


# --------------------------------------------------------------------------- #
# legality                                                                     #
# --------------------------------------------------------------------------- #


def test_pass_always_legal():
    g = _new_game()
    _enter_builder(g)
    assert Action.passing() in g.legal_actions()
    # Even with a full city and no doubloons, PASS remains.
    p = g.state.players[g.state.current_player]
    p.doubloons = 0
    for slot in p.city:
        slot.building = BuildingId.SMALL_INDIGO
    assert g.legal_actions() == [Action.passing()]


def test_cannot_build_already_owned():
    g = _new_game()
    _enter_builder(g)
    p = g.state.players[g.state.current_player]
    p.doubloons = 20
    p.city[0].building = BuildingId.OFFICE
    builds = {a.building for a in g.legal_actions() if a.type == DecisionType.BUILD}
    assert BuildingId.OFFICE not in builds


def test_cannot_build_out_of_supply():
    g = _new_game()
    _enter_builder(g)
    p = g.state.players[g.state.current_player]
    p.doubloons = 20
    g.state.buildings_supply[BuildingId.OFFICE] = 0
    builds = {a.building for a in g.legal_actions() if a.type == DecisionType.BUILD}
    assert BuildingId.OFFICE not in builds


def test_large_building_needs_two_adjacent_empty_slots():
    g = _new_game()
    _enter_builder(g)
    p = g.state.players[g.state.current_player]
    p.doubloons = 20
    # Fill the city so only NON-adjacent single empties remain: empty at 0 and 2.
    # Use the LARGE_CONT sentinel as filler so we don't make the player "own" any
    # real building (which would itself gate it out of the legal set).
    for i in range(len(p.city)):
        p.city[i].building = BuildingId.LARGE_CONT
    p.city[0].building = None
    p.city[2].building = None
    builds = {a.building for a in g.legal_actions() if a.type == DecisionType.BUILD}
    # No large building is buildable (no adjacent pair), but a small one is.
    assert BuildingId.GUILD_HALL not in builds
    assert BuildingId.SMALL_INDIGO in builds  # fits the lone empty slot

    # Now open an adjacent pair (slots 0 and 1): the large building becomes legal.
    p.city[1].building = None
    builds = {a.building for a in g.legal_actions() if a.type == DecisionType.BUILD}
    assert BuildingId.GUILD_HALL in builds


# --------------------------------------------------------------------------- #
# apply                                                                        #
# --------------------------------------------------------------------------- #


def test_apply_build_pays_cost_decrements_supply_places_lowest_slot():
    g = _new_game()
    _enter_builder(g)
    chooser = g.state.current_player
    p = g.state.players[chooser]
    p.doubloons = 10
    _clear_city(p)
    supply_before = g.state.buildings_supply[BuildingId.OFFICE]

    g.apply(Action.build(BuildingId.OFFICE))

    # chooser pays 5 - 1 = 4.
    assert p.doubloons == 6
    assert g.state.buildings_supply[BuildingId.OFFICE] == supply_before - 1
    assert p.city[0].building == BuildingId.OFFICE
    assert p.city[0].colonists == 0


def test_apply_large_building_occupies_two_slots_with_sentinel():
    g = _new_game()
    _enter_builder(g)
    chooser = g.state.current_player
    p = g.state.players[chooser]
    p.doubloons = 20
    _clear_city(p)

    g.apply(Action.build(BuildingId.GUILD_HALL))

    assert p.city[0].building == BuildingId.GUILD_HALL
    assert p.city[1].building == BuildingId.LARGE_CONT
    assert p.city[0].colonists == 0
    assert p.city[1].colonists == 0
    # owns() finds the real building, never the continuation slot.
    assert p.owns(BuildingId.GUILD_HALL)


def test_apply_pass_advances_without_building():
    g = _new_game()
    _enter_builder(g)
    chooser = g.state.current_player
    before = g.state.players[chooser].doubloons
    g.apply(Action.passing())
    assert g.state.players[chooser].doubloons == before
    # Cursor advanced to the next player (still in the builder phase).
    assert g.state.phase == Phase.BUILDER
    assert g.state.current_player != chooser


# --------------------------------------------------------------------------- #
# 12th-building end trigger                                                    #
# --------------------------------------------------------------------------- #


def test_building_twelfth_space_sets_end_triggered():
    g = _new_game()
    _enter_builder(g)
    chooser = g.state.current_player
    p = g.state.players[chooser]
    p.doubloons = 20
    # Fill 11 slots; leave slot 11 empty for the final small build.
    for i in range(11):
        p.city[i].building = BuildingId.SMALL_INDIGO
    p.city[11].building = None

    assert not g.state.end_triggered
    g.apply(Action.build(BuildingId.OFFICE))
    assert p.city[11].building == BuildingId.OFFICE
    assert g.state.end_triggered


def test_building_non_final_space_does_not_set_end_triggered():
    g = _new_game()
    _enter_builder(g)
    p = g.state.players[g.state.current_player]
    p.doubloons = 20
    _clear_city(p)
    g.apply(Action.build(BuildingId.OFFICE))
    assert not g.state.end_triggered


# --------------------------------------------------------------------------- #
# BUILDER_BUILD hook fires                                                     #
# --------------------------------------------------------------------------- #


def test_builder_build_hook_fires_with_slot_and_building(monkeypatch):
    g = _new_game()
    _enter_builder(g)
    p = g.state.players[g.state.current_player]
    p.doubloons = 20
    _clear_city(p)
    # Give the player an occupied university so fire() actually reaches a handler
    # slot (occupancy-gated), and register a spy handler.
    p.city[5].building = BuildingId.UNIVERSITY
    p.city[5].colonists = 1

    seen = {}

    def _spy(state, player_idx, ctx):
        seen["building"] = ctx.building
        seen["slot"] = ctx.extra["slot"]

    monkeypatch.setitem(
        buildings.HANDLERS, (BuildingId.UNIVERSITY, Timing.BUILDER_BUILD), _spy
    )

    g.apply(Action.build(BuildingId.OFFICE))
    assert seen["building"] == BuildingId.OFFICE
    # OFFICE placed at lowest empty slot 0 (university sits at slot 5).
    assert seen["slot"] == 0
