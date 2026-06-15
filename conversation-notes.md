# Conversation & Decisions Notes

Notes from the design discussion that produced these docs. Captures *why* the design is the way it is,
so future readers (and Claude Code) understand the rationale behind the specs in `design/`.

## What we set out to do

Build a digital Puerto Rico: a rules engine, a UI to play it, and a reinforcement-learning opponent to
play against. Started from the uploaded rulebooks (Deluxe + 2002 editions), transcribed to
`docs/puerto-rico-rules.md`, then planned the build.

## Key decisions

1. **Engine is the single source of truth for legality.** The UI and all agents call
   `state.legal_actions()` and `state.apply(action)`; nothing reimplements rules. This is the most
   important architectural invariant — it means legality is solved once and reused by the engine, the
   RL env, the arena, and the UI.

2. **The game is modeled as a stream of "atomic decisions."** There is no composite "turn" action and
   no nested action structure. At every decision point a single current player answers one question
   (pick a role, take a tile, place one colonist, build one building, sell one good, load one good…).
   The engine's phase state machine decides what the *next* question is; the policy just answers
   whatever is in front of it.
   - Rules-irrelevant choices (which board slot a tile/building goes in, the forced amount/ship when
     loading) are **auto-resolved by the engine**, so every action the agent sees is a genuine
     strategic choice, not bookkeeping. This keeps the action space small and meaningful.
   - Combinatorial steps (mayor colonist placement) are **sequenced** — one colonist per decision —
     rather than chosen as a full assignment at once.

3. **One flat, masked action space.** Rather than a hierarchical/autoregressive policy, use a single
   fixed discrete action space (the union of all atomic actions, a few hundred ids) with an
   **action mask**: only the currently-legal subset is selectable (illegal logits → −∞). One policy
   network handles every phase; the observation includes phase/role one-hots so it knows what kind of
   question it's answering. The autoregressive factoring is noted as a future upgrade if the action
   space ever balloons (e.g. with expansions).

4. **Clarified how role-selection relates to the concrete actions.** "Trade vs build" is *not* chosen
   within a phase — it is decided one step earlier at role selection (pick the Trader vs Builder
   placard). Within a phase, all legal actions are of that one category. Selecting a role and then
   taking the role's concrete action are two separate timesteps.

5. **Scope change: target the 4-player standard game, not 2-player.** Originally scoped to 2-player
   (zero-sum, simplest for RL). Kuba chose the standard "one role per player per round" structure with
   **4 players** — it matches the real game and how you'd play with friends. Consequences, now reflected
   in the docs:
   - The engine already supported it (`roles_per_round = 3 if num_players == 2 else 1`); the change is
     mainly setup constants (design/01 now has a per-player-count table) and the RL framing.
   - 4-player is **general-sum, not zero-sum**, so the RL reward is **rank/VP-based** (default: 1st/2nd/
     3rd/4th → +1 / +1⁄3 / −1⁄3 / −1), not ±1 win/lose (design/05).
   - Self-play uses **one shared policy across all four seats** (parameter sharing), with an optional
     opponent pool of frozen snapshots for robustness.
   - "Play against me" = 1 human + 3 AI seats driven by the same policy (design/06).
   - Mild caveat: general-sum N-player play can have kingmaking effects, but Puerto Rico has no
     negotiation/trading/attacks, so interaction is only via shared markets/ships — effects are small.

## Still open / deferred

- Expansions ("The New Buildings", "The Nobles") — the building hook model (design/03) is designed to
  accept them later without touching core flow.
- Whether to add an AlphaZero/MCTS agent (the engine's `clone()` supports it) if PPO plateaus.
- 2-/3-/5-player counts remain config options but are not the tuned target.

## Build order (unchanged)

Engine → Env → baseline agents (random + heuristic) → RL training → UI. A human can play vs the
heuristic agent as soon as the engine + a thin UI exist, before any RL is trained.

## RL Backend Decision: Ray RLlib → Custom PyTorch PPO

**When/Why:** During implementation of the agents/training epic (tasks 03–11), the plan to use Ray
RLlib was revised. Instead, a custom PyTorch PPO trainer was built from scratch.

**Rationale:**
- **Debuggability:** RLlib abstracts away the training loop, making it hard to inspect what the
  agent is doing. A custom trainer lets us log arbitrary telemetry (strategy audit, mask violations)
  and step through the code interactively.
- **Dependency footprint:** RLlib pulls in Ray, which is heavy and requires special serve-time setup.
  A custom trainer uses only torch + numpy, making it lighter and deployable anywhere.
- **Action masking:** While RLlib has action-masking support, it was designed for a different API
  (Gym spaces, policy_mapping_fn). Our masked-logit approach is simpler and easier to verify.
- **Reproducibility:** Custom code makes it easier to reproduce the exact behavior and lock in
  hyperparameters across runs.

**What changed in the docs:**
- `design/05-agents-and-training.md` completely rewritten to describe custom PyTorch instead of RLlib.
- File tree updates: `training/{model,rollout,opponent_pool,ppo,reward_config,evaluate,smoke_train,train_strong,...}.py`
  (not RLlib's `env_factory.py`, `train.py` with RLlib config, etc.).
- Model renamed: `MaskedActorCritic(nn.Module)` (not `TorchModelV2` or RLlib-specific wrappers).
- Reward modes: implemented in `training/reward_config.py` (not RLlib policies).
- Self-play: `OpponentPool` + `collect_rollouts` (not `policy_mapping_fn` / `SelfPlayCallback`).

**Task mapping:**
- agents-task-03: "RLlib env registration" → superseded by `training/rollout.py` (rollout collection)
- agents-task-04: "Masked model" → `training/model.py` (MaskedActorCritic)
- agents-task-05: "Opponent pool & callbacks" → `training/opponent_pool.py` + `training/ppo.py`
- agents-task-07: "PPO training" → `training/ppo.py` (custom loop, no RLlib config)

## Enhancements (E1–E8)

Post-v1 improvements added after the base-game engine + UI were complete:

- **E1 (Captain explicit decisions):** Extended captain phase to make explicit (good, ship) choices
  and optionally keep a good on the windrose (not auto-discard). Deepens captain strategy.
- **E2 (Codec updates):** Updated action codec to encode ship + keep decisions (added CHOOSE block
  for captain windrose; changed LOAD to explicit cargo+wharf encoding). N_ACTIONS → 92.
- **E3 (Heuristic captain):** Improved heuristic agent to make sensible ship/keep choices.
- **E4 (Retrain strong):** Re-trained the RL agent with E1–E3 in place; new checkpoint achieves ~94%
  win rate vs 3 HeuristicAgents (original target: >45%).
- **E5 (Backend preview):** Added `POST /games/{id}/preview` endpoint for hypothetical action
  evaluation. Backend also gained `/catalog` for static building/good reference.
- **E6 (Frontend enhancements):** Added UI tooltips (building descriptions), step/pause AI playback,
  VP-sorted building shelf, good trading values from catalog. Uses preview endpoint for what-if hints.
- **E7 (Strategy audit):** Post-training analysis of the learned policy's behavior (opening roles,
  build order, shipping/trading strategy). Documented in `docs/rl-strategy-audit.md`.
- **E8 (Improve RL):** Evaluated whether the audit found gaps and implemented improvements if needed.
  (In practice, the policy was already strong; E8 was a no-op refinement pass.)
