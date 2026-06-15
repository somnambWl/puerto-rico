# 00 — Overview & Architecture

## Purpose

This document defines the overall architecture, the cross-cutting conventions every other
doc assumes, and the milestone sequence. Read it before the others.

## Goals

- A correct, fast, deterministic Puerto Rico simulator usable both interactively (UI) and at
  scale (RL self-play, millions of steps).
- A clean separation between **rules** (engine), **learning** (agents/training), and
  **presentation** (UI). Each layer depends only on the layer below via a narrow interface.
- An RL opponent that beats the heuristic agent and provides a good game for a human.

## Non-goals (first milestone)

- Both expansions ("The New Buildings", "The Nobles"); 2-, 3-, and 5-player counts as *tuned/tested*
  targets; networked multiplayer between humans; mobile/native UI; or superhuman strength. Deferred.
- We design data structures so these are *possible later* (e.g. building effects are pluggable,
  player count is a parameter — the round's role budget is `3 if num_players == 2 else 1`), but we
  implement and tune for the **4-player base game** first.

## Layered architecture

```
┌─────────────────────────────────────────────┐
│ UI (react frontend  ↔  fastapi/websocket)     │  design/06
├─────────────────────────────────────────────┤
│ Agents: random | heuristic | rl-policy        │  design/05
├─────────────────────────────────────────────┤
│ Env: PettingZoo AEC wrapper + encoders        │  design/04
├─────────────────────────────────────────────┤
│ Engine: GameState, Action, phases, buildings, │  design/01,02,03
│         scoring, setup  (pure Python, no deps) │
└─────────────────────────────────────────────┘
```

The **engine has no dependency on numpy, gym, torch, or the UI.** It is plain Python with a
small public API. The env layer is the only place that imports both the engine and numpy. The
agents depend on the env's encoders but never reimplement rules. The UI depends only on the
engine (for an authoritative game) and on a serialized agent policy.

## The central interaction contract

Every component drives the game through exactly three engine calls:

```python
player_idx: int            = state.current_player          # whose decision is it
actions:    list[Action]   = state.legal_actions()         # the only legal choices, right now
state.apply(actions[k])                                    # advance the game by one atomic decision
```

The game is modeled as a long sequence of **atomic decisions** by a single "current player" at a
time (see design/01 and design/02). There is no notion of a player doing several things at once;
even "place 4 colonists" is four decisions. This makes the action space tractable for RL, gives the
UI natural step-by-step prompts, and keeps the legality logic in one place.

## Conventions (apply to all docs)

- **Language/runtime:** Python 3.11+. Use `dataclasses` (with `slots=True` where hot) for state.
  Prefer explicit enums (`IntEnum`) over strings for goods, roles, building ids, phases.
- **Determinism:** all randomness (tile draws) flows through a single seeded RNG stored in the
  state (`state.rng`). Given a seed and a sequence of actions, the game is fully reproducible.
- **Immutability discipline:** `apply()` mutates the state in place for speed and returns `None`.
  For tree search / rollouts, use `state.clone()` (a deep copy of mutable fields) before applying.
  Never mutate `legal_actions()` results.
- **No hidden rules in callers:** if a caller needs to know something is illegal, it must come from
  `legal_actions()`. Agents and the UI must not encode rules.
- **Goods/types vocabulary:** goods are `CORN, INDIGO, SUGAR, TOBACCO, COFFEE`. Roles are
  `SETTLER, MAYOR, BUILDER, CRAFTSMAN, TRADER, CAPTAIN, PROSPECTOR`. Use these names everywhere.
- **Testing:** every engine rule has a unit test. Integration tests replay scripted games and assert
  final scores. The rulebook's captain-phase worked example is a required test fixture.
- **Style/commits:** follow the repo's gitmoji-commits convention for commit messages.

## Performance targets

- Engine: a full random 2-player game (start → terminal) in **well under 1 ms** of pure-Python
  time on a typical laptop core; target ≥ 50k full games/sec/core eventually. First implementation
  may be slower — correctness first — but avoid per-step allocations, deep copies, and pandas/numpy
  in the engine hot path. If Python proves too slow for training, the engine's pure-function design
  permits a later port of the hot path (Cython/Rust via PyO3) behind the same API.
- The env adds encoding overhead; keep encoders allocation-light (preallocate buffers).

## Milestones

1. **M1 — Engine core + setup + state** (design/01). State model, 4-player setup, action protocol
   skeleton, `clone()`, serialization. Random legal-move playthrough runs to termination.
2. **M2 — Phases + buildings + scoring** (design/02, 03). All seven roles, the follow structure,
   every base-game building effect, end-game triggers, final scoring. Passes the scripted-game and
   worked-example tests.
3. **M3 — Env + baselines** (design/04, 05). PettingZoo AEC env, observation/action encoders,
   action masking; random + heuristic agents; an arena harness reporting win rates.
4. **M4 — RL training** (design/05). PPO self-play with masking, reward shaping, opponent pool,
   evaluation vs baselines and past checkpoints (Elo). Produces a serialized policy.
5. **M5 — UI** (design/06). FastAPI backend hosting an authoritative game + loaded policy; React
   frontend that renders state, highlights legal moves, and plays a full human-vs-AI game.

Each milestone is independently demoable. M3 already lets a human play (vs heuristic) once the
minimal UI from M5 exists, so M5's first cut can be pulled forward if interactive play is wanted early.

## Risks & mitigations

- **Engine bugs masquerading as RL "strategies."** A self-play agent will exploit any rules
  loophole. Mitigation: strong test suite, and treat surprising agent behavior as a bug report
  against the engine first.
- **Action-space/legality complexity** (mayor colonist placement, captain mandatory-load,
  building hooks). Mitigation: the atomic-decision model + a single `legal_actions()` authority.
- **Training cost from long episodes** (4 boards, ~15 rounds). Mitigation: fast engine, vectorized
  rollouts, reward shaping, and scoping to the 4-player base game (no expansions) first.
- **4-player is general-sum, not zero-sum.** There is no clean ±1 win/lose reward across 4 seats,
  and dynamics like kingmaking are possible (though limited in Puerto Rico — no negotiation or direct
  attacks). Mitigation: a rank/VP-based terminal reward and a single shared self-play policy across all
  seats — see design/05.
- **Non-stationarity in self-play.** Mitigation: opponent pool of frozen past checkpoints.
