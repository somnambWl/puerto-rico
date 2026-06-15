"""Tests for the round/phase state machine (phases-task-01).

Covers role-selection legality + doubloon transfer, ``role_chooser`` rotation,
end-of-round bookkeeping (doubloons on unused placards, governor rotation,
resets), ``roles_per_round`` per player count, the ``end_triggered`` -> GAME_OVER
transition, and the ``max_rounds`` safety valve guaranteeing termination.
"""

from __future__ import annotations

import random

from puerto_rico.engine.actions import Action
from puerto_rico.engine.enums import DecisionType, Phase, Role
from puerto_rico.engine.game import Game
from puerto_rico.engine.phases import roles_per_round
from puerto_rico.engine.state import GameConfig


def _new_game(num_players: int = 4, seed: int = 0, max_rounds: int = 50) -> Game:
    return Game(GameConfig(num_players=num_players, seed=seed, max_rounds=max_rounds))


# --------------------------------------------------------------------------- #
# roles_per_round                                                             #
# --------------------------------------------------------------------------- #


def test_roles_per_round_4p_is_one():
    g = _new_game(num_players=4)
    assert roles_per_round(g.state) == 1


def test_roles_per_round_2p_is_three():
    g = _new_game(num_players=2)
    assert roles_per_round(g.state) == 3


# --------------------------------------------------------------------------- #
# role selection legality + doubloon transfer                                 #
# --------------------------------------------------------------------------- #


def test_role_selection_legal_actions_are_untaken_placards():
    g = _new_game()
    actions = g.legal_actions()
    assert all(a.type == DecisionType.SELECT_ROLE for a in actions)
    available = {pl.role for pl in g.state.placards if pl.taken_by is None}
    assert {a.role for a in actions} == available

    # After taking one role and returning to selection, that placard is gone.
    g.apply(Action.select_role(Role.PROSPECTOR))  # prospector resolves inline
    assert g.state.phase == Phase.ROLE_SELECTION
    roles_now = {a.role for a in g.legal_actions()}
    assert Role.PROSPECTOR not in roles_now


def test_select_role_transfers_accumulated_doubloons():
    g = _new_game()
    settler = next(pl for pl in g.state.placards if pl.role == Role.SETTLER)
    settler.doubloons = 3
    before = g.state.players[0].doubloons

    g.apply(Action.select_role(Role.SETTLER))
    assert settler.taken_by == 0
    assert settler.doubloons == 0
    assert g.state.players[0].doubloons == before + 3


def test_prospector_resolves_inline_with_bank_doubloon():
    g = _new_game()
    prospector = next(pl for pl in g.state.placards if pl.role == Role.PROSPECTOR)
    prospector.doubloons = 2
    before = g.state.players[0].doubloons

    g.apply(Action.select_role(Role.PROSPECTOR))
    # +2 accumulated placard doubloons +1 prospector privilege from the bank.
    assert g.state.players[0].doubloons == before + 3
    # No follow phase: back to role selection with the next chooser.
    assert g.state.phase == Phase.ROLE_SELECTION


# --------------------------------------------------------------------------- #
# role_chooser rotation                                                       #
# --------------------------------------------------------------------------- #


def _resolve_role(g: Game, role: Role) -> None:
    """Select ``role`` and resolve its follow phase by passing through every turn.

    Prospector resolves inline during selection. Other roles enter a follow
    phase: stubbed roles end after one PASS, while real phases (e.g. settler)
    give each player a turn. PASS at every decision until the phase ends, which
    is role-agnostic and works for both stubs and real phases.
    """
    g.apply(Action.select_role(role))
    if role == Role.PROSPECTOR:
        return
    # Follow phase: PASS through every player's turn until the role ends.
    assert g.state.phase != Phase.ROLE_SELECTION
    follow = g.state.phase
    guard = 0
    while g.state.phase == follow:
        guard += 1
        assert guard < 50
        g.apply(Action.passing())


def test_role_chooser_advances_clockwise_after_a_pick():
    g = _new_game()
    assert g.state.phase_state.role_chooser == 0
    # Pick a stubbed role: settler enters its follow phase, PASS ends it.
    _resolve_role(g, Role.SETTLER)
    assert g.state.phase == Phase.ROLE_SELECTION
    assert g.state.phase_state.role_chooser == 1
    assert g.current_player == 1


def test_full_4p_round_triggers_end_of_round():
    g = _new_game()
    untaken_roles = [Role.MAYOR, Role.TRADER, Role.PROSPECTOR]
    taken_roles = [Role.SETTLER, Role.BUILDER, Role.CRAFTSMAN, Role.CAPTAIN]

    # Each of the 4 players takes one (stubbed) role, clockwise from governor 0.
    for i, role in enumerate(taken_roles):
        assert g.state.phase_state.role_chooser == i
        _resolve_role(g, role)

    # Round complete -> end-of-round bookkeeping ran.
    # Governor rotated 0 -> 1; new round started at the new governor.
    assert g.state.governor == 1
    assert g.state.phase == Phase.ROLE_SELECTION
    assert g.state.phase_state.role_chooser == 1
    assert g.current_player == 1
    assert g.state.round_number == 1

    # Untaken placards each gained exactly 1 doubloon.
    for pl in g.state.placards:
        if pl.role in untaken_roles:
            assert pl.doubloons == 1
        else:
            assert pl.doubloons == 0

    # All placards reset to available; per-player round counters reset.
    assert all(pl.taken_by is None for pl in g.state.placards)
    assert all(p.roles_taken_this_round == 0 for p in g.state.players)


def test_2p_each_player_takes_three_roles_before_round_ends():
    g = _new_game(num_players=2)
    # 6 selections (3 each) end the round; 1 placard remains untaken.
    selections = 0
    start_round = g.state.round_number
    guard = 0
    while g.state.round_number == start_round:
        guard += 1
        assert guard < 100
        if g.state.phase == Phase.ROLE_SELECTION:
            g.apply(g.legal_actions()[0])  # a SELECT_ROLE
            selections += 1
        else:
            g.apply(g.legal_actions()[0])  # resolve the follow phase

    assert g.state.round_number == start_round + 1
    # Both players took exactly 3 roles -> 6 selections this round.
    assert selections == 6
    assert g.state.governor == 1  # rotated from 0


# --------------------------------------------------------------------------- #
# end_triggered -> GAME_OVER                                                   #
# --------------------------------------------------------------------------- #


def test_end_triggered_during_round_transitions_to_game_over():
    g = _new_game()
    # Resolve player 0's role, then set the end trigger mid-round.
    _resolve_role(g, Role.SETTLER)  # player 0
    g.state.end_triggered = True

    # Resolve the rest of the round (players 1..3). The round must still finish,
    # and only THEN transition to GAME_OVER (not start a new round).
    guard = 0
    while not g.is_terminal:
        guard += 1
        assert guard < 50
        if g.state.phase == Phase.ROLE_SELECTION:
            g.apply(g.legal_actions()[0])  # a SELECT_ROLE
        else:
            g.apply(g.legal_actions()[0])  # resolve the follow phase

    assert g.state.phase == Phase.GAME_OVER
    assert g.is_terminal is True
    assert g.legal_actions() == []
    # The triggering round completed (round_number incremented once) and the
    # game ended before a new round started.
    assert g.state.round_number == 1


# --------------------------------------------------------------------------- #
# safety valve / termination                                                  #
# --------------------------------------------------------------------------- #


def test_max_rounds_safety_valve_forces_game_over():
    g = _new_game(max_rounds=3)
    steps = 0
    while not g.is_terminal:
        g.apply(g.legal_actions()[0])
        steps += 1
        assert steps < 1000
    # Forced over after exactly max_rounds completed rounds.
    assert g.state.round_number == 3
    assert g.state.phase == Phase.GAME_OVER


def test_random_playthrough_terminates():
    g = _new_game(max_rounds=50)
    chooser = random.Random(123)
    steps = 0
    while not g.is_terminal:
        actions = g.legal_actions()
        assert actions, "non-terminal state must have legal actions"
        g.apply(chooser.choice(actions))
        steps += 1
        assert steps < 100_000
    assert g.is_terminal is True
    # Terminates within the safety-valve cap. With the real mayor phase live, the
    # colonist-shortage end trigger may fire before the cap (round_number <= 50).
    assert g.state.round_number <= 50
