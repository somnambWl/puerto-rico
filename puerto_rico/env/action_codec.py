"""Fixed-size discrete action codec for the RL action space (design/04).

The engine emits a *variable* list of structured :class:`~puerto_rico.engine.actions.Action`
objects from ``state.legal_actions()``; RL needs a *fixed* discrete space with a
legality mask. This module is the bridge.

Layout
------
Every atomic action the engine can ever emit is enumerated into a stable integer
id in one of these contiguous blocks (offsets are module constants below):

==================  =====  =========================================================
Block               size   id i in block decodes to
==================  =====  =========================================================
SELECT_ROLE           7    role placard, ``Role(i)`` (0..6)
TAKE_TILE             6    ``TileType`` QUARRY..COFFEE (values 1..6)
PLACE_COLONIST       25    12 city slots (0..11), 12 island slots (0..11), STORE
BUILD                23    ``BuildingId(i)`` (0..22, the 23 real buildings)
SELL                  5    ``Good(i)`` (0..4)
LOAD                 20    cargo: 5 goods x 3 ships, then wharf: 5 goods
CHOOSE                5    craftsman / windrose extra-good pick, ``Good(i)`` (0..4)
PASS                  1    the single decline/pass id
==================  =====  =========================================================

``N_ACTIONS`` is the frozen total (92) — never re-derived per state.

PLACE_COLONIST encoding rationale
---------------------------------
design/04 suggests collapsing colonist placement to destination *categories*
(tile-kind / building-id / store). That is rejected here: a player can own two
empty island slots of the *same* tile kind (or, in principle, equal building
slots), so a category id would map to several distinct legal actions at once —
breaking the codec's two hard invariants (``to_int`` injective over the legal
set; ``mask.sum() == len(legal_actions)``). We instead encode the *raw slot
index* the engine actually uses (``action.target``): city slots 0..11, island
slots 0..11 (the engine tags island targets as ``100 + slot``), and the STORE
sentinel (``target == MAYOR_STORE == -1``). This is an exact bijection with what
the engine emits, so round-trip and mask counts are exact.

LOAD encoding
-------------
The captain's load is an *explicit* (good, ship) choice (the engine reworked the
old auto-resolved variant). A LOAD id encodes either:

* a **cargo** load ``Action(LOAD, good=g, target=ship_idx)`` — the player picks
  both the good kind and the destination cargo ship; the amount is still forced
  maximal by the engine. Encoded as ``good * MAX_SHIPS + ship_idx`` in the cargo
  sub-block.
* a **wharf** load ``Action(LOAD, good=g, choice=CAPTAIN_WHARF)`` — ship ALL of
  one held kind to the supply via the wharf (``target is None``). Encoded by good
  kind in the wharf sub-block that follows the cargo sub-block.

``MAX_SHIPS`` is a fixed upper bound (3, covering 4-player's 3 ships and
2-player's 2) so ``N_ACTIONS`` is constant across player counts. Cargo ids for
ship indices that don't exist in the current config are simply never legal (never
True in the mask), but the block reserves their slots regardless.

CHOOSE encoding
---------------
Two phases emit ``Action(CHOOSE, good=g)`` with identical shape: the craftsman
chooser's extra-good privilege and the captain windrose storage choice. Both are
encoded by good kind in the CHOOSE block; the engine dispatches by phase, so no
distinct id is needed. (The generic ``Action.choose(choice=...)`` constructor
exists but no phase emits it.)
"""

from __future__ import annotations

import numpy as np

from typing import TYPE_CHECKING

from puerto_rico.engine.actions import Action
from puerto_rico.engine.enums import BuildingId, DecisionType, Good, Role, TileType
from puerto_rico.engine.phases import CAPTAIN_WHARF, MAYOR_STORE
from puerto_rico.engine.setup import CITY_SLOTS, ISLAND_SLOTS

if TYPE_CHECKING:
    from puerto_rico.engine.game import Game

# --------------------------------------------------------------------------- #
# block sizes                                                                 #
# --------------------------------------------------------------------------- #

#: Number of selectable role placards.
N_ROLES = 7
#: TAKE_TILE kinds: QUARRY + 5 plantations (TileType values 1..6; EMPTY excluded).
N_TILES = 6
#: City building slots a colonist can be placed on. Derived from the engine's
#: authoritative board size so a board-size change propagates here.
N_CITY_SLOTS = CITY_SLOTS
#: Island plantation/quarry slots a colonist can be placed on. Derived from the
#: engine's authoritative board size.
N_ISLAND_SLOTS = ISLAND_SLOTS
#: Real buildings in the catalog (BuildingId 0..22).
N_BUILDINGS = 23
#: Tradeable/producible goods.
N_GOODS = 5
#: Fixed upper bound on cargo ships across all supported player counts (4p has 3
#: ships, 2p has 2). Keeps the LOAD block — and thus N_ACTIONS — constant.
MAX_SHIPS = 3
#: LOAD block size: cargo (5 goods x MAX_SHIPS ships) + wharf (5 goods).
N_LOAD = N_GOODS * MAX_SHIPS + N_GOODS

# Internal index of the island tile kinds within the TAKE_TILE block. The block
# is laid out in TileType order skipping EMPTY: QUARRY(1)..COFFEE(6) -> 0..5.
_TILE_ORDER: tuple[TileType, ...] = (
    TileType.QUARRY,
    TileType.CORN,
    TileType.INDIGO,
    TileType.SUGAR,
    TileType.TOBACCO,
    TileType.COFFEE,
)

#: Offset the engine adds to an island slot index in a PLACE_COLONIST target
#: (city slots are 0..11, island slots are 100..111). Mirrors phases.py.
_ISLAND_TARGET_OFFSET = 100

# --------------------------------------------------------------------------- #
# block offsets (contiguous)                                                  #
# --------------------------------------------------------------------------- #

ROLE_OFFSET = 0
TAKE_TILE_OFFSET = ROLE_OFFSET + N_ROLES

PLACE_OFFSET = TAKE_TILE_OFFSET + N_TILES
# Within PLACE block: [city 0..11][island 0..11][store]
PLACE_CITY_OFFSET = PLACE_OFFSET
PLACE_ISLAND_OFFSET = PLACE_CITY_OFFSET + N_CITY_SLOTS
PLACE_STORE_OFFSET = PLACE_ISLAND_OFFSET + N_ISLAND_SLOTS
N_PLACE = N_CITY_SLOTS + N_ISLAND_SLOTS + 1  # +1 for STORE

BUILD_OFFSET = PLACE_OFFSET + N_PLACE
SELL_OFFSET = BUILD_OFFSET + N_BUILDINGS

LOAD_OFFSET = SELL_OFFSET + N_GOODS
# Within LOAD block:
#   cargo sub-block: id = LOAD_CARGO_OFFSET + good * MAX_SHIPS + ship_idx
#   wharf sub-block: id = LOAD_WHARF_OFFSET + good
LOAD_CARGO_OFFSET = LOAD_OFFSET
LOAD_WHARF_OFFSET = LOAD_CARGO_OFFSET + N_GOODS * MAX_SHIPS

CHOOSE_OFFSET = LOAD_OFFSET + N_LOAD
PASS_OFFSET = CHOOSE_OFFSET + N_GOODS

#: Frozen total size of the discrete action space. Never re-derive per state.
N_ACTIONS = PASS_OFFSET + 1  # == 92


# --------------------------------------------------------------------------- #
# encode: Action -> int                                                       #
# --------------------------------------------------------------------------- #


def to_int(action: Action) -> int:
    """Encode a structured engine ``Action`` to its stable integer id.

    Total over every action ``state.legal_actions()`` can emit. Inverse of
    :func:`from_int` on the legal set.
    """
    t = action.type

    if t == DecisionType.SELECT_ROLE:
        return ROLE_OFFSET + int(action.role)

    if t == DecisionType.TAKE_TILE:
        # TileType values: QUARRY=1..COFFEE=6 -> 0..5 (EMPTY=0 is never taken).
        return TAKE_TILE_OFFSET + (int(action.tile) - 1)

    if t == DecisionType.PLACE_COLONIST:
        target = action.target
        if target == MAYOR_STORE:
            return PLACE_STORE_OFFSET
        if target >= _ISLAND_TARGET_OFFSET:
            return PLACE_ISLAND_OFFSET + (target - _ISLAND_TARGET_OFFSET)
        return PLACE_CITY_OFFSET + target

    if t == DecisionType.BUILD:
        return BUILD_OFFSET + int(action.building)

    if t == DecisionType.SELL:
        return SELL_OFFSET + int(action.good)

    if t == DecisionType.LOAD:
        if action.choice == CAPTAIN_WHARF:
            return LOAD_WHARF_OFFSET + int(action.good)
        ship_idx = action.target
        if ship_idx is None or not 0 <= ship_idx < MAX_SHIPS:
            raise ValueError(f"cargo LOAD has out-of-range ship target: {action!r}")
        return LOAD_CARGO_OFFSET + int(action.good) * MAX_SHIPS + ship_idx

    if t == DecisionType.CHOOSE:
        # Both the craftsman extra-good pick and the captain windrose storage
        # choice emit Action(CHOOSE, good=g); the engine dispatches by phase.
        return CHOOSE_OFFSET + int(action.good)

    if t == DecisionType.PASS:
        return PASS_OFFSET

    raise ValueError(f"cannot encode action {action!r}")


# --------------------------------------------------------------------------- #
# decode: int -> Action                                                       #
# --------------------------------------------------------------------------- #


def from_int(i: int, state=None) -> Action:
    """Decode id ``i`` back to the exact ``Action`` the engine expects.

    ``state`` is accepted for symmetry with the design (some decoders may need
    it) but is **not required** and is ignored here: the chosen encoding is
    self-contained — every block is a direct bijection, so no state lookup is
    needed to reconstruct the engine-equal ``Action``. The decoded action is
    ``==`` to its counterpart in ``state.legal_actions()``.
    """
    if not 0 <= i < N_ACTIONS:
        raise ValueError(f"action id {i} out of range [0, {N_ACTIONS})")

    if i < TAKE_TILE_OFFSET:
        return Action.select_role(Role(i - ROLE_OFFSET))

    if i < PLACE_OFFSET:
        # TAKE_TILE block: 0..5 -> TileType 1..6.
        return Action.take_tile(TileType((i - TAKE_TILE_OFFSET) + 1))

    if i < BUILD_OFFSET:
        if i == PLACE_STORE_OFFSET:
            return Action.place_colonist(MAYOR_STORE)
        if i >= PLACE_ISLAND_OFFSET:
            slot = i - PLACE_ISLAND_OFFSET
            return Action.place_colonist(_ISLAND_TARGET_OFFSET + slot)
        slot = i - PLACE_CITY_OFFSET
        return Action.place_colonist(slot)

    if i < SELL_OFFSET:
        return Action.build(BuildingId(i - BUILD_OFFSET))

    if i < LOAD_OFFSET:
        return Action.sell(Good(i - SELL_OFFSET))

    if i < CHOOSE_OFFSET:
        if i >= LOAD_WHARF_OFFSET:
            good = Good(i - LOAD_WHARF_OFFSET)
            return Action(DecisionType.LOAD, good=good, choice=CAPTAIN_WHARF)
        rel = i - LOAD_CARGO_OFFSET
        good = Good(rel // MAX_SHIPS)
        ship_idx = rel % MAX_SHIPS
        return Action.load(good, target=ship_idx)

    if i < PASS_OFFSET:
        return Action(DecisionType.CHOOSE, good=Good(i - CHOOSE_OFFSET))

    return Action.passing()


# --------------------------------------------------------------------------- #
# mask                                                                         #
# --------------------------------------------------------------------------- #


def mask(game: "Game") -> np.ndarray:
    """Boolean legality mask of shape ``(N_ACTIONS,)`` for ``game``.

    Built directly from ``game.legal_actions()`` so it can never diverge from
    engine legality. Exactly ``len(game.legal_actions())`` entries are ``True``;
    each ``True`` id decodes (``from_int``) to an action in ``legal_actions()``.
    Takes the ``Game`` facade (not a bare ``GameState``) because it calls
    ``legal_actions()``.
    """
    m = np.zeros(N_ACTIONS, dtype=bool)
    for a in game.legal_actions():
        m[to_int(a)] = True
    return m


class ActionCodec:
    """Stateless namespace wrapper over the module-level codec functions.

    Provided for an object-style call site; all methods are thin static
    delegates to the module functions, which remain the canonical API.
    """

    N_ACTIONS = N_ACTIONS

    @staticmethod
    def to_int(action: Action) -> int:
        return to_int(action)

    @staticmethod
    def from_int(i: int, state=None) -> Action:
        return from_int(i, state)

    @staticmethod
    def mask(game: "Game") -> np.ndarray:
        return mask(game)
