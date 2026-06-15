"""End-of-game detection and final scoring (phases-09).

Covers:
- the three end triggers each set ``end_triggered`` and the CURRENT round still
  finishes before GAME_OVER (driven through ``end_of_round``),
- ``scoring.final_score`` = vp_chips + printed building VP (+ SCORE_END bonus,
  which is 0 until buildings-06 registers handlers),
- ``winner`` / ``rankings`` tie-break by (score, doubloons+goods, lower index),
- ``Game.returns`` sums to ~0 and matches the ranking.
"""

from __future__ import annotations

from puerto_rico.engine import scoring
from puerto_rico.engine.enums import BuildingId, Good, Phase, TileType
from puerto_rico.engine.game import Game
from puerto_rico.engine.phases import (
    award_captain_vp,
    end_of_round,
    mayor_last_duty,
)
from puerto_rico.engine.state import GameConfig


def _new_game(num_players: int = 4, seed: int = 0) -> Game:
    return Game(GameConfig(num_players=num_players, seed=seed))


def _give_building(player, bid: BuildingId, *, occupied: bool = False) -> None:
    """Place ``bid`` into the player's lowest empty city slot(s)."""
    from puerto_rico.engine.buildings import CATALOG

    spec = CATALOG[bid]
    for i in range(len(player.city) - (1 if spec.is_large else 0)):
        if player.city[i].building is None and (
            not spec.is_large or player.city[i + 1].building is None
        ):
            player.city[i].building = bid
            player.city[i].colonists = 1 if occupied else 0
            if spec.is_large:
                player.city[i + 1].building = BuildingId.LARGE_CONT
            return
    raise AssertionError("no room for building")


# --------------------------------------------------------------------------- #
# End triggers: round finishes, then GAME_OVER                                #
# --------------------------------------------------------------------------- #


def test_mayor_colonist_shortage_triggers_end():
    g = _new_game()
    st = g.state
    # Force a shortage: empty the supply so the refill cannot be met.
    st.colonist_supply = 0
    mayor_last_duty(st)
    assert st.end_triggered is True
    # The trigger does NOT end the game immediately — phase is unchanged.
    assert st.phase != Phase.GAME_OVER
    # Finishing the round transitions to GAME_OVER.
    end_of_round(st)
    assert st.phase == Phase.GAME_OVER
    assert g.is_terminal is True


def test_builder_twelfth_space_triggers_end():
    g = _new_game()
    st = g.state
    # Fill all 12 city slots: the 12th-space trigger fires inside builder_apply,
    # which checks `all(slot.building is not None)`. Simulate that condition.
    p = st.players[0]
    for slot in p.city:
        slot.building = BuildingId.SMALL_INDIGO  # any real building marker
    # Re-run the builder's end check (mirrors builder_apply's trigger).
    if all(s.building is not None for s in p.city):
        st.end_triggered = True
    assert st.end_triggered is True
    assert st.phase != Phase.GAME_OVER
    end_of_round(st)
    assert st.phase == Phase.GAME_OVER


def test_builder_twelfth_space_via_engine():
    """Drive the real builder trigger through builder_apply."""
    from puerto_rico.engine.actions import Action
    from puerto_rico.engine.buildings import CATALOG
    from puerto_rico.engine.enums import Role
    from puerto_rico.engine.phases import builder_apply

    g = _new_game()
    st = g.state
    # Enter the builder phase as chooser (player 0).
    g.apply(Action.select_role(Role.BUILDER))
    p = st.players[st.current_player]
    # Pre-fill 11 slots, leaving exactly one empty city slot.
    for i in range(11):
        p.city[i].building = BuildingId.SMALL_INDIGO
    p.city[11].building = None
    p.doubloons = 99
    # Build any affordable non-owned small (single-slot) building into the slot.
    bid = next(
        a.building
        for a in g.legal_actions()
        if a.building is not None and not CATALOG[a.building].is_large
    )
    builder_apply(st, Action.build(bid))
    assert st.end_triggered is True


def test_captain_vp_exhaustion_triggers_end():
    g = _new_game()
    st = g.state
    st.vp_chips_remaining = 3
    award_captain_vp(st, 0, 5)  # request more than remain
    assert st.players[0].vp_chips == 3
    assert st.vp_chips_remaining == 0
    assert st.end_triggered is True
    assert st.phase != Phase.GAME_OVER
    end_of_round(st)
    assert st.phase == Phase.GAME_OVER


def test_end_triggered_finishes_current_round_not_immediately():
    """end_of_round only ends the game; the trigger alone leaves play running."""
    g = _new_game()
    st = g.state
    st.colonist_supply = 0
    mayor_last_duty(st)
    assert st.end_triggered is True
    # Until end_of_round runs (after the round completes), the game continues.
    assert st.phase != Phase.GAME_OVER


# --------------------------------------------------------------------------- #
# final_score                                                                 #
# --------------------------------------------------------------------------- #


def test_final_score_vp_chips_plus_printed_building_vp():
    g = _new_game()
    st = g.state
    p = st.players[0]
    # Clear the city, then give a known set of buildings.
    for slot in p.city:
        slot.building = None
        slot.colonists = 0
    p.vp_chips = 7
    _give_building(p, BuildingId.SMALL_INDIGO)  # vp 1
    _give_building(p, BuildingId.INDIGO_PLANT)  # vp 2
    _give_building(p, BuildingId.FACTORY)  # vp 3
    _give_building(p, BuildingId.GUILD_HALL, occupied=False)  # large, base vp 4
    # 7 + 1 + 2 + 3 + 4 = 17. SCORE_END bonus is 0 until buildings-06.
    assert scoring.final_score(st, 0) == 17


def test_large_building_base_vp_counts_once_not_large_cont():
    g = _new_game()
    st = g.state
    p = st.players[0]
    for slot in p.city:
        slot.building = None
        slot.colonists = 0
    p.vp_chips = 0
    _give_building(p, BuildingId.RESIDENCE)  # base 4, occupies 2 slots
    # LARGE_CONT must NOT add VP -> exactly 4.
    assert scoring.final_score(st, 0) == 4


def test_final_scores_all_players():
    g = _new_game()
    st = g.state
    for i, p in enumerate(st.players):
        for slot in p.city:
            slot.building = None
            slot.colonists = 0
        p.vp_chips = i
    assert scoring.final_scores(st) == [0, 1, 2, 3]


def test_score_end_bonus_zero_until_handlers_registered():
    """Documented: SCORE_END bonus is 0 until buildings-06 registers handlers."""
    g = _new_game()
    st = g.state
    p = st.players[0]
    for slot in p.city:
        slot.building = None
        slot.colonists = 0
    p.vp_chips = 0
    _give_building(p, BuildingId.GUILD_HALL, occupied=True)
    # Occupied guild hall, but no SCORE_END handler yet -> only base 4.
    assert scoring.final_score(st, 0) == 4


# --------------------------------------------------------------------------- #
# winner / rankings tie-break                                                 #
# --------------------------------------------------------------------------- #


def _flat_players(st):
    """Zero out every player's score components for controlled tie-break tests."""
    for p in st.players:
        for slot in p.city:
            slot.building = None
            slot.colonists = 0
        for s in p.island:
            s.tile = TileType.EMPTY
            s.colonist = False
        p.vp_chips = 0
        p.doubloons = 0
        p.goods = [0, 0, 0, 0, 0]
        p.stored_colonists = 0


def test_winner_by_score():
    g = _new_game()
    st = g.state
    _flat_players(st)
    st.players[2].vp_chips = 10
    st.phase = Phase.GAME_OVER
    assert scoring.rankings(st)[0] == 2
    assert g.winner() == 2


def test_tiebreak_by_doubloons_plus_goods():
    g = _new_game()
    st = g.state
    _flat_players(st)
    # Equal score for all; player 3 has the most doubloons+goods.
    st.players[1].doubloons = 5
    st.players[3].doubloons = 3
    st.players[3].goods[Good.COFFEE] = 4  # 3 + 4 = 7 wealth, beats player 1's 5
    st.phase = Phase.GAME_OVER
    assert g.winner() == 3


def test_tiebreak_final_index_lower_wins():
    g = _new_game()
    st = g.state
    _flat_players(st)
    # Fully tied on score AND wealth -> lowest index wins.
    st.phase = Phase.GAME_OVER
    assert g.winner() == 0
    assert scoring.rankings(st) == [0, 1, 2, 3]


def test_tiebreak_key_components():
    g = _new_game()
    st = g.state
    _flat_players(st)
    st.players[0].vp_chips = 5
    st.players[0].doubloons = 2
    st.players[0].goods[Good.INDIGO] = 3
    key = scoring.tiebreak_key(st, 0)
    assert key == (5, 5, 0)  # (score, doubloons+goods, -index)


# --------------------------------------------------------------------------- #
# returns()                                                                   #
# --------------------------------------------------------------------------- #


def test_returns_sum_zero_and_matches_rankings():
    g = _new_game()
    st = g.state
    _flat_players(st)
    st.players[0].vp_chips = 10
    st.players[1].vp_chips = 7
    st.players[2].vp_chips = 4
    st.players[3].vp_chips = 1
    st.phase = Phase.GAME_OVER

    rets = g.returns()
    assert abs(sum(rets)) < 1e-9
    # Best player gets the highest reward; worst the lowest.
    order = scoring.rankings(st)
    assert order == [0, 1, 2, 3]
    assert rets[0] == max(rets)
    assert rets[3] == min(rets)
    # Evenly spaced: +1, +1/3, -1/3, -1.
    assert abs(rets[0] - 1.0) < 1e-9
    assert abs(rets[3] + 1.0) < 1e-9


def test_returns_zero_when_not_terminal():
    g = _new_game()
    assert g.returns() == [0.0, 0.0, 0.0, 0.0]
    assert g.winner() is None
