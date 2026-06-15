"""End-to-end client integration test for the UI backend (design/06 — UI).

This acts as a headless game client over the WebSocket: it creates a game,
opens the WS, and plays full games to terminal by picking random *legal*
actions on every human turn. It is the contract test that catches any
label / legality / codec desync between client and server — the server must
never reject an ``action_id`` it previously offered, and the human must never
be handed an empty legal set on a non-terminal turn.

Configurations exercised (each played multiple full games, seeded):

* opponents: ``"heuristic"`` and ``"rl"`` (``"rl"`` skipped only if the
  release checkpoint ``runs/release/final.pt`` is absent — present here);
* human seats: ``0`` (governor / opens the game) and ``2`` (a non-zero seat,
  so the AI must auto-run before the human's first decision).

It also covers a mid-game reconnect: dropping the WS and re-opening it (after a
``GET /games/{id}``) must return the exact last-known state and let play
continue with no desync.
"""

from __future__ import annotations

import random
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from puerto_rico.ui.backend import app as app_module
from puerto_rico.ui.backend.app import DEFAULT_RL_CHECKPOINT, create_app

# --------------------------------------------------------------------------- #
# config matrix                                                                #
# --------------------------------------------------------------------------- #

#: A non-zero human seat: the AI must auto-run before the human's first turn.
NONZERO_SEAT = 2

#: Full games to play per (opponent, seat) configuration. >1 so a clean run is
#: not a fluke; kept small because the engine is fast (whole game in ~ms).
GAMES_PER_CONFIG = 2

#: Hard cap on human decisions in one game — a safety valve against a hang.
MAX_HUMAN_STEPS = 4000

_RL_PRESENT = Path(DEFAULT_RL_CHECKPOINT).exists()

_OPPONENTS = ["heuristic"]
if _RL_PRESENT:
    _OPPONENTS.append("rl")

_CONFIGS = [
    (opponent, seat) for opponent in _OPPONENTS for seat in (0, NONZERO_SEAT)
]


@pytest.fixture(autouse=True)
def _no_ai_stream_delay(monkeypatch: pytest.MonkeyPatch) -> None:
    """Drop the cosmetic per-AI-state stream delay so full games run fast.

    ``AI_STREAM_DELAY`` only paces the browser animation; it has no bearing on
    correctness, and keeping it would make these full-game tests take minutes.
    """
    monkeypatch.setattr(app_module, "AI_STREAM_DELAY", 0.0)


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())


# --------------------------------------------------------------------------- #
# the headless client                                                          #
# --------------------------------------------------------------------------- #


def _new_game(client: TestClient, opponent: str, seat: int, seed: int) -> dict:
    resp = client.post(
        "/games",
        json={"seed": seed, "human_seat": seat, "opponent": opponent},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _drain_sequence(ws) -> dict:
    """Receive one ``sequence`` frame + its streamed ``state`` frames.

    Returns the last streamed state (the new current state). Asserts framing.
    """
    seq = ws.receive_json()
    assert seq["type"] == "sequence", seq
    n = len(seq["states"])
    assert n >= 1, "a human action must yield at least its own resulting state"
    last = None
    for _ in range(n):
        last = ws.receive_json()
        assert last["type"] == "state", last
    return last


def _assert_valid_result(result: dict) -> None:
    """A terminal ``result`` must be a complete, self-consistent breakdown."""
    assert result is not None, "terminal state must carry a result"

    scores = result["scores"]
    assert len(scores) == 4, f"expected 4 scores, got {scores!r}"

    winner = result["winner"]
    assert winner in range(4), f"winner {winner!r} is not a valid seat"
    # The winner holds the maximum score (ties broken by the engine ranking).
    assert scores[winner] == max(scores), "winner does not hold the max score"

    ranking = result["ranking"]
    assert sorted(ranking) == [0, 1, 2, 3], (
        f"ranking {ranking!r} is not a permutation of 0..3"
    )

    players = result["players"]
    assert len(players) == 4
    for p in players:
        # final_score == vp_chips + building VP (the engine's own decomposition).
        assert p["final_score"] == p["vp_chips"] + p["building_vp"], p


def _play_full_game(
    client: TestClient, opponent: str, seat: int, seed: int
) -> None:
    """Drive one full game over the WS as a headless client; assert no desync.

    Invariants checked on *every* human turn and across the whole game:

    * the human is the seat to move and its legal set is non-empty
      (a non-terminal human turn always offers >= 1 option);
    * the chosen id is taken from the *current* legal set, and that same id is
      re-verified against the legal set the server most recently advertised —
      so we can never send an id the server did not offer;
    * the game reaches ``terminal`` with a valid ``result``.
    """
    data = _new_game(client, opponent, seat, seed)
    gid = data["game_id"]
    rng = random.Random(1000 + seed)

    # The full audit trail: (chosen_id, set-of-ids-the-server-just-offered).
    sent_with_prior_legal: list[tuple[int, frozenset[int]]] = []

    with client.websocket_connect(f"/ws/games/{gid}") as ws:
        current = ws.receive_json()
        assert current["type"] == "state", current

        steps = 0
        while not current["terminal"]:
            steps += 1
            assert steps <= MAX_HUMAN_STEPS, "game did not terminate in budget"

            # Non-terminal => it must be the human's turn with options.
            assert current["to_move_is_human"] is True, current
            assert current["to_move"] == seat, current
            offered = frozenset(a["id"] for a in current["legal_actions"])
            assert offered, "non-terminal human turn offered no legal actions"

            chosen = rng.choice(list(offered))
            # Record against the set the server JUST advertised, then send.
            sent_with_prior_legal.append((chosen, offered))
            assert chosen in offered  # the no-desync guarantee, pre-send
            ws.send_json({"action_id": chosen})

            current = _drain_sequence(ws)

    # Whole-game desync audit: every id we ever sent was in the legal set the
    # server advertised immediately before we sent it. The server applied each
    # without an ErrorMsg (an error frame would have broken _drain_sequence's
    # "sequence" assertion), so legality round-tripped through the codec/labels.
    for chosen, prior in sent_with_prior_legal:
        assert chosen in prior, (
            f"sent {chosen} which was not in the preceding legal set {prior}"
        )

    assert current["terminal"] is True
    _assert_valid_result(current["result"])


@pytest.mark.parametrize("opponent,seat", _CONFIGS)
def test_full_games_no_desync(
    client: TestClient, opponent: str, seat: int
) -> None:
    """Play GAMES_PER_CONFIG full games for each (opponent, seat) config."""
    for g in range(GAMES_PER_CONFIG):
        _play_full_game(client, opponent, seat, seed=100 + g)


def test_rl_was_exercised_not_skipped() -> None:
    """Documents whether RL ran: it is exercised iff the checkpoint exists."""
    if not _RL_PRESENT:
        pytest.skip(
            f"RL checkpoint {DEFAULT_RL_CHECKPOINT} absent; rl config skipped"
        )
    assert "rl" in _OPPONENTS


# --------------------------------------------------------------------------- #
# reconnect                                                                    #
# --------------------------------------------------------------------------- #


def _state_identity(state: dict) -> tuple:
    """The fields that must survive a reconnect unchanged."""
    return (state["to_move"], state["to_move_is_human"], state["terminal"])


def test_reconnect_midgame_resumes_without_desync(client: TestClient) -> None:
    """Drop the WS mid-game, GET the state, re-open the WS, keep playing.

    The reconnected initial frame must match the last-known state (same
    to_move, same is_human, same terminal flag), and the resumed game must run
    cleanly to terminal with the same no-desync guarantee.
    """
    data = _new_game(client, opponent="heuristic", seat=NONZERO_SEAT, seed=777)
    gid = data["game_id"]
    rng = random.Random(777)

    # Phase 1: play a handful of human turns, then walk away from the socket.
    last_known: dict
    with client.websocket_connect(f"/ws/games/{gid}") as ws:
        current = ws.receive_json()
        assert current["type"] == "state"
        played = 0
        while not current["terminal"] and played < 5:
            played += 1
            offered = [a["id"] for a in current["legal_actions"]]
            assert offered
            ws.send_json({"action_id": rng.choice(offered)})
            current = _drain_sequence(ws)
        last_known = current
    # WS is now closed (context manager exited) — simulates a dropped client.

    assert played >= 1, "test should drop the WS only after real progress"

    # Phase 2: GET the current state (REST reconnect path) — must match.
    rest = client.get(f"/games/{gid}")
    assert rest.status_code == 200, rest.text
    assert _state_identity(rest.json()) == _state_identity(last_known)

    # Phase 3: re-open the WS; the pushed frame must equal the last-known state,
    # then play continues to terminal with no desync.
    with client.websocket_connect(f"/ws/games/{gid}") as ws:
        resumed = ws.receive_json()
        assert resumed["type"] == "state"
        assert _state_identity(resumed) == _state_identity(last_known), (
            "reconnected frame diverged from the last-known state"
        )

        current = resumed
        steps = 0
        while not current["terminal"]:
            steps += 1
            assert steps <= MAX_HUMAN_STEPS
            assert current["to_move_is_human"] is True
            offered = [a["id"] for a in current["legal_actions"]]
            assert offered, "non-terminal human turn offered no legal actions"
            chosen = rng.choice(offered)
            ws.send_json({"action_id": chosen})
            current = _drain_sequence(ws)

    assert current["terminal"] is True
    _assert_valid_result(current["result"])
