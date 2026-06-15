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
from puerto_rico.engine.enums import BuildingId, Good

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
    }


def _good_entry(good: Good) -> dict:
    return {
        "good": int(good),
        "name": GOOD_NAMES[good],
        "base_value": GOOD_BASE_VALUE[good],
    }


#: Building list ordered by BuildingId (production, small beige, large beige).
BUILDINGS: list[dict] = [_building_entry(CATALOG[bid]) for bid in CATALOG]

#: Good base sell values in Good order (corn 0 .. coffee 4).
GOODS: list[dict] = [_good_entry(g) for g in Good]

#: Combined static reference payload for ``GET /catalog``.
CATALOG_RESPONSE: dict = {"buildings": BUILDINGS, "goods": GOODS}
