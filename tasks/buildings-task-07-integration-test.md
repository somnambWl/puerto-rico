# Task 07: Integration Test — Full Catalog & Interactions

## Status
done

## Epic
buildings

## Dependencies
- buildings-task-01
- buildings-task-02
- buildings-task-03
- buildings-task-04
- buildings-task-05
- buildings-task-06

## Overview
End-to-end test that constructs a state with all 23 buildings built and occupied, runs end-game scoring, and asserts the total VP matches a hand-computed expected value documented in the test.

## Design References
- `design/03-buildings-reference.md`
- `design/01-engine-core-and-state.md`

## Files to Create/Modify
| File | Action | Changes |
|------|--------|---------|
| `puerto_rico/engine/test_buildings_integration.py` | Create | Full catalog build + occupy + score integration test |

## Specification
- Construct a game/player state in which **all 23 buildings** are owned by a single player, each occupied (≥1 colonist), with a defined island and VP-chip configuration.
- Fire `SCORE_END` across all buildings via `fire()` and compute end VP.
- The test must:
  - **Document the expected total** as an inline comment breaking down: base printed VP (all 23 buildings) + each large building's SCORE_END extra, given the fixed test setup.
  - Hand-compute each large building's extra from the Task 06 rules for the chosen setup (guild hall from owned production counts, residence from filled island spaces, fortress from total colonists, customs house from VP chips, city hall from beige-building count of 17).
  - Assert computed end VP equals the documented hand total.
- Include the two required interaction sub-tests (or reference the dedicated ones in Task 05): hacienda + construction hut, and hacienda + hospice.
- Assert catalog completeness here too: all 23 ids buildable, none missing a spec.

### Setup notes for the hand computation
- Beige buildings owned = 17 (12 small + 5 large) → city hall extra = +17.
- Production buildings owned = 6 (2 small + 4 large) → guild hall extra = +(2*1 + 4*2) = +10.
- Residence/fortress/customs house extras depend on the chosen island/colonist/VP-chip values — fix these explicitly in the test fixture and compute accordingly.
- Base printed VP from the 23 buildings: production = 1+2+1+2+3+3 = 12; small beige (12) printed = 1+1+1+1+2+2+2+2+3+3+3+3 = 24; large beige base = 5*4 = 20. Base total = 56 (before any SCORE_END extras and before earned VP chips).

## Verification
Run `pytest puerto_rico/engine/test_buildings_integration.py`.

Expected behavior:
- All 23 buildings present, built, and occupied in the fixture.
- Computed end VP equals the inline-documented hand total (base 56 + documented large-building extras + earned VP chips).
- Interaction sub-tests pass.
