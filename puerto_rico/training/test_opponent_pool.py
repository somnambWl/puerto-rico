"""Tests for the self-play opponent pool (training/opponent_pool.py)."""

from __future__ import annotations

import numpy as np
import torch

from ..engine.game import Game
from ..engine.state import GameConfig
from ..env import action_codec
from .model import MaskedActorCritic
from .opponent_pool import (
    OpponentPool,
    Snapshot,
    make_snapshot_opponent,
)
from .rollout import collect_rollouts


def _fresh_policy(seed: int = 0) -> MaskedActorCritic:
    torch.manual_seed(seed)
    return MaskedActorCritic()


def _drive_states(opp, *, num_games: int = 3, base_seed: int = 0):
    """Drive several real games; at every decision call ``opp`` and assert legality.

    Returns the number of decisions checked.
    """
    checked = 0
    for g in range(num_games):
        game = Game(GameConfig(num_players=4, seed=base_seed * 100 + g))
        while not game.is_terminal:
            action_id = opp(game)
            mask = action_codec.mask(game)
            assert 0 <= action_id < mask.shape[0]
            assert mask[action_id], (
                f"opponent returned illegal action {action_id} "
                f"(mask==0) in game {g}"
            )
            action = action_codec.from_int(action_id, game.state)
            game.apply(action, validate=False)
            checked += 1
    return checked


# --------------------------------------------------------------------------- #
# frozen snapshot opponent legality                                           #
# --------------------------------------------------------------------------- #


def test_snapshot_opponent_returns_only_legal_actions():
    policy = _fresh_policy(seed=1)
    opp = make_snapshot_opponent(policy.state_dict())
    checked = _drive_states(opp, num_games=4, base_seed=1)
    assert checked > 0  # actually exercised the engine


def test_deterministic_snapshot_opponent_legal():
    policy = _fresh_policy(seed=2)
    opp = make_snapshot_opponent(policy.state_dict(), deterministic=True)
    checked = _drive_states(opp, num_games=3, base_seed=2)
    assert checked > 0


# --------------------------------------------------------------------------- #
# add_snapshot stores an independent copy                                      #
# --------------------------------------------------------------------------- #


def test_add_snapshot_is_independent_of_live_weights():
    policy = _fresh_policy(seed=3)
    pool = OpponentPool(max_snapshots=5)
    pool.add_snapshot(policy.state_dict(), iteration=0)
    snap = pool.latest()
    assert snap is not None

    seed = 4321

    def replay_argmax() -> list[int]:
        """Deterministic (argmax) replay of the stored snapshot, for exact compare."""
        opp = make_snapshot_opponent(snap.state_dict, deterministic=True)
        g = Game(GameConfig(num_players=4, seed=seed))
        actions: list[int] = []
        while not g.is_terminal:
            a = opp(g)
            actions.append(a)
            g.apply(action_codec.from_int(a, g.state), validate=False)
        return actions

    # capture stored-snapshot behaviour BEFORE mutating live weights.
    before = replay_argmax()

    # now drastically mutate the live policy's weights in place.
    with torch.no_grad():
        for p in policy.parameters():
            p.add_(torch.randn_like(p) * 5.0)

    # stored state_dict tensors must be unchanged (deep copy, not aliased).
    for k, v in snap.state_dict.items():
        assert not torch.allclose(v, policy.state_dict()[k]), (
            f"stored snapshot weight {k} tracked the live mutation"
        )

    # the stored snapshot replays the SAME trajectory after the live mutation.
    after = replay_argmax()
    assert before == after, "stored snapshot behaviour changed after live mutation"


# --------------------------------------------------------------------------- #
# eviction                                                                     #
# --------------------------------------------------------------------------- #


def test_max_snapshots_eviction_fifo():
    policy = _fresh_policy(seed=5)
    cap = 3
    pool = OpponentPool(max_snapshots=cap)

    evicted = []
    for it in range(cap):
        ev = pool.add_snapshot(policy.state_dict(), iteration=it)
        assert ev is None  # under cap, nothing evicted
    assert len(pool) == cap

    # adding beyond the cap evicts the oldest (FIFO) and keeps size capped.
    for it in range(cap, cap + 4):
        ev = pool.add_snapshot(policy.state_dict(), iteration=it)
        evicted.append(ev)
        assert len(pool) == cap

    # evicted iterations are the oldest ones, in order.
    assert [e.iteration for e in evicted] == [0, 1, 2, 3]
    # remaining snapshots are the most recent `cap`.
    assert [s.iteration for s in pool.snapshots] == [4, 5, 6]
    assert pool.latest().iteration == 6


# --------------------------------------------------------------------------- #
# sample_opponents count + reachability + distribution                        #
# --------------------------------------------------------------------------- #


def test_sample_opponents_count_and_callable():
    policy = _fresh_policy(seed=6)
    pool = OpponentPool(max_snapshots=4)
    pool.add_snapshot(policy.state_dict(), iteration=0)
    rng = np.random.default_rng(0)

    for n in (0, 1, 3, 7):
        opps = pool.sample_opponents(n, policy, rng=rng)
        assert len(opps) == n
        for o in opps:
            assert callable(o)

    # every sampled opponent is legal across real states.
    opps = pool.sample_opponents(3, policy, rng=np.random.default_rng(1))
    for o in opps:
        _drive_states(o, num_games=1, base_seed=9)


def test_baselines_are_reachable():
    # With no snapshots and self_play_prob=0, all non-self mass goes to baselines;
    # both random and heuristic must appear over many draws.
    policy = _fresh_policy(seed=7)
    pool = OpponentPool(max_snapshots=4)
    rng = np.random.default_rng(123)

    random_opp = pool.baseline_opponents()["random"]
    heuristic_opp = pool.baseline_opponents()["heuristic"]

    seen_random = seen_heuristic = False
    opps = pool.sample_opponents(400, policy, self_play_prob=0.0, rng=rng)
    for o in opps:
        if o is random_opp:
            seen_random = True
        elif o is heuristic_opp:
            seen_heuristic = True
    assert seen_random and seen_heuristic


def test_distribution_roughly_honors_self_play_prob():
    policy = _fresh_policy(seed=8)
    pool = OpponentPool(max_snapshots=4, self_play_prob=0.5)
    # add a snapshot so the non-self branch can also hit snapshots.
    pool.add_snapshot(policy.state_dict(), iteration=0)

    baseline_ids = {
        id(pool.baseline_opponents()["random"]),
        id(pool.baseline_opponents()["heuristic"]),
    }

    rng = np.random.default_rng(42)
    n = 4000
    opps = pool.sample_opponents(n, policy, rng=rng)

    # A "self" or "snapshot" opponent is a freshly-built closure (not a baseline
    # identity); count non-baseline draws as the self+snapshot bucket.
    non_baseline = sum(1 for o in opps if id(o) not in baseline_ids)
    frac_non_baseline = non_baseline / n

    # self_play_prob=0.5; of the remaining 0.5, snapshot_share=0.7 -> snapshots,
    # so non-baseline fraction ~ 0.5 + 0.5*0.7 = 0.85. Wide tolerance.
    assert 0.78 < frac_non_baseline < 0.92


# --------------------------------------------------------------------------- #
# integration with collect_rollouts                                           #
# --------------------------------------------------------------------------- #


def test_integration_one_learner_vs_three_pool_opponents():
    policy = _fresh_policy(seed=10)
    pool = OpponentPool(max_snapshots=4)
    pool.add_snapshot(policy.state_dict(), iteration=0)

    rng = np.random.default_rng(7)
    sampled = pool.sample_opponents(3, policy, rng=rng)
    opponents = {1: sampled[0], 2: sampled[1], 3: sampled[2]}

    batch = collect_rollouts(
        policy,
        target_steps=256,
        opponent_policies=opponents,
        rng_seed=11,
    )
    assert batch["info"]["mask_violations"] == 0
    assert batch["info"]["learner_seats"] == [0]
    assert batch["actions"].shape[0] >= 256
    # all collected actions legal under their own masks.
    chosen = batch["action_masks"].gather(1, batch["actions"].unsqueeze(1)).squeeze(1)
    assert (chosen > 0.5).all()


def test_snapshot_dataclass_fields():
    snap = Snapshot(iteration=3, state_dict={}, metadata={"elo": 1000.0})
    assert snap.iteration == 3
    assert snap.metadata["elo"] == 1000.0
