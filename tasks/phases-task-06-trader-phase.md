# Task 06: TRADER Phase

## Status
not started

## Epic
engine-phases

## Dependencies
- phases-task-01
- engine-core-task-07
- engine-core-task-02
- buildings-task-NN (soft: market buildings, office — stub the hooks if buildings epic not yet done)

## Overview
Implement the trader role: each player may sell one good into the trading house (which holds up to 4 goods), normally only goods of kinds not already in the house unless the seller owns an occupied office. Prices include privilege and market bonuses; the house is cleared when full.

## Design References
- `design/02-engine-phases-and-flow.md`
- `design/03-buildings-reference.md`
- `design/01-engine-core-and-state.md`

## Files to Create/Modify
| File | Action | Changes |
|------|--------|---------|
| `puerto_rico/engine/phases.py` | Modify | `trader_legal_actions()`, `trader_apply()`, `trader_last_duty()` |
| `puerto_rico/engine/test_phases.py` | Modify | Trader phase tests |

## Specification
- Trading house holds 0-4 goods. Normally it may not contain two goods of the same kind.
- For the acting player, `SELL(good)` is legal iff ALL of:
  - The player holds at least one of `good`.
  - The house has room (fewer than 4 goods).
  - The kind `good` is NOT already in the house, OR the player owns an occupied office (office lets you sell a kind already present).
- `PASS` is always legal.
- Sale price (doubloons paid from supply to the seller):
  - Base by kind: corn 0, indigo 1, sugar 2, tobacco 3, coffee 4.
  - `+1` if the seller is the chooser (trader privilege).
  - `+1` if the seller owns an occupied small market.
  - `+2` if the seller owns an occupied large market.
  - (Small + large markets stack if both owned/occupied.)
- On sale: move the good from the player to the house, pay the price from the supply.
- Last duty (after all players, by chooser/end of phase): if the house now holds 4 goods, clear all of them to the goods supply; otherwise the goods carry over to the next trader phase.
- Edge cases: a corn sale yields base 0 but still benefits from privilege/market bonuses; office only relaxes the duplicate-kind restriction, not the 4-good capacity; paying price is clamped by available supply doubloons (document if supply can run out).

## Verification
- `pytest puerto_rico/engine/test_phases.py -k trader`
  - Expected: cannot sell a kind already in the house without an office; can with an office.
  - Expected: house caps at 4; full house clears to supply in last duty, partial house carries over.
  - Expected: price = base + chooser(+1) + small market(+1) + large market(+2).
