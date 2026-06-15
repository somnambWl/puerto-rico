"""Tests for the UI backend: schemas, labeling, session, REST, and WebSocket."""

from __future__ import annotations

import random
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from puerto_rico.engine.actions import Action
from puerto_rico.engine.enums import BuildingId, DecisionType, Good, Role, TileType
from puerto_rico.engine.game import Game
from puerto_rico.engine.state import GameConfig
from puerto_rico.ui.backend import labels
from puerto_rico.ui.backend.app import DEFAULT_RL_CHECKPOINT, create_app

# --------------------------------------------------------------------------- #
# helpers                                                                      #
# --------------------------------------------------------------------------- #


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())


def _new_game(client: TestClient, opponent: str = "heuristic", seed: int = 7) -> dict:
    resp = client.post(
        "/games", json={"seed": seed, "human_seat": 0, "opponent": opponent}
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


# --------------------------------------------------------------------------- #
# labels                                                                       #
# --------------------------------------------------------------------------- #


def test_label_action_covers_each_decision_type() -> None:
    game = Game(GameConfig(num_players=4, seed=1))

    # ROLE_SELECTION is the opening phase: SELECT_ROLE labels read from the game.
    role_label = labels.label_action(Action.select_role(Role.SETTLER), game)
    assert "Settler" in role_label
    assert labels.label_action_kind(Action.select_role(Role.SETTLER)) == "role"

    tile_label = labels.label_action(Action.take_tile(TileType.INDIGO), game)
    assert "Indigo" in tile_label and "plantation" in tile_label
    assert labels.label_action_kind(Action.take_tile(TileType.INDIGO)) == "tile"

    assert labels.label_action(Action.take_tile(TileType.QUARRY), game) == "Take Quarry"

    build_label = labels.label_action(Action.build(BuildingId.COFFEE_ROASTER), game)
    assert "Coffee Roaster" in build_label and "cost" in build_label
    assert labels.label_action_kind(Action.build(BuildingId.COFFEE_ROASTER)) == "build"

    colonist_label = labels.label_action(Action.place_colonist(0), game)
    assert "colonist" in colonist_label.lower()
    assert labels.label_action_kind(Action.place_colonist(0)) == "colonist"

    store_label = labels.label_action(Action.place_colonist(-1), game)
    assert "storage" in store_label.lower()

    sell_label = labels.label_action(Action.sell(Good.COFFEE), game)
    assert sell_label == "Sell Coffee"
    assert labels.label_action_kind(Action.sell(Good.COFFEE)) == "sell"

    ship_label = labels.label_action(Action.load(Good.TOBACCO), game)
    assert "Tobacco" in ship_label
    assert labels.label_action_kind(Action.load(Good.TOBACCO)) == "ship"

    wharf_label = labels.label_action(
        Action(DecisionType.LOAD, good=Good.SUGAR, choice=1), game
    )
    assert "Wharf" in wharf_label and "Sugar" in wharf_label

    choose_label = labels.label_action(
        Action(DecisionType.CHOOSE, good=Good.CORN), game
    )
    assert "Corn" in choose_label
    assert labels.label_action_kind(Action(DecisionType.CHOOSE, good=Good.CORN)) == "choose"

    assert labels.label_action(Action.passing(), game) == "Pass"
    assert labels.label_action_kind(Action.passing()) == "pass"


# --------------------------------------------------------------------------- #
# REST                                                                         #
# --------------------------------------------------------------------------- #


def test_post_games_returns_initial_state(client: TestClient) -> None:
    data = _new_game(client)
    assert "game_id" in data
    state = data["state"]
    # human_seat=0 is the governor / first chooser, so it is the human's turn.
    assert state["to_move_is_human"] is True
    assert state["terminal"] is False
    assert state["result"] is None
    legal = state["legal_actions"]
    assert len(legal) > 0
    for a in legal:
        assert set(a) == {"id", "label", "kind"}
        assert isinstance(a["id"], int)
        assert isinstance(a["label"], str) and a["label"]
    # Opening decision is role selection.
    assert all(a["kind"] == "role" for a in legal)
    assert any("Take role" in a["label"] for a in legal)


def test_get_game_reconnect_and_404(client: TestClient) -> None:
    data = _new_game(client)
    gid = data["game_id"]

    r1 = client.get(f"/games/{gid}")
    r2 = client.get(f"/games/{gid}")
    assert r1.status_code == 200 and r2.status_code == 200
    # Read-only: two reads return the same to_move (no mutation).
    assert r1.json()["to_move"] == r2.json()["to_move"]

    assert client.get("/games/does-not-exist").status_code == 404


# --------------------------------------------------------------------------- #
# WebSocket                                                                    #
# --------------------------------------------------------------------------- #


def test_ws_initial_state_and_one_step(client: TestClient) -> None:
    data = _new_game(client)
    gid = data["game_id"]

    with client.websocket_connect(f"/ws/games/{gid}") as ws:
        first = ws.receive_json()
        assert first["type"] == "state"
        assert first["to_move_is_human"] is True
        legal_ids = [a["id"] for a in first["legal_actions"]]
        assert legal_ids

        ws.send_json({"action_id": legal_ids[0]})

        seq = ws.receive_json()
        assert seq["type"] == "sequence"
        assert len(seq["states"]) >= 1
        # Drain the streamed per-state frames for this sequence.
        for _ in seq["states"]:
            frame = ws.receive_json()
            assert frame["type"] == "state"


def test_ws_illegal_action_then_recovers(client: TestClient) -> None:
    data = _new_game(client)
    gid = data["game_id"]

    with client.websocket_connect(f"/ws/games/{gid}") as ws:
        first = ws.receive_json()
        legal_ids = {a["id"] for a in first["legal_actions"]}

        # Find an id that is NOT legal right now.
        illegal = next(i for i in range(82) if i not in legal_ids)
        ws.send_json({"action_id": illegal})
        err = ws.receive_json()
        assert err["type"] == "error"

        # A subsequent valid action still works (no desync).
        ws.send_json({"action_id": next(iter(legal_ids))})
        seq = ws.receive_json()
        assert seq["type"] == "sequence"


def _play_full_game_over_ws(client: TestClient, opponent: str) -> dict:
    """Play a full game via the WS, picking random legal human actions.

    Asserts every action sent was in the prior legal set (no desync). Returns
    the final state frame.
    """
    data = _new_game(client, opponent=opponent, seed=123)
    gid = data["game_id"]
    rng = random.Random(42)

    with client.websocket_connect(f"/ws/games/{gid}") as ws:
        current = ws.receive_json()
        assert current["type"] == "state"

        for _ in range(2000):
            if current["terminal"]:
                break
            assert current["to_move_is_human"] is True
            legal = current["legal_actions"]
            legal_ids = {a["id"] for a in legal}
            assert legal_ids, "human turn but no legal actions offered"

            chosen = rng.choice(list(legal_ids))
            assert chosen in legal_ids  # only ever send a previously-legal id
            ws.send_json({"action_id": chosen})

            seq = ws.receive_json()
            assert seq["type"] == "sequence"
            # Drain the streamed states; the last one is the new current state.
            last = None
            for _ in seq["states"]:
                last = ws.receive_json()
                assert last["type"] == "state"
            current = last
        else:  # pragma: no cover - safety valve
            pytest.fail("game did not terminate within the step budget")

    return current


def test_ws_full_game_heuristic(client: TestClient) -> None:
    final = _play_full_game_over_ws(client, "heuristic")
    assert final["terminal"] is True
    result = final["result"]
    assert result is not None
    assert "scores" in result and len(result["scores"]) == 4
    assert result["winner"] in range(4)
    assert len(result["players"]) == 4
    for p in result["players"]:
        assert p["final_score"] == p["vp_chips"] + p["building_vp"]


def test_ws_full_game_rl_or_fallback(client: TestClient) -> None:
    # Whether or not the checkpoint exists, a full game must run cleanly:
    # RLPolicy when present, heuristic fallback otherwise.
    final = _play_full_game_over_ws(client, "rl")
    assert final["terminal"] is True
    assert final["result"] is not None
    # Sanity: just confirm the checkpoint path constant is the release one.
    assert DEFAULT_RL_CHECKPOINT.endswith("final.pt")


def test_rl_checkpoint_presence_note() -> None:
    # Informational: the release checkpoint is expected at this path.
    # The fallback test above covers the missing-checkpoint case implicitly.
    _ = Path(DEFAULT_RL_CHECKPOINT)
