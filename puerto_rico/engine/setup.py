"""Game setup / initialization for the Puerto Rico engine.

``new_game(config)`` builds a fully initialized :class:`GameState` for the
start of a game. All per-player-count constants live in the module-level
``SETUP`` table so a ruleset / player-count change is a *data* change, not a
logic change (see design/01 §Setup). 4-player is the implemented/tuned target;
other counts are sketched for generalization.

All randomness flows through ``state.rng`` (a ``random.Random`` seeded from
``config.seed``), keeping games reproducible (see design/00 §Determinism).
"""

from __future__ import annotations

import random

from .buildings import CATALOG
from .enums import BuildingId, Good, Phase, Role, TileType
from .phase_state import PhaseState
from .state import (
    CargoShip,
    CitySlot,
    GameConfig,
    GameState,
    IslandSlot,
    PlayerState,
    RolePlacard,
)

# Fixed structural constants (independent of player count, base game).
ISLAND_SLOTS = 12
CITY_SLOTS = 12

# Full base-game plantation deck composition (tile kind -> count).
# 8 coffee, 9 tobacco, 10 corn, 11 sugar, 12 indigo = 50 tiles total.
PLANTATION_DECK_COUNTS: dict[TileType, int] = {
    TileType.COFFEE: 8,
    TileType.TOBACCO: 9,
    TileType.CORN: 10,
    TileType.SUGAR: 11,
    TileType.INDIGO: 12,
}

# Full base-game goods supply totals (Deluxe counts), indexed by Good.
GOODS_SUPPLY_COUNTS: dict[Good, int] = {
    Good.CORN: 10,
    Good.SUGAR: 11,
    Good.INDIGO: 11,
    Good.TOBACCO: 9,
    Good.COFFEE: 9,
}


# Per-player-count setup constants. 4-player is the primary, fully-populated
# target; 2-player is sketched (the data-driven entries that differ are filled
# in, but 2-player rules are not the tuned target for this milestone).
#
# Notes on table fields:
# - "roles": which Role placards are present. 4p/2p drop one PROSPECTOR.
# - "tiles_removed_each": plantation/quarry tiles removed from supply per kind
#   before play (2-player variant). 0 for 4-player.
# - "goods_removed_each": goods tokens removed per kind (2-player variant).
SETUP: dict[int, dict] = {
    4: {
        "doubloons": 3,
        "vp_pool": 100,
        "colonist_supply": 75,
        # colonists on the colonist ship at start (= num_players).
        "colonist_ship": 4,
        "cargo_ship_capacities": [5, 6, 7],
        # All seven roles except one prospector -> drop one PROSPECTOR placard.
        "roles": [
            Role.SETTLER,
            Role.MAYOR,
            Role.BUILDER,
            Role.CRAFTSMAN,
            Role.TRADER,
            Role.CAPTAIN,
            Role.PROSPECTOR,
        ],
        "faceup_plantations": 5,
        "quarry_supply": 8,
        "tiles_removed_each": 0,
        "goods_removed_each": 0,
        # Starting island tile per seat (rulebook): 0,1 -> INDIGO; 2,3 -> CORN.
        "starting_tiles": [
            TileType.INDIGO,
            TileType.INDIGO,
            TileType.CORN,
            TileType.CORN,
        ],
    },
    # --- 2-player sketch (not the tuned target for this milestone) ---
    2: {
        "doubloons": 3,
        "vp_pool": 65,
        "colonist_supply": 40,
        "colonist_ship": 2,
        "cargo_ship_capacities": [4, 6],
        # Two-player uses 7 role placards with a single prospector (per the
        # rules' two-player section).
        "roles": [
            Role.SETTLER,
            Role.MAYOR,
            Role.BUILDER,
            Role.CRAFTSMAN,
            Role.TRADER,
            Role.CAPTAIN,
            Role.PROSPECTOR,
        ],
        "faceup_plantations": 3,
        "quarry_supply": 8,
        "tiles_removed_each": 3,
        "goods_removed_each": 2,
        "starting_tiles": [TileType.INDIGO, TileType.CORN],
    },
}


def _build_plantation_deck(rng: random.Random, removed_each: int) -> list[TileType]:
    """Construct and shuffle the face-down plantation deck via ``rng``.

    ``removed_each`` tiles of each kind are removed first (2-player variant);
    0 for 4-player. The remaining tiles are shuffled deterministically.
    """
    deck: list[TileType] = []
    for tile, count in PLANTATION_DECK_COUNTS.items():
        deck.extend([tile] * max(0, count - removed_each))
    rng.shuffle(deck)
    return deck


def _build_goods_supply(removed_each: int) -> list[int]:
    """Length-5 goods supply array indexed by ``Good``."""
    supply = [0] * len(Good)
    for good, count in GOODS_SUPPLY_COUNTS.items():
        supply[good] = max(0, count - removed_each)
    return supply


def _build_buildings_supply() -> dict[BuildingId, int]:
    """Initial ``buildings_supply`` counts keyed by ``BuildingId``.

    Data-driven from ``buildings.CATALOG``. Standard base-game on-board supply
    (docs/puerto-rico-rules.md "Buildings on the board": **1 of each beige**,
    **2 of each** production building). Each player may build any building only
    once, so a single beige copy suffices; production buildings have two copies.
    The ``LARGE_CONT`` sentinel is not a real building and is skipped.
    """
    supply: dict[BuildingId, int] = {}
    for bid, spec in CATALOG.items():
        supply[bid] = 2 if spec.is_production else 1
    return supply


def new_game(config: GameConfig) -> GameState:
    """Build a fully initialized :class:`GameState` at the start of a game.

    Produces a legal ``ROLE_SELECTION`` start position for ``config.num_players``
    (4-player is the tuned target). All randomness is driven by an ``rng``
    seeded from ``config.seed``.
    """
    if config.num_players not in SETUP:
        raise ValueError(
            f"unsupported num_players={config.num_players}; "
            f"supported: {sorted(SETUP)}"
        )
    s = SETUP[config.num_players]
    n = config.num_players

    rng = random.Random(config.seed)

    # Players.
    players: list[PlayerState] = []
    for seat in range(n):
        island = [IslandSlot() for _ in range(ISLAND_SLOTS)]
        # Starting plantation tile placed on the player's island (rulebook).
        island[0] = IslandSlot(tile=s["starting_tiles"][seat], colonist=False)
        city = [CitySlot() for _ in range(CITY_SLOTS)]
        players.append(
            PlayerState(
                doubloons=s["doubloons"],
                island=island,
                city=city,
                goods=[0] * len(Good),
                stored_colonists=0,
                vp_chips=0,
                roles_taken_this_round=0,
            )
        )

    # Role placards (one per Role in the table), all unclaimed with 0 doubloons.
    placards = [RolePlacard(role=role) for role in s["roles"]]

    # Cargo ships.
    cargo_ships = [CargoShip(capacity=c) for c in s["cargo_ship_capacities"]]

    # Plantation deck: shuffle face-down, deal the face-up row.
    facedown = _build_plantation_deck(rng, s["tiles_removed_each"])
    faceup = [facedown.pop() for _ in range(s["faceup_plantations"])]

    return GameState(
        config=config,
        rng=rng,
        players=players,
        governor=0,
        current_player=0,
        phase=Phase.ROLE_SELECTION,
        placards=placards,
        colonist_ship=s["colonist_ship"],
        colonist_supply=s["colonist_supply"],
        cargo_ships=cargo_ships,
        trading_house=[],
        goods_supply=_build_goods_supply(s["goods_removed_each"]),
        plantation_faceup=faceup,
        plantation_facedown=facedown,
        plantation_discard=[],
        quarry_supply=s["quarry_supply"],
        vp_chips_remaining=s["vp_pool"],
        buildings_supply=_build_buildings_supply(),
        phase_state=PhaseState(),
        end_triggered=False,
    )
