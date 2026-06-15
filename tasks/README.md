# Tasks

Generated from `design/00`–`design/06`. Build order follows the dependency chain in `CLAUDE.md`:
**Engine (core → phases → buildings) → Env → Agents/Training → UI.**

Status legend: `not started` | `in progress` | `done`

## Epic: enhancements (post-v1)
Deeper strategic decisions + stronger AI (user request: model must be able to beat humans).

| Task | Title | Status | Dependencies |
|------|-------|--------|--------------|
| E1 | Captain: explicit ship-selection + goods-keep CHOOSE | done | engine, phases-07 |
| E2 | Codec: encode ship + keep decisions | done | E1 |
| E3 | Heuristic: ship/keep strategy | done | E1, E2 |
| E4 | Retrain strong model (beat-humans target) | done | E1, E2, E3 |
| E5 | Backend: action-preview endpoint + building catalog/descriptions + good values | done | ui-backend |
| E6 | Frontend: tooltips, step/pause AI playback, VP-sorted shelf, trading values, action preview | done | E5 |
| E7 | RL strategy audit (measurable strong-play signatures) | done | E4 |
| E8 | Improve RL toward dominant strategies (if audit finds gaps) | not started | E7 |

## Epic: engine-core
Design: `design/00-overview-and-architecture.md`, `design/01-engine-core-and-state.md`

| Task | Title | Status | Dependencies |
|------|-------|--------|--------------|
| [01](engine-core-task-01-enums.md) | Enums | done | None |
| [02](engine-core-task-02-state-data-structures.md) | State data structures | done | 01 |
| [03](engine-core-task-03-action-protocol.md) | Action protocol | done | 01 |
| [04](engine-core-task-04-setup-initialization.md) | Setup & initialization | done | 01, 02, 03 |
| [05](engine-core-task-05-clone-immutability.md) | Clone & immutability | done | 01, 02 |
| [06](engine-core-task-06-serialization.md) | Serialization | done | 01, 02, 03 |
| [07](engine-core-task-07-public-api.md) | Public API (`Game`) | done | 01–06 |
| [08](engine-core-task-08-integration-random-playthrough.md) | Integration: random playthrough | done | 01–07 |

## Epic: engine-phases
Design: `design/02-engine-phases-and-flow.md`. Depends on engine-core (esp. `engine-core-task-07`).

| Task | Title | Status | Dependencies |
|------|-------|--------|--------------|
| [01](phases-task-01-phasestate-and-rotation.md) | PhaseState & governor rotation | done | engine-core-07 |
| [02](phases-task-02-settler-phase.md) | Settler phase | done | phases-01, buildings-05* |
| [03](phases-task-03-mayor-phase.md) | Mayor phase | done | phases-01 |
| [04](phases-task-04-builder-phase.md) | Builder phase | done | phases-01, buildings-01* |
| [05](phases-task-05-craftsman-phase.md) | Craftsman phase | done | phases-01, buildings-04* |
| [06](phases-task-06-trader-phase.md) | Trader phase | done | phases-01, buildings-04* |
| [07](phases-task-07-captain-phase.md) | Captain phase | done | phases-01, buildings-04* |
| [08](phases-task-08-prospector-inline.md) | Prospector (inline) | done | phases-01 |
| [09](phases-task-09-end-of-game-and-scoring.md) | End-of-game & scoring | done | phases-02…08, buildings-06* |
| [10](phases-task-10-integration-tests.md) | Integration: full-game tests | done | phases-01…09 |

\* soft dependency — stub the building hook if the buildings epic isn't done yet.

## Epic: buildings
Design: `design/03-buildings-reference.md`. Depends on `engine-core-task-01`.

| Task | Title | Status | Dependencies |
|------|-------|--------|--------------|
| [01](buildings-task-01-buildingid-and-catalog.md) | BuildingId enum & CATALOG | done | engine-core-01 |
| [02](buildings-task-02-hook-framework.md) | Hook framework | done | buildings-01 |
| [03](buildings-task-03-production-specs.md) | Production building specs | done | buildings-01 |
| [04](buildings-task-04-small-beige-core-handlers.md) | Small beige core handlers | done | buildings-01, 02 |
| [05](buildings-task-05-settler-mayor-handlers.md) | Settler/mayor handlers | done | buildings-01, 02, phases-02 |
| [06](buildings-task-06-large-scoring-handlers.md) | Large beige scoring handlers | done | buildings-01, 02, 03 |
| [07](buildings-task-07-integration-test.md) | Integration: full catalog | done | buildings-01…06 |
| [08](buildings-task-08-helper-functions.md) | Helper functions | done | buildings-01 |

## Epic: env
Design: `design/04-rl-environment.md`. Depends on the full engine (core + phases + buildings).

| Task | Title | Status | Dependencies |
|------|-------|--------|--------------|
| [01](env-task-01-action-codec.md) | ActionCodec | done | engine complete |
| [02](env-task-02-obs-codec.md) | ObsCodec | done | engine complete |
| [03](env-task-03-pettingzoo-env.md) | PettingZoo AEC env | done | env-01, 02 |
| [04](env-task-04-gymnasium-wrapper.md) | Gymnasium single-agent wrapper | done | env-03 |

## Epic: agents-training
Design: `design/05-agents-and-training.md`. Depends on env + engine.
**NOTE:** RL stack reworked from Ray RLlib → **custom PyTorch PPO** (user-approved; see memory `rl-backend-decision`). Tasks 03/04/05/07 remapped to PyTorch modules.

| Task | Title | Status | Dependencies |
|------|-------|--------|--------------|
| [01](agents-task-01-random-agent.md) | RandomAgent | done | env-03 |
| [02](agents-task-02-heuristic-agent.md) | HeuristicAgent | done | agents-01 |
| [04](agents-task-04-masked-model.md) | Masked actor-critic (`training/model.py`) | done | env-02 |
| [03](agents-task-03-env-registration.md) | Self-play rollout collector (`training/rollout.py`) | done | agents-04 |
| [05](agents-task-05-opponent-pool.md) | Opponent pool & snapshotting | done | agents-01, 02, 04 |
| [06](agents-task-06-reward-shaping.md) | Reward shaping | done | engine, training config |
| [07](agents-task-07-ppo-training.md) | PPO trainer (`training/ppo.py`) | done | agents-03, 04, 05, 06 |
| [08](agents-task-08-rl-policy.md) | RLPolicy inference wrapper | done | agents-07 |
| [09](agents-task-09-evaluation-harness.md) | Evaluation harness (Arena/Elo) | done | agents-01, 02, 08 |
| [10](agents-task-10-smoke-test.md) | Smoke test (>80% vs random) | done | agents-01…09 |
| [11](agents-task-11-rl-vs-heuristic-benchmark.md) | RL vs heuristic benchmark (M4) | done | agents-01…10 |

## Epic: ui
Design: `design/06-ui.md`. Depends on engine + agents.

| Task | Title | Status | Dependencies |
|------|-------|--------|--------------|
| [01](ui-task-01-backend-schemas-and-session.md) | Backend schemas & session | done | engine, agents-02, 08 |
| [02](ui-task-02-fastapi-app-and-session-manager.md) | FastAPI app & session manager | done | ui-01 |
| [03](ui-task-03-websocket-protocol.md) | WebSocket protocol | done | ui-01, 02 |
| [04](ui-task-04-action-labeling.md) | Action labeling | done | engine, env-01 |
| [05](ui-task-05-react-setup-and-board.md) | React setup & Board | done | ui-03 |
| [06](ui-task-06-react-playerboards.md) | React PlayerBoards | done | ui-05 |
| [07](ui-task-07-react-action-prompt-and-highlighting.md) | Action prompt & highlighting | done | ui-05, 04 |
| [08](ui-task-08-react-log-and-gameover.md) | Log & game-over | done | ui-05, 03 |
| [09](ui-task-09-client-integration-test.md) | Client integration test | done | ui-01, 02, 03 |
