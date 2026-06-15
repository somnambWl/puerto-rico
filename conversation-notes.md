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
