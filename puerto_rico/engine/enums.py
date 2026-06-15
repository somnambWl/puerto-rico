"""Core enumerations used throughout the Puerto Rico engine.

All enums are ``IntEnum`` so their values double as array indices and map
directly into the RL action-int space. Members are hashable and have unique
values within each enum.
"""

from enum import IntEnum


class Good(IntEnum):
    """Tradeable/producible goods. Values index the length-5 goods arrays."""

    CORN = 0
    INDIGO = 1
    SUGAR = 2
    TOBACCO = 3
    COFFEE = 4


class Role(IntEnum):
    """The role placards a player can select once per round."""

    SETTLER = 0
    MAYOR = 1
    BUILDER = 2
    CRAFTSMAN = 3
    TRADER = 4
    CAPTAIN = 5
    PROSPECTOR = 6


class TileType(IntEnum):
    """Island tile kinds. EMPTY = no tile; QUARRY and plantation kinds."""

    EMPTY = 0
    QUARRY = 1
    CORN = 2
    INDIGO = 3
    SUGAR = 4
    TOBACCO = 5
    COFFEE = 6


class Phase(IntEnum):
    """The active phase of the round/turn state machine."""

    ROLE_SELECTION = 0
    SETTLER = 1
    MAYOR = 2
    BUILDER = 3
    CRAFTSMAN = 4
    TRADER = 5
    CAPTAIN = 6
    GAME_OVER = 7


class DecisionType(IntEnum):
    """Tag identifying the kind of atomic decision an ``Action`` represents."""

    SELECT_ROLE = 0
    TAKE_TILE = 1
    PLACE_COLONIST = 2
    BUILD = 3
    SELL = 4
    LOAD = 5
    PASS = 6
    CHOOSE = 7


class BuildingId(IntEnum):
    """Authoritative building-id enum for the base game.

    All 23 real buildings (6 production + 12 small beige + 5 large beige) plus
    the ``LARGE_CONT`` sentinel. Stable integer values (0..22 for real
    buildings) double as array indices / RL action ints. The full catalog of
    per-building data (cost, column, VP, capacity, produces, timings) lives in
    ``buildings.py`` (``CATALOG``); see ``design/03-buildings-reference.md``.

    ``LARGE_CONT`` is NOT a real building: it marks the continuation (second)
    slot occupied by a large (two-slot) building in a player's city. Its value
    (99) is deliberately outside the 0..22 real-building range and it is never
    present in ``CATALOG``.
    """

    # --- production buildings (6) ---
    SMALL_INDIGO = 0
    INDIGO_PLANT = 1
    SMALL_SUGAR = 2
    SUGAR_MILL = 3
    TOBACCO_STORAGE = 4
    COFFEE_ROASTER = 5

    # --- small beige buildings (12) ---
    SMALL_MARKET = 6
    HACIENDA = 7
    CONSTRUCTION_HUT = 8
    SMALL_WAREHOUSE = 9
    HOSPICE = 10
    OFFICE = 11
    LARGE_MARKET = 12
    LARGE_WAREHOUSE = 13
    FACTORY = 14
    UNIVERSITY = 15
    HARBOR = 16
    WHARF = 17

    # --- large beige buildings (5) ---
    GUILD_HALL = 18
    RESIDENCE = 19
    FORTRESS = 20
    CUSTOMS_HOUSE = 21
    CITY_HALL = 22

    # --- sentinel: not a real building ---
    LARGE_CONT = 99
