"""Behavior tests for the public :class:`Game` facade.

These exercise the M1 surface: construction, role-selection legality, illegal
action rejection, clone independence, and a full play-out to terminal with sane
``returns()`` / ``winner()``. Per-phase rules live in the engine-phases epic.
"""

from __future__ import annotations

import pytest

from puerto_rico.engine.actions import Action
from puerto_rico.engine.enums import DecisionType, Phase, Role
from puerto_rico.engine.game import Game, IllegalAction
from puerto_rico.engine.state import GameConfig


def _new_game(num_players: int = 4, seed: int = 0) -> Game:
    return Game(GameConfig(num_players=num_players, seed=seed))


def test_new_game_initial_state():
    g = _new_game()
    assert g.state.phase == Phase.ROLE_SELECTION
    assert g.current_player == 0
    assert g.state.governor == 0
    assert len(g.state.players) == 4
    assert g.is_terminal is False


def test_legal_actions_role_selection_one_per_placard():
    g = _new_game()
    actions = g.legal_actions()
    # 4-player keeps 7 placards (all roles minus one prospector); none taken yet.
    assert len(g.state.placards) == 7
    assert len(actions) == 7
    assert all(a.type == DecisionType.SELECT_ROLE for a in actions)
    # One action per distinct available placard role.
    roles = {a.role for a in actions}
    assert roles == {pl.role for pl in g.state.placards}


def test_apply_illegal_action_raises():
    g = _new_game()
    # PASS is not legal during ROLE_SELECTION.
    with pytest.raises(IllegalAction):
        g.apply(Action.passing())


def test_apply_illegal_role_raises_when_role_absent():
    g = _new_game()
    # 4-player has no second prospector; selecting an absent role is illegal.
    # Take every available role until one becomes unavailable, then retry it.
    first = g.legal_actions()[0]
    g.apply(first)
    with pytest.raises(IllegalAction):
        g.apply(first)  # that placard is now taken_by someone


def test_select_role_transfers_doubloons_and_marks_taken():
    g = _new_game()
    # Seed an accumulated doubloon on the CRAFTSMAN placard. CRAFTSMAN is still a
    # stubbed follow phase (settler, mayor, and builder are now real multi-turn
    # phases — see test_settler.py / test_mayor.py / test_builder.py), so a single
    # PASS resolves it cleanly for this selection test.
    craftsman = next(pl for pl in g.state.placards if pl.role == Role.CRAFTSMAN)
    craftsman.doubloons = 2
    before = g.state.players[0].doubloons
    g.apply(Action.select_role(Role.CRAFTSMAN))
    assert craftsman.taken_by == 0
    assert craftsman.doubloons == 0
    assert g.state.players[0].doubloons == before + 2
    # Selecting a non-prospector role now ENTERS its follow phase (engine-phases
    # state machine); the chooser acts first. The phase is stubbed for now, so a
    # PASS resolves it and returns to ROLE_SELECTION with the next chooser.
    assert g.state.phase == Phase.CRAFTSMAN
    assert g.current_player == 0
    g.apply(Action.passing())
    assert g.state.phase == Phase.ROLE_SELECTION
    assert g.current_player == 1


def test_clone_independence():
    g = _new_game()
    clone = g.clone()
    clone.apply(clone.legal_actions()[0])
    # Original untouched: still nobody has taken a placard, still player 0.
    assert all(pl.taken_by is None for pl in g.state.placards)
    assert g.current_player == 0
    assert g.is_terminal is False


def test_play_to_terminal_returns_and_winner():
    g = _new_game()
    steps = 0
    while not g.is_terminal:
        actions = g.legal_actions()
        assert actions, "non-terminal state must have legal actions"
        g.apply(actions[0])
        steps += 1
        assert steps < 1000, "game failed to terminate"

    assert g.is_terminal is True
    assert g.legal_actions() == []

    rets = g.returns()
    assert len(rets) == 4
    # Rank-based payoffs are evenly spaced around 0 -> sum ~ 0.
    assert abs(sum(rets)) < 1e-9

    w = g.winner()
    assert w is not None
    assert 0 <= w < 4


def test_returns_zeros_when_not_terminal():
    g = _new_game()
    assert g.returns() == [0.0, 0.0, 0.0, 0.0]
    assert g.winner() is None


def test_public_view_delegates():
    g = _new_game()
    view = g.public_view(perspective=0)
    assert view["perspective"] == 0
    assert view["phase"] == int(Phase.ROLE_SELECTION)
    assert len(view["players"]) == 4
