"""Tests for the MAYOR phase (phases-task-03).

Covers: phase-entry distribution (privilege colonist + round-robin ship deal into
``stored_colonists``), the placement sub-phase (empty-circle PLACE_COLONIST
actions, building/plantation manning, STORE only when no circle remains, the lift
/ rearrange model) and the chooser's last-duty ship refill including the
colonist-shortage end trigger.
"""

from __future__ import annotations

from puerto_rico.engine.actions import Action
from puerto_rico.engine.enums import BuildingId, DecisionType, Phase, Role, TileType
from puerto_rico.engine.game import Game
from puerto_rico.engine.phases import MAYOR_STORE, mayor_last_duty
from puerto_rico.engine.state import GameConfig


def _new_game(num_players: int = 4, seed: int = 0) -> Game:
    return Game(GameConfig(num_players=num_players, seed=seed))


def _enter_mayor(g: Game) -> None:
    g.apply(Action.select_role(Role.MAYOR))
    assert g.state.phase == Phase.MAYOR


# --------------------------------------------------------------------------- #
# phase entry / distribution                                                  #
# --------------------------------------------------------------------------- #


def test_chooser_gets_privilege_colonist():
    g = _new_game()
    chooser = g.state.phase_state.role_chooser
    g.state.colonist_ship = 0
    g.state.colonist_supply = 10
    before = g.state.players[chooser].stored_colonists

    _enter_mayor(g)

    assert g.state.players[chooser].stored_colonists == before + 1
    assert g.state.colonist_supply == 9


def test_privilege_skipped_when_supply_empty():
    g = _new_game()
    chooser = g.state.phase_state.role_chooser
    g.state.colonist_ship = 0
    g.state.colonist_supply = 0
    before = g.state.players[chooser].stored_colonists

    _enter_mayor(g)

    assert g.state.players[chooser].stored_colonists == before


def test_ship_distributed_round_robin_from_chooser():
    g = _new_game(num_players=4)
    chooser = g.state.phase_state.role_chooser
    g.state.colonist_supply = 0  # isolate from the privilege
    g.state.colonist_ship = 6
    stored_before = [p.stored_colonists for p in g.state.players]

    _enter_mayor(g)

    # 6 colonists, 4 players, chooser first clockwise: chooser & next get 2, rest 1.
    n = 4
    expected = [0, 0, 0, 0]
    for i in range(6):
        expected[(chooser + i) % n] += 1
    for seat in range(n):
        gained = g.state.players[seat].stored_colonists - stored_before[seat]
        assert gained == expected[seat]
    assert g.state.colonist_ship == 0


# --------------------------------------------------------------------------- #
# placement sub-phase                                                         #
# --------------------------------------------------------------------------- #


def test_place_colonist_actions_for_empty_circles():
    g = _new_game()
    chooser = g.state.phase_state.role_chooser
    g.state.colonist_ship = 0
    g.state.colonist_supply = 0
    # Give the chooser a building circle and an unmanned plantation before entry.
    p = g.state.players[chooser]
    p.city[0].building = BuildingId.INDIGO_PLANT  # capacity 3
    p.city[0].colonists = 0
    p.island[0].tile = TileType.CORN
    p.island[0].colonist = False
    p.stored_colonists = 1  # supply is 0, so no privilege; one to place

    _enter_mayor(g)
    assert g.current_player == chooser
    assert g.state.players[chooser].stored_colonists == 1

    actions = g.legal_actions()
    assert all(a.type == DecisionType.PLACE_COLONIST for a in actions)
    targets = {a.target for a in actions}
    assert 0 in targets  # the building circle (city slot 0)
    assert 100 in targets  # the island plantation (offset 100 + slot 0)
    assert MAYOR_STORE not in targets


def test_place_fills_building_circle():
    g = _new_game()
    chooser = g.state.phase_state.role_chooser
    g.state.colonist_ship = 0
    g.state.colonist_supply = 0
    p = g.state.players[chooser]
    p.city[0].building = BuildingId.INDIGO_PLANT
    p.city[0].colonists = 0
    p.stored_colonists = 1  # supply 0 -> no privilege; one to place

    _enter_mayor(g)
    g.apply(Action.place_colonist(0))

    assert g.state.players[chooser].city[0].colonists == 1
    assert g.state.players[chooser].stored_colonists == 0


def test_place_mans_plantation():
    g = _new_game()
    chooser = g.state.phase_state.role_chooser
    g.state.colonist_ship = 0
    g.state.colonist_supply = 0
    p = g.state.players[chooser]
    p.island[5].tile = TileType.SUGAR
    p.island[5].colonist = False
    p.stored_colonists = 1  # supply 0 -> no privilege; one to place

    _enter_mayor(g)
    g.apply(Action.place_colonist(105))

    assert g.state.players[chooser].island[5].colonist is True


def test_store_only_offered_when_no_empty_circle():
    g = _new_game()
    chooser = g.state.phase_state.role_chooser
    g.state.colonist_ship = 0
    g.state.colonist_supply = 0
    p = g.state.players[chooser]
    # Player has colonists but no buildings and no tiles -> nowhere to place.
    for slot in p.island:
        slot.tile = TileType.EMPTY
        slot.colonist = False
    for slot in p.city:
        slot.building = None
        slot.colonists = 0
    p.stored_colonists = 2

    _enter_mayor(g)
    actions = g.legal_actions()
    assert actions == [Action.place_colonist(MAYOR_STORE)]


def test_lift_rearranges_existing_colonists():
    g = _new_game()
    chooser = g.state.phase_state.role_chooser
    g.state.colonist_ship = 0
    g.state.colonist_supply = 0
    p = g.state.players[chooser]
    # Pre-place a colonist on a building; at turn start it must be lifted to store.
    p.city[0].building = BuildingId.INDIGO_PLANT
    p.city[0].colonists = 1
    p.island[0].tile = TileType.CORN
    p.island[0].colonist = True
    p.stored_colonists = 0  # supply 0 -> no privilege

    _enter_mayor(g)

    # Lifted: 1 (building) + 1 (island) = 2 stored, board empty.
    assert g.state.players[chooser].stored_colonists == 2
    assert g.state.players[chooser].city[0].colonists == 0
    assert g.state.players[chooser].island[0].colonist is False


def test_store_ends_turn_and_advances():
    g = _new_game(num_players=4)
    chooser = g.state.phase_state.role_chooser
    g.state.colonist_ship = 0
    g.state.colonist_supply = 0
    # No one has anywhere to place; each will be offered STORE only.
    _enter_mayor(g)

    for _ in range(4):
        assert g.state.phase == Phase.MAYOR
        assert g.legal_actions() == [Action.place_colonist(MAYOR_STORE)]
        g.apply(Action.place_colonist(MAYOR_STORE))

    # After all four store, the role ends and we return to selection.
    assert g.state.phase == Phase.ROLE_SELECTION


# --------------------------------------------------------------------------- #
# last duty                                                                   #
# --------------------------------------------------------------------------- #


def test_last_duty_refills_ship_to_empty_building_circles():
    g = _new_game(num_players=4)
    _enter_mayor(g)
    g.state.colonist_ship = 0
    g.state.colonist_supply = 50

    # Give one player two empty building circles (indigo plant capacity 3, 1 manned).
    p = g.state.players[0]
    p.city[0].building = BuildingId.INDIGO_PLANT
    p.city[0].colonists = 1  # 2 empty circles
    # Plantations must NOT count.
    p.island[0].tile = TileType.CORN
    p.island[0].colonist = False

    before_supply = g.state.colonist_supply
    mayor_last_duty(g.state)

    # max(num_players=4, empty_building_circles=2) = 4.
    assert g.state.colonist_ship == 4
    assert g.state.colonist_supply == before_supply - 4
    assert g.state.end_triggered is False


def test_last_duty_uses_empty_circles_when_above_num_players():
    g = _new_game(num_players=2)
    _enter_mayor(g)
    g.state.colonist_ship = 0
    g.state.colonist_supply = 50

    p = g.state.players[0]
    p.city[0].building = BuildingId.INDIGO_PLANT  # capacity 3, 0 manned -> 3
    p.city[0].colonists = 0
    p.city[2].building = BuildingId.SUGAR_MILL  # capacity 3, 0 manned -> 3
    p.city[2].colonists = 0

    mayor_last_duty(g.state)

    # 6 empty circles > num_players(2) -> refill 6.
    assert g.state.colonist_ship == 6


def test_last_duty_shortage_sets_end_triggered():
    g = _new_game(num_players=4)
    _enter_mayor(g)
    g.state.colonist_ship = 0
    g.state.colonist_supply = 2  # fewer than required (>= num_players = 4)

    mayor_last_duty(g.state)

    assert g.state.colonist_ship == 2
    assert g.state.colonist_supply == 0
    assert g.state.end_triggered is True
