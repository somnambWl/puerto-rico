"""Human-readable labels for engine :class:`Action`s (design/06 — UI).

The backend is the single place that turns an engine action into a friendly
string the browser can render verbatim. It reads the live :class:`Game` for the
concrete detail an action implies (a building's discounted cost, the good held,
the role placard's accumulated doubloons, etc.) so the frontend never derives
anything.

Two entry points:

* :func:`label_action` — the display string, e.g. ``"Build Coffee Roaster
  (cost 6)"``, ``"Ship 3 Tobacco"``, ``"Take role: Settler (+1 doubloon)"``.
* :func:`label_action_kind` — a coarse category (``"role"``, ``"tile"``,
  ``"build"``, ``"colonist"``, ``"sell"``, ``"ship"``, ``"pass"``, ``"choose"``)
  used by the UI to group / style the action buttons.

Both are robust for **every** :class:`DecisionType`: an unrecognized or
malformed action degrades to a sane string rather than raising, so the UI can
never be wedged by a labeling gap.
"""

from __future__ import annotations

from puerto_rico.engine.actions import Action
from puerto_rico.engine.buildings import CATALOG
from puerto_rico.engine.enums import (
    BuildingId,
    DecisionType,
    Good,
    Role,
    TileType,
)

# Mirrors the engine's PLACE_COLONIST / LOAD encoding constants (phases.py),
# kept local so this module does not import engine-private names.
_MAYOR_STORE = -1
_ISLAND_TARGET_OFFSET = 100
_CAPTAIN_WHARF = 1


# --------------------------------------------------------------------------- #
# pretty-print helpers                                                         #
# --------------------------------------------------------------------------- #

_GOOD_NAMES: dict[Good, str] = {
    Good.CORN: "Corn",
    Good.INDIGO: "Indigo",
    Good.SUGAR: "Sugar",
    Good.TOBACCO: "Tobacco",
    Good.COFFEE: "Coffee",
}

_ROLE_NAMES: dict[Role, str] = {
    Role.SETTLER: "Settler",
    Role.MAYOR: "Mayor",
    Role.BUILDER: "Builder",
    Role.CRAFTSMAN: "Craftsman",
    Role.TRADER: "Trader",
    Role.CAPTAIN: "Captain",
    Role.PROSPECTOR: "Prospector",
}

_TILE_NAMES: dict[TileType, str] = {
    TileType.QUARRY: "Quarry",
    TileType.CORN: "Corn",
    TileType.INDIGO: "Indigo",
    TileType.SUGAR: "Sugar",
    TileType.TOBACCO: "Tobacco",
    TileType.COFFEE: "Coffee",
}


def _good_name(good: Good | None) -> str:
    if good is None:
        return "goods"
    return _GOOD_NAMES.get(good, str(good))


def _building_name(bid: BuildingId | None) -> str:
    """Title-cased catalog name, e.g. ``BuildingId.COFFEE_ROASTER`` -> ``Coffee Roaster``."""
    if bid is None:
        return "building"
    spec = CATALOG.get(bid)
    if spec is None:
        return str(bid)
    return spec.name.title()


# --------------------------------------------------------------------------- #
# discounted build cost (mirrors engine _build_cost in phases.py)             #
# --------------------------------------------------------------------------- #


def _discounted_build_cost(game, bid: BuildingId) -> int:
    """The doubloon cost the current player would actually pay for ``bid`` now.

    Replicates the engine's discount rule (printed cost − chooser privilege −
    quarry discount, floored at 0) so the label matches what the engine charges.
    Falls back to the printed cost if any state field is unavailable.
    """
    spec = CATALOG.get(bid)
    if spec is None:
        return 0
    try:
        state = game.state
        player_idx = state.current_player
        player = state.players[player_idx]
        cost = spec.cost
        if player_idx == state.phase_state.role_chooser:
            cost -= 1
        quarries = sum(
            1
            for s in player.island
            if s.tile == TileType.QUARRY and s.colonist
        )
        cost -= min(quarries, spec.column)
        return max(0, cost)
    except Exception:
        return spec.cost


# --------------------------------------------------------------------------- #
# kind classification                                                          #
# --------------------------------------------------------------------------- #


def label_action_kind(action: Action) -> str:
    """Coarse UI category for an action (used for button grouping / styling)."""
    t = action.type
    if t == DecisionType.SELECT_ROLE:
        return "role"
    if t == DecisionType.TAKE_TILE:
        return "tile"
    if t == DecisionType.PLACE_COLONIST:
        return "colonist"
    if t == DecisionType.BUILD:
        return "build"
    if t == DecisionType.SELL:
        return "sell"
    if t == DecisionType.LOAD:
        return "ship"
    if t == DecisionType.CHOOSE:
        return "choose"
    if t == DecisionType.PASS:
        return "pass"
    return "other"


# --------------------------------------------------------------------------- #
# label                                                                        #
# --------------------------------------------------------------------------- #


def _role_placard_doubloons(game, role: Role) -> int:
    """Accumulated doubloons sitting on ``role``'s placard (0 if none / unknown)."""
    try:
        for placard in game.state.placards:
            if placard.role == role:
                return int(placard.doubloons)
    except Exception:
        pass
    return 0


def _colonist_target_label(game, target: int) -> str:
    """Describe a PLACE_COLONIST target slot in human terms."""
    if target == _MAYOR_STORE:
        return "Keep colonist in San Juan (storage)"
    try:
        player = game.state.players[game.state.current_player]
        if target >= _ISLAND_TARGET_OFFSET:
            slot = player.island[target - _ISLAND_TARGET_OFFSET]
            tile_name = _TILE_NAMES.get(slot.tile, "tile")
            return f"Place colonist on {tile_name} plantation"
        slot = player.city[target]
        bid = slot.building
        if bid is None or bid == BuildingId.LARGE_CONT:
            return f"Place colonist on city slot {target}"
        return f"Place colonist on {_building_name(bid)}"
    except Exception:
        return f"Place colonist on slot {target}"


def label_action(action: Action, game) -> str:
    """Human-readable label for ``action`` given the current ``game``.

    Robust for every :class:`DecisionType`; unknown shapes degrade gracefully.
    """
    t = action.type

    if t == DecisionType.SELECT_ROLE:
        name = _ROLE_NAMES.get(action.role, str(action.role))
        bonus = _role_placard_doubloons(game, action.role)
        if bonus > 0:
            plural = "s" if bonus != 1 else ""
            return f"Take role: {name} (+{bonus} doubloon{plural})"
        return f"Take role: {name}"

    if t == DecisionType.TAKE_TILE:
        if action.tile == TileType.QUARRY:
            return "Take Quarry"
        name = _TILE_NAMES.get(action.tile, str(action.tile))
        return f"Take {name} plantation"

    if t == DecisionType.PLACE_COLONIST:
        return _colonist_target_label(game, action.target)

    if t == DecisionType.BUILD:
        cost = _discounted_build_cost(game, action.building)
        return f"Build {_building_name(action.building)} (cost {cost})"

    if t == DecisionType.SELL:
        return f"Sell {_good_name(action.good)}"

    if t == DecisionType.LOAD:
        good_name = _good_name(action.good)
        if action.choice == _CAPTAIN_WHARF:
            return f"Use Wharf to ship {good_name}"
        try:
            held = game.state.players[game.state.current_player].goods[action.good]
            return f"Ship {held} {good_name}"
        except Exception:
            return f"Ship {good_name}"

    if t == DecisionType.CHOOSE:
        # The only CHOOSE the engine emits is the craftsman extra-good pick.
        if action.good is not None:
            return f"Take extra {_good_name(action.good)}"
        return f"Choose option {action.choice}"

    if t == DecisionType.PASS:
        return "Pass"

    return str(action)
