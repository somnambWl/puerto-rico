"""``HeuristicAgent`` — a hand-written, decent-but-beatable baseline (design/05).

Unlike :class:`~puerto_rico.agents.random_agent.RandomAgent`, which is
**obs-based** (it picks uniformly from the encoded ``obs["action_mask"]`` and
needs nothing else), ``HeuristicAgent`` is deliberately **state-based**: it
reasons over the real :class:`~puerto_rico.engine.game.Game` /
:class:`~puerto_rico.engine.state.GameState`, not over the flat float
observation vector. Encoding strategy over a float vector is impractical — the
heuristics below need to read the acting player's island/city, owned buildings,
goods, doubloons, and the shared market/ships, which are all first-class on the
``GameState`` but lossy or awkward on the obs vector.

This is an intentional divergence from the strict obs-based
:class:`~puerto_rico.agents.base.Agent` protocol (``act(obs, *, rng)``). The
primary entry point here is :meth:`act` **taking a Game** (it is
``game.current_player``'s turn) and returning a structured
:class:`~puerto_rico.engine.actions.Action` chosen from ``game.legal_actions()``.
For callers that need the discrete action id (the env/arena masked space),
:meth:`act_id` returns ``ActionCodec.to_int(chosen_action)``.

The engine remains the single source of truth for legality: every branch picks
*from* ``game.legal_actions()`` and falls back to a sensible legal default
(ultimately a seeded random-legal pick), so the agent can never return an
illegal action and never crashes on an unexpected state.

Determinism: a per-agent seeded ``numpy`` generator breaks all ties, so the same
seed yields the same choices.
"""

from __future__ import annotations

import numpy as np

from puerto_rico.engine.actions import Action
from puerto_rico.engine.buildings import CATALOG
from puerto_rico.engine.enums import (
    BuildingId,
    DecisionType,
    Good,
    Phase,
    Role,
    TileType,
)
from puerto_rico.env.action_codec import to_int

# Market base price by good (mirrors the engine's trader price ladder). Higher is
# better to sell / produce / ship.
_GOOD_VALUE: dict[Good, int] = {
    Good.CORN: 0,
    Good.INDIGO: 1,
    Good.SUGAR: 2,
    Good.TOBACCO: 3,
    Good.COFFEE: 4,
}

# Tile kind -> the good it produces (corn needs no building; others pair with a
# production building of the same good).
_GOOD_FOR_TILE: dict[TileType, Good] = {
    TileType.CORN: Good.CORN,
    TileType.INDIGO: Good.INDIGO,
    TileType.SUGAR: Good.SUGAR,
    TileType.TOBACCO: Good.TOBACCO,
    TileType.COFFEE: Good.COFFEE,
}


class HeuristicAgent:
    """State-based rule policy: decent but beatable, comfortably above random.

    Parameters
    ----------
    seed:
        Seed for the internal ``numpy.random.Generator`` used to break ties
        deterministically.
    """

    def __init__(self, seed: int | None = None) -> None:
        self._rng = np.random.default_rng(seed)

    def reset(self) -> None:
        """No per-episode caches to clear."""
        return None

    # --- public entry points ------------------------------------------------

    def act(self, game) -> Action:
        """Choose one legal :class:`Action` for ``game.current_player``.

        Dispatches on the current phase to a small, robust per-phase rule. Always
        returns an action drawn from ``game.legal_actions()``.
        """
        legal = game.legal_actions()
        if not legal:
            raise ValueError("HeuristicAgent received a state with no legal actions")
        if len(legal) == 1:
            return legal[0]

        state = game.state
        phase = state.phase
        player = state.players[state.current_player]

        if phase == Phase.ROLE_SELECTION:
            return self._role_selection(state, player, legal)
        if phase == Phase.SETTLER:
            return self._settler(state, player, legal)
        if phase == Phase.MAYOR:
            return self._mayor(state, player, legal)
        if phase == Phase.BUILDER:
            return self._builder(state, player, legal)
        if phase == Phase.CRAFTSMAN:
            return self._craftsman(state, player, legal)
        if phase == Phase.TRADER:
            return self._trader(state, player, legal)
        if phase == Phase.CAPTAIN:
            return self._captain(state, player, legal)
        return self._fallback(legal)

    def act_id(self, game) -> int:
        """Return the discrete action id of :meth:`act`'s choice."""
        return to_int(self.act(game))

    # --- tie-breaking / fallback -------------------------------------------

    def _pick(self, candidates: list[Action]) -> Action:
        """Deterministically pick among equally-ranked candidates via the rng."""
        if len(candidates) == 1:
            return candidates[0]
        idx = int(self._rng.integers(len(candidates)))
        return candidates[idx]

    def _fallback(self, legal: list[Action]) -> Action:
        """A reasonable legal default: prefer acting over passing, else random."""
        non_pass = [a for a in legal if a.type != DecisionType.PASS]
        pool = non_pass if non_pass else legal
        return self._pick(pool)

    # --- phase rules --------------------------------------------------------

    def _role_selection(self, state, player, legal: list[Action]) -> Action:
        """Score each available role by how much it advances *this* player.

        Heuristic value per role:
          * accumulated doubloons on the placard always add value (free money);
          * SETTLER/BUILDER/MAYOR/CRAFTSMAN/TRADER/CAPTAIN are scored by a rough
            measure of how much the player benefits this round;
          * PROSPECTOR is a low-value fallback that gains weight when the player
            is short on doubloons and nothing else is compelling.
        """
        placard_by_role = {pl.role: pl for pl in state.placards}
        best: list[tuple[float, Action]] = []
        best_score = -1e18
        for action in legal:
            role = action.role
            score = self._role_score(state, player, role)
            placard = placard_by_role.get(role)
            if placard is not None:
                # Accumulated doubloons are pure upside; weight scarcity-aware.
                score += placard.doubloons * (2.0 if player.doubloons < 3 else 1.0)
            if score > best_score + 1e-9:
                best_score = score
                best = [action]
            elif abs(score - best_score) <= 1e-9:
                best.append(action)
        return self._pick(best)

    def _role_score(self, state, player, role: Role) -> float:
        """Rough per-role benefit for the acting player this round."""
        if role == Role.SETTLER:
            # Useful while the island still has empty space to fill chains.
            empty_island = sum(
                1 for s in player.island if s.tile == TileType.EMPTY
            )
            return 3.0 + min(empty_island, 4) * 0.5

        if role == Role.MAYOR:
            # Useful when there are empty circles to staff (idle capacity).
            empties = player.empty_building_circles() + sum(
                1
                for s in player.island
                if s.tile != TileType.EMPTY and not s.colonist
            )
            return 2.0 + min(empties, 6) * 0.6

        if role == Role.BUILDER:
            # Useful when we can afford something and have city room.
            return 3.5 + min(player.doubloons, 8) * 0.2

        if role == Role.CRAFTSMAN:
            # Value scales with how much we'd actually produce.
            return 2.5 + min(self._production_potential(player), 6) * 0.7

        if role == Role.TRADER:
            # Value scales with the best good we could sell.
            best = max(
                (_GOOD_VALUE[g] for g in Good if player.goods[g] > 0),
                default=0,
            )
            return 1.5 + best * 0.7

        if role == Role.CAPTAIN:
            # Value scales with goods on hand (VP via shipping).
            total_goods = sum(player.goods)
            return 1.5 + min(total_goods, 6) * 0.6

        if role == Role.PROSPECTOR:
            # Last resort; more attractive when broke.
            return 2.5 if player.doubloons < 2 else 1.0

        return 0.0

    def _production_potential(self, player) -> int:
        """Rough count of goods this player would make if production ran now."""
        total = 0
        for good in Good:
            tile = _plantation_for_good(good)
            plantations = sum(
                1 for s in player.island if s.tile == tile and s.colonist
            )
            if good == Good.CORN:
                total += plantations
            else:
                circles = _manned_production_circles(player, good)
                total += min(plantations, circles)
        return total

    def _settler(self, state, player, legal: list[Action]) -> Action:
        """Prefer a plantation that completes a production chain, else a useful tile.

        For each offered plantation, value it by:
          * how much its production building is under-fed (owning the building but
            lacking plantations of that kind is the best pickup), and
          * the good's market value.
        Quarry is valued when the player is building-heavy / plans expensive
        builds (owns several beige buildings or has spare doubloons).
        """
        take = [a for a in legal if a.type == DecisionType.TAKE_TILE]
        if not take:
            return self._fallback(legal)

        best: list[Action] = []
        best_score = -1e18
        for action in take:
            tile = action.tile
            if tile == TileType.QUARRY:
                score = self._quarry_value(player)
            else:
                good = _GOOD_FOR_TILE[tile]
                score = self._plantation_value(player, good)
            if score > best_score + 1e-9:
                best_score = score
                best = [action]
            elif abs(score - best_score) <= 1e-9:
                best.append(action)
        return self._pick(best)

    def _plantation_value(self, player, good: Good) -> float:
        """Value of adding a plantation of ``good`` to the island."""
        value = 1.0 + _GOOD_VALUE[good] * 0.4
        if good == Good.CORN:
            # Corn needs no building; always somewhat useful (cheap engine).
            return value + 1.0
        owns_building = _owns_production_for(player, good)
        plantations = sum(
            1 for s in player.island if s.tile == _plantation_for_good(good)
        )
        building_cap = _production_capacity(player, good)
        if owns_building and plantations < building_cap:
            # Completing an under-fed chain is the most valuable settle.
            value += 3.0
        elif owns_building:
            value += 0.5
        else:
            # No building yet — speculative, mild value.
            value += 0.3
        return value

    def _quarry_value(self, player) -> float:
        """Value of taking a quarry (build discounts), higher when building-heavy."""
        beige = sum(
            1
            for s in player.island
            if s.tile == TileType.QUARRY
        )
        doubloons = player.doubloons
        # More attractive early (few quarries) and with money to spend.
        base = 1.5 + max(0, 3 - beige) * 0.5
        if doubloons >= 4:
            base += 0.8
        return base

    def _mayor(self, state, player, legal: list[Action]) -> Action:
        """Place a colonist to MAN a production chain first, else high-value slots.

        Ranking of placement targets (engine encodes city slots, island slots at
        +100, and STORE at -1):
          1. an empty production-building circle whose matching plantation is
             already manned (turns idle capacity into output);
          2. a plantation tile whose production building is manned/owned;
          3. any other production building circle;
          4. any plantation tile;
          5. any beige building circle;
          6. STORE only as a last resort.
        """
        places = [
            a
            for a in legal
            if a.type == DecisionType.PLACE_COLONIST and a.target != _MAYOR_STORE
        ]
        if not places:
            return self._fallback(legal)

        best: list[Action] = []
        best_score = -1e18
        for action in places:
            score = self._mayor_target_value(player, action.target)
            if score > best_score + 1e-9:
                best_score = score
                best = [action]
            elif abs(score - best_score) <= 1e-9:
                best.append(action)
        return self._pick(best)

    def _mayor_target_value(self, player, target: int) -> float:
        """Score a single colonist-placement target."""
        if target >= _ISLAND_TARGET_OFFSET:
            slot = player.island[target - _ISLAND_TARGET_OFFSET]
            tile = slot.tile
            if tile == TileType.QUARRY:
                # Quarry colonists enable build discounts — moderate value.
                return 4.0
            good = _GOOD_FOR_TILE.get(tile)
            if good is None:
                return 1.0
            if good == Good.CORN:
                return 6.0  # corn produces with no building — reliable output.
            # A plantation is only useful if its building has manned room.
            if _production_has_open_circle(player, good):
                return 7.0
            if _owns_production_for(player, good):
                return 3.0
            return 2.0

        # City building slot.
        slot = player.city[target]
        bid = slot.building
        if bid is None or bid == BuildingId.LARGE_CONT:
            return 0.0
        spec = CATALOG[bid]
        if spec.is_production:
            good = spec.produces
            # Manning a production building that has a manned plantation = output.
            if _manned_plantations(player, good) > _manned_production_circles(
                player, good
            ):
                return 8.0  # immediately yields a good of value.
            return 3.5
        # Beige building: value by its printed VP (rough proxy for usefulness).
        return 2.0 + spec.vp * 0.5

    def _builder(self, state, player, legal: list[Action]) -> Action:
        """Buy the building that best increases production or VP density.

        Scores each affordable building by a blend of production usefulness, VP,
        and (negative) cost, and refuses to build something it cannot man unless
        nothing better is available. PASS only when no build scores positively.
        """
        builds = [a for a in legal if a.type == DecisionType.BUILD]
        if not builds:
            return self._fallback(legal)

        # Rough "early game" signal: few owned buildings -> favor the engine.
        owned = sum(
            1
            for s in player.city
            if s.building is not None and s.building != BuildingId.LARGE_CONT
        )
        early = owned < 4

        best: list[Action] = []
        best_score = -1e18
        for action in builds:
            score = self._build_value(state, player, action.building, early)
            if score > best_score + 1e-9:
                best_score = score
                best = [action]
            elif abs(score - best_score) <= 1e-9:
                best.append(action)

        # Always build something if any build is non-negative; the engine offers
        # PASS but a productive build beats idling for a baseline.
        if best_score <= 0:
            return self._pick(builds)
        return self._pick(best)

    def _build_value(self, state, player, bid: BuildingId, early: bool) -> float:
        """Heuristic desirability of building ``bid`` now."""
        spec = CATALOG[bid]
        cost = self._build_cost(state, player, bid)
        score = 0.0

        if spec.is_production:
            good = spec.produces
            # Worth more if we already have (or are likely to get) plantations.
            plantations = sum(
                1
                for s in player.island
                if s.tile == _plantation_for_good(good)
            )
            score += 4.0 + min(plantations, 3) * 1.0 + _GOOD_VALUE[good] * 0.3
            if early:
                score += 2.0
        else:
            # Beige building: value its VP, more so late game.
            score += 2.0 + spec.vp * (1.2 if not early else 0.6)
            # A few specific economy buildings are reliably good.
            if bid in (
                BuildingId.SMALL_MARKET,
                BuildingId.HACIENDA,
                BuildingId.HARBOR,
                BuildingId.FACTORY,
                BuildingId.OFFICE,
            ):
                score += 1.5

        # Cheaper is better (doubloon efficiency); penalize buying something that
        # leaves us totally broke.
        score -= cost * 0.4
        if cost >= player.doubloons:
            score -= 0.5  # spends everything
        return score

    def _build_cost(self, state, player, bid: BuildingId) -> int:
        """Mirror the engine's discounted build cost for ranking purposes."""
        spec = CATALOG[bid]
        cost = spec.cost
        if state.current_player == state.phase_state.role_chooser:
            cost -= 1
        quarries = sum(
            1
            for s in player.island
            if s.tile == TileType.QUARRY and s.colonist
        )
        cost -= min(quarries, spec.column)
        return max(0, cost)

    def _craftsman(self, state, player, legal: list[Action]) -> Action:
        """Take the bonus good of the highest market value available."""
        choices = [a for a in legal if a.type == DecisionType.CHOOSE]
        if not choices:
            return self._fallback(legal)
        best = max(choices, key=lambda a: _GOOD_VALUE[a.good])
        # Tie-break deterministically among equal-value goods.
        top = [a for a in choices if _GOOD_VALUE[a.good] == _GOOD_VALUE[best.good]]
        return self._pick(top)

    def _trader(self, state, player, legal: list[Action]) -> Action:
        """Sell the highest-price good that is currently legal to sell."""
        sells = [a for a in legal if a.type == DecisionType.SELL]
        if not sells:
            return self._fallback(legal)
        best = max(sells, key=lambda a: _GOOD_VALUE[a.good])
        top = [a for a in sells if _GOOD_VALUE[a.good] == _GOOD_VALUE[best.good]]
        return self._pick(top)

    def _captain(self, state, player, legal: list[Action]) -> Action:
        """Captain phase: ship to maximize VP, then keep the best goods.

        Two interactive decisions reach this method:

        **LOADING** — ``LOAD(good, target=ship_idx)`` cargo loads and optional
        ``LOAD(good, choice=WHARF)`` wharf loads. Each load is +1 VP per good
        shipped, so we want to ship as MANY goods as possible:

          * Good choice: prefer the kind the player holds the MOST of (ships the
            most VP this phase); market value breaks ties (retain cheap goods for
            the windrose later by shipping expensive ones is *not* the goal here —
            shipping volume is, but value is a sensible secondary).
          * Ship choice (the NEW decision): for the chosen good, prefer the cargo
            ship that will load the MOST of it, i.e. the legal ship with the most
            remaining space ``capacity - count``. Filling the roomiest ship ships
            more goods now and tends to deny that space to opponents — a simple,
            robust proxy for the strategic ship pick.
          * Wharf: ships the WHOLE held kind to the supply in one go. Use it only
            when it strictly out-ships the best cargo option for that good (or when
            a held kind cannot go on any cargo ship at all); otherwise prefer a
            cargo ship (keeps the one-shot wharf for a bigger pile).

        **WINDROSE** — ``CHOOSE(good)`` keeps 1 of ``good`` on the windrose and
        discards the rest of every other unprotected kind. Keep the kind the
        player holds the MOST of, tie-broken by market value — retain the most
        valuable goods, discard the least.
        """
        # WINDROSE storage sub-phase: CHOOSE which held kind to keep.
        chooses = [a for a in legal if a.type == DecisionType.CHOOSE]
        if chooses:
            best = max(
                chooses,
                key=lambda a: (player.goods[a.good], _GOOD_VALUE[a.good]),
            )
            top = [
                a
                for a in chooses
                if player.goods[a.good] == player.goods[best.good]
                and _GOOD_VALUE[a.good] == _GOOD_VALUE[best.good]
            ]
            return self._pick(top)

        # LOADING sub-phase.
        loads = [a for a in legal if a.type == DecisionType.LOAD]
        if not loads:
            return self._fallback(legal)

        # How many goods each load would actually ship (the VP it earns).
        def shipped(action: Action) -> int:
            held = player.goods[action.good]
            if action.choice == _CAPTAIN_WHARF:
                return held  # wharf ships the whole held kind.
            ship = state.cargo_ships[action.target]
            return min(held, ship.capacity - ship.count)

        # Best cargo load PER good = the ship that ships the most of that good
        # (most remaining space); this is the strategic ship choice.
        best_cargo: dict[Good, Action] = {}
        for action in loads:
            if action.choice == _CAPTAIN_WHARF:
                continue
            cur = best_cargo.get(action.good)
            if cur is None or shipped(action) > shipped(cur):
                best_cargo[action.good] = action

        candidates: list[Action] = []
        # One cargo candidate per good (the most-loading ship for that good).
        candidates.extend(best_cargo.values())
        # Wharf candidates: keep only when they strictly out-ship the best cargo
        # for the same good, or when that good has no cargo ship at all.
        for action in loads:
            if action.choice != _CAPTAIN_WHARF:
                continue
            cargo = best_cargo.get(action.good)
            if cargo is None or shipped(action) > shipped(cargo):
                candidates.append(action)

        if not candidates:
            return self._fallback(loads)

        best: list[Action] = []
        best_score = -1e18
        for action in candidates:
            # Primary: VP shipped now. Secondary: market value (tiny tie-break).
            score = shipped(action) + _GOOD_VALUE[action.good] * 0.01
            if action.choice == _CAPTAIN_WHARF:
                score += 0.001  # nudge to use the one-shot wharf when it ties.
            if score > best_score + 1e-9:
                best_score = score
                best = [action]
            elif abs(score - best_score) <= 1e-9:
                best.append(action)
        return self._pick(best)


# --------------------------------------------------------------------------- #
# Engine-mirroring helpers (read-only; kept local so the agent is self-contained)
# --------------------------------------------------------------------------- #

# These mirror the engine's encoding constants (phases.py) so the agent can read
# raw PLACE_COLONIST / LOAD targets without importing engine-private names.
_MAYOR_STORE = -1
_ISLAND_TARGET_OFFSET = 100
_CAPTAIN_WHARF = 1


def _plantation_for_good(good: Good) -> TileType:
    return {
        Good.CORN: TileType.CORN,
        Good.INDIGO: TileType.INDIGO,
        Good.SUGAR: TileType.SUGAR,
        Good.TOBACCO: TileType.TOBACCO,
        Good.COFFEE: TileType.COFFEE,
    }[good]


def _owns_production_for(player, good: Good) -> bool:
    """Whether the player owns any production building producing ``good``."""
    for slot in player.city:
        bid = slot.building
        if bid is None or bid == BuildingId.LARGE_CONT:
            continue
        spec = CATALOG[bid]
        if spec.is_production and spec.produces == good:
            return True
    return False


def _production_capacity(player, good: Good) -> int:
    """Total colonist-circle capacity of owned buildings producing ``good``."""
    total = 0
    for slot in player.city:
        bid = slot.building
        if bid is None or bid == BuildingId.LARGE_CONT:
            continue
        spec = CATALOG[bid]
        if spec.is_production and spec.produces == good:
            total += spec.capacity
    return total


def _manned_production_circles(player, good: Good) -> int:
    """Manned production-building circles producing ``good``."""
    total = 0
    for slot in player.city:
        bid = slot.building
        if bid is None or bid == BuildingId.LARGE_CONT:
            continue
        spec = CATALOG[bid]
        if spec.is_production and spec.produces == good:
            total += min(slot.colonists, spec.capacity)
    return total


def _manned_plantations(player, good: Good) -> int:
    """Count manned plantations of ``good``'s tile kind."""
    tile = _plantation_for_good(good)
    return sum(1 for s in player.island if s.tile == tile and s.colonist)


def _production_has_open_circle(player, good: Good) -> bool:
    """Whether an owned production building for ``good`` has an empty circle."""
    for slot in player.city:
        bid = slot.building
        if bid is None or bid == BuildingId.LARGE_CONT:
            continue
        spec = CATALOG[bid]
        if spec.is_production and spec.produces == good:
            if slot.colonists < spec.capacity:
                return True
    return False
