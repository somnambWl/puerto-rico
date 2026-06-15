"""Tests for the TRADER phase (phases-task-06).

Covers: legality (sell a held good when the house has room and the kind is not a
duplicate; the duplicate-kind block without an office; the office exception;
the 4-good-full house blocks all sales; PASS always legal), price (base by kind
plus the chooser privilege; market bonuses are exercised in buildings-04), apply
(good moves player -> house, seller paid, supply untouched until the clear), and
the last duty (a full house clears to supply; a partial house carries over).
"""

from __future__ import annotations

from puerto_rico.engine import buildings
from puerto_rico.engine.actions import Action
from puerto_rico.engine.enums import BuildingId, DecisionType, Good, Phase, Role
from puerto_rico.engine.game import Game
from puerto_rico.engine.phases import _trader_sale_price, trader_last_duty
from puerto_rico.engine.state import GameConfig


def _new_game(num_players: int = 4, seed: int = 0) -> Game:
    return Game(GameConfig(num_players=num_players, seed=seed))


def _enter_trader(g: Game) -> None:
    """Select TRADER so the engine enters Phase.TRADER at the chooser's turn."""
    g.apply(Action.select_role(Role.TRADER))
    assert g.state.phase == Phase.TRADER


def _clear_goods(player) -> None:
    for i in range(len(player.goods)):
        player.goods[i] = 0


def _give_building(player, bid: BuildingId, colonists: int) -> None:
    """Place ``bid`` into the lowest empty city slot, manned with ``colonists``."""
    for slot in player.city:
        if slot.building is None:
            slot.building = bid
            slot.colonists = colonists
            return


def _sell_goods(g: Game):
    return [a.good for a in g.legal_actions() if a.type == DecisionType.SELL]


# --------------------------------------------------------------------------- #
# legality                                                                     #
# --------------------------------------------------------------------------- #


def test_can_sell_held_good_house_has_room():
    g = _new_game()
    _enter_trader(g)
    chooser = g.state.phase_state.role_chooser
    p = g.state.players[chooser]
    _clear_goods(p)
    p.goods[Good.SUGAR] = 1
    assert Good.SUGAR in _sell_goods(g)
    # A good the player does not hold is not sellable.
    assert Good.COFFEE not in _sell_goods(g)


def test_pass_always_legal():
    g = _new_game()
    _enter_trader(g)
    p = g.state.players[g.state.phase_state.role_chooser]
    _clear_goods(p)  # nothing to sell at all
    actions = g.legal_actions()
    assert any(a.type == DecisionType.PASS for a in actions)


def test_duplicate_kind_blocked_without_office():
    g = _new_game()
    _enter_trader(g)
    p = g.state.players[g.state.phase_state.role_chooser]
    _clear_goods(p)
    p.goods[Good.INDIGO] = 1
    g.state.trading_house.append(Good.INDIGO)  # same kind already in the house
    assert Good.INDIGO not in _sell_goods(g)


def test_duplicate_kind_allowed_with_occupied_office():
    g = _new_game()
    _enter_trader(g)
    p = g.state.players[g.state.phase_state.role_chooser]
    _clear_goods(p)
    p.goods[Good.INDIGO] = 1
    g.state.trading_house.append(Good.INDIGO)
    _give_building(p, BuildingId.OFFICE, colonists=1)  # occupied office
    assert Good.INDIGO in _sell_goods(g)


def test_full_house_blocks_all_sales():
    g = _new_game()
    _enter_trader(g)
    p = g.state.players[g.state.phase_state.role_chooser]
    _clear_goods(p)
    p.goods[Good.CORN] = 1
    # House full (4 goods) -> no SELL even for a fresh kind; only PASS.
    g.state.trading_house.extend(
        [Good.INDIGO, Good.SUGAR, Good.TOBACCO, Good.COFFEE]
    )
    assert _sell_goods(g) == []
    assert g.legal_actions() == [Action.passing()]


# --------------------------------------------------------------------------- #
# price                                                                        #
# --------------------------------------------------------------------------- #


def test_base_prices_by_kind():
    g = _new_game()
    _enter_trader(g)
    chooser = g.state.phase_state.role_chooser
    other = (chooser + 1) % 4  # a non-chooser: no privilege, no markets
    expected = {Good.CORN: 0, Good.INDIGO: 1, Good.SUGAR: 2, Good.TOBACCO: 3, Good.COFFEE: 4}
    for good, base in expected.items():
        assert _trader_sale_price(g.state, other, good) == base


def test_chooser_privilege_adds_one():
    g = _new_game()
    _enter_trader(g)
    chooser = g.state.phase_state.role_chooser
    # Chooser sells coffee: base 4 + privilege 1 = 5 (markets are 0 here).
    assert _trader_sale_price(g.state, chooser, Good.COFFEE) == 5
    # Corn for the chooser: base 0 + privilege 1 = 1.
    assert _trader_sale_price(g.state, chooser, Good.CORN) == 1
    # Market stacking (small +1, large +2) is covered in the buildings-04 tests;
    # those handlers are not registered here, so the bonus is 0.


# --------------------------------------------------------------------------- #
# apply                                                                        #
# --------------------------------------------------------------------------- #


def test_apply_sell_moves_good_pays_seller_supply_untouched():
    g = _new_game()
    _enter_trader(g)
    chooser = g.state.phase_state.role_chooser
    p = g.state.players[chooser]
    _clear_goods(p)
    p.goods[Good.TOBACCO] = 1
    before_doubloons = p.doubloons
    supply_before = list(g.state.goods_supply)

    g.apply(Action.sell(Good.TOBACCO))

    assert p.goods[Good.TOBACCO] == 0  # good left the player
    assert Good.TOBACCO in g.state.trading_house  # ... and entered the house
    # Chooser sells tobacco: base 3 + privilege 1 = 4 doubloons from the bank.
    assert p.doubloons == before_doubloons + 4
    # Supply is unaffected until the house is cleared in the last duty.
    assert list(g.state.goods_supply) == supply_before


# --------------------------------------------------------------------------- #
# last duty                                                                    #
# --------------------------------------------------------------------------- #


def test_last_duty_full_house_clears_to_supply():
    g = _new_game()
    _enter_trader(g)
    g.state.trading_house = [Good.CORN, Good.INDIGO, Good.SUGAR, Good.TOBACCO]
    supply_before = list(g.state.goods_supply)

    trader_last_duty(g.state)

    assert g.state.trading_house == []  # full house cleared
    for good in (Good.CORN, Good.INDIGO, Good.SUGAR, Good.TOBACCO):
        assert g.state.goods_supply[good] == supply_before[good] + 1
    assert g.state.goods_supply[Good.COFFEE] == supply_before[Good.COFFEE]


def test_last_duty_partial_house_carries_over():
    g = _new_game()
    _enter_trader(g)
    g.state.trading_house = [Good.CORN, Good.INDIGO, Good.SUGAR]  # only 3
    supply_before = list(g.state.goods_supply)

    trader_last_duty(g.state)

    assert g.state.trading_house == [Good.CORN, Good.INDIGO, Good.SUGAR]
    assert list(g.state.goods_supply) == supply_before  # nothing returned
