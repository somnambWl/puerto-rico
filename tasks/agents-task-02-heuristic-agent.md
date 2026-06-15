# Task 02: HeuristicAgent

## Status
not started

## Epic
agents-training

## Dependencies
- agents-task-01
- engine

## Overview
Implement a rule-based `HeuristicAgent` with phase/role-specific decision logic. Target strength: decent but beatable, comfortably above random.

## Design References
- `design/05-agents-and-training.md`

## Files to Create/Modify
| File | Action | Changes |
|------|--------|---------|
| `puerto_rico/agents/heuristic_agent.py` | Create | `HeuristicAgent` implementation |
| `puerto_rico/agents/__init__.py` | Modify | Export `HeuristicAgent` |

## Specification

### `HeuristicAgent(Agent)`
- Conforms to the `Agent` protocol from agents-task-01: `act(obs, *, rng=None) -> int`, `reset()`.
- Decisions must be derived only from legal actions exposed by the engine (the engine remains the source of truth for legality). The agent decodes the current decision context (which role/phase is being resolved and the candidate actions) and applies the matching rule below. Ties broken with `rng` when provided, else deterministically.

### Phase-specific rules
- **Role selection:** prefer roles that advance the player's engine (production/development). Pick **Prospector** when low on doubloons. Grab roles carrying accumulated doubloon placards when doubloons are scarce.
- **Settler:** choose plantations that complete production chains (match owned/empty production buildings); prefer **Quarry** when entitled and it is useful for build discounts.
- **Mayor:** distribute colonists to fill production chains first (occupy production buildings that have output but lack workers); avoid leaving colonists wasted/unused.
- **Builder:** buy the cheapest building that increases production or victory points; apply quarry discounts; avoid buildings that cannot be staffed or paid for.
- **Craftsman:** when choosing the extra/bonus good, take the good of highest market value available.
- **Trader:** sell the highest-price good that is currently legal to sell.
- **Captain:** ship to maximize victory points this round; exploit Harbor (extra VP) and Wharf (own ship) when owned.

### General
- Every branch must select from the legal action set; if a rule's preferred action is not legal, fall back to the next-best legal action, and ultimately to any legal action (never violate the mask).
- `reset()` clears any per-episode caches.

## Verification
- Full 4-player games with `HeuristicAgent`s: **0 action-mask violations**.
- Over >=200 seat-rotated games of 1 `HeuristicAgent` vs 3 `RandomAgent`s, the heuristic seat wins **well above 25%** (clearly dominant).
