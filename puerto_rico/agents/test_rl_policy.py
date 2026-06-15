"""Tests for :class:`~puerto_rico.agents.rl_policy.RLPolicy`.

Test checkpoint
---------------
We build the checkpoint artifact **directly** (a dict matching the schema in
``training/ppo.py``: ``format``, ``version``, ``codec``, ``model_state``,
``obs_dim``, ``n_actions``, ``hidden``, ``config``, ``iteration``) from a freshly
initialized :class:`MaskedActorCritic` state_dict and ``torch.save`` it to
``tmp_path/final.pt``. This is faster and more isolated than running a real
training iteration — RLPolicy only needs a schema-valid artifact, and these tests
verify the *load + inference* path, not training quality. (The trainer's own
``save_checkpoint`` is exercised by the training tests.)
"""

from __future__ import annotations

import time

import pytest
import torch

from puerto_rico.agents.rl_policy import RLPolicy
from puerto_rico.engine.game import Game
from puerto_rico.engine.state import GameConfig
from puerto_rico.env import action_codec
from puerto_rico.env.action_codec import N_ACTIONS, to_int
from puerto_rico.env.obs_codec import OBS_LEN
from puerto_rico.training.model import MaskedActorCritic

NUM_PLAYERS = 4
HIDDEN = (32, 32)  # tiny torso: fast to build / run; load path is identical.


def _build_checkpoint(path, *, seed: int = 0, iteration="final"):
    """Write a schema-valid RLPolicy artifact from a fresh net to ``path``."""
    torch.manual_seed(seed)
    net = MaskedActorCritic(OBS_LEN, N_ACTIONS, HIDDEN)
    artifact = {
        "format": "puerto_rico.rl_policy",
        "version": 1,
        "codec": {"obs_codec": 1, "action_codec": 1},
        "model_state": net.state_dict(),
        "obs_dim": OBS_LEN,
        "n_actions": N_ACTIONS,
        "hidden": list(HIDDEN),
        "config": {"num_players": NUM_PLAYERS},
        "iteration": iteration,
    }
    torch.save(artifact, path)
    return path


@pytest.fixture
def checkpoint(tmp_path):
    return _build_checkpoint(tmp_path / "final.pt")


def _new_game(seed: int) -> Game:
    return Game(GameConfig(num_players=NUM_PLAYERS, seed=seed))


# --------------------------------------------------------------------------- #
# load                                                                        #
# --------------------------------------------------------------------------- #


def test_loads_without_trainer_import():
    """Loading + serving must not import the trainer loop or RLlib.

    Run in a fresh subprocess so we can assert ``training.ppo`` / ``ray`` never
    get imported as a side effect of building and using an RLPolicy.
    """
    import subprocess
    import sys
    import tempfile

    code = """
import sys, tempfile, os
import torch
from puerto_rico.training.model import MaskedActorCritic
from puerto_rico.env.obs_codec import OBS_LEN
from puerto_rico.env.action_codec import N_ACTIONS

d = tempfile.mkdtemp()
p = os.path.join(d, "final.pt")
net = MaskedActorCritic(OBS_LEN, N_ACTIONS, (32, 32))
torch.save({
    "format": "puerto_rico.rl_policy", "version": 1,
    "codec": {"obs_codec": 1, "action_codec": 1},
    "model_state": net.state_dict(),
    "obs_dim": OBS_LEN, "n_actions": N_ACTIONS, "hidden": [32, 32],
    "config": {}, "iteration": "final",
}, p)

from puerto_rico.agents.rl_policy import RLPolicy
from puerto_rico.engine.game import Game
from puerto_rico.engine.state import GameConfig

policy = RLPolicy(p)
game = Game(GameConfig(num_players=4, seed=1))
policy.act(game)

assert "puerto_rico.training.ppo" not in sys.modules, "trainer loop imported!"
assert "ray" not in sys.modules, "ray imported!"
assert "puerto_rico.training.rollout" not in sys.modules, "rollout imported!"
print("OK")
"""
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as fh:
        fh.write(code)
        script = fh.name
    result = subprocess.run(
        [sys.executable, script], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "OK" in result.stdout


def test_load_fields(checkpoint):
    policy = RLPolicy(checkpoint)
    assert policy.obs_dim == OBS_LEN
    assert policy.n_actions == N_ACTIONS
    assert policy.hidden == HIDDEN


def test_from_checkpoint_factory(checkpoint):
    policy = RLPolicy.from_checkpoint(checkpoint, deterministic=False)
    assert policy.deterministic is False


def test_rejects_bad_format(tmp_path):
    bad = tmp_path / "bad.pt"
    torch.save({"format": "not_us", "version": 1}, bad)
    with pytest.raises(ValueError, match="format"):
        RLPolicy(bad)


def test_rejects_bad_version(tmp_path):
    net = MaskedActorCritic(OBS_LEN, N_ACTIONS, HIDDEN)
    bad = tmp_path / "v99.pt"
    torch.save(
        {
            "format": "puerto_rico.rl_policy",
            "version": 99,
            "model_state": net.state_dict(),
            "obs_dim": OBS_LEN,
            "n_actions": N_ACTIONS,
            "hidden": list(HIDDEN),
        },
        bad,
    )
    with pytest.raises(ValueError, match="version"):
        RLPolicy(bad)


# --------------------------------------------------------------------------- #
# legality                                                                    #
# --------------------------------------------------------------------------- #


def test_act_returns_legal_action_across_states(checkpoint):
    policy = RLPolicy(checkpoint, deterministic=True)
    illegal = 0
    states_checked = 0
    for g in range(8):
        game = _new_game(seed=1000 + g)
        steps = 0
        while not game.is_terminal and steps < 5000:
            action = policy.act(game)
            legal = game.legal_actions()
            if action not in legal:
                illegal += 1
            states_checked += 1
            game.apply(action, validate=False)
            steps += 1
    assert states_checked > 100
    assert illegal == 0


def test_full_game_all_rl_seats_completes(checkpoint):
    policy = RLPolicy(checkpoint, deterministic=False)
    game = _new_game(seed=42)
    steps = 0
    while not game.is_terminal and steps < 10000:
        action = policy.act(game)
        assert action in game.legal_actions()
        game.apply(action, validate=False)
        steps += 1
    assert game.is_terminal


# --------------------------------------------------------------------------- #
# determinism                                                                 #
# --------------------------------------------------------------------------- #


def test_deterministic_is_reproducible(checkpoint):
    p1 = RLPolicy(checkpoint, deterministic=True)
    p2 = RLPolicy(checkpoint, deterministic=True)
    # Same state -> same action, repeatedly, for both fresh instances.
    for g in range(4):
        game = _new_game(seed=7000 + g)
        steps = 0
        while not game.is_terminal and steps < 200:
            a1 = p1.act_id(game)
            a2 = p1.act_id(game)  # same instance, no state change -> identical
            a3 = p2.act_id(game)  # separate instance, same weights -> identical
            assert a1 == a2 == a3
            game.apply(action_codec.from_int(a1, game.state), validate=False)
            steps += 1


def test_stochastic_is_legal_and_can_vary(checkpoint):
    policy = RLPolicy(checkpoint, deterministic=False)
    torch.manual_seed(0)
    # Drive to a state with several legal actions, then sample many times.
    game = _new_game(seed=3)
    chosen = None
    while not game.is_terminal:
        if len(game.legal_actions()) >= 3:
            chosen = game
            break
        a = policy.act(game)
        game.apply(a, validate=False)
    assert chosen is not None
    legal_ids = {to_int(a) for a in chosen.legal_actions()}
    seen = set()
    for _ in range(50):
        aid = policy.act_id(chosen)
        assert aid in legal_ids  # always legal
        seen.add(aid)
    # Stochastic sampling should produce more than one distinct action here.
    assert len(seen) >= 2


def test_per_call_override(checkpoint):
    policy = RLPolicy(checkpoint, deterministic=False)
    game = _new_game(seed=11)
    while len(game.legal_actions()) < 3 and not game.is_terminal:
        game.apply(policy.act(game, deterministic=True), validate=False)
    a1 = policy.act_id(game, deterministic=True)
    a2 = policy.act_id(game, deterministic=True)
    assert a1 == a2  # forced deterministic despite instance default


# --------------------------------------------------------------------------- #
# act_id / act parity + speed                                                 #
# --------------------------------------------------------------------------- #


def test_act_id_matches_to_int_of_act(checkpoint):
    policy = RLPolicy(checkpoint, deterministic=True)
    for g in range(4):
        game = _new_game(seed=500 + g)
        steps = 0
        while not game.is_terminal and steps < 300:
            action = policy.act(game)
            aid = policy.act_id(game)
            assert to_int(action) == aid
            game.apply(action, validate=False)
            steps += 1


def test_inference_speed_under_100ms(checkpoint):
    policy = RLPolicy(checkpoint, deterministic=True)
    game = _new_game(seed=99)
    # Warm up.
    policy.act(game)
    n = 0
    t0 = time.perf_counter()
    while not game.is_terminal and n < 300:
        action = policy.act(game)
        game.apply(action, validate=False)
        n += 1
    elapsed = time.perf_counter() - t0
    avg_ms = (elapsed / max(1, n)) * 1000.0
    assert avg_ms < 100.0, f"avg act() {avg_ms:.2f}ms exceeds 100ms"
