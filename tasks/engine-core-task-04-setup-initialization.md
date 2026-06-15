# Task 04: Setup & Initialization

## Status
not started

## Epic
engine-core

## Dependencies
- engine-core-task-01
- engine-core-task-02
- engine-core-task-03

## Overview
Implement `new_game(config)` which builds a fully initialized `GameState` for the start of a game, with all per-player-count constants centralized in a `SETUP` dict.

## Design References
- `design/00-overview-and-architecture.md`
- `design/01-engine-core-and-state.md`
- `design/03-buildings-reference.md`

## Files to Create/Modify
| File | Action | Changes |
|------|--------|---------|
| `puerto_rico/engine/setup.py` | Create | `SETUP` constants dict + `new_game()` |
| `puerto_rico/engine/test_setup.py` | Create | `test_4player_initial_state` |

## Specification
In `puerto_rico/engine/setup.py`:

`new_game(config: GameConfig) -> GameState`

Centralize per-player-count constants in a `SETUP` dict keyed by `num_players` so 2-player remains configurable. The 4-player entry must produce:

- **Doubloons**: 3 per player.
- **VP pool** (`vp_chips_remaining`): 100.
- **Colonist supply** (`colonist_supply`): 75.
- **Colonist ship** (`colonist_ship`): 4 colonists at start.
- **Cargo ships**: 3 ships with capacities 5, 6, 7.
- **Role placards**: 7 placards (one per `Role`), each starting with 0 doubloons, `taken_by=None`.
- **Face-up plantations** (`plantation_faceup`): 5 tiles revealed.
- **Plantation tile counts (base game, full supply)**: 8 coffee, 9 tobacco, 10 corn, 11 sugar, 12 indigo, plus 8 quarries.
- **Goods supply** (`goods_supply`, indexed by `Good`): corn 10, sugar 11, indigo 11, tobacco 9, coffee 9.
- **Buildings supply** (`buildings_supply`): 2 of each small/production building, 1 of each large building, with production-building counts per `design/03-buildings-reference.md`.
- **Starting tiles**: players 0 and 1 each start with one INDIGO plantation; players 2 and 3 each start with one CORN plantation.
- `governor = 0`
- `current_player = 0`
- `phase = Phase.ROLE_SELECTION`

Initialize `rng` from `config.seed` (deterministic). Plantation face-down deck and any shuffling must be driven by `rng` so games are reproducible.

## Notes
- Quarry tiles tracked via `quarry_supply` (8); plantation tiles via faceup/facedown/discard lists.
- Downstream epics (engine-phases, buildings) assume `new_game` leaves the state in a legal `ROLE_SELECTION` start position.

## Verification
Run `pytest puerto_rico/engine/test_setup.py`.

`test_4player_initial_state` asserts all of the above for a 4-player `GameConfig`:
- 4 players, each with 3 doubloons.
- `vp_chips_remaining == 100`, `colonist_supply == 75`, `colonist_ship == 4`.
- cargo ship capacities `[5, 6, 7]`.
- 7 placards; 5 face-up plantations.
- goods supply `corn=10, sugar=11, indigo=11, tobacco=9, coffee=9`.
- starting tiles: players 0,1 INDIGO; players 2,3 CORN.
- `governor == 0`, `current_player == 0`, `phase == Phase.ROLE_SELECTION`.
- Two `new_game` calls with the same seed produce identical states.
