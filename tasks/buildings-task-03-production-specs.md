# Task 03: Production Buildings — Vanilla Specs

## Status
not started

## Epic
buildings

## Dependencies
- buildings-task-01

## Overview
Confirm and lock the six production buildings as pure data: they have no custom hooks (their output is computed in the craftsman phase, design/02) and therefore declare `timings=()`.

## Design References
- `design/03-buildings-reference.md`
- `design/01-engine-core-and-state.md`

## Files to Create/Modify
| File | Action | Changes |
|------|--------|---------|
| `puerto_rico/engine/buildings.py` | Modify | Ensure the 6 production specs are correct in `CATALOG` (data only; no handlers) |
| `puerto_rico/engine/test_buildings_production.py` | Create | Per-building spec assertions |

## Specification
The six production buildings are vanilla — **no entries in `HANDLERS`**. Each has `is_production=True`, `is_large=False`, `produces` set, and `timings=()`. Production output (`min(manned circles, occupied matching plantations, supply)`) is computed by the craftsman phase, not by a building hook. There is no corn production building.

| id | name | cost | col | vp | capacity (circles) | produces |
|----|------|------|-----|----|--------------------|----------|
| SMALL_INDIGO | small indigo plant | 1 | 1 | 1 | 1 | INDIGO |
| INDIGO_PLANT | indigo plant | 3 | 2 | 2 | 3 | INDIGO |
| SMALL_SUGAR | small sugar mill | 2 | 1 | 1 | 1 | SUGAR |
| SUGAR_MILL | sugar mill | 4 | 2 | 2 | 3 | SUGAR |
| TOBACCO_STORAGE | tobacco storage | 5 | 3 | 3 | 3 | TOBACCO |
| COFFEE_ROASTER | coffee roaster | 6 | 3 | 3 | 2 | COFFEE |

(If Task 01 already encoded these correctly, this task is verification + the dedicated test file. Do not add handlers.)

## Verification
Run `pytest puerto_rico/engine/test_buildings_production.py`.

Expected behavior:
- For each of the 6 ids: cost, column, vp, capacity, and `produces` match the table.
- Every production spec has `timings == ()`.
- No `(production_id, *)` key exists in `HANDLERS`.
- No production spec has `is_large == True`.
