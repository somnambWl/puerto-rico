# Task 06: Serialization

## Status
not started

## Epic
engine-core

## Dependencies
- engine-core-task-01
- engine-core-task-02
- engine-core-task-03

## Overview
Implement lossless serialization (`to_dict`/`from_dict`) and a perspective-aware `public_view` that hides hidden information from opponents.

## Design References
- `design/00-overview-and-architecture.md`
- `design/01-engine-core-and-state.md`

## Files to Create/Modify
| File | Action | Changes |
|------|--------|---------|
| `puerto_rico/engine/serialize.py` | Create | `to_dict`, `from_dict`, `public_view` |
| `puerto_rico/engine/test_serialize.py` | Create | Round-trip + public_view tests |

## Specification
In `puerto_rico/engine/serialize.py`:

- `to_dict(state: GameState) -> dict`: lossless. Must capture every field needed to reconstruct the exact state, including `state.rng.getstate()` (serialized in a JSON-friendly form, e.g. lists for the tuple state).
- `from_dict(d: dict) -> GameState`: inverse of `to_dict`. The reconstructed state must be equal to the original, including RNG state (restored via `setstate`).
- `public_view(state: GameState, perspective: int | None = None) -> dict`: a view safe to send to a client/agent.
  - When `perspective` is set to a player index, hide hidden information from other players:
    - Other players' `vp_chips` (victory-point chips are face-down / secret).
    - The identity and ordering of the face-down plantation deck (`plantation_facedown`) — expose count only, not contents/order.
  - The perspective player's own hidden info is fully visible.
  - When `perspective is None`, return the full (god-view) public dict (no hiding) — used for debugging/spectator.

## Notes
- `to_dict`/`from_dict` must round-trip enums (store as int values) and `None`s correctly.
- `public_view` is for transport, not for re-loading; it intentionally drops information.
- Downstream: the UI epic (`design/06-ui.md`) consumes `public_view`.

## Verification
Run `pytest puerto_rico/engine/test_serialize.py`.

Expected behavior:
- **Round-trip**: `from_dict(to_dict(s))` equals `s`, including RNG (the reconstructed state produces the same next RNG values as the original).
- **public_view hides opponents**: with `perspective=p`, other players' `vp_chips` are absent/masked and `plantation_facedown` exposes only a count, not contents; player `p`'s own data is intact.
