"""Flat observation encoder: ``GameState -> np.ndarray(OBS_LEN, float32)``.

``encode(state, perspective)`` turns a :class:`~puerto_rico.engine.state.GameState`
into a fixed-length ``float32`` vector seen from one player's point of view, for
RL. The layout is **perspective-symmetric**: the player blocks are ordered
self-first, then opponents in clockwise seating order, so a parameter-shared
self-play policy sees its own seat in the same slots regardless of which seat it
occupies (critical for self-play, see design/04 / design/05).

Hidden information is respected:
- An opponent's ``vp_chips`` is never written (encoded ``0`` plus a "known" flag
  that is ``1.0`` only for self), so the policy cannot read hidden VP.
- The face-down plantation stack is encoded by **count only** — never by the
  identity of its tiles.

Everything is normalized to roughly ``[0, 1]`` (a few one-hot/flag features are
exactly ``0``/``1``) by dividing by documented maxima (see ``_MAX_*`` below).
Values are clipped so out-of-range states (e.g. doubloon piles above the cap)
still produce finite, in-range numbers — no NaNs or infs ever.

The layout lives in ONE place: a list of named field groups assembled in
``_build_layout()``, which yields both the writer order and ``describe()``'s
per-index labels, so the two can never drift apart.
"""

from __future__ import annotations

import numpy as np

from ..engine.buildings import CATALOG
from ..engine.enums import BuildingId, Good, Phase, Role, TileType
from ..engine.state import GameState

# --------------------------------------------------------------------------- #
# Structural constants                                                        #
# --------------------------------------------------------------------------- #

# Player-count-independent block sizing so OBS_LEN is constant across configs.
# 4-player is the tuned target; 2-player encodes into the same vector with the
# unused opponent blocks left at zero.
MAX_PLAYERS = 4
MAX_CARGO_SHIPS = 3

# Real buildings only (LARGE_CONT is a sentinel, never in CATALOG), in stable
# enum order so per-building features have a fixed index.
_BUILDINGS: list[BuildingId] = sorted(CATALOG.keys(), key=int)
NUM_BUILDINGS = len(_BUILDINGS)

_GOODS: list[Good] = list(Good)  # 5
NUM_GOODS = len(_GOODS)

_ROLES: list[Role] = list(Role)  # 7
NUM_ROLES = len(_ROLES)

# Island tile kinds that can actually occupy a slot (EMPTY excluded): QUARRY +
# the 5 plantation kinds = 6.
_TILE_KINDS: list[TileType] = [t for t in TileType if t != TileType.EMPTY]
NUM_TILE_KINDS = len(_TILE_KINDS)

_PHASES: list[Phase] = list(Phase)  # 8 (incl GAME_OVER)
NUM_PHASES = len(_PHASES)

# --------------------------------------------------------------------------- #
# Normalization maxima (documented caps; values are clipped to [0, 1])        #
# --------------------------------------------------------------------------- #

_MAX_DOUBLOONS = 60.0  # doubloon pile rarely exceeds ~50; cap a bit above.
_MAX_VP = 75.0  # 4p VP pool is 100, but a single player's chips ~ up to 75.
_MAX_GOODS_HELD = 12.0  # a player rarely holds more than a dozen of one good.
_MAX_COLONISTS_HELD = 20.0  # stored colonists at one player.
_MAX_ISLAND_SLOTS = 12.0
_MAX_CITY_CIRCLES = 12.0  # free building circles across a city.
_MAX_TILE_OF_KIND = 12.0  # at most 12 island slots -> 12 of one kind.

_MAX_PLACARD_DOUBLOONS = 10.0  # doubloons that pile up on a skipped placard.
_MAX_COLONIST_SHIP = 12.0  # colonists waiting on the ship.
_MAX_COLONIST_SUPPLY = 75.0  # 4p starting supply.
_MAX_CARGO_CAPACITY = 8.0  # largest cargo ship capacity (+ headroom).
_MAX_TRADING_HOUSE = 4.0  # trading house holds at most 4 goods.
_MAX_GOODS_SUPPLY = 12.0  # per-good supply pool size.
_MAX_FACEUP_OF_KIND = 6.0  # face-up plantation row is small.
_MAX_FACEDOWN = 50.0  # full plantation deck size.
_MAX_QUARRY_SUPPLY = 8.0
_MAX_VP_REMAINING = 100.0  # 4p VP pool.
_MAX_BUILDING_SUPPLY = 2.0  # production buildings have 2 copies, beige have 1.

_MAX_COLONISTS_TO_PLACE = 12.0  # mayor placement scratch.
# Cap for seat-relative *indices* (order_pos, current_player_rel). These range
# 0..num_players-1, so dividing by MAX_PLAYERS leaves the top of [0, 1] slightly
# unreachable (e.g. 3/4 at 4 players). Kept as MAX_PLAYERS for a stable cap that
# never clips across configs; it is an upper bound, not the literal max index.
_MAX_ORDER_INDEX_CAP = float(MAX_PLAYERS)


# --------------------------------------------------------------------------- #
# Layout: a single ordered list of feature names -> OBS_LEN + describe()      #
# --------------------------------------------------------------------------- #


def _player_block_names(tag: str) -> list[str]:
    """Feature labels for one player block (``tag`` is ``"self"`` or ``"oppK"``)."""
    names = [
        f"{tag}.doubloons",
        f"{tag}.stored_colonists",
        f"{tag}.vp_chips",
        f"{tag}.vp_known_flag",
        f"{tag}.filled_island_spaces",
        f"{tag}.empty_building_circles",
    ]
    names += [f"{tag}.goods[{g.name}]" for g in _GOODS]
    names += [f"{tag}.island_count[{t.name}]" for t in _TILE_KINDS]
    names += [f"{tag}.island_manned[{t.name}]" for t in _TILE_KINDS]
    for b in _BUILDINGS:
        names.append(f"{tag}.city_owned[{b.name}]")
        names.append(f"{tag}.city_occupied[{b.name}]")
    return names


def _shared_block_names() -> list[str]:
    names: list[str] = []
    for r in _ROLES:
        names.append(f"shared.placard_available[{r.name}]")
        names.append(f"shared.placard_doubloons[{r.name}]")
    names.append("shared.colonist_ship")
    names.append("shared.colonist_supply")
    for k in range(MAX_CARGO_SHIPS):
        names.append(f"shared.ship{k}.capacity")
        for g in _GOODS:
            names.append(f"shared.ship{k}.good[{g.name}]")
        names.append(f"shared.ship{k}.empty")
        names.append(f"shared.ship{k}.count")
    names += [f"shared.trading_house[{g.name}]" for g in _GOODS]
    names += [f"shared.goods_supply[{g.name}]" for g in _GOODS]
    names += [f"shared.plantation_faceup[{t.name}]" for t in _TILE_KINDS]
    names.append("shared.plantation_facedown_size")
    names.append("shared.quarry_supply")
    names.append("shared.vp_chips_remaining")
    names += [f"shared.buildings_supply[{b.name}]" for b in _BUILDINGS]
    return names


def _phase_block_names() -> list[str]:
    names = [f"phase.onehot[{p.name}]" for p in _PHASES]
    names += [f"phase.active_role[{r.name}]" for r in _ROLES]
    names.append("phase.active_role[NONE]")
    names.append("phase.colonists_to_place")
    names.append("phase.order_pos")
    names.append("phase.current_player_rel")
    return names


def _build_layout() -> list[str]:
    names: list[str] = []
    names += _player_block_names("self")
    for k in range(MAX_PLAYERS - 1):
        names += _player_block_names(f"opp{k}")
    names += _shared_block_names()
    names += _phase_block_names()
    return names


_FEATURE_NAMES: list[str] = _build_layout()
OBS_LEN: int = len(_FEATURE_NAMES)

# Size of one player block (constant); used for per-block self/opp validation.
PLAYER_BLOCK_LEN: int = len(_player_block_names("self"))


def describe() -> list[str]:
    """Human-readable label per feature index (length == ``OBS_LEN``)."""
    return list(_FEATURE_NAMES)


# --------------------------------------------------------------------------- #
# Encoding                                                                     #
# --------------------------------------------------------------------------- #


def _norm(value: float, cap: float) -> float:
    """Scale ``value`` to ``[0, 1]`` by ``cap``, clipped; never NaN/inf."""
    if cap <= 0:
        return 0.0
    x = value / cap
    if x < 0.0:
        return 0.0
    if x > 1.0:
        return 1.0
    return x


def _write_player_block(
    out: np.ndarray, base: int, player, is_self: bool
) -> int:
    """Write one player block at ``out[base:]``; return the next free offset."""
    i = base
    out[i] = _norm(player.doubloons, _MAX_DOUBLOONS); i += 1
    out[i] = _norm(player.stored_colonists, _MAX_COLONISTS_HELD); i += 1
    # vp_chips: self only — opponents' VP is hidden info -> 0, flag 0.
    out[i] = _norm(player.vp_chips, _MAX_VP) if is_self else 0.0; i += 1
    out[i] = 1.0 if is_self else 0.0; i += 1
    out[i] = _norm(player.filled_island_spaces(), _MAX_ISLAND_SLOTS); i += 1
    out[i] = _norm(player.empty_building_circles(), _MAX_CITY_CIRCLES); i += 1

    for g in _GOODS:
        out[i] = _norm(player.goods[g], _MAX_GOODS_HELD); i += 1

    # Island tile-kind counts and how many of each kind are manned.
    counts = {t: 0 for t in _TILE_KINDS}
    manned = {t: 0 for t in _TILE_KINDS}
    for slot in player.island:
        if slot.tile == TileType.EMPTY:
            continue
        counts[slot.tile] += 1
        if slot.colonist:
            manned[slot.tile] += 1
    for t in _TILE_KINDS:
        out[i] = _norm(counts[t], _MAX_TILE_OF_KIND); i += 1
    for t in _TILE_KINDS:
        out[i] = _norm(manned[t], _MAX_TILE_OF_KIND); i += 1

    # City: per building (owned?, occupied?).
    for b in _BUILDINGS:
        owned = player.owns(b)
        out[i] = 1.0 if owned else 0.0; i += 1
        out[i] = 1.0 if (owned and player.occupied(b)) else 0.0; i += 1

    return i


def _write_shared_block(out: np.ndarray, base: int, state: GameState) -> int:
    i = base
    # Role placards: available? + doubloons-on-it. Index by Role so a missing
    # placard (e.g. dropped prospector) reads as unavailable.
    placard_by_role: dict[Role, object] = {}
    for pl in state.placards:
        placard_by_role.setdefault(pl.role, pl)
    for r in _ROLES:
        pl = placard_by_role.get(r)
        if pl is None:
            out[i] = 0.0; i += 1
            out[i] = 0.0; i += 1
        else:
            available = pl.taken_by is None
            out[i] = 1.0 if available else 0.0; i += 1
            out[i] = _norm(pl.doubloons, _MAX_PLACARD_DOUBLOONS); i += 1

    out[i] = _norm(state.colonist_ship, _MAX_COLONIST_SHIP); i += 1
    out[i] = _norm(state.colonist_supply, _MAX_COLONIST_SUPPLY); i += 1

    # Cargo ships (fixed MAX_CARGO_SHIPS; absent ships read all-zero w/ empty=1).
    for k in range(MAX_CARGO_SHIPS):
        ship = state.cargo_ships[k] if k < len(state.cargo_ships) else None
        if ship is None:
            out[i] = 0.0; i += 1  # capacity
            for _ in _GOODS:
                out[i] = 0.0; i += 1  # good one-hot
            out[i] = 1.0; i += 1  # empty flag
            out[i] = 0.0; i += 1  # count
            continue
        out[i] = _norm(ship.capacity, _MAX_CARGO_CAPACITY); i += 1
        for g in _GOODS:
            out[i] = 1.0 if ship.good == g else 0.0; i += 1
        out[i] = 1.0 if (ship.good is None or ship.count == 0) else 0.0; i += 1
        out[i] = _norm(ship.count, _MAX_CARGO_CAPACITY); i += 1

    # Trading house: multiset over the 5 goods.
    th_counts = {g: 0 for g in _GOODS}
    for g in state.trading_house:
        th_counts[g] += 1
    for g in _GOODS:
        out[i] = _norm(th_counts[g], _MAX_TRADING_HOUSE); i += 1

    for g in _GOODS:
        out[i] = _norm(state.goods_supply[g], _MAX_GOODS_SUPPLY); i += 1

    # Face-up plantation row: count per kind (identities ARE public here).
    faceup_counts = {t: 0 for t in _TILE_KINDS}
    for t in state.plantation_faceup:
        if t in faceup_counts:
            faceup_counts[t] += 1
    for t in _TILE_KINDS:
        out[i] = _norm(faceup_counts[t], _MAX_FACEUP_OF_KIND); i += 1

    # Face-down stack: SIZE ONLY (identities are hidden info).
    out[i] = _norm(len(state.plantation_facedown), _MAX_FACEDOWN); i += 1
    out[i] = _norm(state.quarry_supply, _MAX_QUARRY_SUPPLY); i += 1
    out[i] = _norm(state.vp_chips_remaining, _MAX_VP_REMAINING); i += 1

    for b in _BUILDINGS:
        out[i] = _norm(state.buildings_supply.get(b, 0), _MAX_BUILDING_SUPPLY); i += 1

    return i


def _write_phase_block(
    out: np.ndarray, base: int, state: GameState, perspective: int
) -> int:
    i = base
    for p in _PHASES:
        out[i] = 1.0 if state.phase == p else 0.0; i += 1

    ps = state.phase_state
    for r in _ROLES:
        out[i] = 1.0 if ps.active_role == r else 0.0; i += 1
    out[i] = 1.0 if ps.active_role is None else 0.0; i += 1

    out[i] = _norm(ps.colonists_to_place, _MAX_COLONISTS_TO_PLACE); i += 1
    out[i] = _norm(ps.order_pos, _MAX_ORDER_INDEX_CAP); i += 1

    # Current player relative to perspective (0 == perspective is to move).
    n = len(state.players)
    rel = (state.current_player - perspective) % n
    out[i] = _norm(rel, _MAX_ORDER_INDEX_CAP); i += 1
    return i


def encode(state: GameState, perspective: int) -> np.ndarray:
    """Encode ``state`` from ``perspective``'s point of view.

    Returns a flat ``float32`` array of length ``OBS_LEN``. Player blocks are
    ordered self-first then opponents clockwise, so the encoding is symmetric
    across seats. ``perspective`` must be a valid player index.
    """
    n = len(state.players)
    if not (0 <= perspective < n):
        raise IndexError(f"perspective {perspective} out of range for {n} players")

    out = np.zeros(OBS_LEN, dtype=np.float32)
    i = 0

    # Self first, then opponents in clockwise seating order.
    i = _write_player_block(out, i, state.players[perspective], is_self=True)
    for k in range(1, MAX_PLAYERS):
        if k < n:
            seat = (perspective + k) % n
            i = _write_player_block(out, i, state.players[seat], is_self=False)
        else:
            # Absent seat (e.g. 2-player): leave its block all-zero.
            i += PLAYER_BLOCK_LEN

    i = _write_shared_block(out, i, state)
    i = _write_phase_block(out, i, state, perspective)

    assert i == OBS_LEN, f"layout mismatch: wrote {i}, expected {OBS_LEN}"
    return out
