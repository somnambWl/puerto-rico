"""Tests for the PROSPECTOR role (phases-task-08).

PROSPECTOR resolves INLINE during ROLE_SELECTION: the chooser collects the
placard's accumulated doubloons (the normal SELECT_ROLE transfer) PLUS one
doubloon from the bank (the prospector privilege), and there is NO follow phase
— control returns straight to ROLE_SELECTION (next chooser, or end of round).

These tests pin the spec properties from design/02 §The Prospector:
1. accumulated placard doubloons + 1 bank doubloon to the chooser; placard cleared,
2. no settler/mayor/... follow phase — phase is ROLE_SELECTION immediately after,
3. role_chooser advances (or the round ends) exactly like any other role,
4. the prospector placard is selectable in ROLE_SELECTION when untaken (4p: once).
"""

from __future__ import annotations

from puerto_rico.engine.actions import Action
from puerto_rico.engine.enums import DecisionType, Phase, Role
from puerto_rico.engine.game import Game
from puerto_rico.engine.state import GameConfig


def _new_game(num_players: int = 4, seed: int = 0, max_rounds: int = 50) -> Game:
    return Game(GameConfig(num_players=num_players, seed=seed, max_rounds=max_rounds))


def _placard(g: Game, role: Role):
    return next(pl for pl in g.state.placards if pl.role == role)


# --------------------------------------------------------------------------- #
# doubloon transfer: N accumulated + 1 from the bank                          #
# --------------------------------------------------------------------------- #


def test_prospector_grants_accumulated_plus_one_and_clears_placard():
    g = _new_game()
    chooser = g.state.phase_state.role_chooser
    prospector = _placard(g, Role.PROSPECTOR)
    prospector.doubloons = 4  # N accumulated doubloons on the placard
    before = g.state.players[chooser].doubloons

    g.apply(Action.select_role(Role.PROSPECTOR))

    # Chooser gains N + 1 (the +1 is the prospector privilege from the bank).
    assert g.state.players[chooser].doubloons == before + 4 + 1
    # Placard is marked taken by the chooser and its doubloon pile is cleared.
    assert prospector.taken_by == chooser
    assert prospector.doubloons == 0


def test_prospector_with_no_accumulated_doubloons_grants_exactly_one():
    g = _new_game()
    chooser = g.state.phase_state.role_chooser
    prospector = _placard(g, Role.PROSPECTOR)
    assert prospector.doubloons == 0  # fresh placard
    before = g.state.players[chooser].doubloons

    g.apply(Action.select_role(Role.PROSPECTOR))

    assert g.state.players[chooser].doubloons == before + 1


# --------------------------------------------------------------------------- #
# no follow phase: straight back to ROLE_SELECTION, chooser advanced           #
# --------------------------------------------------------------------------- #


def test_prospector_has_no_follow_phase():
    g = _new_game()
    g.apply(Action.select_role(Role.PROSPECTOR))

    # No settler/mayor/... follow phase was entered: we are already back at
    # ROLE_SELECTION, and there is no active role cursor lingering.
    assert g.state.phase == Phase.ROLE_SELECTION
    assert g.state.phase_state.active_role is None
    # Legal actions are SELECT_ROLE again (a fresh selection node), not a
    # follow-phase action set.
    assert all(a.type == DecisionType.SELECT_ROLE for a in g.legal_actions())


def test_prospector_advances_role_chooser_and_bumps_counter():
    g = _new_game()
    chooser = g.state.phase_state.role_chooser
    assert chooser == 0

    g.apply(Action.select_role(Role.PROSPECTOR))

    # The chooser took one role this round.
    assert g.state.players[chooser].roles_taken_this_round == 1
    # role_chooser advanced clockwise to the next player (4p: one role each).
    assert g.state.phase_state.role_chooser == 1
    assert g.current_player == 1


def test_prospector_as_last_pick_ends_the_round():
    g = _new_game()
    # Players 0..2 take stubbed roles (each enters a follow phase ended by PASS).
    for i, role in enumerate([Role.SETTLER, Role.BUILDER, Role.CRAFTSMAN]):
        assert g.state.phase_state.role_chooser == i
        g.apply(Action.select_role(role))
        while g.state.phase != Phase.ROLE_SELECTION:
            g.apply(Action.passing())

    # Player 3 takes prospector as the round's final pick -> end of round.
    assert g.state.phase_state.role_chooser == 3
    g.apply(Action.select_role(Role.PROSPECTOR))

    # End-of-round bookkeeping ran: governor rotated 0 -> 1, new round begins
    # at the new governor in ROLE_SELECTION.
    assert g.state.phase == Phase.ROLE_SELECTION
    assert g.state.governor == 1
    assert g.state.phase_state.role_chooser == 1
    # Counters reset for the new round.
    assert all(p.roles_taken_this_round == 0 for p in g.state.players)


# --------------------------------------------------------------------------- #
# placard presence + selectability                                            #
# --------------------------------------------------------------------------- #


def test_prospector_placard_exists_exactly_once_in_4p():
    g = _new_game()
    prospectors = [pl for pl in g.state.placards if pl.role == Role.PROSPECTOR]
    assert len(prospectors) == 1
    # 4-player base game: one placard per role -> 7 placards total.
    assert len(g.state.placards) == 7


def test_prospector_is_selectable_when_untaken():
    g = _new_game()
    roles = {a.role for a in g.legal_actions()}
    assert Role.PROSPECTOR in roles

    g.apply(Action.select_role(Role.PROSPECTOR))

    # Once taken, it is no longer offered in role selection.
    roles_after = {a.role for a in g.legal_actions()}
    assert Role.PROSPECTOR not in roles_after
