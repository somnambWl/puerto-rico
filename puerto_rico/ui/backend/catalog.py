"""Static building catalog + good base values for the UI (design/06 — UI).

The frontend needs two pieces of *static*, game-independent reference data:

* a list of every building (for hover tooltips and a VP-sorted build shelf), and
* the base sell value of each good (for the trading-house UI).

Both are derived once at import time from the engine's authoritative
``buildings.CATALOG`` and ``enums`` — the descriptions are concise, rules-accurate
one-liners written from ``design/03-buildings-reference.md``. Nothing here
reimplements a rule; it is display metadata only.
"""

from __future__ import annotations

from puerto_rico.engine.buildings import CATALOG
from puerto_rico.engine.enums import BuildingId, Good, Role
from puerto_rico.engine.game import new_game
from puerto_rico.engine.state import GameConfig

from ._display import GOOD_BASE_VALUE, GOOD_NAMES

# --------------------------------------------------------------------------- #
# per-building human-readable descriptions (from design/03)                   #
# --------------------------------------------------------------------------- #
#
# One short, rules-accurate sentence per building (what it DOES). Production
# buildings get a generated "Produces <good> (needs colonists)" line below.

_DESCRIPTIONS: dict[BuildingId, str] = {
    BuildingId.SMALL_MARKET: "Sell goods for +1 doubloon.",
    BuildingId.HACIENDA: "When you settle, first take an extra random plantation.",
    BuildingId.CONSTRUCTION_HUT: "Settle a quarry instead of a plantation.",
    BuildingId.SMALL_WAREHOUSE: "Keep all goods of 1 chosen kind at the captain's discard.",
    BuildingId.HOSPICE: "Place a free colonist on each plantation/quarry you take.",
    BuildingId.OFFICE: "Sell a good of a kind already in the trading house.",
    BuildingId.LARGE_MARKET: "Sell goods for +2 doubloons (stacks with small market for +3).",
    BuildingId.LARGE_WAREHOUSE: "Keep all goods of 2 chosen kinds at the captain's discard.",
    BuildingId.FACTORY: "Earn doubloons by variety produced (2/3/4/5 kinds = 1/2/3/5).",
    BuildingId.UNIVERSITY: "New buildings come with a free colonist.",
    BuildingId.HARBOR: "+1 victory point each time you ship goods.",
    BuildingId.WHARF: "Your own ship: ship any one good type to the supply.",
    BuildingId.GUILD_HALL: (
        "End-game: +1 VP per small production building, "
        "+2 per large production building."
    ),
    BuildingId.RESIDENCE: (
        "End-game VP by filled island spaces (4/5/6/7 for <=9/10/11/12)."
    ),
    BuildingId.FORTRESS: "End-game +1 VP per 3 colonists you have.",
    BuildingId.CUSTOMS_HOUSE: "End-game +1 VP per 4 VP chips you earned.",
    BuildingId.CITY_HALL: "End-game +1 VP per violet (non-production) building you own.",
}


def _description(spec) -> str:
    """A concise one-sentence description for ``spec`` (rules-accurate per design/03)."""
    if spec.is_production:
        good = GOOD_NAMES.get(spec.produces, "goods")
        return f"Produces {good} (needs colonists)."
    return _DESCRIPTIONS.get(spec.id, spec.name.capitalize() + ".")


def _kind(spec) -> str:
    """Coarse build-shelf category: ``"production"`` / ``"large"`` / ``"small"``."""
    if spec.is_production:
        return "production"
    if spec.is_large:
        return "large"
    return "small"


# --------------------------------------------------------------------------- #
# initial supply counts (read from the engine's actual 4-player setup)         #
# --------------------------------------------------------------------------- #
#
# Computed once from a fresh game so it always matches whatever the engine
# produces (including the corrected small-violet=2 / large=1 counts). We read
# the standard 4-player game and map each BuildingId -> its initial count.

_INITIAL_SUPPLY: dict[BuildingId, int] = dict(
    new_game(GameConfig(num_players=4)).buildings_supply
)


def _building_entry(spec) -> dict:
    return {
        "id": int(spec.id),
        "name": spec.name,
        "cost": spec.cost,
        "column": spec.column,
        "vp": spec.vp,
        "capacity": spec.capacity,
        "is_large": spec.is_large,
        "is_production": spec.is_production,
        "produces": (GOOD_NAMES[spec.produces] if spec.produces is not None else None),
        "kind": _kind(spec),
        "description": _description(spec),
        "supply": int(_INITIAL_SUPPLY[spec.id]),
    }


def _good_entry(good: Good) -> dict:
    return {
        "good": int(good),
        "name": GOOD_NAMES[good],
        "base_value": GOOD_BASE_VALUE[good],
    }


# --------------------------------------------------------------------------- #
# role reference (privilege + shared action, from puerto-rico-rules.md)        #
# --------------------------------------------------------------------------- #
#
# Concise one-liners for role tooltips. The frontend appends dynamic
# quantitative bits (e.g. the current colonist-ship count) itself.

_ROLE_NAMES: dict[Role, str] = {
    Role.SETTLER: "Settler",
    Role.MAYOR: "Mayor",
    Role.BUILDER: "Builder",
    Role.CRAFTSMAN: "Craftsman",
    Role.TRADER: "Trader",
    Role.CAPTAIN: "Captain",
    Role.PROSPECTOR: "Prospector",
}

_ROLE_DESCRIPTIONS: dict[Role, str] = {
    Role.SETTLER: (
        "Take a plantation tile (chooser may take a quarry). "
        "Privilege: may take a quarry."
    ),
    Role.MAYOR: (
        "Take colonists: 1 from the supply (privilege), then everyone draws "
        "from the colonist ship; place them on buildings/plantations."
    ),
    Role.BUILDER: "Build one building. Privilege: pay 1 doubloon less.",
    Role.CRAFTSMAN: (
        "All players produce goods. Privilege: take 1 extra good of a kind "
        "you produced."
    ),
    Role.TRADER: (
        "Sell one good to the trading house. Privilege: +1 doubloon on your sale."
    ),
    Role.CAPTAIN: (
        "Ship goods for victory points (mandatory if able). "
        "Privilege: +1 VP on your first shipment."
    ),
    Role.PROSPECTOR: "Take 1 doubloon from the bank. No shared action.",
}


def _role_entry(role: Role) -> dict:
    return {
        "role": int(role),
        "name": _ROLE_NAMES[role],
        "description": _ROLE_DESCRIPTIONS[role],
    }


#: Building list ordered by BuildingId (production, small beige, large beige).
BUILDINGS: list[dict] = [_building_entry(CATALOG[bid]) for bid in CATALOG]

#: Good base sell values in Good order (corn 0 .. coffee 4).
GOODS: list[dict] = [_good_entry(g) for g in Good]

#: Role privilege/action reference in Role order (settler .. prospector).
ROLES: list[dict] = [_role_entry(r) for r in Role]

#: Combined static reference payload for ``GET /catalog``.
CATALOG_RESPONSE: dict = {"buildings": BUILDINGS, "goods": GOODS, "roles": ROLES}
