"""Tests for the SETTLER phase (phases-task-02).

Covers: legal-action construction (distinct face-up plantations; quarry only for
the chooser or an occupied construction-hut owner), auto-placement onto the
lowest empty island slot, the full-island PASS-only case, and the chooser's
last-duty row refresh including the discard-reshuffle path.
"""

from __future__ import annotations

from puerto_rico.engine.actions import Action
from puerto_rico.engine.enums import (
    BuildingId,
    DecisionType,
    Phase,
    Role,
    TileType,
)
from puerto_rico.engine.game import Game
from puerto_rico.engine.phases import settler_last_duty
from puerto_rico.engine.state import GameConfig


def _new_game(num_players: int = 4, seed: int = 0) -> Game:
    return Game(GameConfig(num_players=num_players, seed=seed))


def _enter_settler(g: Game) -> None:
    """Select SETTLER so the engine enters Phase.SETTLER at the chooser's turn."""
    g.apply(Action.select_role(Role.SETTLER))
    assert g.state.phase == Phase.SETTLER


def _set_faceup(g: Game, tiles: list[TileType]) -> None:
    g.state.plantation_faceup[:] = tiles


# --------------------------------------------------------------------------- #
# legal actions                                                               #
# --------------------------------------------------------------------------- #


def test_legal_actions_list_distinct_faceup_plus_pass():
    g = _new_game()
    _enter_settler(g)
    _set_faceup(g, [TileType.CORN, TileType.CORN, TileType.INDIGO, TileType.SUGAR])
    g.state.quarry_supply = 0  # isolate from the quarry privilege

    actions = g.legal_actions()
    take_tiles = {a.tile for a in actions if a.type == DecisionType.TAKE_TILE}
    assert take_tiles == {TileType.CORN, TileType.INDIGO, TileType.SUGAR}
    assert Action.passing() in actions


def test_chooser_sees_quarry():
    g = _new_game()
    _enter_settler(g)
    _set_faceup(g, [TileType.CORN])
    g.state.quarry_supply = 8

    # order[0] is the chooser; current_player is the chooser at order_pos 0.
    assert g.current_player == g.state.phase_state.role_chooser
    actions = g.legal_actions()
    assert Action.take_tile(TileType.QUARRY) in actions


def test_non_chooser_without_hut_cannot_take_quarry():
    g = _new_game()
    _enter_settler(g)
    _set_faceup(g, [TileType.CORN])
    g.state.quarry_supply = 8

    # Advance to the second player in order (a non-chooser): chooser takes corn.
    g.apply(Action.take_tile(TileType.CORN))
    assert g.current_player != g.state.phase_state.role_chooser
    actions = g.legal_actions()
    assert Action.take_tile(TileType.QUARRY) not in actions


def test_non_chooser_with_construction_hut_can_take_quarry():
    g = _new_game()
    _enter_settler(g)
    _set_faceup(g, [TileType.CORN, TileType.CORN])
    g.state.quarry_supply = 8

    chooser = g.state.phase_state.role_chooser
    g.apply(Action.take_tile(TileType.CORN))  # chooser acts -> next player
    other = g.current_player
    assert other != chooser

    # Give the non-chooser an occupied construction hut.
    p = g.state.players[other]
    p.city[0].building = BuildingId.CONSTRUCTION_HUT
    p.city[0].colonists = 1

    actions = g.legal_actions()
    assert Action.take_tile(TileType.QUARRY) in actions


# --------------------------------------------------------------------------- #
# placement                                                                   #
# --------------------------------------------------------------------------- #


def test_take_tile_auto_places_lowest_empty_slot_and_removes_from_faceup():
    g = _new_game()
    _enter_settler(g)
    _set_faceup(g, [TileType.SUGAR, TileType.COFFEE])
    g.state.quarry_supply = 0

    chooser = g.state.phase_state.role_chooser
    # Occupy island slot 0 so the lowest EMPTY slot is 1.
    g.state.players[chooser].island[0].tile = TileType.CORN

    g.apply(Action.take_tile(TileType.SUGAR))

    assert g.state.players[chooser].island[1].tile == TileType.SUGAR
    assert TileType.SUGAR not in g.state.plantation_faceup
    assert g.state.plantation_faceup == [TileType.COFFEE]


def test_take_quarry_decrements_supply_and_places():
    g = _new_game()
    _enter_settler(g)
    _set_faceup(g, [TileType.CORN])
    before = g.state.quarry_supply = 5

    chooser = g.state.phase_state.role_chooser
    slot = next(
        i for i, s in enumerate(g.state.players[chooser].island)
        if s.tile == TileType.EMPTY
    )
    g.apply(Action.take_tile(TileType.QUARRY))

    assert g.state.players[chooser].island[slot].tile == TileType.QUARRY
    assert g.state.quarry_supply == before - 1


def test_full_island_only_pass():
    g = _new_game()
    _enter_settler(g)
    _set_faceup(g, [TileType.CORN, TileType.INDIGO])
    g.state.quarry_supply = 8

    chooser = g.state.phase_state.role_chooser
    for slot in g.state.players[chooser].island:
        slot.tile = TileType.CORN  # fill all 12 slots

    actions = g.legal_actions()
    assert actions == [Action.passing()]


# --------------------------------------------------------------------------- #
# building handlers end-to-end (hacienda / hospice through settler_apply)      #
# --------------------------------------------------------------------------- #


def _empty_slots(p) -> list[int]:
    return [i for i, s in enumerate(p.island) if s.tile == TileType.EMPTY]


def test_hacienda_end_to_end_adds_extra_tile_before_main_take():
    g = _new_game()
    _enter_settler(g)
    _set_faceup(g, [TileType.SUGAR])
    g.state.quarry_supply = 0
    g.state.plantation_facedown[:] = [TileType.TOBACCO]  # top = TOBACCO

    chooser = g.state.phase_state.role_chooser
    p = g.state.players[chooser]
    p.city[0].building = BuildingId.HACIENDA
    p.city[0].colonists = 1
    s_extra, s_main = _empty_slots(p)[:2]  # two lowest empty island slots

    g.apply(Action.take_tile(TileType.SUGAR))

    # Island gains TWO tiles this turn: hacienda extra first, then the main take.
    assert p.island[s_extra].tile == TileType.TOBACCO  # hacienda extra, first
    assert p.island[s_main].tile == TileType.SUGAR  # main take
    assert p.island[s_extra].colonist is False  # hacienda does not man
    assert g.state.plantation_facedown == []


def test_hospice_end_to_end_mans_the_main_tile():
    g = _new_game()
    _enter_settler(g)
    _set_faceup(g, [TileType.CORN])
    g.state.quarry_supply = 0
    g.state.colonist_supply = 5

    chooser = g.state.phase_state.role_chooser
    p = g.state.players[chooser]
    p.city[0].building = BuildingId.HOSPICE
    p.city[0].colonists = 1
    s_main = _empty_slots(p)[0]

    g.apply(Action.take_tile(TileType.CORN))

    assert p.island[s_main].tile == TileType.CORN
    assert p.island[s_main].colonist is True  # hospice manned the placed tile
    assert g.state.colonist_supply == 4


def test_hacienda_plus_hospice_end_to_end_mans_only_main_tile():
    g = _new_game()
    _enter_settler(g)
    _set_faceup(g, [TileType.SUGAR])
    g.state.quarry_supply = 0
    g.state.colonist_supply = 5
    g.state.plantation_facedown[:] = [TileType.TOBACCO]

    chooser = g.state.phase_state.role_chooser
    p = g.state.players[chooser]
    p.city[0].building = BuildingId.HACIENDA
    p.city[0].colonists = 1
    p.city[1].building = BuildingId.HOSPICE
    p.city[1].colonists = 1
    s_extra, s_main = _empty_slots(p)[:2]

    g.apply(Action.take_tile(TileType.SUGAR))

    # Hacienda extra (unmanned) first, then main take (hospice-manned).
    assert p.island[s_extra].tile == TileType.TOBACCO
    assert p.island[s_extra].colonist is False
    assert p.island[s_main].tile == TileType.SUGAR
    assert p.island[s_main].colonist is True
    assert g.state.colonist_supply == 4


# --------------------------------------------------------------------------- #
# last duty                                                                   #
# --------------------------------------------------------------------------- #


def test_last_duty_refills_faceup_to_num_players_plus_one():
    g = _new_game(num_players=4)
    _enter_settler(g)
    old_faceup = list(g.state.plantation_faceup)
    g.state.plantation_facedown.extend(
        [TileType.CORN] * 10
    )  # ensure plenty to draw

    settler_last_duty(g.state)

    assert len(g.state.plantation_faceup) == 5  # num_players + 1
    # The old face-up tiles were discarded.
    for t in old_faceup:
        assert t in g.state.plantation_discard


def test_last_duty_reshuffles_discard_when_facedown_drains():
    g = _new_game(num_players=4)
    _enter_settler(g)

    # Drain face-down to 1 tile; stock discard so the reshuffle path is forced.
    g.state.plantation_facedown[:] = [TileType.CORN]
    g.state.plantation_faceup[:] = []
    g.state.plantation_discard[:] = [TileType.INDIGO] * 6

    settler_last_duty(g.state)

    # Needed 5: 1 from facedown, then reshuffle the 6 discards and draw 4 more.
    assert len(g.state.plantation_faceup) == 5
    # All 6 discarded tiles went back into the stack: 4 drawn, 2 remain face-down.
    assert len(g.state.plantation_facedown) == 2


def test_last_duty_runs_end_to_end_when_all_players_act():
    g = _new_game(num_players=4)
    _enter_settler(g)
    # Make sure the row can be refilled.
    g.state.plantation_facedown.extend([TileType.CORN] * 10)

    # Every player passes; after the last, the role ends and the row refreshes.
    for _ in range(4):
        assert g.state.phase == Phase.SETTLER
        g.apply(Action.passing())

    assert g.state.phase == Phase.ROLE_SELECTION
    assert len(g.state.plantation_faceup) == 5
