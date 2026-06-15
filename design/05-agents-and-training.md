# 05 — Agents & Training

## Purpose

Specify the baseline agents (used for early play and as benchmarks), the RL approach (PPO self-play
with action masking), reward design, the self-play opponent pool, and evaluation. Depends on
design/04 (env, codecs, mask format).

```
puerto_rico/agents/
├── base.py          Agent protocol: act(observation_dict, legal_actions) -> int
├── random_agent.py  uniform over the mask
├── heuristic_agent.py
└── rl_policy.py      loads a trained policy checkpoint; act() runs masked inference
puerto_rico/training/
├── env_factory.py    registers PuertoRicoAEC with RLlib; policy mapping
├── masked_model.py   action-masking model (logits += (mask-1)*1e9)
├── selfplay.py       opponent pool, snapshotting, policy-mapping callbacks
├── train.py          PPO config + training loop + checkpointing
└── evaluate.py       arena: win rates + Elo vs baselines and past checkpoints
```

## Agent protocol (base.py)

```python
class Agent(Protocol):
    def act(self, obs: dict, *, rng=None) -> int: ...   # returns a legal action int (respects obs["action_mask"])
    def reset(self) -> None: ...
```
All agents consume the same masked obs dict the env emits, so they are interchangeable in the arena
and the UI.

## Baseline agents

- **RandomAgent:** sample uniformly among `action_mask == 1`. Sanity baseline and the floor for win-rate.
- **HeuristicAgent:** hand-written policy encoding standard Puerto Rico heuristics, decided by phase:
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
  - *Craftsman:* take the bonus good of the highest trade/ship value you can use.
  - *Trader:* sell the highest-price good that's legal; respect the different-kind rule.
  - *Captain:* ship to maximize VP this phase; exploit harbor/wharf if owned.
  This agent is deliberately decent-but-beatable; it is the **primary benchmark** the RL agent must
  surpass, and it's what a human plays against before RL exists.

## RL approach

**Algorithm:** PPO with action masking, multi-agent self-play via RLlib. PPO is chosen over
AlphaZero-style MCTS for the first agent because: it tolerates the stochastic tile draws and variable
action space without chance-node bookkeeping, needs no perfect simulator-clone in the loop, and is far
faster to get working. (An AlphaZero/MCTS agent using `engine.clone()` is a documented future option if
PPO plateaus below desired strength.)

**Masked model (masked_model.py):** a standard MLP torso over `obs["observation"]`; before sampling,
add `(action_mask - 1) * 1e9` to the logits so illegal actions get ~`-inf`. Mask both the policy head
and any entropy/regularization terms. This is the single most important correctness detail in training.

**Policies & self-play (selfplay.py):**
- The game is seat-symmetric (observations are from the acting player's perspective, design/04), so use
  a single shared policy `"main"` that **controls all four seats** during training (full parameter
  sharing — every seat's transitions train the same network). This is the simplest and most
  sample-efficient setup for a symmetric N-player game.
- For robustness against non-stationarity and strategy cycling, mix in an **opponent pool**: with some
  probability, fill 1–3 of the non-learner seats from frozen snapshots of `"main"` (taken every N
  iterations), plus the random and heuristic agents early on to bootstrap. `policy_mapping_fn` assigns
  `"main"` to the learner seat(s) and sampled frozen policies to the rest.
- Rotate which seat(s) the learner occupies each episode so no policy becomes governor/first-player
  biased; the perspective encoding (design/04) makes this free.

## Reward design

4-player Puerto Rico is **general-sum** (there is no single opponent to be ±1 against), so the terminal
reward is based on final standing, not a zero-sum win/lose. `engine.returns()` supports a configurable
`reward_mode`:

- **`rank` (default):** map final placement to a fixed reward, e.g. 1st → +1, 2nd → +1/3, 3rd → −1/3,
  4th → −1 (zero-mean across seats, and dense enough to distinguish 2nd from 4th — important, because a
  pure win/lose signal is only ~25% positive with four players and therefore very sparse).
- **`win`:** +1 to the winner, 0 to the rest (sparser; keep as an ablation only).
- **`vp_margin`:** standardized final VP (z-scored across the four players); smoothest signal but can
  reward VP-hoarding over winning — use mainly for early bootstrapping, then switch to `rank`.

- **Optional dense shaping** (`shaping_coef`, small, annealed to 0): `coef * Δ(self_vp − mean(other
  players' vp))` measured at end-of-round, for early gradient signal in the long, multi-board game. It
  must vanish by the end of training so it cannot distort the standing-based objective; verify policies
  are stable under a `coef = 0` fine-tune.
- Otherwise keep step rewards at 0 (no hand-coded per-action rewards that would bias strategy).

> Multiplayer dynamics: general-sum N-player games admit kingmaking/coalition effects, but Puerto Rico
> has no trading, voting, or direct attacks between players — interaction is only through the shared
> markets, the colonist ship, and the cargo ships — so these effects are mild. A shared self-play policy
> converging toward symmetric, individually-rational play is a reasonable target.

## Training loop (train.py)

- RLlib PPO; vectorized rollout workers (the env is cheap if the engine is fast — design/00 targets).
- Hyperparameters to expose in a config file: lr, gamma (use ~0.999 given long episodes), gae lambda,
  clip, entropy coef (decay), train batch / minibatch / epochs, model hidden sizes, snapshot interval,
  pool size, shaping coef + anneal schedule, total timesteps.
- Checkpoint `"main"` regularly; export a lightweight inference artifact (torch weights + obs/action
  codec versions) for `rl_policy.py` and the UI to load without RLlib at serve time.
- Log: episode length, win rate vs each pool member, vs heuristic, entropy, value loss, mask-violation
  count (must stay 0).

## Evaluation (evaluate.py)

- **Arena:** play K games with a chosen 4-agent line-up, rotating seat assignments across games; report
  each agent's win rate, mean placement (1st–4th), and mean VP.
- **Benchmarks:** in 4-player tables, track `"main"`'s win rate and mean placement against: all-Random
  (should dominate, win rate ≫ the 25% chance baseline), all-Heuristic (target ≫ 25%), and tables
  seeded with past checkpoints.
- **Elo:** maintain an Elo table across all checkpoints + baselines to confirm monotonic improvement
  and detect cycling.
- **Sanity/strategy audit:** log notable behaviors; if the agent finds a "too good" line, first suspect
  an engine bug (design/00 risk) and add a regression test.

## Acceptance criteria

- RandomAgent and HeuristicAgent run full 4-player games via the arena with 0 mask violations.
- A short PPO run learns to dominate a table of 3 RandomAgents (win rate ≫ the 25% chance baseline,
  e.g. > 80% over 200 games) — a smoke test that the masked model + reward wiring are correct.
- The training pipeline checkpoints and reloads a policy that plays a full game through `rl_policy.py`.
- Evaluation produces a reproducible Elo table and win-rate/placement report.
- Stretch target for M4 "done": `"main"` wins clearly more than the 25% baseline against a table of 3
  HeuristicAgents (target ≥ 45% over ≥ 500 seat-rotated games).
