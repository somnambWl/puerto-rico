"""Tests for the ``Agent`` protocol and ``RandomAgent`` (agents-task-01).

Covers, against the real :class:`PuertoRicoAEC` env:
  * ``act`` always returns a mask-legal id over many sampled states,
  * a full 4-player game driven by 4 ``RandomAgent``s completes with zero mask
    violations,
  * reproducibility: same seed -> same choices,
  * win-rate sanity: each seat wins ~25% over many fast games.
"""

from __future__ import annotations

import numpy as np
import pytest

from puerto_rico.agents import Agent, RandomAgent
from puerto_rico.env import action_codec
from puerto_rico.env.pettingzoo_env import PuertoRicoAEC


def _new_env(seed: int) -> PuertoRicoAEC:
    env = PuertoRicoAEC(config={"num_players": 4, "seed": seed})
    env.reset()
    return env


def test_protocol_runtime_checkable() -> None:
    assert isinstance(RandomAgent(seed=0), Agent)


def test_act_never_returns_illegal_over_many_states() -> None:
    """Step the env with the agent itself; every chosen id must be mask-legal."""
    agent = RandomAgent(seed=123)
    checked = 0
    for game_seed in range(20):
        env = _new_env(game_seed)
        for agent_name in env.agent_iter():
            obs, _reward, term, trunc, _info = env.last()
            if term or trunc:
                action = None
            else:
                mask = obs["action_mask"]
                action = agent.act(obs)
                assert 0 <= action < action_codec.N_ACTIONS
                assert mask[action] == 1, "agent returned a masked-illegal id"
                checked += 1
            env.step(action)
    assert checked > 0


def test_empty_mask_raises() -> None:
    agent = RandomAgent(seed=0)
    obs = {"action_mask": np.zeros(action_codec.N_ACTIONS, dtype=np.int8)}
    with pytest.raises(ValueError):
        agent.act(obs)


def _play_game(seed: int, agents: list[RandomAgent]) -> int:
    """Drive a full 4-player AEC game; return the winning seat."""
    env = PuertoRicoAEC(config={"num_players": 4, "seed": seed})
    env.reset()
    for a in agents:
        a.reset()
    for agent_name in env.agent_iter():
        obs, _reward, term, trunc, _info = env.last()
        if term or trunc:
            action = None
        else:
            seat = int(agent_name.split("_")[1])
            action = agents[seat].act(obs)
            # Mask check inline so any violation fails the game loop.
            assert obs["action_mask"][action] == 1
        env.step(action)
    assert env.game.is_terminal
    return env.game.winner()


def test_full_game_completes_without_violations() -> None:
    agents = [RandomAgent(seed=s) for s in range(4)]
    winner = _play_game(seed=7, agents=agents)
    assert 0 <= winner < 4


def test_reproducibility_same_seed_same_choices() -> None:
    """Two agents with the same seed make identical choices on identical obs."""
    a1 = RandomAgent(seed=999)
    a2 = RandomAgent(seed=999)
    env = _new_env(42)
    choices1: list[int] = []
    choices2: list[int] = []
    for agent_name in env.agent_iter():
        obs, _reward, term, trunc, _info = env.last()
        if term or trunc:
            action = None
        else:
            action = a1.act(obs)
            # Second agent sees the exact same obs (recomputed below via observe).
            choices1.append(action)
            choices2.append(a2.act(obs))
        env.step(action)
    assert choices1 == choices2


def test_reproducibility_full_run_deterministic() -> None:
    """A whole game replayed with identically-seeded agents is identical."""
    w1 = _play_game(seed=11, agents=[RandomAgent(seed=s) for s in range(4)])
    w2 = _play_game(seed=11, agents=[RandomAgent(seed=s) for s in range(4)])
    assert w1 == w2


def test_winrate_sanity() -> None:
    """4 RandomAgents over many games: each seat wins within a wide band."""
    n_games = 200
    wins = [0, 0, 0, 0]
    for g in range(n_games):
        # Distinct per-seat seeds per game so seats are not symmetric clones.
        agents = [RandomAgent(seed=1000 * g + s) for s in range(4)]
        winner = _play_game(seed=g, agents=agents)
        wins[winner] += 1
    rates = [w / n_games for w in wins]
    # Puerto Rico has genuine seat asymmetry (governor/first-player advantage), and
    # 200 games is noisy, so this is a loose sanity band: no seat dominates or collapses.
    for r in rates:
        assert 0.10 <= r <= 0.45, f"seat win-rates outside band: {rates}"
    assert abs(sum(rates) - 1.0) < 1e-9
