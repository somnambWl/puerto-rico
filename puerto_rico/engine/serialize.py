"""(De)serialization for the Puerto Rico engine.

Three entry points:

- ``to_dict(state)`` / ``from_dict(d)``: lossless, round-trippable conversion of
  a full :class:`GameState` to/from a plain JSON-friendly ``dict``. Enums are
  stored by their int value; the RNG is captured via ``rng.getstate()`` (a tuple
  whose middle element is itself a tuple) converted to nested lists.
- ``public_view(state, perspective)``: a UI-facing snapshot that intentionally
  drops hidden information (other players' VP chips, the identity/order of the
  face-down plantation stack). It is for transport only, not for reloading.
"""

from __future__ import annotations

import random

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


# --------------------------------------------------------------------------- #
# helpers: enums / None                                                        #
# --------------------------------------------------------------------------- #


def _enum_val(e):
    """Serialize an enum (or ``None``) to its int value (or ``None``)."""
    return None if e is None else int(e)


# --------------------------------------------------------------------------- #
# nested dataclass -> dict                                                     #
# --------------------------------------------------------------------------- #


def _island_to_dict(s: IslandSlot) -> dict:
    return {"tile": int(s.tile), "colonist": s.colonist}


def _city_to_dict(s: CitySlot) -> dict:
    return {"building": _enum_val(s.building), "colonists": s.colonists}


def _cargo_to_dict(s: CargoShip) -> dict:
    return {"capacity": s.capacity, "good": _enum_val(s.good), "count": s.count}


def _placard_to_dict(p: RolePlacard) -> dict:
    return {
        "role": int(p.role),
        "doubloons": p.doubloons,
        "taken_by": p.taken_by,
    }


def _player_to_dict(p: PlayerState) -> dict:
    return {
        "doubloons": p.doubloons,
        "island": [_island_to_dict(s) for s in p.island],
        "city": [_city_to_dict(s) for s in p.city],
        "goods": list(p.goods),
        "stored_colonists": p.stored_colonists,
        "vp_chips": p.vp_chips,
        "roles_taken_this_round": p.roles_taken_this_round,
    }


def _phase_state_to_dict(ps: PhaseState) -> dict:
    return {
        "role_chooser": ps.role_chooser,
        "active_role": _enum_val(ps.active_role),
        "order": list(ps.order),
        "order_pos": ps.order_pos,
        "colonists_to_place": ps.colonists_to_place,
        "captain_done": sorted(ps.captain_done),
        "sub": ps.sub,
    }


def _config_to_dict(c: GameConfig) -> dict:
    return {
        "num_players": c.num_players,
        "seed": c.seed,
        "ruleset": c.ruleset,
        "max_rounds": c.max_rounds,
    }


def _rng_to_list(rng: random.Random):
    """Serialize ``rng.getstate()`` to a JSON-friendly nested list.

    ``getstate()`` returns ``(version, internalstate, gauss_next)`` where
    ``internalstate`` is itself a tuple of ints. We convert both tuple levels to
    lists so the whole thing is JSON-serializable.
    """
    version, internalstate, gauss_next = rng.getstate()
    return [version, list(internalstate), gauss_next]


# --------------------------------------------------------------------------- #
# to_dict                                                                      #
# --------------------------------------------------------------------------- #


def to_dict(state: GameState) -> dict:
    """Lossless serialization of every :class:`GameState` field."""
    return {
        "config": _config_to_dict(state.config),
        "rng": _rng_to_list(state.rng),
        "players": [_player_to_dict(p) for p in state.players],
        "governor": state.governor,
        "current_player": state.current_player,
        "phase": int(state.phase),
        "placards": [_placard_to_dict(p) for p in state.placards],
        "colonist_ship": state.colonist_ship,
        "colonist_supply": state.colonist_supply,
        "cargo_ships": [_cargo_to_dict(s) for s in state.cargo_ships],
        "trading_house": [int(g) for g in state.trading_house],
        "goods_supply": list(state.goods_supply),
        "plantation_faceup": [int(t) for t in state.plantation_faceup],
        "plantation_facedown": [int(t) for t in state.plantation_facedown],
        "plantation_discard": [int(t) for t in state.plantation_discard],
        "quarry_supply": state.quarry_supply,
        "vp_chips_remaining": state.vp_chips_remaining,
        "buildings_supply": {
            int(bid): n for bid, n in state.buildings_supply.items()
        },
        "phase_state": _phase_state_to_dict(state.phase_state),
        "end_triggered": state.end_triggered,
        "round_number": state.round_number,
    }


# --------------------------------------------------------------------------- #
# dict -> nested dataclass                                                     #
# --------------------------------------------------------------------------- #


def _island_from_dict(d: dict) -> IslandSlot:
    return IslandSlot(tile=TileType(d["tile"]), colonist=d["colonist"])


def _city_from_dict(d: dict) -> CitySlot:
    b = d["building"]
    return CitySlot(
        building=None if b is None else BuildingId(b),
        colonists=d["colonists"],
    )


def _cargo_from_dict(d: dict) -> CargoShip:
    g = d["good"]
    return CargoShip(
        capacity=d["capacity"],
        good=None if g is None else Good(g),
        count=d["count"],
    )


def _placard_from_dict(d: dict) -> RolePlacard:
    return RolePlacard(
        role=Role(d["role"]),
        doubloons=d["doubloons"],
        taken_by=d["taken_by"],
    )


def _player_from_dict(d: dict) -> PlayerState:
    return PlayerState(
        doubloons=d["doubloons"],
        island=[_island_from_dict(s) for s in d["island"]],
        city=[_city_from_dict(s) for s in d["city"]],
        goods=list(d["goods"]),
        stored_colonists=d["stored_colonists"],
        vp_chips=d["vp_chips"],
        roles_taken_this_round=d["roles_taken_this_round"],
    )


def _phase_state_from_dict(d: dict) -> PhaseState:
    ar = d["active_role"]
    return PhaseState(
        role_chooser=d["role_chooser"],
        active_role=None if ar is None else Role(ar),
        order=list(d["order"]),
        order_pos=d["order_pos"],
        colonists_to_place=d["colonists_to_place"],
        captain_done=set(d["captain_done"]),
        sub=d["sub"],
    )


def _config_from_dict(d: dict) -> GameConfig:
    return GameConfig(
        num_players=d["num_players"],
        seed=d["seed"],
        ruleset=d["ruleset"],
        max_rounds=d.get("max_rounds", GameConfig.max_rounds),
    )


def _rng_from_list(data) -> random.Random:
    """Reconstruct a ``random.Random`` from a serialized state list.

    ``setstate`` requires the exact tuple shape it produced: ``(version,
    internalstate_tuple, gauss_next)`` where ``internalstate_tuple`` is a tuple
    of ints. JSON has turned both into lists, so we rebuild the tuples.
    """
    version, internalstate, gauss_next = data
    rng = random.Random()
    rng.setstate((version, tuple(internalstate), gauss_next))
    return rng


# --------------------------------------------------------------------------- #
# from_dict                                                                    #
# --------------------------------------------------------------------------- #


def from_dict(d: dict) -> GameState:
    """Inverse of :func:`to_dict`: reconstruct an equal :class:`GameState`."""
    return GameState(
        config=_config_from_dict(d["config"]),
        rng=_rng_from_list(d["rng"]),
        players=[_player_from_dict(p) for p in d["players"]],
        governor=d["governor"],
        current_player=d["current_player"],
        phase=Phase(d["phase"]),
        placards=[_placard_from_dict(p) for p in d["placards"]],
        colonist_ship=d["colonist_ship"],
        colonist_supply=d["colonist_supply"],
        cargo_ships=[_cargo_from_dict(s) for s in d["cargo_ships"]],
        trading_house=[Good(g) for g in d["trading_house"]],
        goods_supply=list(d["goods_supply"]),
        plantation_faceup=[TileType(t) for t in d["plantation_faceup"]],
        plantation_facedown=[TileType(t) for t in d["plantation_facedown"]],
        plantation_discard=[TileType(t) for t in d["plantation_discard"]],
        quarry_supply=d["quarry_supply"],
        vp_chips_remaining=d["vp_chips_remaining"],
        buildings_supply={
            BuildingId(int(bid)): n for bid, n in d["buildings_supply"].items()
        },
        phase_state=_phase_state_from_dict(d["phase_state"]),
        end_triggered=d["end_triggered"],
        round_number=d.get("round_number", 0),
    )


# --------------------------------------------------------------------------- #
# public_view                                                                  #
# --------------------------------------------------------------------------- #


def _player_public(p: PlayerState, *, hide_vp: bool) -> dict:
    """Public dict for one player. ``hide_vp`` masks the secret VP-chip total."""
    return {
        "doubloons": p.doubloons,
        "island": [_island_to_dict(s) for s in p.island],
        "city": [_city_to_dict(s) for s in p.city],
        "goods": list(p.goods),
        "stored_colonists": p.stored_colonists,
        "vp_chips": None if hide_vp else p.vp_chips,
        "roles_taken_this_round": p.roles_taken_this_round,
    }


def public_view(state: GameState, perspective: int | None = None) -> dict:
    """A UI-facing snapshot that hides hidden information.

    Hidden information in Puerto Rico:
    - Other players' ``vp_chips`` (face-down, secret). When ``perspective`` is a
      player index, only that player's VP total is exposed; the others are
      ``None``. When ``perspective`` is ``None`` (god/spectator view), all VP
      totals are shown.
    - The identity and ordering of ``plantation_facedown`` (the draw stack):
      always exposed as a count only, never as tile contents.

    Everything else (roles, doubloons, buildings, island tiles + colonists,
    goods, face-up plantations, ships, supplies) is public.
    """
    return {
        "config": _config_to_dict(state.config),
        "players": [
            _player_public(
                p,
                hide_vp=(perspective is not None and i != perspective),
            )
            for i, p in enumerate(state.players)
        ],
        "perspective": perspective,
        "governor": state.governor,
        "current_player": state.current_player,
        "phase": int(state.phase),
        "placards": [_placard_to_dict(p) for p in state.placards],
        "colonist_ship": state.colonist_ship,
        "colonist_supply": state.colonist_supply,
        "cargo_ships": [_cargo_to_dict(s) for s in state.cargo_ships],
        "trading_house": [int(g) for g in state.trading_house],
        "goods_supply": list(state.goods_supply),
        "plantation_faceup": [int(t) for t in state.plantation_faceup],
        # hidden: identity/order of the draw stack -> count only
        "plantation_facedown_count": len(state.plantation_facedown),
        "plantation_discard": [int(t) for t in state.plantation_discard],
        "quarry_supply": state.quarry_supply,
        "vp_chips_remaining": state.vp_chips_remaining,
        "buildings_supply": {
            int(bid): n for bid, n in state.buildings_supply.items()
        },
        "phase_state": _phase_state_to_dict(state.phase_state),
        "end_triggered": state.end_triggered,
    }
