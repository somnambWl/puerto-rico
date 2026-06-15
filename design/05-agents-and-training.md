# 05 — Agents & Training

## Purpose

Specify the baseline agents (used for early play and as benchmarks), the RL approach (custom PyTorch
PPO self-play with action masking), reward design, the self-play opponent pool, and evaluation.
Depends on design/04 (env, codecs, mask format). **Note:** The RL stack is implemented in pure
PyTorch with no RLlib dependency — see the RL backend decision in `conversation-notes.md`.

```
puerto_rico/agents/
├── base.py              Agent protocol: act(obs: dict, *, rng=None) -> int
├── random_agent.py      uniform over the action_mask
├── heuristic_agent.py   hand-written policy (phase-dependent heuristics)
├── rl_policy.py         loads a trained checkpoint; act() runs masked inference
puerto_rico/training/
├── model.py             MaskedActorCritic(nn.Module) with hard action masking
├── rollout.py           collect_rollouts() — parallel episode collection, GAE-Lambda
├── opponent_pool.py     OpponentPool: frozen policy snapshots for self-play robustness
├── ppo.py               train(cfg) — PPO loop, snapshots, checkpointing
├── reward_config.py     reward modes: rank / win / vp_margin + shaping schedule
├── evaluate.py          arena: win rates, Elo, strategy audit logging
├── smoke_train.py       quick smoke test (>80% vs random, ~5 min)
├── train_strong.py      production training (beat-heuristic target)
├── train_improved.py    continuation training from a checkpoint
└── strategy_audit.py    analysis of learned behavior (opening roles, playstyle)
```

## Agent protocol (base.py)

```python
class Agent(Protocol):
    def act(self, obs: dict, *, rng=None) -> int: ...
        # obs = {"observation": np.ndarray(OBS_LEN), "action_mask": np.ndarray(N_ACTIONS)}
        # Returns an int in [0, N_ACTIONS) that is legal (mask[action] == 1.0).
        # rng: optional random.Random for stochastic tie-breaking; unused by deterministic policies.
    def reset(self) -> None: ...
```
All agents consume the same masked obs dict the env emits, so they are interchangeable in the arena
and the UI. The `action_mask` is a float32 array (1.0 legal, 0.0 illegal); the agent always respects
it.

## Baseline agents

**RandomAgent (`agents/random_agent.py`):** samples a uniform random action from `np.where(action_mask)`.
Sanity baseline and the floor for win rate (25% in 4-player with no strategy).

**HeuristicAgent (`agents/heuristic_agent.py`):** hand-written policy encoding standard Puerto Rico
heuristics, decided by phase:

- *Role pick:* prefer roles that advance your own engine and that you benefit from more than the
  opponent (the craftsman-risk principle); take prospector if nothing else helps and doubloons are
  low; grab placards with accumulated doubloons.
- *Settler:* take tiles that complete a production chain (plantation matching an owned, manned
  production building) or a quarry if building-heavy; take the chooser quarry privilege when planning
  expensive buildings.
- *Mayor:* fill production chains first (plantation+building balance), then high-value buildings;
  never waste colonists on unmanned production capacity.
- *Builder:* buy the cheapest building that increases production or VP density; prioritize a
  production engine early, big-VP buildings late; use quarry discounts.
- *Craftsman:* take the bonus good of the highest trade/ship value you can use (good choice in
  E3, ship choice in E1 via captain decisions).
- *Trader:* sell the highest-price good that's legal; respect the different-kind rule.
- *Captain:* ship to maximize VP this phase; explicitly choose which good and ship (E1), or keep
  choice (E1); exploit harbor/wharf if owned.

This agent is deliberately decent-but-beatable; it is the **primary benchmark** the RL agent must
surpass, and it is what a human plays against before RL exists.

## RL approach

**Algorithm:** Custom PyTorch PPO with action masking and multi-agent self-play. PPO is chosen over
AlphaZero-style MCTS for the first agent because: it tolerates stochastic tile draws and variable
action spaces without chance-node bookkeeping, needs no simulator-clone in the loop, and is simpler
and faster to implement and debug. (An AlphaZero/MCTS agent is a documented future option if PPO
plateaus below desired strength; the engine's `clone()` supports it.)

**Model architecture (training/model.py):**
```python
class MaskedActorCritic(nn.Module):
    def __init__(self, obs_dim=OBS_LEN, n_actions=N_ACTIONS, hidden=(256, 256)):
        # Shared MLP torso: linear + tanh layers (orthogonal init)
        # Policy head: n_actions logits (small gain, ~0.01)
        # Value head: scalar (standard gain, 1.0)
```

Before sampling or computing entropy, apply hard action masking to the policy logits:
```
masked_logits = logits + (action_mask - 1.0) * 1e9
```
Legal actions (mask == 1) add 0 (unchanged); illegal actions (mask == 0) add -1e9, pushing them to
~0 probability. The Categorical distribution is built from masked logits, so illegal actions never
get sampled and never inflate entropy. **This is the single most important correctness detail.**

**Self-play with opponent pool (training/rollout.py, training/opponent_pool.py, training/ppo.py):**

- The game is seat-symmetric (observations are from the acting player's perspective, design/04), so
  use a **single shared policy** that controls all four seats during training (full parameter sharing
  — every seat's transitions train the same network). This is the simplest and most sample-efficient
  setup for a symmetric N-player game.
- `collect_rollouts()` runs parallel episodes to gather a batch of transitions. Each episode samples
  the action from the current policy (all seats) or from the opponent pool (with configurable
  probability). All transitions are collected; the PPO update trains only on learner-seat transitions,
  but the opponent seats' actions influence the state evolution.
- The **OpponentPool** stores frozen snapshots of the main policy (taken every `snapshot_interval`
  iterations). With probability `self_play_prob`, an iteration mixes 1–3 pool / baseline opponents into
  the table; otherwise, all seats are learner (full self-play). Pool mixing adds robustness against
  strategy cycling and non-stationarity.
- Rotate which seat(s) the learner occupies each episode (or by episode index in parallel collection)
  so no policy becomes governor/first-player biased; the perspective encoding makes this free.

## Reward design (training/reward_config.py)

4-player Puerto Rico is **general-sum** (no single opponent to be ±1 against), so the terminal reward
is based on final standing, not a zero-sum win/lose. `Game.returns(reward_mode)` supports three modes
implemented in `reward_config.py`:

- **`rank` (default):** map final placement (1st, 2nd, 3rd, 4th) to fixed rewards: +1, +1/3, −1/3,
  −1. Zero-mean across seats; dense enough to distinguish 2nd from 4th (important, because pure win/
  lose is only ~25% positive with four players — very sparse gradient). Ties share the average reward
  of the ranks they occupy.
- **`win`:** +1 to the winner, 0 to the rest. Sparser; use as an ablation baseline only.
- **`vp_margin`:** standardized final VP (z-scored across the four players). Smoothest signal but can
  reward VP-hoarding over winning — use for early bootstrapping, then switch to `rank` for the
  final objective.

**Optional dense shaping** (controlled by `shaping_coef`, annealed to 0 over training):
```
reward += shaping_coef * (self_vp - mean(other_players_vp))
```
Measured at end-of-round, for early gradient signal in the long, multi-board game. Must vanish by
the end of training so it cannot distort the standing-based objective; verify policies are stable
under a `coef = 0` fine-tune.

**Step rewards:** always 0 (no hand-coded per-action bonuses that would bias strategy toward
unintended play).

> Multiplayer dynamics: general-sum N-player games admit kingmaking/coalition effects, but Puerto
> Rico has no trading, voting, or direct attacks — interaction is only through shared markets, the
> colonist ship, and cargo ships. Effects are mild. A shared self-play policy converging toward
> symmetric, individually-rational play is a reasonable target.

## Training loop (training/ppo.py)

```python
@dataclass
class PPOConfig:
    # Game setup
    num_players: int = 4
    reward_mode: str = "rank"
    
    # Schedule
    total_iterations: int              # total training iterations
    rollout_steps: int                 # transitions per rollout batch
    
    # PPO core
    lr: float                          # learning rate
    gamma: float = 0.999               # discount (long episodes in PR)
    gae_lambda: float = 0.95           # GAE-Lambda advantage estimation
    clip: float = 0.2                  # PPO clip range
    update_epochs: int                 # passes over the batch
    minibatch_size: int                # minibatch for each epoch
    
    # Model
    hidden: tuple[int, ...] = (256, 256)  # torso layer sizes
    
    # Entropy annealing (early exploration, late decisiveness)
    entropy_coef: float                # initial entropy bonus
    entropy_coef_final: float = 0.0    # final entropy bonus
    entropy_anneal_iters: int          # iters to anneal over
    
    # Self-play
    self_play_prob: float = 1.0        # prob of pure self-play (vs mixed with pool/baselines)
    snapshot_interval: int             # iterations between snapshots
    max_snapshots: int                 # max snapshots kept in pool
    
    # Evaluation
    eval_interval: int                 # iterations between in-loop evals
    eval_games: int = 100              # games per eval
```

Each iteration:
1. Call `collect_rollouts(cfg)` → returns a batch of transitions with GAE-Lambda advantages
   (batch-normalized) and raw returns. Parallel episodes speed collection if the engine is fast.
2. Update the policy via `ppo_update()`: shuffle the batch, split into minibatches, run SGD over
   `update_epochs` passes of the clipped PPO surrogate loss (scalar return targets, not action-returns).
3. Update the value head on the same batch (MSE loss vs raw returns).
4. Anneal entropy coefficient toward `entropy_coef_final`.
5. Every `snapshot_interval` iterations, freeze the current weights into the opponent pool.
6. Every `eval_interval` iterations, evaluate the deterministic policy (argmax actions) vs
   RandomAgents and HeuristicAgents in a seat-rotated benchmark.

**Checkpoint artifact (training/ppo.py, line ~35):**
```python
torch.save({
    "format": "puerto_rico.rl_policy",       # artifact tag
    "version": 1,                            # schema version
    "codec": {"obs_codec": 1, "action_codec": 1},
    "model_state": network.state_dict(),
    "obs_dim": OBS_LEN,
    "n_actions": N_ACTIONS,
    "hidden": [256, 256],                    # hyperparams for reconstruction
    "config": asdict(cfg),
    "iteration": 1234,                       # or "final"
}, "path/to/checkpoint.pt")
```

This artifact is loadable by `agents/rl_policy.py` **without importing the trainer** — just torch,
the codecs, and the model. The UI loads it this way.

**Logging:** episode length, win rate vs each pool member, vs heuristic, entropy, value loss, mask
violation count (must stay 0), total return per episode.

## Evaluation (training/evaluate.py)

**Arena:** play K games with a chosen 4-agent line-up, rotating seat assignments across games so
each agent gets equal time in each position. Report per-agent:
- Win rate (1st-place %): main target metric
- Mean placement (1st–4th): proxy for consistency
- Mean VP: absolute strength

**Benchmarks (in-loop and post-training):**
- `main` vs all-RandomAgents: should dominate (win rate >> 25% chance baseline; target: > 80%)
- `main` vs all-HeuristicAgents: primary target ≫ 25% (target: > 45% over ≥500 games)
- `main` vs mixed tables with past snapshots: detect strategy cycling

**Elo rating:** maintain an Elo table across all checkpoints + baselines to confirm monotonic
improvement and detect non-convergence. Useful for detecting when a newly-trained policy drifts
(possibly due to luck or distribution shift) vs steady improvement.

**Strategy audit (training/strategy_audit.py, docs/rl-strategy-audit.md):**
Log and analyze learned behaviors:
- Opening role preferences: does the policy prefer certain roles at the start?
- Build order: which buildings does it prioritize?
- Production chains: does it understand colonist→tile→building→good synergy?
- Trading and shipping: does it maximize VP per cargo, use the wharf?
- Playstyle across positions: governor bias (should be minimal with seat rotation)?

If the agent finds a "too good" or "nonsensical" line, first suspect an engine bug (design/00 risk)
and add a regression test. Known results: final trained model (`runs/release/final.pt`) achieves ~94%
win rate vs 3 HeuristicAgents over 500+ seat-rotated games.

## Acceptance criteria

- **Baseline sanity:** RandomAgent and HeuristicAgent run full 4-player games via the arena with
  0 mask violations.
- **Smoke test (training/smoke_train.py):** a short PPO run (< 5 min CPU, ~300 iterations) learns
  to dominate 3 RandomAgents (win rate > 80% over 240 games) — verifies the masked model + reward
  wiring are correct. Artifact saved to `runs/smoke/final.pt`.
- **Checkpoint roundtrip:** training pipeline checkpoints and `rl_policy.py` can load the artifact
  and play full games without importing the trainer (torch + codecs only).
- **Evaluation reproducibility:** evaluation produces repeatable Elo rankings and win-rate/placement
  tables (seeded RNG).
- **Production target (design/05 & E4, training/train_strong.py):** `main` wins > 45% vs 3 HeuristicAgents
  over ≥ 500 seat-rotated games. Achieved by the release checkpoint (`runs/release/final.pt`): ~94%
  win rate vs heuristic baseline.
