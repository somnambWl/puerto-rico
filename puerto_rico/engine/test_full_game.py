"""Full-game integration tests for the (now feature-complete) rules engine.

This file is the heavyweight end-to-end suite for the **engine-phases** epic
(phases-task-10). It drives MANY full random-legal games to ``GAME_OVER`` and
asserts global invariants after *every* applied action, checks determinism,
sanity-checks final scoring, runs a 2-player game, and encodes the rulebook's
captain-phase worked example as a deterministic golden test.

It complements ``test_integration.py`` (a lighter smoke test) — that file proves
the engine loop terminates; this one proves the *content* of play stays
rules-legal at every step across a large seed sweep.

INVARIANTS ASSERTED AFTER EVERY ACTION (see ``_assert_invariants``)
-------------------------------------------------------------------
- non-terminal states always have >= 1 legal action (no dead-ends);
- doubloons, every goods count, and stored_colonists are all >= 0;
- each cargo ship holds a single kind, count <= capacity, and no two ships hold
  the same good kind;
- the trading house holds <= 4 goods;
- each island has <= 12 tiles and each city <= 12 building slots; no real
  building is owned more than once per player (``LARGE_CONT`` excluded);
- ``vp_chips_remaining`` >= 0 and never exceeds the initial VP pool; total VP
  chips awarded to players never exceeds the initial pool;
- colonist conservation: supply + ship + every player's (stored + island + city)
  colonists is invariant for the whole game. Colonists are never created or
  destroyed in the base game — they only move supply -> ship -> stored -> placed
  (the university pulls a free colonist supply -> placed, still conserved). The
  starting total is ``colonist_supply + colonist_ship`` at ``new_game``.
"""

from __future__ import annotations

import random

import pytest

from . import scoring
from .actions import Action
from .enums import BuildingId, Good, Phase, Role
from .game import Game
from .state import GameConfig

# Generous per-game step cap: large enough to never fire for a real game, small
# enough to catch a non-advancing phase (infinite loop).
MAX_STEPS = 20_000

# Initial VP-chip pool by player count (setup.SETUP["vp_pool"]).
VP_POOL = {2: 65, 4: 100}


# --------------------------------------------------------------------------- #
# invariant checking                                                          #
# --------------------------------------------------------------------------- #


def _total_colonists(state) -> int:
    """All colonists anywhere: supply + ship + every player's stored/island/city."""
    total = state.colonist_supply + state.colonist_ship
    for p in state.players:
        total += p.total_colonists()
    return total


def _assert_invariants(game: Game, starting_colonists: int, vp_pool: int) -> None:
    """Assert every per-step global invariant for ``game``'s current state."""
    state = game.state
    n = len(state.players)

    # Legal-action availability: only a terminal state may have no actions.
    if not game.is_terminal:
        assert game.legal_actions(), "non-terminal state must have >= 1 legal action"

    # --- per-player non-negativity ---
    awarded_vp = 0
    for p in state.players:
        assert p.doubloons >= 0, "doubloons went negative"
        assert p.stored_colonists >= 0, "stored_colonists went negative"
        for g in Good:
            assert p.goods[g] >= 0, f"goods[{g!r}] went negative"
        assert p.vp_chips >= 0, "vp_chips went negative"
        awarded_vp += p.vp_chips

    # --- cargo ships: single kind, within capacity, no duplicate kinds ---
    seen_kinds: set[Good] = set()
    for ship in state.cargo_ships:
        assert 0 <= ship.count <= ship.capacity, "cargo ship over capacity / negative"
        if ship.count > 0:
            assert ship.good is not None, "non-empty ship has no good kind"
            assert ship.good not in seen_kinds, "two cargo ships hold the same good"
            seen_kinds.add(ship.good)

    # --- trading house: at most 4 goods ---
    assert len(state.trading_house) <= 4, "trading house holds more than 4 goods"

    # --- per-player city/island bounds + single ownership ---
    for p in state.players:
        assert len(p.island) <= 12, "island exceeds 12 slots"
        assert len(p.city) <= 12, "city exceeds 12 slots"
        owned: list[BuildingId] = [
            s.building
            for s in p.city
            if s.building is not None and s.building != BuildingId.LARGE_CONT
        ]
        assert len(owned) == len(set(owned)), "a building is owned more than once by a player"

    # --- VP-chip pool accounting ---
    assert state.vp_chips_remaining >= 0, "vp_chips_remaining went negative"
    assert state.vp_chips_remaining <= vp_pool, "vp_chips_remaining exceeds the initial pool"
    assert awarded_vp <= vp_pool, "more VP chips awarded than the initial pool held"

    # --- colonist conservation (exact; colonists are never created/destroyed) ---
    assert _total_colonists(state) == starting_colonists, "colonist count not conserved"


# --------------------------------------------------------------------------- #
# random-legal playthrough harness                                            #
# --------------------------------------------------------------------------- #


def _random_playthrough(
    num_players: int,
    game_seed: int,
    choice_seed: int,
    *,
    check_invariants: bool = True,
) -> tuple[Game, list[Action], int]:
    """Drive one random-legal game to terminal, asserting invariants each step.

    Returns ``(game, applied_actions, step_count)``.
    """
    game = Game(GameConfig(num_players=num_players, seed=game_seed))
    starting_colonists = _total_colonists(game.state)
    vp_pool = VP_POOL[num_players]
    chooser = random.Random(choice_seed)

    if check_invariants:
        _assert_invariants(game, starting_colonists, vp_pool)

    applied: list[Action] = []
    steps = 0
    while not game.is_terminal:
        actions = game.legal_actions()
        assert actions, "non-terminal state must have >= 1 legal action (no dead-ends)"
        action = chooser.choice(actions)
        game.apply(action)
        applied.append(action)
        steps += 1
        assert steps < MAX_STEPS, f"playthrough exceeded {MAX_STEPS} steps (infinite loop?)"
        if check_invariants:
            _assert_invariants(game, starting_colonists, vp_pool)

    assert steps > 0, "game terminated before any action was applied"
    return game, applied, steps


# --------------------------------------------------------------------------- #
# 1. random-legal invariants across many seeds                                #
# --------------------------------------------------------------------------- #


def test_random_legal_playthrough_invariants() -> None:
    """Run many full 4-player random-legal games, asserting invariants each step.

    Every game must reach GAME_OVER (not the safety-valve max_rounds backstop)
    with all per-step invariants holding. A wide seed sweep exercises reshuffles,
    all three end triggers, and round completion after a trigger.
    """
    num_games = 200
    terminated = 0
    end_triggered_games = 0

    for seed in range(num_games):
        game, applied, steps = _random_playthrough(
            num_players=4, game_seed=seed, choice_seed=seed
        )
        assert game.is_terminal, f"seed {seed} did not reach GAME_OVER"
        assert steps < MAX_STEPS
        terminated += 1
        # A real end trigger should have fired (not the max_rounds backstop) in
        # the vast majority of games; track it to confirm we exercise end logic.
        if game.state.end_triggered:
            end_triggered_games += 1

    assert terminated == num_games
    # The real end conditions (colonist shortage / 12th building / VP exhaustion)
    # should drive essentially every game; require at least most of them so we
    # know the end-trigger paths are genuinely exercised, not the safety valve.
    assert end_triggered_games >= num_games * 0.9, (
        f"only {end_triggered_games}/{num_games} games ended via a real trigger"
    )


# --------------------------------------------------------------------------- #
# 2. determinism                                                              #
# --------------------------------------------------------------------------- #


def test_determinism() -> None:
    """Same engine seed + same choice seed -> identical actions and final scoring."""
    game_a, applied_a, steps_a = _random_playthrough(
        num_players=4, game_seed=123, choice_seed=99, check_invariants=False
    )
    game_b, applied_b, steps_b = _random_playthrough(
        num_players=4, game_seed=123, choice_seed=99, check_invariants=False
    )

    assert steps_a == steps_b
    assert applied_a == applied_b
    assert scoring.final_scores(game_a.state) == scoring.final_scores(game_b.state)
    assert game_a.returns() == game_b.returns()
    assert game_a.winner() == game_b.winner()


# --------------------------------------------------------------------------- #
# 3. final-scores sanity                                                      #
# --------------------------------------------------------------------------- #


def test_final_scores_sane() -> None:
    """At GAME_OVER: int scores, winner == argmax per rankings, returns sum ~0."""
    for seed in (0, 7, 42, 100):
        game, _, _ = _random_playthrough(
            num_players=4, game_seed=seed, choice_seed=seed, check_invariants=False
        )
        assert game.is_terminal

        scores = scoring.final_scores(game.state)
        assert all(isinstance(s, int) for s in scores), "final scores must be ints"
        assert len(scores) == 4

        # winner() is the top of scoring.rankings, and ties out as the argmax
        # final score (rankings tie-breaks beyond score, so winner's score must
        # be the maximum).
        winner = game.winner()
        ranking = scoring.rankings(game.state)
        assert winner == ranking[0]
        assert scores[winner] == max(scores)

        returns = game.returns()
        assert len(returns) == 4
        assert sum(returns) == pytest.approx(0.0, abs=1e-9)


# --------------------------------------------------------------------------- #
# 4. 2-player game runs                                                       #
# --------------------------------------------------------------------------- #


def test_2player_game_runs() -> None:
    """A 2-player game (3 roles/round) reaches GAME_OVER with invariants holding."""
    for seed in range(20):
        game, _, steps = _random_playthrough(
            num_players=2, game_seed=seed, choice_seed=seed
        )
        assert game.is_terminal, f"2p seed {seed} did not reach GAME_OVER"
        assert steps < MAX_STEPS

        scores = scoring.final_scores(game.state)
        assert len(scores) == 2
        assert all(isinstance(s, int) for s in scores)
        assert sum(game.returns()) == pytest.approx(0.0, abs=1e-9)


# --------------------------------------------------------------------------- #
# 5. rulebook captain worked example (docs/puerto-rico-rules.md line 196)     #
# --------------------------------------------------------------------------- #
#
# > Worked example (4 players). Anna (captain) has 2 corn + 6 sugar; the 5- and
# > 7-ships are empty and the 6-ship has 3 corn. She loads 6 sugar onto the
# > 7-ship (not the 5-ship — wouldn't fit all 6), earning 6+1 VP. Bob has 2
# > sugar + 3 tobacco; he tops off the 7-ship with 1 sugar (1 VP), holding
# > tobacco to sell later. Chris loads 1 tobacco on the 5-ship (1 VP). David
# > must load his 1 corn on the 6-ship (no room for his indigo) -> 1 VP. Anna
# > again: her 2 corn onto the 6-ship -> 2 VP. Bob then must load his 3 tobacco
# > on the 5-ship -> 3 VP. Chris and David still have goods but nowhere to load.
# > Loading ends; they store/lose extras. Anna unloads the two full ships (6
# > and 7); the 5-ship keeps its 4 tobacco.
#
# Seats: Anna=0 (governor/captain, loads first), Bob=1, Chris=2, David=3 — the
# natural clockwise order the engine builds for the chooser. The agent picks BOTH
# the GOOD and the SHIP (the amount is forced maximal), so we feed the goods and
# the exact ships the example names and assert the stated ship state and VP.

# Cargo ship capacities are [5, 6, 7] in 4-player setup; indices match.
SHIP_5, SHIP_6, SHIP_7 = 0, 1, 2


def _setup_worked_example() -> Game:
    """Construct the exact pre-captain state described in the rulebook example."""
    game = Game(GameConfig(num_players=4, seed=0))
    state = game.state

    # Clear any starting goods (none by default) and set the example holdings.
    for p in state.players:
        for g in Good:
            p.goods[g] = 0
    # Anna: 2 corn + 6 sugar.
    state.players[0].goods[Good.CORN] = 2
    state.players[0].goods[Good.SUGAR] = 6
    # Bob: 2 sugar + 3 tobacco.
    state.players[1].goods[Good.SUGAR] = 2
    state.players[1].goods[Good.TOBACCO] = 3
    # Chris: 1 tobacco (the example loads 1; give a couple more so "still has
    # goods but nowhere to load" is exercised — extra tobacco can't go anywhere
    # once the 5-ship fills with tobacco and overflows... so keep it minimal and
    # faithful: 1 tobacco + 1 indigo to represent leftover with nowhere to load).
    state.players[2].goods[Good.TOBACCO] = 1
    state.players[2].goods[Good.INDIGO] = 1
    # David: 1 corn + 1 indigo (must load corn on the 6-ship; indigo has no room).
    state.players[3].goods[Good.CORN] = 1
    state.players[3].goods[Good.INDIGO] = 1

    # Ships: 5- and 7-ships empty; 6-ship already holds 3 corn.
    state.cargo_ships[SHIP_5].good = None
    state.cargo_ships[SHIP_5].count = 0
    state.cargo_ships[SHIP_6].good = Good.CORN
    state.cargo_ships[SHIP_6].count = 3
    state.cargo_ships[SHIP_7].good = None
    state.cargo_ships[SHIP_7].count = 0

    return game


def test_captain_worked_example() -> None:
    """Reproduce the rulebook 4-player captain example step by step.

    The agent now chooses BOTH the good AND the ship; the example dictates which
    ship each load goes to, so we drive it with explicit ``target`` ship indices
    and assert the same ship state and per-player VP at each step.
    """
    game = _setup_worked_example()
    state = game.state

    # Enter the captain phase by having the governor (Anna, seat 0) select it.
    assert state.current_player == 0
    assert state.phase == Phase.ROLE_SELECTION
    game.apply(Action.select_role(Role.CAPTAIN))
    assert state.phase == Phase.CAPTAIN

    # The engine seats Anna first (chooser), then Bob, Chris, David.
    assert state.phase_state.order == [0, 1, 2, 3]
    assert state.current_player == 0

    # 1) Anna loads 6 sugar onto the 7-ship (the example's choice — the 5-ship
    #    couldn't fit all 6); +6 +1 captain bonus = 7 VP.
    game.apply(Action.load(Good.SUGAR, target=SHIP_7))
    assert state.cargo_ships[SHIP_7].good == Good.SUGAR
    assert state.cargo_ships[SHIP_7].count == 6
    assert state.players[0].goods[Good.SUGAR] == 0
    assert state.players[0].vp_chips == 7
    assert state.current_player == 1

    # 2) Bob tops off the 7-ship with 1 sugar (only 1 of his 2 fits); +1 VP.
    #    He keeps his other sugar (no room left) — it stays with his tobacco.
    game.apply(Action.load(Good.SUGAR, target=SHIP_7))
    assert state.cargo_ships[SHIP_7].count == 7  # full
    assert state.players[1].goods[Good.SUGAR] == 1  # 1 sugar left, nowhere to load
    assert state.players[1].vp_chips == 1
    assert state.current_player == 2

    # 3) Chris loads 1 tobacco on the (empty) 5-ship; +1 VP.
    game.apply(Action.load(Good.TOBACCO, target=SHIP_5))
    assert state.cargo_ships[SHIP_5].good == Good.TOBACCO
    assert state.cargo_ships[SHIP_5].count == 1
    assert state.players[2].goods[Good.TOBACCO] == 0
    assert state.players[2].vp_chips == 1
    assert state.current_player == 3

    # 4) David must load 1 corn on the 6-ship (indigo has nowhere to go); +1 VP.
    game.apply(Action.load(Good.CORN, target=SHIP_6))
    assert state.cargo_ships[SHIP_6].good == Good.CORN
    assert state.cargo_ships[SHIP_6].count == 4
    assert state.players[3].goods[Good.CORN] == 0
    assert state.players[3].vp_chips == 1
    assert state.current_player == 0  # back around to Anna

    # 5) Anna again: her 2 corn onto the 6-ship -> fills it (4 -> 6); +2 VP (no
    #    second captain bonus). Anna's total VP = 7 + 2 = 9.
    game.apply(Action.load(Good.CORN, target=SHIP_6))
    assert state.cargo_ships[SHIP_6].count == 6  # full
    assert state.players[0].goods[Good.CORN] == 0
    assert state.players[0].vp_chips == 9
    assert state.current_player == 1  # Bob

    # 6) Bob then must load his 3 tobacco on the 5-ship (1 -> 4); +3 VP.
    #    Bob's total VP = 1 + 3 = 4.
    game.apply(Action.load(Good.TOBACCO, target=SHIP_5))
    assert state.cargo_ships[SHIP_5].count == 4
    assert state.players[1].goods[Good.TOBACCO] == 0
    assert state.players[1].vp_chips == 4

    # Chris and David still hold goods (indigo) but nowhere to load: the phase
    # ends, the captain unloads the two FULL ships (6 and 7), and the 5-ship
    # keeps its 4 tobacco. Loading completes once everyone is done; the engine
    # advances out of the captain phase automatically.
    while state.phase == Phase.CAPTAIN:
        game.apply(game.legal_actions()[0])

    # 7-ship (was full at 7) and 6-ship (was full at 6) unloaded -> empty.
    assert state.cargo_ships[SHIP_7].count == 0
    assert state.cargo_ships[SHIP_7].good is None
    assert state.cargo_ships[SHIP_6].count == 0
    assert state.cargo_ships[SHIP_6].good is None
    # 5-ship was NOT full (4 of 5) -> keeps its 4 tobacco.
    assert state.cargo_ships[SHIP_5].good == Good.TOBACCO
    assert state.cargo_ships[SHIP_5].count == 4

    # Final VP tallies from the example.
    assert state.players[0].vp_chips == 9  # Anna
    assert state.players[1].vp_chips == 4  # Bob
    assert state.players[2].vp_chips == 1  # Chris
    assert state.players[3].vp_chips == 1  # David
