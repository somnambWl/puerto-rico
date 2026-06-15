"""Tests for the CRAFTSMAN phase (phases-task-05).

Covers: deterministic production (corn needs no building; non-corn needs BOTH a
manned plantation AND a manned production-building circle; output is the min of
the two and the remaining supply), goods-supply caps, the factory
CRAFTSMAN_PRODUCE hook firing with the distinct produced kinds, the chooser's
single privilege-pick decision node (CHOOSE per produced kind with supply, plus
PASS; nothing-produced => PASS only), and that non-choosers get no decision.
"""

from __future__ import annotations

from puerto_rico.engine import buildings
from puerto_rico.engine.actions import Action
from puerto_rico.engine.buildings import Timing
from puerto_rico.engine.enums import (
    BuildingId,
    DecisionType,
    Good,
    Phase,
    Role,
    TileType,
)
from puerto_rico.engine.game import Game
from puerto_rico.engine.state import GameConfig


def _new_game(num_players: int = 4, seed: int = 0) -> Game:
    return Game(GameConfig(num_players=num_players, seed=seed))


def _clear_island(player) -> None:
    for slot in player.island:
        slot.tile = TileType.EMPTY
        slot.colonist = False


def _clear_city(player) -> None:
    for slot in player.city:
        slot.building = None
        slot.colonists = 0


def _give_plantations(player, tile: TileType, n: int, occupied: int) -> None:
    """Place ``n`` plantations of ``tile``, ``occupied`` of them manned.

    Fills empty island slots from the front; never disturbs existing tiles.
    """
    placed = 0
    for slot in player.island:
        if placed >= n:
            break
        if slot.tile == TileType.EMPTY:
            slot.tile = tile
            slot.colonist = placed < occupied
            placed += 1


def _give_building(player, bid: BuildingId, colonists: int) -> None:
    """Place ``bid`` into the lowest empty city slot, manned with ``colonists``."""
    for slot in player.city:
        if slot.building is None:
            slot.building = bid
            slot.colonists = colonists
            return


def _clear_all(g: Game) -> None:
    for p in g.state.players:
        _clear_island(p)
        _clear_city(p)


def _enter_craftsman(g: Game) -> None:
    """Select CRAFTSMAN so production runs and the engine parks at the pick."""
    g.apply(Action.select_role(Role.CRAFTSMAN))
    assert g.state.phase == Phase.CRAFTSMAN


# --------------------------------------------------------------------------- #
# production                                                                   #
# --------------------------------------------------------------------------- #


def test_corn_needs_no_building():
    g = _new_game()
    _clear_all(g)
    chooser = g.state.phase_state.role_chooser
    p = g.state.players[chooser]
    _give_plantations(p, TileType.CORN, n=2, occupied=2)
    _enter_craftsman(g)
    assert p.goods[Good.CORN] == 2


def test_unmanned_corn_plantation_does_not_produce():
    g = _new_game()
    _clear_all(g)
    chooser = g.state.phase_state.role_chooser
    p = g.state.players[chooser]
    _give_plantations(p, TileType.CORN, n=2, occupied=1)
    _enter_craftsman(g)
    assert p.goods[Good.CORN] == 1


def test_noncorn_needs_plantation_and_building():
    g = _new_game()
    _clear_all(g)
    chooser = g.state.phase_state.role_chooser
    p = g.state.players[chooser]
    # Manned indigo plantation but NO indigo building -> 0 indigo.
    _give_plantations(p, TileType.INDIGO, n=2, occupied=2)
    _enter_craftsman(g)
    assert p.goods[Good.INDIGO] == 0


def test_noncorn_needs_manned_plantation_with_building():
    g = _new_game()
    _clear_all(g)
    chooser = g.state.phase_state.role_chooser
    p = g.state.players[chooser]
    # Manned indigo building but NO manned plantation -> 0 indigo.
    _give_building(p, BuildingId.SMALL_INDIGO, colonists=1)
    _give_plantations(p, TileType.INDIGO, n=1, occupied=0)
    _enter_craftsman(g)
    assert p.goods[Good.INDIGO] == 0


def test_noncorn_output_is_min_of_plantations_and_circles():
    g = _new_game()
    _clear_all(g)
    chooser = g.state.phase_state.role_chooser
    p = g.state.players[chooser]
    # 3 manned indigo plantations, but only a 1-circle small indigo plant manned.
    _give_plantations(p, TileType.INDIGO, n=3, occupied=3)
    _give_building(p, BuildingId.SMALL_INDIGO, colonists=1)
    _enter_craftsman(g)
    assert p.goods[Good.INDIGO] == 1  # limited by the single manned circle


def test_noncorn_output_limited_by_plantations():
    g = _new_game()
    _clear_all(g)
    chooser = g.state.phase_state.role_chooser
    p = g.state.players[chooser]
    # Large indigo plant (3 circles) all manned, but only 2 manned plantations.
    _give_building(p, BuildingId.INDIGO_PLANT, colonists=3)
    _give_plantations(p, TileType.INDIGO, n=2, occupied=2)
    _enter_craftsman(g)
    assert p.goods[Good.INDIGO] == 2  # limited by the 2 plantations


def test_supply_cap_limits_production():
    g = _new_game()
    _clear_all(g)
    chooser = g.state.phase_state.role_chooser
    p = g.state.players[chooser]
    _give_plantations(p, TileType.CORN, n=4, occupied=4)
    g.state.goods_supply[Good.CORN] = 3
    _enter_craftsman(g)
    assert p.goods[Good.CORN] == 3
    assert g.state.goods_supply[Good.CORN] == 0


# --------------------------------------------------------------------------- #
# factory hook                                                                 #
# --------------------------------------------------------------------------- #


def test_factory_hook_fires_with_distinct_kinds(monkeypatch):
    g = _new_game()
    _clear_all(g)
    chooser = g.state.phase_state.role_chooser
    p = g.state.players[chooser]
    # Produce corn (1) + indigo (1) => 2 distinct kinds.
    _give_plantations(p, TileType.CORN, n=1, occupied=1)
    _give_plantations(p, TileType.INDIGO, n=1, occupied=1)
    _give_building(p, BuildingId.SMALL_INDIGO, colonists=1)
    # Occupied factory so fire() reaches the handler (occupancy-gated).
    _give_building(p, BuildingId.FACTORY, colonists=1)

    seen = {}

    def _spy(state, player_idx, ctx):
        if player_idx == chooser:
            seen["kinds"] = set(ctx.kinds)

    monkeypatch.setitem(
        buildings.HANDLERS, (BuildingId.FACTORY, Timing.CRAFTSMAN_PRODUCE), _spy
    )

    _enter_craftsman(g)
    assert seen["kinds"] == {Good.CORN, Good.INDIGO}


def test_factory_hook_does_not_error_without_handler():
    g = _new_game()
    _clear_all(g)
    chooser = g.state.phase_state.role_chooser
    p = g.state.players[chooser]
    _give_plantations(p, TileType.CORN, n=1, occupied=1)
    _give_building(p, BuildingId.FACTORY, colonists=1)
    # No handler registered -> fire() is a silent no-op; must not raise.
    _enter_craftsman(g)
    assert p.goods[Good.CORN] == 1


# --------------------------------------------------------------------------- #
# chooser privilege                                                            #
# --------------------------------------------------------------------------- #


def test_chooser_sees_choose_per_produced_kind():
    g = _new_game()
    _clear_all(g)
    chooser = g.state.phase_state.role_chooser
    p = g.state.players[chooser]
    _give_plantations(p, TileType.CORN, n=1, occupied=1)
    _give_plantations(p, TileType.INDIGO, n=1, occupied=1)
    _give_building(p, BuildingId.SMALL_INDIGO, colonists=1)
    _enter_craftsman(g)

    actions = g.legal_actions()
    choose_goods = {a.good for a in actions if a.type == DecisionType.CHOOSE}
    assert choose_goods == {Good.CORN, Good.INDIGO}
    assert Action.passing() in actions
    assert g.state.current_player == chooser


def test_chooser_privilege_gives_one_extra_good():
    g = _new_game()
    _clear_all(g)
    chooser = g.state.phase_state.role_chooser
    p = g.state.players[chooser]
    _give_plantations(p, TileType.CORN, n=1, occupied=1)
    _enter_craftsman(g)
    assert p.goods[Good.CORN] == 1
    before_supply = g.state.goods_supply[Good.CORN]

    g.apply(Action(DecisionType.CHOOSE, good=Good.CORN))
    assert p.goods[Good.CORN] == 2
    assert g.state.goods_supply[Good.CORN] == before_supply - 1
    # The single decision node ended the role -> back to selection.
    assert g.state.phase == Phase.ROLE_SELECTION


def test_choose_unavailable_when_supply_empty():
    g = _new_game()
    _clear_all(g)
    chooser = g.state.phase_state.role_chooser
    p = g.state.players[chooser]
    _give_plantations(p, TileType.CORN, n=1, occupied=1)
    # Drain corn supply so production gets 0 and no CHOOSE is offered for it.
    g.state.goods_supply[Good.CORN] = 0
    _enter_craftsman(g)
    actions = g.legal_actions()
    assert all(a.type == DecisionType.PASS for a in actions)


def test_chooser_with_no_production_sees_only_pass():
    g = _new_game()
    _clear_all(g)
    _enter_craftsman(g)
    actions = g.legal_actions()
    assert actions == [Action.passing()]


def test_chooser_pass_ends_role():
    g = _new_game()
    _clear_all(g)
    _enter_craftsman(g)
    g.apply(Action.passing())
    assert g.state.phase == Phase.ROLE_SELECTION


# --------------------------------------------------------------------------- #
# non-choosers get no decision node                                           #
# --------------------------------------------------------------------------- #


def test_nonchoosers_produce_but_have_no_decision():
    g = _new_game()
    _clear_all(g)
    chooser = g.state.phase_state.role_chooser
    other = (chooser + 1) % 4
    po = g.state.players[other]
    _give_plantations(po, TileType.CORN, n=2, occupied=2)
    _enter_craftsman(g)
    # Non-chooser's production was auto-applied at phase entry.
    assert po.goods[Good.CORN] == 2
    # The only decision node is the chooser's; current player is the chooser.
    assert g.state.current_player == chooser
    # Chooser produced nothing -> only PASS, and applying it ends the role with
    # no further (non-chooser) decision nodes.
    assert g.legal_actions() == [Action.passing()]
    g.apply(Action.passing())
    assert g.state.phase == Phase.ROLE_SELECTION
