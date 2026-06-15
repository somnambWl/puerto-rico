"""Tests for the CAPTAIN phase (phases-task-07).

Covers: loading legality (single-kind-per-ship, no-duplicate-kind-across-ships,
full ship blocked), mandatory loading (a player who can load has no PASS, and the
engine loads the most-filling ship / max amount), the wharf (optional, ships all
of a kind to supply, once per phase, PASS allowed only when wharf is the sole
option), VP scoring (+1 per good, chooser +1 on first load only, vp_chips_remaining
decrement, exhaustion -> end_triggered), the last duty (full ships unload, partial
ships carry over), goods storage (windrose + warehouse keep, excess to supply), and
the rulebook worked example.
"""

from __future__ import annotations

from puerto_rico.engine import buildings
from puerto_rico.engine.actions import Action
from puerto_rico.engine.enums import BuildingId, DecisionType, Good, Phase, Role
from puerto_rico.engine.game import Game
from puerto_rico.engine.phases import (
    CAPTAIN_WHARF,
    _enter_storage,
    _legal_ships_for_good,
    _store_goods_for_player,
    award_captain_vp,
)
from puerto_rico.engine.state import GameConfig


def _new_game(num_players: int = 4, seed: int = 0) -> Game:
    return Game(GameConfig(num_players=num_players, seed=seed))


def _enter_captain(g: Game) -> int:
    """Select CAPTAIN; return the chooser index. Clears everyone's goods first.

    Clearing goods means no player can load at entry, so the cursor lands on the
    chooser with only PASS — then the test arranges goods/ships and re-enters by
    calling captain_phase_enter via fresh setup. To keep control, callers set up
    state BEFORE selecting; here we just select and assert the phase.
    """
    g.apply(Action.select_role(Role.CAPTAIN))
    assert g.state.phase == Phase.CAPTAIN
    return g.state.phase_state.role_chooser


def _clear_goods(player) -> None:
    for i in range(len(player.goods)):
        player.goods[i] = 0


def _clear_all_goods(state) -> None:
    for p in state.players:
        _clear_goods(p)


def _give_building(player, bid: BuildingId, colonists: int) -> None:
    for slot in player.city:
        if slot.building is None:
            slot.building = bid
            slot.colonists = colonists
            return


def _setup_captain(g: Game):
    """Clear all goods/ships, then (re-)enter the captain phase cleanly.

    Returns the chooser index. The caller mutates goods/ships AFTER this and then
    calls ``_reenter`` so phase entry re-evaluates the cursor.
    """
    _clear_all_goods(g.state)
    for ship in g.state.cargo_ships:
        ship.good = None
        ship.count = 0
    return _enter_captain(g)


def _reenter(g: Game) -> None:
    """Re-run captain phase entry after mutating goods/ships in a test."""
    from puerto_rico.engine.phases import captain_phase_enter

    captain_phase_enter(g.state)


def _load_actions(g: Game):
    return [a for a in g.legal_actions() if a.type == DecisionType.LOAD and a.choice is None]


def _load(g: Game, good: Good):
    """Apply the (first legal) cargo LOAD of ``good`` for the current player.

    With explicit ship choice the agent must name a ship; tests that don't care
    which ship just take the lowest-index legal one.
    """
    act = next(a for a in _load_actions(g) if a.good == good)
    g.apply(act)


def _wharf_actions(g: Game):
    return [a for a in g.legal_actions() if a.type == DecisionType.LOAD and a.choice == CAPTAIN_WHARF]


# --------------------------------------------------------------------------- #
# ship-selection legality                                                      #
# --------------------------------------------------------------------------- #


def test_single_kind_per_ship_and_no_duplicate_across_ships():
    g = _new_game()
    chooser = _setup_captain(g)
    p = g.state.players[chooser]
    # Ship 0 already holds SUGAR; ship 1 empty; ship 2 empty.
    g.state.cargo_ships[0].good = Good.SUGAR
    g.state.cargo_ships[0].count = 1
    p.goods[Good.SUGAR] = 2
    p.goods[Good.CORN] = 2
    _reenter(g)

    # SUGAR can load (onto ship 0, which already holds it).
    # CORN can load onto an empty ship (not on any other ship).
    kinds = {a.good for a in _load_actions(g)}
    assert Good.SUGAR in kinds
    assert Good.CORN in kinds
    # SUGAR's only legal ship is the one already holding it (ship 0).
    assert _legal_ships_for_good(g.state, Good.SUGAR) == [0]
    # CORN may go to either empty ship (1 or 2) but NOT ship 0 (holds sugar).
    assert _legal_ships_for_good(g.state, Good.CORN) == [1, 2]

    # Now fill ship 1 with CORN, so CORN living in two places is impossible:
    g.state.cargo_ships[1].good = Good.CORN
    g.state.cargo_ships[1].count = 6  # full
    # A NEW kind (TOBACCO) may still take the remaining empty ship 2.
    p.goods[Good.TOBACCO] = 1
    _reenter(g)
    # CORN cannot go to ship 0 (holds sugar) nor ship 1 (full) nor an empty ship
    # (corn already on ship 1) -> CORN not loadable.
    assert _legal_ships_for_good(g.state, Good.CORN) == []
    # TOBACCO may take the last empty ship (index 2).
    assert _legal_ships_for_good(g.state, Good.TOBACCO) == [2]


def test_full_ship_cannot_receive():
    g = _new_game()
    chooser = _setup_captain(g)
    p = g.state.players[chooser]
    g.state.cargo_ships[0].good = Good.CORN
    g.state.cargo_ships[0].count = 5  # capacity 5 -> full
    p.goods[Good.CORN] = 3
    # Only the full ship holds corn; corn cannot go to any empty ship (already on
    # ship 0) -> not loadable.
    _reenter(g)
    assert _legal_ships_for_good(g.state, Good.CORN) == []


def test_explicit_ship_choice_loads_chosen_ship():
    """LOAD(good, target=ship_idx) loads the player-chosen ship, not a forced one."""
    g = _new_game()
    chooser = _setup_captain(g)
    p = g.state.players[chooser]
    # 3 sugar, all three ships empty -> sugar can go on ANY of the three ships.
    p.goods[Good.SUGAR] = 3
    _reenter(g)
    targets = {a.target for a in _load_actions(g) if a.good == Good.SUGAR}
    assert targets == {0, 1, 2}

    # Choose the cap-5 ship (index 0), NOT the most-filling cap-7 ship.
    g.apply(Action.load(Good.SUGAR, target=0))
    assert g.state.cargo_ships[0].good == Good.SUGAR
    assert g.state.cargo_ships[0].count == 3
    assert p.goods[Good.SUGAR] == 0
    # The other ships stayed empty.
    assert g.state.cargo_ships[2].count == 0


def test_amount_is_max_that_fits_on_chosen_ship():
    """The chosen ship loads min(holds, remaining) — amount stays maximal."""
    g = _new_game()
    chooser = _setup_captain(g)
    p = g.state.players[chooser]
    # 6 sugar; load onto the cap-5 ship (index 0) -> only 5 fit; 1 sugar remains.
    p.goods[Good.SUGAR] = 6
    # Give a second player a good so the phase stays in the loading loop (the
    # cap-5 ship is otherwise FULL and would be unloaded when the phase ends).
    other = next(i for i in g.state.phase_state.order if i != chooser)
    g.state.players[other].goods[Good.CORN] = 1
    _reenter(g)
    g.apply(Action.load(Good.SUGAR, target=0))
    assert g.state.cargo_ships[0].count == 5  # filled to capacity, not unloaded yet
    assert p.goods[Good.SUGAR] == 1  # 1 sugar didn't fit, stays with the player


# --------------------------------------------------------------------------- #
# mandatory load + most-filling ship                                           #
# --------------------------------------------------------------------------- #


def test_player_who_can_load_has_no_pass():
    g = _new_game()
    chooser = _setup_captain(g)
    p = g.state.players[chooser]
    p.goods[Good.SUGAR] = 1
    _reenter(g)
    assert g.state.current_player == chooser
    actions = g.legal_actions()
    assert all(a.type != DecisionType.PASS for a in actions)
    assert any(a.type == DecisionType.LOAD for a in actions)


def test_load_onto_ship_already_holding_kind():
    g = _new_game()
    chooser = _setup_captain(g)
    p = g.state.players[chooser]
    # ship1 cap6 already holds 3 corn (remaining 3); loading 2 tops it off to 5
    # (still not full, so it is NOT unloaded when the phase ends).
    g.state.cargo_ships[1].good = Good.CORN
    g.state.cargo_ships[1].count = 3
    p.goods[Good.CORN] = 2
    _reenter(g)
    # CORN's only legal ship is the one already holding it (an empty ship would be
    # a duplicate kind).
    assert _legal_ships_for_good(g.state, Good.CORN) == [1]
    g.apply(Action.load(Good.CORN, target=1))
    assert g.state.cargo_ships[1].count == 5
    assert p.goods[Good.CORN] == 0


# --------------------------------------------------------------------------- #
# wharf                                                                        #
# --------------------------------------------------------------------------- #


def test_wharf_ships_all_to_supply_once_per_phase():
    g = _new_game()
    chooser = _setup_captain(g)
    p = g.state.players[chooser]
    # No cargo loads possible (all ships empty but give a kind only via wharf):
    # Make every ship full of OTHER kinds so cargo loading is impossible.
    g.state.cargo_ships[0].good = Good.INDIGO
    g.state.cargo_ships[0].count = 5
    g.state.cargo_ships[1].good = Good.TOBACCO
    g.state.cargo_ships[1].count = 6
    g.state.cargo_ships[2].good = Good.COFFEE
    g.state.cargo_ships[2].count = 7
    p.goods[Good.SUGAR] = 4
    _give_building(p, BuildingId.WHARF, colonists=1)  # occupied wharf
    _reenter(g)

    supply_before = g.state.goods_supply[Good.SUGAR]
    # Wharf available; cargo not possible -> PASS also offered.
    assert _wharf_actions(g)
    assert any(a.type == DecisionType.PASS for a in g.legal_actions())

    g.apply(Action(DecisionType.LOAD, good=Good.SUGAR, choice=CAPTAIN_WHARF))
    assert p.goods[Good.SUGAR] == 0
    assert g.state.goods_supply[Good.SUGAR] == supply_before + 4
    # Wharf is single-use: it must not be offered again (player back later not
    # applicable here since they have no more goods, but flag is recorded).
    assert chooser in g.state.phase_state.sub["wharf_used"]


def test_pass_allowed_only_when_wharf_is_sole_option():
    g = _new_game()
    chooser = _setup_captain(g)
    p = g.state.players[chooser]
    # A cargo load IS possible -> mandatory, no PASS even with a wharf present.
    p.goods[Good.SUGAR] = 1
    _give_building(p, BuildingId.WHARF, colonists=1)
    _reenter(g)
    actions = g.legal_actions()
    assert any(a.type == DecisionType.LOAD and a.choice is None for a in actions)
    assert any(a.choice == CAPTAIN_WHARF for a in actions)
    assert all(a.type != DecisionType.PASS for a in actions)  # mandatory cargo load


def test_clone_isolates_captain_sub_sets_on_apply():
    """Regression: applying a captain action to a CLONE must not mutate the
    original game's ``sub`` sets (``wharf_used`` / ``first_load_done``).

    Before the clone() fix these sets were shared by reference, so loading via
    wharf on the clone added the chooser to the ORIGINAL's ``wharf_used`` set —
    silently corrupting MCTS/RL rollouts.
    """
    g = _new_game()
    chooser = _setup_captain(g)
    p = g.state.players[chooser]
    # Make cargo loading impossible (all ships full of other kinds) so the only
    # move is a wharf load, which mutates sub["wharf_used"].
    g.state.cargo_ships[0].good = Good.INDIGO
    g.state.cargo_ships[0].count = 5
    g.state.cargo_ships[1].good = Good.TOBACCO
    g.state.cargo_ships[1].count = 6
    g.state.cargo_ships[2].good = Good.COFFEE
    g.state.cargo_ships[2].count = 7
    p.goods[Good.SUGAR] = 4
    _give_building(p, BuildingId.WHARF, colonists=1)
    _reenter(g)

    # sub sets exist and the chooser has not used the wharf yet.
    assert chooser not in g.state.phase_state.sub["wharf_used"]

    clone = g.clone()
    # The inner set objects must be distinct between game and clone.
    assert (
        clone.state.phase_state.sub["wharf_used"]
        is not g.state.phase_state.sub["wharf_used"]
    )

    # Apply a wharf load on the CLONE only.
    clone.apply(Action(DecisionType.LOAD, good=Good.SUGAR, choice=CAPTAIN_WHARF))

    # Clone records the wharf use; original is untouched.
    assert chooser in clone.state.phase_state.sub["wharf_used"]
    assert chooser not in g.state.phase_state.sub["wharf_used"]


# --------------------------------------------------------------------------- #
# VP scoring                                                                   #
# --------------------------------------------------------------------------- #


def test_vp_one_per_good_and_chooser_first_load_bonus():
    g = _new_game()
    chooser = _setup_captain(g)
    p = g.state.players[chooser]
    vp_before = p.vp_chips
    remaining_before = g.state.vp_chips_remaining
    p.goods[Good.SUGAR] = 3
    _reenter(g)

    _load(g, Good.SUGAR)  # 3 goods + 1 chooser bonus = 4 VP
    assert p.vp_chips == vp_before + 4
    assert g.state.vp_chips_remaining == remaining_before - 4


def test_chooser_bonus_only_on_first_load():
    g = _new_game()
    chooser = _setup_captain(g)
    p = g.state.players[chooser]
    # Give the chooser two separate loadable kinds; make others unable to load so
    # the chooser comes back around for a second load.
    for other in range(len(g.state.players)):
        if other != chooser:
            _clear_goods(g.state.players[other])
    p.goods[Good.SUGAR] = 1
    p.goods[Good.TOBACCO] = 1
    _reenter(g)
    vp_before = p.vp_chips

    _load(g, Good.SUGAR)   # 1 + 1 bonus = 2
    # Back to chooser (others can't load).
    assert g.state.current_player == chooser
    _load(g, Good.TOBACCO)  # 1, no bonus
    assert p.vp_chips == vp_before + 2 + 1


def test_vp_exhaustion_sets_end_triggered():
    g = _new_game()
    chooser = _setup_captain(g)
    p = g.state.players[chooser]
    g.state.vp_chips_remaining = 2
    p.goods[Good.SUGAR] = 5  # would earn 5 + 1 bonus, but only 2 remain
    _reenter(g)

    _load(g, Good.SUGAR)
    assert g.state.vp_chips_remaining == 0
    assert g.state.end_triggered is True
    assert p.vp_chips == 2  # only the 2 remaining chips awarded


def test_award_captain_vp_helper():
    g = _new_game()
    g.state.vp_chips_remaining = 3
    award_captain_vp(g.state, 0, 5)
    assert g.state.players[0].vp_chips == 3
    assert g.state.vp_chips_remaining == 0
    assert g.state.end_triggered is True


# --------------------------------------------------------------------------- #
# last duty: unload full ships, carry over partials                            #
# --------------------------------------------------------------------------- #


def test_last_duty_full_ships_unload_partial_carries_over():
    g = _new_game()
    _setup_captain(g)
    _clear_all_goods(g.state)
    # ship0 full (cap5, 5 corn) -> unload; ship1 partial (3 sugar) -> carry over;
    # ship2 empty -> untouched.
    g.state.cargo_ships[0].good = Good.CORN
    g.state.cargo_ships[0].count = 5
    g.state.cargo_ships[1].good = Good.SUGAR
    g.state.cargo_ships[1].count = 3
    supply_corn = g.state.goods_supply[Good.CORN]

    # Drive the REAL interactive end-of-phase path. With all goods cleared no
    # player has a windrose choice, so storage auto-resolves and the storage
    # sub-phase finishes by unloading full ships (and ending the role).
    g.state.phase_state.order = [0, 1, 2, 3]
    _enter_storage(g.state)

    assert g.state.cargo_ships[0].good is None
    assert g.state.cargo_ships[0].count == 0
    assert g.state.goods_supply[Good.CORN] == supply_corn + 5
    # Partial ship retained.
    assert g.state.cargo_ships[1].good == Good.SUGAR
    assert g.state.cargo_ships[1].count == 3


# --------------------------------------------------------------------------- #
# goods storage                                                                #
# --------------------------------------------------------------------------- #


def test_storage_within_capacity_keeps_all():
    g = _new_game()
    _setup_captain(g)
    p = g.state.players[0]
    _clear_goods(p)
    p.goods[Good.SUGAR] = 1  # a single good fits on the windrose
    _store_goods_for_player(g.state, 0)
    assert p.goods[Good.SUGAR] == 1


def test_storage_over_capacity_returns_excess():
    g = _new_game()
    _setup_captain(g)
    p = g.state.players[0]
    _clear_goods(p)
    # No warehouse: keep only 1 good on the windrose; rest to supply.
    p.goods[Good.SUGAR] = 3
    p.goods[Good.CORN] = 2
    supply_sugar = g.state.goods_supply[Good.SUGAR]
    supply_corn = g.state.goods_supply[Good.CORN]

    _store_goods_for_player(g.state, 0)

    kept = p.goods[Good.SUGAR] + p.goods[Good.CORN]
    assert kept == 1  # exactly one windrose good
    # Highest-count kind (sugar, 3) is kept as the single windrose good.
    assert p.goods[Good.SUGAR] == 1
    assert p.goods[Good.CORN] == 0
    assert g.state.goods_supply[Good.SUGAR] == supply_sugar + 2
    assert g.state.goods_supply[Good.CORN] == supply_corn + 2


def test_storage_with_small_warehouse_keeps_one_whole_kind():
    g = _new_game()
    _setup_captain(g)
    p = g.state.players[0]
    _clear_goods(p)
    _give_building(p, BuildingId.SMALL_WAREHOUSE, colonists=1)  # occupied (only occupied tiles function)
    p.goods[Good.SUGAR] = 4  # protected whole kind
    p.goods[Good.CORN] = 2   # 1 stays on the windrose, 1 to supply
    supply_corn = g.state.goods_supply[Good.CORN]

    _store_goods_for_player(g.state, 0)

    assert p.goods[Good.SUGAR] == 4  # whole kind kept by the warehouse
    assert p.goods[Good.CORN] == 1   # windrose single
    assert g.state.goods_supply[Good.CORN] == supply_corn + 1


def test_storage_large_warehouse_keeps_two_kinds():
    g = _new_game()
    _setup_captain(g)
    p = g.state.players[0]
    _clear_goods(p)
    _give_building(p, BuildingId.LARGE_WAREHOUSE, colonists=1)  # occupied (only occupied tiles function)
    p.goods[Good.SUGAR] = 3
    p.goods[Good.TOBACCO] = 2
    p.goods[Good.CORN] = 5

    _store_goods_for_player(g.state, 0)

    # Two highest-count kinds protected (corn 5, sugar 3); tobacco's count (2)
    # leaves 1 on the windrose.
    assert p.goods[Good.CORN] == 5
    assert p.goods[Good.SUGAR] == 3
    assert p.goods[Good.TOBACCO] == 1


# --------------------------------------------------------------------------- #
# interactive storage sub-phase (windrose CHOOSE)                              #
# --------------------------------------------------------------------------- #


def _block_all_ships(g: Game) -> None:
    """Fill every cargo ship full with distinct kinds so no player can load.

    Ships are filled with INDIGO/COFFEE/CORN. Storage tests below give players
    SUGAR/TOBACCO (+ a filler kind already on a full ship), so their SUGAR and
    TOBACCO supply counts stay clean: those kinds are never unloaded by a filler
    ship. (Full ships unload at phase end; that only pollutes the filler kinds.)
    """
    fillers = [Good.INDIGO, Good.COFFEE, Good.CORN]
    for i, ship in enumerate(g.state.cargo_ships):
        ship.good = fillers[i]
        ship.count = ship.capacity


def _choose_actions(g: Game):
    return [a for a in g.legal_actions() if a.type == DecisionType.CHOOSE]


def test_storage_choose_node_when_over_capacity():
    """A player with >= 2 unprotected kinds gets a windrose CHOOSE; choosing keeps
    that single good and discards the rest of the unprotected goods to supply.

    Ships are filled (INDIGO/COFFEE/CORN) so nobody can load; the player holds
    CORN (blocked: on a full ship), SUGAR, TOBACCO. All three are unprotected, so
    the windrose CHOOSE ranges over all three.
    """
    g = _new_game()
    chooser = _setup_captain(g)
    _clear_all_goods(g.state)
    _block_all_ships(g)  # nobody can load -> loop ends -> storage
    p = g.state.players[chooser]
    p.goods[Good.CORN] = 2
    p.goods[Good.SUGAR] = 3
    p.goods[Good.TOBACCO] = 1
    # SUGAR/TOBACCO are not filler kinds, so their supply counts stay clean.
    sup_sugar = g.state.goods_supply[Good.SUGAR]
    sup_tob = g.state.goods_supply[Good.TOBACCO]
    _reenter(g)

    # No cargo load possible; the chooser PASSes out of loading -> storage starts.
    g.apply(Action.passing())

    # The storage sub-phase now seats the chooser (3 unprotected kinds) for a
    # windrose CHOOSE.
    assert g.state.phase == Phase.CAPTAIN
    assert g.state.phase_state.sub.get("storage") is True
    assert g.state.current_player == chooser
    choices = {a.good for a in _choose_actions(g)}
    assert choices == {Good.CORN, Good.SUGAR, Good.TOBACCO}

    # Keep SUGAR on the windrose; CORN and TOBACCO go entirely to supply.
    g.apply(Action(DecisionType.CHOOSE, good=Good.SUGAR))
    assert p.goods[Good.SUGAR] == 1
    assert p.goods[Good.CORN] == 0
    assert p.goods[Good.TOBACCO] == 0
    # 3 sugar held, 1 kept on the windrose -> 2 sugar discarded to supply.
    assert g.state.goods_supply[Good.SUGAR] == sup_sugar + 2
    # All tobacco discarded (sugar was chosen for the windrose instead).
    assert g.state.goods_supply[Good.TOBACCO] == sup_tob + 1
    # Storage done for everyone -> phase exits.
    assert g.state.phase != Phase.CAPTAIN


def test_storage_no_decision_when_within_capacity():
    """A player with <= 1 unprotected kind gets NO storage decision node."""
    g = _new_game()
    chooser = _setup_captain(g)
    _clear_all_goods(g.state)
    _block_all_ships(g)
    p = g.state.players[chooser]
    p.goods[Good.SUGAR] = 4  # a single kind: keep 1 on the windrose, no choice
    _reenter(g)

    g.apply(Action.passing())  # nothing to load -> storage auto-resolves
    # No CHOOSE node ever surfaced; the captain phase is already over.
    assert g.state.phase != Phase.CAPTAIN
    assert p.goods[Good.SUGAR] == 1


def test_storage_warehouse_kinds_autokept_only_windrose_chosen():
    """Warehouse-protected kinds are auto-kept in full; only the windrose single
    among UNPROTECTED kinds is the CHOOSE."""
    g = _new_game()
    chooser = _setup_captain(g)
    _clear_all_goods(g.state)
    _block_all_ships(g)
    p = g.state.players[chooser]
    _give_building(p, BuildingId.SMALL_WAREHOUSE, colonists=1)  # protects 1 kind
    # Highest-count held kind (corn 5) is warehouse-protected; sugar+tobacco are
    # the unprotected kinds the windrose choice ranges over.
    p.goods[Good.CORN] = 5
    p.goods[Good.SUGAR] = 3
    p.goods[Good.TOBACCO] = 2
    _reenter(g)

    g.apply(Action.passing())
    assert g.state.phase_state.sub.get("storage") is True
    # CHOOSE ranges only over UNPROTECTED kinds (corn is auto-kept by the warehouse).
    choices = {a.good for a in _choose_actions(g)}
    assert choices == {Good.SUGAR, Good.TOBACCO}

    g.apply(Action(DecisionType.CHOOSE, good=Good.TOBACCO))
    assert p.goods[Good.CORN] == 5   # warehouse kind kept in full
    assert p.goods[Good.TOBACCO] == 1  # windrose single
    assert p.goods[Good.SUGAR] == 0    # the other unprotected kind discarded


# --------------------------------------------------------------------------- #
# loop integration: phase ends when no one can load                            #
# --------------------------------------------------------------------------- #


def test_loop_ends_when_nobody_can_load():
    g = _new_game()
    chooser = _setup_captain(g)
    # Only the chooser has a single good; everyone else has none.
    for i, p in enumerate(g.state.players):
        _clear_goods(p)
    g.state.players[chooser].goods[Good.SUGAR] = 1
    _reenter(g)

    _load(g, Good.SUGAR)
    # No one has goods left to load -> phase ended, back to selection (or round end).
    assert g.state.phase != Phase.CAPTAIN


# --------------------------------------------------------------------------- #
# rulebook worked example (4 players)                                          #
# --------------------------------------------------------------------------- #


def test_rulebook_worked_example():
    """Encode the design/02 / rules captain worked example and check VP outcomes.

    Anna (captain) 2 corn + 6 sugar; ships are 5-,6-,7-space; the 6-ship holds
    3 corn. Loads resolve as in the rulebook; final: Anna +6(sugar)+1(privilege)
    +2(corn) = 9, Bob +1(sugar)+3(tobacco) = 4, Chris +1, David +1. Full ships
    (6 and 7) unload; the 5-ship keeps its 4 tobacco.
    """
    g = _new_game(num_players=4)
    # Force a known seating: make player 0 the chooser by selecting from governor.
    chooser = _setup_captain(g)
    # Map roles onto seats relative to the chooser (clockwise order).
    order = g.state.phase_state.order
    anna, bob, chris, david = order[0], order[1], order[2], order[3]

    for i in (anna, bob, chris, david):
        _clear_goods(g.state.players[i])
    for ship in g.state.cargo_ships:
        ship.good = None
        ship.count = 0
    # Ships: index0 cap5, index1 cap6 (holds 3 corn), index2 cap7.
    g.state.cargo_ships[1].good = Good.CORN
    g.state.cargo_ships[1].count = 3

    g.state.players[anna].goods[Good.CORN] = 2
    g.state.players[anna].goods[Good.SUGAR] = 6
    g.state.players[bob].goods[Good.SUGAR] = 2
    g.state.players[bob].goods[Good.TOBACCO] = 3
    g.state.players[chris].goods[Good.TOBACCO] = 1
    g.state.players[david].goods[Good.CORN] = 1
    g.state.players[david].goods[Good.INDIGO] = 1

    vp0 = {i: g.state.players[i].vp_chips for i in order}
    _reenter(g)

    # Anna: must choose. The example dictates she loads 6 sugar onto the 7-ship
    # (idx2) — NOT the 5-ship, which couldn't fit all 6. With explicit ship choice
    # she could pick any empty ship; the example names the 7-ship.
    assert g.state.current_player == anna
    # Sugar can go on either EMPTY ship (5-ship idx0 or 7-ship idx2); the 6-ship
    # (idx1) holds corn, so sugar may not go there.
    sugar_targets = {a.target for a in _load_actions(g) if a.good == Good.SUGAR}
    assert sugar_targets == {0, 2}
    g.apply(Action.load(Good.SUGAR, target=2))  # the 7-ship
    assert g.state.cargo_ships[2].good == Good.SUGAR
    assert g.state.cargo_ships[2].count == 6

    # Bob: tops off the 7-ship with 1 sugar; he could also start tobacco on the
    # empty 5-ship. The example has him choose sugar onto the 7-ship.
    assert g.state.current_player == bob
    assert {a.good for a in _load_actions(g)} == {Good.SUGAR, Good.TOBACCO}
    g.apply(Action.load(Good.SUGAR, target=2))  # top off the 7-ship
    assert g.state.cargo_ships[2].count == 7  # full

    # Chris: loads 1 tobacco onto the empty 5-ship (idx0).
    assert g.state.current_player == chris
    g.apply(Action.load(Good.TOBACCO, target=0))
    assert g.state.cargo_ships[0].good == Good.TOBACCO
    assert g.state.cargo_ships[0].count == 1

    # David: must load 1 corn on the 6-ship (indigo has no room).
    assert g.state.current_player == david
    assert {a.good for a in _load_actions(g)} == {Good.CORN}
    g.apply(Action.load(Good.CORN, target=1))  # the 6-ship
    assert g.state.cargo_ships[1].count == 4

    # Anna again: her 2 corn onto the 6-ship (now 6, full).
    assert g.state.current_player == anna
    g.apply(Action.load(Good.CORN, target=1))
    assert g.state.cargo_ships[1].count == 6

    # Bob: must load his 3 tobacco onto the 5-ship (the only ship holding tobacco).
    assert g.state.current_player == bob
    g.apply(Action.load(Good.TOBACCO, target=0))
    assert g.state.cargo_ships[0].count == 4

    # Chris and David still have goods but nowhere to load -> loop ends.
    assert g.state.phase != Phase.CAPTAIN

    anna_p = g.state.players[anna]
    bob_p = g.state.players[bob]
    chris_p = g.state.players[chris]
    david_p = g.state.players[david]
    assert anna_p.vp_chips - vp0[anna] == 6 + 1 + 2  # sugar + privilege + corn
    assert bob_p.vp_chips - vp0[bob] == 1 + 3
    assert chris_p.vp_chips - vp0[chris] == 1
    assert david_p.vp_chips - vp0[david] == 1

    # Last duty already ran at end_of_role: full ships (6-ship idx1, 7-ship idx2)
    # unloaded; the 5-ship (idx0) keeps its 4 tobacco.
    assert g.state.cargo_ships[1].count == 0
    assert g.state.cargo_ships[2].count == 0
    assert g.state.cargo_ships[0].good == Good.TOBACCO
    assert g.state.cargo_ships[0].count == 4
