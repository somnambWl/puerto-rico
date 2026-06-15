# Task 04: Action Labeling Module

## Status
done

## Epic
ui

## Dependencies
- engine
- env-task-01 (ActionCodec)

## Overview
Produce human-readable labels for each legal action by decoding the action int and
querying the current game state for the relevant detail (building cost, ship index,
plantation type, etc.).

## Design References
- `design/06-ui.md`

## Files to Create/Modify
| File | Action | Changes |
|------|--------|---------|
| `puerto_rico/ui/backend/labels.py` | create | `label_action(...)` + helpers |
| `puerto_rico/ui/backend/test_labels.py` | create | label string tests per kind |

## Specification

### `label_action(action_id, game, legal_actions) -> str`
- Decode `action_id` via the env `ActionCodec` (env-task-01) into a structured
  action (kind + parameters).
- Query `game` state to enrich the label with concrete detail.

Examples (exact wording is a guideline, must be sensible and unambiguous):
- Build a building → `"Build Coffee Roaster (cost 6)"` (name + doubloon cost).
- Ship goods → `"Ship 3 sugar to ship #2"` (quantity, good, ship index).
- Select a plantation → `"Take Indigo plantation"`.
- Pick a role → `"Take Captain (+1 doubloon)"` when doubloons sit on the placard.
- Trade → `"Sell coffee for 5 doubloons"`.
- Pass / decline options → `"Pass"`, `"Take no plantation"`, etc.

Also expose a helper that returns the action `kind` and a structured `detail` dict
(used by `StateMsg.legal_actions[]` for board highlighting in task 07). The session
(task 01) calls this to populate each `LegalAction.{label,kind,detail}`.

`legal_actions` (the full set) is passed so the labeler can disambiguate (e.g. order
of multiple identical-looking ship actions).

## Verification
`pytest puerto_rico/ui/backend/test_labels.py`:
- For a game positioned (or stubbed) to expose each action kind, assert
  `label_action` returns a non-empty, sensible string containing the expected
  tokens (e.g. a build label contains the building name and `"cost"`; a ship label
  contains a quantity and good name).
