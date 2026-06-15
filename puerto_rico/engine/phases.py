"""The round/phase finite-state machine (design/02).

This module is the architectural core of the **engine-phases** epic. It owns:

- **Role selection** — the ROLE_SELECTION decision node: which placards are
  selectable, and what selecting one does (mark taken, transfer doubloons, set
  up the role phase).
- **Round structure** — ``roles_per_round`` (1, or 3 in 2-player), advancing the
  ``role_chooser`` clockwise, and end-of-round bookkeeping (doubloons on unused
  placards, reset, governor rotation, end-of-game check).
- **Dispatch** — ``dispatch_legal_actions`` / ``dispatch_apply`` which
  ``game.py`` delegates to. These read ``state.phase`` and route to the active
  role's handlers via the ``ROLE_PHASES`` registry.

ROLE_PHASES registry
--------------------
All six role phases (settler, mayor, builder, craftsman, trader, captain) are
fully implemented here. ``ROLE_PHASES`` maps each role ``Phase`` to a
:class:`RolePhase` of three callables, providing the structural organization the
dispatcher routes through:

- ``legal_actions(state) -> list[Action]`` — atomic choices for the current
  player's turn in this phase.
- ``apply(state, action) -> None`` — mutate state and advance the cursor; call
  :func:`end_of_role` when the phase finishes.
- ``last_duty(state) -> None`` — the role's clean-up step run by
  :func:`end_of_role` *before* returning to selection (settler refills the row,
  mayor refills the ship, trader clears a full house, ...). ``None`` for roles
  with no clean-up (builder, craftsman, captain — the captain finishes via its
  interactive storage sub-phase instead).

PROSPECTOR has no follow phase: it resolves inline during role selection. A
generic stub :class:`RolePhase` (:func:`_stub_phase`) still exists as a safe
default but no role uses it now — every phase is registered with its real logic.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from . import buildings
from .actions import Action
from .buildings import Ctx, Timing
from .enums import BuildingId, DecisionType, Good, Phase, Role, TileType
from .state import GameState

# Phase that each Role's follow-action runs in. PROSPECTOR has no follow phase
# (it resolves inline during selection), so it is absent here.
_ROLE_TO_PHASE: dict[Role, Phase] = {
    Role.SETTLER: Phase.SETTLER,
    Role.MAYOR: Phase.MAYOR,
    Role.BUILDER: Phase.BUILDER,
    Role.CRAFTSMAN: Phase.CRAFTSMAN,
    Role.TRADER: Phase.TRADER,
    Role.CAPTAIN: Phase.CAPTAIN,
}


# --------------------------------------------------------------------------- #
# round helpers                                                               #
# --------------------------------------------------------------------------- #


def roles_per_round(state: GameState) -> int:
    """Roles each player takes per round: 3 in 2-player, else 1 (design/02)."""
    return 3 if state.config.num_players == 2 else 1


def _build_order(state: GameState, chooser: int) -> list[int]:
    """Resolution order for the active role: chooser first, then clockwise."""
    n = len(state.players)
    return [(chooser + i) % n for i in range(n)]


# --------------------------------------------------------------------------- #
# ROLE_SELECTION                                                              #
# --------------------------------------------------------------------------- #


def role_selection_legal_actions(state: GameState) -> list[Action]:
    """One ``SELECT_ROLE`` per still-available placard (``taken_by is None``)."""
    return [
        Action.select_role(pl.role)
        for pl in state.placards
        if pl.taken_by is None
    ]


def apply_select_role(state: GameState, action: Action) -> None:
    """Resolve a ``SELECT_ROLE`` decision (design/02 §ROLE_SELECTION apply).

    1. Mark the placard ``taken_by`` the chooser; transfer accumulated doubloons.
    2. Bump the chooser's ``roles_taken_this_round``.
    3. Enter the role's follow phase: set ``phase``, build ``order`` (chooser
       first, clockwise) and ``order_pos = 0``, reset per-role scratch, set
       ``current_player = order[0]``.

    PROSPECTOR has no follow phase: it resolves inline (chooser +1 doubloon) and
    then immediately runs :func:`end_of_role`. The canonical prospector lives in
    phases-task-08; this inline form is sufficient and rules-correct.
    """
    chooser = state.phase_state.role_chooser
    placard = next(pl for pl in state.placards if pl.role == action.role)

    placard.taken_by = chooser
    state.players[chooser].doubloons += placard.doubloons
    placard.doubloons = 0
    state.players[chooser].roles_taken_this_round += 1

    role = action.role
    if role == Role.PROSPECTOR:
        # Prospector privilege: +1 doubloon from the bank, no follow action.
        state.players[chooser].doubloons += 1
        end_of_role(state)
        return

    ps = state.phase_state
    ps.active_role = role
    ps.order = _build_order(state, chooser)
    ps.order_pos = 0
    # Reset per-role scratch so a phase always starts from a clean cursor.
    ps.colonists_to_place = 0
    ps.captain_done = set()
    ps.sub = None

    state.phase = _ROLE_TO_PHASE[role]
    state.current_player = ps.order[0]

    # Per-role phase-entry setup. MAYOR distributes colonists (privilege + ship)
    # before any placement decisions, then seeds the first player's placement
    # cursor. Other roles need no entry hook today.
    if role == Role.MAYOR:
        mayor_phase_enter(state)
        _mayor_begin_turn(state)
    elif role == Role.CRAFTSMAN:
        craftsman_phase_enter(state)
    elif role == Role.CAPTAIN:
        captain_phase_enter(state)


# --------------------------------------------------------------------------- #
# end-of-role / end-of-round transitions                                      #
# --------------------------------------------------------------------------- #


def end_of_role(state: GameState) -> None:
    """Finish the active role phase and return to selection (or end the round).

    Runs the role's ``last_duty`` (if any), then either advances the
    ``role_chooser`` to the next player who still owes a role this round, or —
    when the round's selection budget is spent — runs :func:`end_of_round`.
    """
    role = state.phase_state.active_role
    if role is not None:
        phase = _ROLE_TO_PHASE.get(role)
        if phase is not None:
            rp = ROLE_PHASES.get(phase)
            if rp is not None and rp.last_duty is not None:
                rp.last_duty(state)

    # Clear the active-role cursor; we are leaving the follow phase.
    state.phase_state.active_role = None
    state.phase_state.order = []
    state.phase_state.order_pos = 0

    if _round_budget_remaining(state):
        return_to_role_selection(state)
    else:
        end_of_round(state)


def _advance_order(state: GameState, *, on_next: Callable[[GameState], None] | None = None) -> None:
    """Advance ``order_pos`` one step; end the role when ``order`` is exhausted.

    The shared single-pass cursor for the settler/mayor/builder/trader phases
    (each player acts once, in ``order``). When stepping to the next player it
    seats the cursor and, if given, runs ``on_next(state)`` (the mayor uses this
    to begin the next player's placement turn). When every player has acted, runs
    :func:`end_of_role`. The captain's looping cursor is separate (it revisits
    players), so it does not use this helper.
    """
    ps = state.phase_state
    ps.order_pos += 1
    if ps.order_pos >= len(ps.order):
        end_of_role(state)
    else:
        state.current_player = ps.order[ps.order_pos]
        if on_next is not None:
            on_next(state)


def _round_budget_remaining(state: GameState) -> bool:
    """True iff at least one player still owes a role this round."""
    per = roles_per_round(state)
    return any(p.roles_taken_this_round < per for p in state.players)


def advance_role_chooser(state: GameState) -> int:
    """Advance ``role_chooser`` clockwise to the next player who still owes a role.

    Assumes at least one such player exists (the caller checks the round budget).
    In 2-player this naturally alternates between the two seats until both have
    taken their three roles. Returns the new chooser.
    """
    n = len(state.players)
    per = roles_per_round(state)
    chooser = state.phase_state.role_chooser
    for step in range(1, n + 1):
        cand = (chooser + step) % n
        if state.players[cand].roles_taken_this_round < per:
            state.phase_state.role_chooser = cand
            return cand
    # Unreachable: caller guarantees a player with budget remaining.
    return chooser


def return_to_role_selection(state: GameState) -> None:
    """Return to ROLE_SELECTION with the next eligible chooser."""
    advance_role_chooser(state)
    state.phase = Phase.ROLE_SELECTION
    state.current_player = state.phase_state.role_chooser


def end_of_round(state: GameState) -> None:
    """End-of-round bookkeeping, then start the next round or end the game.

    In order (design/02 §End of a role phase):
    1. Place 1 doubloon on each placard NOT taken this round.
    2. Reset every placard's ``taken_by`` to ``None``.
    3. Reset ``roles_taken_this_round`` to 0 for all players.
    4. Pass the governor clockwise; the new governor is the next chooser.
    5. End-of-game check: if ``end_triggered`` (the round that just finished was
       the last), transition to GAME_OVER instead of starting a new round.

    The three REAL end triggers (phases-09) are all wired and set
    ``end_triggered``: colonist-shortage (``mayor_last_duty``), 12th-building
    (``builder_apply``), and VP-exhaustion (``award_captain_vp``). The
    ``config.max_rounds`` cap below is now only a BACKSTOP against a pathological
    game (e.g. a stuck rollout) and should essentially never fire in real play.
    """
    n = len(state.players)

    # 1. Untaken placards each accrue 1 doubloon from the supply.
    for pl in state.placards:
        if pl.taken_by is None:
            pl.doubloons += 1
    # 2. Reset taken_by so every placard is available next round.
    for pl in state.placards:
        pl.taken_by = None
    # 3. Reset per-player round counters.
    for p in state.players:
        p.roles_taken_this_round = 0

    state.round_number += 1

    # 4. Pass governor clockwise; the new governor chooses first next round.
    state.governor = (state.governor + 1) % n
    state.phase_state.role_chooser = state.governor

    # 5. End-of-game check (real triggers: phases-09) OR safety-valve cap.
    if state.end_triggered or state.round_number >= state.config.max_rounds:
        state.phase = Phase.GAME_OVER
        return

    state.phase = Phase.ROLE_SELECTION
    state.current_player = state.governor


# --------------------------------------------------------------------------- #
# ROLE_PHASES registry — the seam role tasks (phases-02..08) plug into        #
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class RolePhase:
    """The three callables a role phase provides (see module docstring)."""

    legal_actions: Callable[[GameState], list[Action]]
    apply: Callable[[GameState, Action], None]
    last_duty: Callable[[GameState], None] | None = None


def _stub_legal_actions(state: GameState) -> list[Action]:
    """Stub role phase: a single PASS so the dispatcher always has an action.

    A real role task replaces this with the phase's true legal actions. The
    matching :func:`_stub_apply` consumes the PASS and ends the role.
    """
    return [Action.passing()]


def _stub_apply(state: GameState, action: Action) -> None:
    """Stub role phase: do nothing, immediately end the role.

    Until the owning role task lands, selecting this role simply consumes the
    turn and returns to role selection (or ends the round). This keeps full
    playthroughs running while phases are filled in one at a time.
    """
    end_of_role(state)


def _stub_phase() -> RolePhase:
    """A fresh stub ``RolePhase`` (no last duty)."""
    return RolePhase(legal_actions=_stub_legal_actions, apply=_stub_apply)


# Registry keyed by role Phase. Role tasks phases-02..08 REPLACE the stub entry
# for their phase with a real RolePhase via register_role_phase(). Until then,
# every role does nothing and returns to selection.
ROLE_PHASES: dict[Phase, RolePhase] = {
    Phase.SETTLER: _stub_phase(),
    Phase.MAYOR: _stub_phase(),
    Phase.BUILDER: _stub_phase(),
    Phase.CRAFTSMAN: _stub_phase(),
    Phase.TRADER: _stub_phase(),
    Phase.CAPTAIN: _stub_phase(),
}


def register_role_phase(phase: Phase, role_phase: RolePhase) -> None:
    """Install a role task's real :class:`RolePhase` for ``phase``.

    The seam role tasks (phases-02..08) call this to replace the stub. Kept as a
    function (rather than direct dict assignment) so the registration point is
    greppable and validated.
    """
    if phase not in _ROLE_TO_PHASE.values():
        raise ValueError(f"{phase!r} is not a role phase")
    ROLE_PHASES[phase] = role_phase


# --------------------------------------------------------------------------- #
# SETTLER (Phase.SETTLER) — design/02 §The Settler                            #
# --------------------------------------------------------------------------- #
#
# Per-player turn (current_player = order[order_pos]). The acting player takes
# one tile (plantation or, with the chooser privilege / construction hut, a
# quarry) which is auto-placed onto the lowest-index empty island slot — the
# agent chooses only *which* tile kind, never the slot (rules-equivalent, since
# island position carries no rules meaning). Taking is voluntary (PASS), and a
# player whose island is full may only PASS.
#
# Building hooks fire at Timing.SETTLER_PLACE (handlers in the buildings epic,
# task buildings-05). They are NO-OPs until those handlers register; firing here
# defines the seam so they plug in without phase changes.
#
# SETTLER_PLACE ctx contract (the Ctx fields handlers may read/mutate)
# --------------------------------------------------------------------
# ``fire(Timing.SETTLER_PLACE, state, player_idx, ctx)`` is called TWICE per
# take by the chooser (hacienda pre-take, then the post-place for the chosen
# tile) and once per take by any other player (post-place only). The phase tells
# the two firings apart, and tells handlers what to do, via ``ctx.extra``:
#
#   ctx.extra["event"]   : str — "pre_take" or "post_place".
#       - "pre_take"  fires BEFORE the player picks a face-up tile. The HACIENDA
#         handler uses this to take an extra random face-down plantation and
#         auto-place it (chooser privilege; rules let hacienda owners draw one
#         extra tile each settler turn). No tile is chosen yet.
#       - "post_place" fires AFTER a tile has been auto-placed. The HOSPICE
#         handler uses this to drop a free colonist from ``colonist_supply``
#         onto the just-placed slot, occupying it immediately.
#   ctx.extra["is_chooser"] : bool — whether player_idx is the settler chooser.
#         INFORMATIONAL/UNUSED: no handler consumes it. HACIENDA fires for every
#         settler-phase player (chooser and non-chooser alike) and does not gate
#         on the chooser, so this flag is purely descriptive context.
#   ctx.extra["slot"]    : int | None — for "post_place", the island slot index
#         the tile was just placed into (the slot HOSPICE should man). None for
#         "pre_take".
#   ctx.tile             : TileType | None — for "post_place", the tile kind that
#         was placed. None for "pre_take".
#
# Handlers MUST be defensive about exhausted supplies: HACIENDA skips if the
# face-down/discard stacks are empty; HOSPICE skips if ``colonist_supply <= 0``.
# Quarry LEGALITY is decided here (chooser OR occupied construction hut AND
# quarry_supply > 0), NOT via a handler — effects-vs-legality split per the epic.

# Face-up tile kinds are always plantations; the QUARRY privilege is separate.
_PLANTATION_TILES = frozenset(
    {
        TileType.CORN,
        TileType.INDIGO,
        TileType.SUGAR,
        TileType.TOBACCO,
        TileType.COFFEE,
    }
)


def _can_take_quarry(state: GameState, player_idx: int) -> bool:
    """Whether ``player_idx`` may take a quarry this settler turn.

    True iff a quarry is in supply AND the player either is the settler chooser
    (privilege) or owns an occupied construction hut (design/02 / design/03).
    Legality only — the construction-hut *effect* is just this permission.
    """
    if state.quarry_supply <= 0:
        return False
    is_chooser = player_idx == state.phase_state.role_chooser
    return is_chooser or state.players[player_idx].occupied(BuildingId.CONSTRUCTION_HUT)


def _lowest_empty_island_slot(player) -> int | None:
    """Index of the lowest empty island slot, or ``None`` if the island is full."""
    for i, slot in enumerate(player.island):
        if slot.tile == TileType.EMPTY:
            return i
    return None


def settler_legal_actions(state: GameState) -> list[Action]:
    """Legal actions for the acting settler player (design/02 §The Settler).

    One ``TAKE_TILE`` per DISTINCT face-up plantation kind, plus
    ``TAKE_TILE(QUARRY)`` when the player may take a quarry (chooser privilege or
    occupied construction hut, and quarry supply remains). Taking is voluntary,
    so ``PASS`` is always offered. A player whose island is full may only PASS.
    """
    player = state.players[state.current_player]
    if _lowest_empty_island_slot(player) is None:
        return [Action.passing()]

    actions: list[Action] = []
    # Distinct face-up plantation kinds, in TileType order for determinism.
    distinct = {t for t in state.plantation_faceup if t in _PLANTATION_TILES}
    for tile in sorted(distinct):
        actions.append(Action.take_tile(tile))
    if _can_take_quarry(state, state.current_player):
        actions.append(Action.take_tile(TileType.QUARRY))
    actions.append(Action.passing())
    return actions


def _place_tile(state: GameState, player_idx: int, tile: TileType) -> int | None:
    """Auto-place ``tile`` onto the lowest empty island slot; return its index.

    Returns ``None`` if the island is full (no placement happened). Removes the
    tile from the appropriate source: one matching face-up plantation, or one
    quarry from ``quarry_supply``.
    """
    player = state.players[player_idx]
    slot_idx = _lowest_empty_island_slot(player)
    if slot_idx is None:
        return None
    player.island[slot_idx].tile = tile
    if tile == TileType.QUARRY:
        state.quarry_supply -= 1
    else:
        state.plantation_faceup.remove(tile)
    return slot_idx


def settler_apply(state: GameState, action: Action) -> None:
    """Resolve the acting settler player's turn, then advance the cursor.

    ``PASS``: take nothing. ``TAKE_TILE``: fire the hacienda pre-take hook
    (chooser privilege; no-op until buildings-05), auto-place the chosen tile on
    the lowest empty slot, then fire the hospice post-place hook on that slot.
    Advancing past the end of ``order`` ends the role.
    """
    player_idx = state.current_player
    if action.type == DecisionType.TAKE_TILE:
        is_chooser = player_idx == state.phase_state.role_chooser

        # Hacienda hook (pre-take): chooser may take an extra face-down tile
        # first. No-op until the buildings-05 handler registers.
        pre_ctx = Ctx()
        pre_ctx.extra = {
            "event": "pre_take",
            "is_chooser": is_chooser,
            "slot": None,
        }
        buildings.fire(Timing.SETTLER_PLACE, state, player_idx, pre_ctx)

        # Auto-place the chosen tile onto the lowest empty island slot.
        slot_idx = _place_tile(state, player_idx, action.tile)

        # Hospice hook (post-place): occupy the just-placed slot with a free
        # colonist. No-op until the buildings-05 handler registers.
        if slot_idx is not None:
            post_ctx = Ctx(tile=action.tile)
            post_ctx.extra = {
                "event": "post_place",
                "is_chooser": is_chooser,
                "slot": slot_idx,
            }
            buildings.fire(Timing.SETTLER_PLACE, state, player_idx, post_ctx)

    _advance_settler(state)


def _advance_settler(state: GameState) -> None:
    """Advance ``order_pos``; end the role when every player has acted."""
    _advance_order(state)


def settler_last_duty(state: GameState) -> None:
    """Refresh the plantation row (design/02 §The Settler last duty).

    Discard remaining face-up plantations to ``plantation_discard``, then draw
    ``num_players + 1`` new tiles from ``plantation_facedown`` to face-up. When
    the face-down stack empties mid-draw, reshuffle the discard back into it via
    ``state.rng`` and continue; if still short, the row is simply shorter.
    """
    state.plantation_discard.extend(state.plantation_faceup)
    state.plantation_faceup.clear()

    needed = state.config.num_players + 1
    for _ in range(needed):
        if not state.plantation_facedown:
            if not state.plantation_discard:
                break  # nothing left to draw — row stays shorter.
            state.plantation_facedown = state.plantation_discard
            state.plantation_discard = []
            state.rng.shuffle(state.plantation_facedown)
        state.plantation_faceup.append(state.plantation_facedown.pop())


register_role_phase(
    Phase.SETTLER,
    RolePhase(
        legal_actions=settler_legal_actions,
        apply=settler_apply,
        last_duty=settler_last_duty,
    ),
)


# --------------------------------------------------------------------------- #
# MAYOR (Phase.MAYOR) — design/02 §The Mayor                                   #
# --------------------------------------------------------------------------- #
#
# Phase entry (mayor_phase_enter, run from apply_select_role): the chooser takes
# one colonist from ``colonist_supply`` as the mayor privilege, then the ship is
# distributed one colonist at a time, chooser first and clockwise, into each
# player's ``stored_colonists`` until ``colonist_ship`` is empty. All deterministic.
#
# Placement sub-phase: for each player in ``order`` (chooser first), the player
# places stored colonists onto empty circles one at a time. At the START of a
# player's turn we "lift" ALL their already-placed colonists (island + city) back
# into ``stored_colonists`` — the rulebook lets you rearrange every colonist each
# mayor phase, so re-placing from scratch is equivalent and keeps decisions
# uniform. ``colonists_to_place`` is unused as a separate counter here; the loop
# is driven directly by ``stored_colonists`` and the set of empty circles.
#
# PLACE_COLONIST target encoding (``action.target``):
#   - 0..11           -> a CITY slot index (a building circle on that building).
#   - 100 + i (i<12)  -> an ISLAND slot index i (man that plantation/quarry tile).
#   - MAYOR_STORE (-1)-> leave remaining stored colonists in San Juan / storage.
# STORE is only legal when the player has NO empty circle available (rulebook: you
# may not store while empty circles remain).

#: Sentinel ``PLACE_COLONIST(target=...)`` value: leave remaining colonists stored.
MAYOR_STORE = -1
#: Offset added to an island slot index to distinguish it from a city slot index
#: in a PLACE_COLONIST target. City slots are 0..11, island slots are 100..111.
ISLAND_TARGET_OFFSET = 100
#: Backwards-compatible alias for the historical private name.
_ISLAND_TARGET_OFFSET = ISLAND_TARGET_OFFSET


def mayor_phase_enter(state: GameState) -> None:
    """Distribute colonists at the start of the mayor phase (design/02).

    1. Chooser takes 1 colonist from ``colonist_supply`` (privilege) if any remain.
    2. Deal the ship one colonist at a time, chooser first then clockwise, into
       each player's ``stored_colonists`` until ``colonist_ship`` is empty.
    """
    ps = state.phase_state
    chooser = ps.role_chooser

    # Mayor privilege: one colonist from the supply (skip if the supply is empty).
    if state.colonist_supply > 0:
        state.colonist_supply -= 1
        state.players[chooser].stored_colonists += 1

    # Distribute the ship round-robin from the chooser clockwise until empty.
    n = len(state.players)
    i = 0
    while state.colonist_ship > 0:
        seat = (chooser + i) % n
        state.players[seat].stored_colonists += 1
        state.colonist_ship -= 1
        i += 1


def _empty_circle_targets(player) -> list[int]:
    """Encoded targets for every empty colonist circle the player owns.

    City building circles (capacity − colonists each) come first as plain slot
    indices, then unmanned plantation/quarry island slots as offset indices.
    """
    targets: list[int] = []
    for idx, slot in enumerate(player.city):
        if slot.building is None or slot.building == BuildingId.LARGE_CONT:
            continue
        if slot.colonists < buildings.CATALOG[slot.building].capacity:
            targets.append(idx)
    for idx, slot in enumerate(player.island):
        if slot.tile != TileType.EMPTY and not slot.colonist:
            targets.append(ISLAND_TARGET_OFFSET + idx)
    return targets


def _lift_all_colonists(state: GameState, player_idx: int) -> None:
    """Lift every placed colonist (island + city) back into ``stored_colonists``.

    Rearrangement model: at the start of a player's placement turn all their
    colonists become available, so they re-place from scratch. Net colonist count
    is unchanged.
    """
    player = state.players[player_idx]
    for slot in player.city:
        if slot.colonists:
            player.stored_colonists += slot.colonists
            slot.colonists = 0
    for slot in player.island:
        if slot.colonist:
            player.stored_colonists += 1
            slot.colonist = False


def _mayor_begin_turn(state: GameState) -> None:
    """Start the current player's placement turn: lift, then seed the cursor."""
    player_idx = state.current_player
    _lift_all_colonists(state, player_idx)
    state.phase_state.colonists_to_place = state.players[player_idx].stored_colonists


def mayor_legal_actions(state: GameState) -> list[Action]:
    """Placement actions for the acting mayor-phase player (design/02 §The Mayor).

    One ``PLACE_COLONIST(target=circle)`` per empty circle the player owns. If the
    player has stored colonists but NO empty circle remains, the only action is
    ``PLACE_COLONIST(target=MAYOR_STORE)`` (keep the excess in storage). A player
    with no stored colonists also stores (nothing to place).
    """
    player = state.players[state.current_player]
    if player.stored_colonists <= 0:
        return [Action.place_colonist(MAYOR_STORE)]
    targets = _empty_circle_targets(player)
    if not targets:
        return [Action.place_colonist(MAYOR_STORE)]
    return [Action.place_colonist(t) for t in targets]


def mayor_apply(state: GameState, action: Action) -> None:
    """Resolve one placement decision, then advance within / past the player.

    ``PLACE_COLONIST(MAYOR_STORE)``: end this player's turn, leaving any remaining
    colonists stored. Otherwise place one colonist on the targeted city building
    circle or island slot. The turn ends when the player runs out of stored
    colonists (auto-store) or chooses/ is forced to STORE.
    """
    player_idx = state.current_player
    player = state.players[player_idx]
    target = action.target

    if target == MAYOR_STORE:
        _mayor_advance(state)
        return

    if target >= ISLAND_TARGET_OFFSET:
        player.island[target - ISLAND_TARGET_OFFSET].colonist = True
    else:
        player.city[target].colonists += 1
    player.stored_colonists -= 1
    state.phase_state.colonists_to_place = player.stored_colonists

    # Out of colonists, or none can be placed anywhere: this player is done.
    if player.stored_colonists <= 0 or not _empty_circle_targets(player):
        _mayor_advance(state)


def _mayor_advance(state: GameState) -> None:
    """Advance ``order_pos`` to the next player (begin their turn), or end role."""
    _advance_order(state, on_next=_mayor_begin_turn)


def mayor_last_duty(state: GameState) -> None:
    """Refill the colonist ship (design/02 §The Mayor last duty).

    Count empty BUILDING circles across all players (plantation/quarry circles do
    NOT count); the refill is ``max(num_players, that count)``. Move that many
    colonists from ``colonist_supply`` to ``colonist_ship``. If the supply cannot
    meet the required count, move all that remains and set ``end_triggered`` — the
    colonist-shortage end condition (design/02 §Game End).
    """
    empty_circles = sum(p.empty_building_circles() for p in state.players)
    required = max(state.config.num_players, empty_circles)

    if state.colonist_supply < required:
        state.colonist_ship += state.colonist_supply
        state.colonist_supply = 0
        state.end_triggered = True
    else:
        state.colonist_supply -= required
        state.colonist_ship += required


register_role_phase(
    Phase.MAYOR,
    RolePhase(
        legal_actions=mayor_legal_actions,
        apply=mayor_apply,
        last_duty=mayor_last_duty,
    ),
)


# --------------------------------------------------------------------------- #
# BUILDER (Phase.BUILDER) — design/02 §The Builder                             #
# --------------------------------------------------------------------------- #
#
# Per-player turn (current_player = order[order_pos], chooser first). The acting
# player either BUILDs one building or PASSes. Each player gets exactly one turn;
# the one-turn-per-player structure enforces "no more than one building per
# player per round". After a turn we advance order_pos; when every player has
# acted, end_of_role runs (the builder has no last duty).
#
# COST (design/02 / design/03):
#   cost = CATALOG[bid].cost
#          − (1 if player is the chooser, builder privilege)
#          − quarry_discount
#          − any BUILDER_BUILD cost-hook adjustment (none in base game)
#   floored at 0.
#   quarry_discount = min(occupied quarries, CATALOG[bid].column). A quarry is
#   "occupied" when its island slot holds a colonist. The building's column
#   (1..4) caps how many quarries may discount it.
#
# LEGALITY — BUILD(bid) is legal iff ALL of:
#   - the player does NOT already own bid (each building at most once per player),
#   - buildings_supply[bid] > 0 (a copy remains),
#   - doubloons >= computed cost (affordable),
#   - the player has room in the city: a normal building needs >=1 empty city
#     slot; a LARGE building (is_large) needs 2 ADJACENT empty city slots.
#   PASS is always legal.
#
# CITY ADJACENCY: the city is a flat 12-slot list. We define two slots as
# adjacent iff their indices are CONSECUTIVE (i and i+1). A large building thus
# needs some i with both city[i] and city[i+1] empty; it occupies the lowest
# such i (real building in slot i, LARGE_CONT sentinel in slot i+1).
#
# BUILDER_BUILD ctx contract (the Ctx fields the UNIVERSITY handler reads)
# -----------------------------------------------------------------------
# ``fire(Timing.BUILDER_BUILD, state, player_idx, ctx)`` is called ONCE per
# successful build, AFTER the building has been placed (and starts with 0
# colonists). The phase exposes the just-built building to handlers via:
#   ctx.building          : BuildingId — the building just built.
#   ctx.extra["slot"]     : int — the city-slot index the building was placed in
#         (the slot the UNIVERSITY handler should drop a free colonist onto).
# The UNIVERSITY handler (buildings-04) uses this to man the new building with
# one free colonist from ``colonist_supply`` (skipping if the supply is empty).
# No-op until that handler registers — firing here only defines the seam.


def _occupied_quarries(player) -> int:
    """Number of the player's quarry island tiles that hold a colonist."""
    return sum(
        1 for s in player.island if s.tile == TileType.QUARRY and s.colonist
    )


def build_cost(state: GameState, player_idx: int, building_id: BuildingId) -> int:
    """Doubloon cost for ``player_idx`` to build ``building_id`` this builder turn.

    printed cost − chooser privilege (−1) − quarry discount, floored at 0. The
    quarry discount is ``min(occupied quarries, column)``: the building's board
    column (1..4) caps how many quarries may reduce its cost.

    Public engine API: the single source of truth for build cost. The builder
    phase uses it directly; the UI backend / agents should call this rather than
    re-deriving the discount logic.
    """
    spec = buildings.CATALOG[building_id]
    cost = spec.cost
    if player_idx == state.phase_state.role_chooser:
        cost -= 1
    cost -= min(_occupied_quarries(state.players[player_idx]), spec.column)
    return max(0, cost)


#: Backwards-compatible alias for the historical private name (tests import this).
_build_cost = build_cost


def _empty_city_slot(player) -> int | None:
    """Lowest-index empty city slot, or ``None`` if the city is full."""
    for i, slot in enumerate(player.city):
        if slot.building is None:
            return i
    return None


def _adjacent_empty_pair(player) -> int | None:
    """Lowest index ``i`` with city slots ``i`` and ``i+1`` both empty, or ``None``.

    "Adjacent" means consecutive indices in the flat 12-slot city list (the
    representation a large building occupies: real building at ``i``, LARGE_CONT
    sentinel at ``i+1``).
    """
    city = player.city
    for i in range(len(city) - 1):
        if city[i].building is None and city[i + 1].building is None:
            return i
    return None


def _has_room(player, bid: BuildingId) -> bool:
    """Whether ``player`` has city room to build ``bid`` (large needs 2 adjacent)."""
    if buildings.CATALOG[bid].is_large:
        return _adjacent_empty_pair(player) is not None
    return _empty_city_slot(player) is not None


def builder_legal_actions(state: GameState) -> list[Action]:
    """Legal actions for the acting builder player (design/02 §The Builder).

    One ``BUILD(building=bid)`` per building the player may build now: not already
    owned, a copy remains in ``buildings_supply``, affordable at the computed cost,
    and the player has city room (a large building needs 2 adjacent empty slots).
    ``PASS`` is always offered (building is optional).
    """
    player_idx = state.current_player
    player = state.players[player_idx]

    actions: list[Action] = []
    # Iterate in BuildingId order for determinism.
    for bid in sorted(state.buildings_supply, key=int):
        if state.buildings_supply[bid] <= 0:
            continue
        if player.owns(bid):
            continue
        if player.doubloons < build_cost(state, player_idx, bid):
            continue
        if not _has_room(player, bid):
            continue
        actions.append(Action.build(bid))
    actions.append(Action.passing())
    return actions


def builder_apply(state: GameState, action: Action) -> None:
    """Resolve the acting builder player's turn, then advance the cursor.

    ``PASS``: build nothing. ``BUILD``: pay the computed cost to the bank, decrement
    the building supply, auto-place the building into the lowest empty city slot
    (a large building occupies the lowest adjacent empty pair, with LARGE_CONT in
    the second slot), fire the BUILDER_BUILD university hook on the new building,
    and set ``end_triggered`` if this filled the player's 12th (last) city space.
    Advancing past the end of ``order`` ends the role (no builder last duty).
    """
    player_idx = state.current_player
    if action.type == DecisionType.BUILD:
        player = state.players[player_idx]
        bid = action.building
        spec = buildings.CATALOG[bid]

        # Pay the cost to the bank (doubloons leave the game, not to a player).
        player.doubloons -= build_cost(state, player_idx, bid)
        state.buildings_supply[bid] -= 1

        # Auto-place into the lowest empty slot(s). New building starts unmanned.
        if spec.is_large:
            slot_idx = _adjacent_empty_pair(player)
            player.city[slot_idx].building = bid
            player.city[slot_idx].colonists = 0
            player.city[slot_idx + 1].building = BuildingId.LARGE_CONT
            player.city[slot_idx + 1].colonists = 0
        else:
            slot_idx = _empty_city_slot(player)
            player.city[slot_idx].building = bid
            player.city[slot_idx].colonists = 0

        # UNIVERSITY hook: an occupied university mans the new building with one
        # free colonist. No-op until the buildings-04 handler registers.
        ctx = Ctx(building=bid)
        ctx.extra = {"slot": slot_idx}
        buildings.fire(Timing.BUILDER_BUILD, state, player_idx, ctx)

        # 12th-building end trigger: the build filled the player's last city space
        # (all 12 slots occupied, counting the LARGE_CONT continuation slot).
        if all(s.building is not None for s in player.city):
            state.end_triggered = True

    _advance_builder(state)


def _advance_builder(state: GameState) -> None:
    """Advance ``order_pos``; end the role when every player has acted."""
    _advance_order(state)


register_role_phase(
    Phase.BUILDER,
    RolePhase(
        legal_actions=builder_legal_actions,
        apply=builder_apply,
        last_duty=None,
    ),
)


# --------------------------------------------------------------------------- #
# CRAFTSMAN (Phase.CRAFTSMAN) — design/02 §The Craftsman                        #
# --------------------------------------------------------------------------- #
#
# Production is DETERMINISTIC for every player, so the whole production step runs
# at phase entry (craftsman_phase_enter) for ALL players in order (chooser
# first). The phase then has exactly ONE decision node: the chooser's privilege
# pick (take one extra good of a kind they produced this phase). Non-choosers
# have no decision at all.
#
# Production per good kind (for a single player):
#   produced = min(manned production-building circles for that good,
#                  manned plantations of that good,
#                  goods_supply[good])
#   CORN is special: it needs NO building, so
#   produced = min(manned corn plantations, corn supply).
# "manned production-building circles for a good" = sum over the player's
# production buildings that produce that good of min(circle colonists, capacity)
# (a building's colonists never exceed its capacity in practice; min() guards).
# "manned plantations of a good" = island slots with that tile AND colonist.
#
# FACTORY hook: after a player's production, fire Timing.CRAFTSMAN_PRODUCE so an
# occupied factory grants bonus doubloons by the number of DISTINCT good kinds
# produced this phase (2->+1, 3->+2, 4->+3, 5->+5; 0/1 -> +0).
#
# CRAFTSMAN_PRODUCE ctx contract (the Ctx field the FACTORY handler reads)
# -----------------------------------------------------------------------
# ``fire(Timing.CRAFTSMAN_PRODUCE, state, player_idx, ctx)`` is called ONCE per
# player, AFTER that player's production has been added to their goods. The phase
# exposes what was produced via:
#   ctx.kinds : set[Good] — the DISTINCT good kinds this player produced (>0 of)
#         this phase. The FACTORY handler (buildings-04) maps len(ctx.kinds) to a
#         doubloon bonus and adds it to the player. No-op until that handler
#         registers — firing here only defines the seam.
#
# Chooser privilege model: craftsman_phase_enter stores the chooser's produced
# kinds in ``phase_state.sub["chooser_kinds"]``. The single legal-action node
# offers Action(CHOOSE, good=g) for each such kind whose supply still has >0,
# plus PASS. Applying it (CHOOSE gives +1 of g and decrements supply; PASS does
# nothing) ends the role.

# Fixed kind order for deterministic production resolution.
_PRODUCE_ORDER: tuple[Good, ...] = (
    Good.CORN,
    Good.INDIGO,
    Good.SUGAR,
    Good.TOBACCO,
    Good.COFFEE,
)

_PLANTATION_FOR_GOOD: dict[Good, TileType] = {
    Good.CORN: TileType.CORN,
    Good.INDIGO: TileType.INDIGO,
    Good.SUGAR: TileType.SUGAR,
    Good.TOBACCO: TileType.TOBACCO,
    Good.COFFEE: TileType.COFFEE,
}


def _manned_plantations(player, good: Good) -> int:
    """Count of the player's island slots of ``good``'s tile that hold a colonist."""
    tile = _PLANTATION_FOR_GOOD[good]
    return sum(1 for s in player.island if s.tile == tile and s.colonist)


def _manned_building_circles(player, good: Good) -> int:
    """Manned production-building circles that produce ``good``.

    Sums ``min(colonists, capacity)`` over every production building the player
    owns whose ``produces`` is ``good``. Corn has no production building, so this
    is always 0 for corn (corn output is gated only by its plantations).
    """
    total = 0
    for slot in player.city:
        bid = slot.building
        if bid is None or bid == BuildingId.LARGE_CONT:
            continue
        spec = buildings.CATALOG[bid]
        if not spec.is_production or spec.produces != good:
            continue
        total += min(slot.colonists, spec.capacity)
    return total


def _produce_for_player(state: GameState, player_idx: int) -> set[Good]:
    """Apply deterministic production for one player; return the kinds produced.

    For each good kind (corn first, then in fixed order) compute the output and
    add it to the player's goods, decrementing ``goods_supply``. Corn needs no
    building; other goods need BOTH manned plantations AND manned building
    circles of the kind. Returns the set of kinds with output > 0.
    """
    player = state.players[player_idx]
    produced: set[Good] = set()
    for good in _PRODUCE_ORDER:
        plantations = _manned_plantations(player, good)
        if good == Good.CORN:
            capacity = plantations
        else:
            capacity = min(plantations, _manned_building_circles(player, good))
        output = min(capacity, state.goods_supply[good])
        if output > 0:
            player.goods[good] += output
            state.goods_supply[good] -= output
            produced.add(good)
    return produced


def craftsman_phase_enter(state: GameState) -> None:
    """Run all production (chooser first), fire factory hooks, set up the pick.

    Deterministic: produce goods for every player in ``order``, firing the
    CRAFTSMAN_PRODUCE (factory) hook per player with the distinct kinds produced.
    The chooser's produced kinds are stored in ``phase_state.sub`` so the single
    decision node — the chooser's privilege pick — can offer them.
    """
    ps = state.phase_state
    chooser = ps.role_chooser
    chooser_kinds: set[Good] = set()
    for player_idx in ps.order:
        kinds = _produce_for_player(state, player_idx)
        if player_idx == chooser:
            chooser_kinds = kinds
        # FACTORY hook: occupied factory pays by distinct kinds produced.
        ctx = Ctx()
        ctx.kinds = kinds
        buildings.fire(Timing.CRAFTSMAN_PRODUCE, state, player_idx, ctx)

    ps.sub = {"chooser_kinds": chooser_kinds}
    # The only decision node belongs to the chooser; park the cursor there.
    state.current_player = chooser


def craftsman_legal_actions(state: GameState) -> list[Action]:
    """The chooser's privilege pick (design/02 §The Craftsman).

    One ``CHOOSE(good=g)`` for each kind ``g`` the chooser produced this phase
    whose supply still has at least 1 remaining, plus ``PASS`` (declining the
    privilege). If the chooser produced nothing eligible, only ``PASS``.
    """
    sub = state.phase_state.sub or {}
    kinds: set[Good] = sub.get("chooser_kinds", set())
    actions: list[Action] = [
        Action(DecisionType.CHOOSE, good=g)
        for g in sorted(kinds)
        if state.goods_supply[g] > 0
    ]
    actions.append(Action.passing())
    return actions


def craftsman_apply(state: GameState, action: Action) -> None:
    """Resolve the chooser's privilege pick, then end the role.

    ``CHOOSE(good=g)``: take one extra ``g`` (decrement its supply). ``PASS``:
    take nothing. Either way the craftsman phase is done (production already ran
    at phase entry), so end the role.
    """
    if action.type == DecisionType.CHOOSE:
        good = action.good
        if state.goods_supply[good] > 0:
            state.players[state.current_player].goods[good] += 1
            state.goods_supply[good] -= 1
    end_of_role(state)


register_role_phase(
    Phase.CRAFTSMAN,
    RolePhase(
        legal_actions=craftsman_legal_actions,
        apply=craftsman_apply,
        last_duty=None,
    ),
)


# --------------------------------------------------------------------------- #
# TRADER (Phase.TRADER) — design/02 §The Trader                                #
# --------------------------------------------------------------------------- #
#
# Per-player turn (current_player = order[order_pos], chooser first). The acting
# player either SELLs one good into the trading house or PASSes (selling is
# optional). Each player gets exactly one turn; after a turn we advance
# order_pos. When every player has acted, end_of_role runs the trader last duty.
#
# LEGALITY — SELL(good=g) is legal iff buildings.can_sell(state, player_idx, g):
#   - the player holds at least one g (goods[g] > 0),
#   - the trading house has room (< 4 goods),
#   - g is not already in the house, UNLESS the player occupies an OFFICE.
#   can_sell() is the single source of truth for all three conditions, so the
#   phase does NOT re-check them. PASS is always legal.
#
# PRICE of selling g = base price + chooser bonus + market/office bonuses:
#   - base: corn 0, indigo 1, sugar 2, tobacco 3, coffee 4 (== Good int value).
#   - +1 if the seller is the chooser (trader privilege) — a PHASE rule, applied
#     directly here (not a building handler).
#   - market bonuses come from the TRADER_SELL_PRICE hook: occupied small market
#     +1, occupied large market +2 (stack to +3). Until the buildings-04 handlers
#     register, the hook is a no-op and the market bonus is 0 (acceptable).
#
# TRADER_SELL_PRICE ctx contract (the Ctx fields handlers read/mutate)
# -------------------------------------------------------------------
# ``fire(Timing.TRADER_SELL_PRICE, state, player_idx, ctx)`` is called ONCE per
# sale, after the phase has seeded the base + chooser bonus:
#   ctx.good  : Good — the good being sold (read-only; handlers may key off it).
#   ctx.price : int  — MUTABLE running price. The phase seeds it with
#         base + chooser bonus; market handlers ADD their bonus to it. The final
#         ctx.price (clamped at >= 0) is paid to the seller from the bank.

#: Base trader sale price per good kind (corn 0 .. coffee 4 == Good int value).
_TRADER_BASE_PRICE: dict[Good, int] = {
    Good.CORN: 0,
    Good.INDIGO: 1,
    Good.SUGAR: 2,
    Good.TOBACCO: 3,
    Good.COFFEE: 4,
}


def _trader_sale_price(state: GameState, player_idx: int, good: Good) -> int:
    """Doubloon price ``player_idx`` is paid for selling ``good`` this phase.

    Base price by kind, +1 if the seller is the trader chooser (privilege), plus
    any market/office bonus from the TRADER_SELL_PRICE hook (no-op until the
    buildings-04 handlers register). Clamped at >= 0.
    """
    base = _TRADER_BASE_PRICE[good]
    if player_idx == state.phase_state.role_chooser:
        base += 1  # trader privilege (a phase rule, not a building)

    ctx = Ctx(good=good)
    ctx.price = base
    buildings.fire(Timing.TRADER_SELL_PRICE, state, player_idx, ctx)
    return max(0, ctx.price)


def trader_legal_actions(state: GameState) -> list[Action]:
    """Legal actions for the acting trader player (design/02 §The Trader).

    One ``SELL(good=g)`` per good the player may sell now — delegated wholesale to
    :func:`buildings.can_sell` (holds the good, house has room, and the
    duplicate-kind/office rule). ``PASS`` is always offered (selling is optional).
    """
    player_idx = state.current_player
    actions: list[Action] = [
        Action.sell(g)
        for g in _PRODUCE_ORDER
        if buildings.can_sell(state, player_idx, g)
    ]
    actions.append(Action.passing())
    return actions


def trader_apply(state: GameState, action: Action) -> None:
    """Resolve the acting trader player's turn, then advance the cursor.

    ``PASS``: sell nothing. ``SELL(good=g)``: remove one g from the player, append
    g to ``trading_house``, and pay the computed sale price to the seller from the
    bank. Advancing past the end of ``order`` ends the role (then the last duty
    clears a full house).
    """
    player_idx = state.current_player
    if action.type == DecisionType.SELL:
        good = action.good
        player = state.players[player_idx]
        price = _trader_sale_price(state, player_idx, good)

        player.goods[good] -= 1
        state.trading_house.append(good)
        player.doubloons += price

    _advance_trader(state)


def _advance_trader(state: GameState) -> None:
    """Advance ``order_pos``; end the role when every player has acted."""
    _advance_order(state)


def trader_last_duty(state: GameState) -> None:
    """Clear a full trading house (design/02 §The Trader last duty).

    If ``trading_house`` holds 4 goods, return them all to ``goods_supply`` (each
    good's supply count is incremented) and empty the house. A house with fewer
    than 4 goods is left untouched — it carries over to the next trader phase.
    """
    if len(state.trading_house) >= 4:
        for good in state.trading_house:
            state.goods_supply[good] += 1
        state.trading_house.clear()


register_role_phase(
    Phase.TRADER,
    RolePhase(
        legal_actions=trader_legal_actions,
        apply=trader_apply,
        last_duty=trader_last_duty,
    ),
)


# --------------------------------------------------------------------------- #
# CAPTAIN (Phase.CAPTAIN) — design/02 §The Captain                             #
# --------------------------------------------------------------------------- #
#
# The only MANDATORY action phase, and the only one where a player takes many
# turns. The phase loops around ``order`` (chooser first, clockwise), giving the
# acting player ONE load per turn, until NO player can load any more (every index
# is in ``phase_state.captain_done``).
#
# TURN GRANULARITY
# ----------------
# One ``LOAD`` action = ONE kind of good onto ONE ship (as many as fit), per the
# rules ("only one kind of good to one ship per turn"). After a player loads,
# play passes to the NEXT not-done player. A player who CANNOT load any cargo
# ship (and has used/declined the optional wharf) is added to ``captain_done``
# and skipped on future passes. ``captain_apply`` does one load then advances to
# the next loadable player, re-evaluating done status for everyone as ship state
# changes (e.g. a freed kind opening a new option). The loop terminates because
# every load strictly consumes ship capacity, which is finite.
#
# SHIP SELECTION + AMOUNT (the agent chooses BOTH the good AND the ship)
# ----------------------------------------------------------------------
# A cargo ship holds exactly ONE kind; no two ships hold the SAME kind. A ship is
# a candidate for good ``g`` iff:
#   - it already holds ``g`` and has space (count < capacity), OR
#   - it is empty AND ``g`` is not already held by ANOTHER cargo ship.
# The acting player CHOOSES which candidate ship to load (a core Puerto Rico
# decision): ``legal_actions`` emits one ``LOAD(good=g, target=ship_idx)`` per
# legal (good, ship) pair. The AMOUNT is still forced to the maximum that fits
# ("load as many as fit"): ``min(player_holds, ship_remaining_capacity)`` of ``g``
# leave the player and go onto the CHOSEN ship.
#
# WHARF (optional; once per captain phase)
# ----------------------------------------
# A player occupying an unused-this-phase wharf may instead ship ALL of one held
# kind to the goods supply (a private "ship" of unlimited capacity), scoring VP as
# normal. Offered as ``Action(LOAD, good=g, choice=CAPTAIN_WHARF)`` for each held
# kind. Wharf is OPTIONAL: it does NOT make the player non-done by itself. PASS is
# legal ONLY when the player has NO compulsory cargo-ship load (the wharf, being
# optional, never forces an action). Per-player wharf usage is tracked in
# ``phase_state.sub["wharf_used"]`` (a set of player indices).
#
# VP SCORING (per load)
# ---------------------
# +1 VP per good loaded (every kind equal). The CHOOSER (captain) gets +1 BONUS VP
# on their FIRST load of the phase only (privilege). The HARBOR hook fires at
# Timing.CAPTAIN_LOAD and (buildings-04) adds +1 VP per load. VP is drawn from
# ``vp_chips_remaining`` into the player's ``vp_chips``; when the remaining pool
# would be exhausted, only what remains is awarded and ``end_triggered`` is set
# (the VP-exhaustion end condition — the game ends after the current round).
# First-load tracking lives in ``phase_state.sub["first_load_done"]`` (a set of
# player indices that have already taken their first load).
#
# CAPTAIN_LOAD ctx contract (the Ctx fields the HARBOR handler reads)
# ------------------------------------------------------------------
# ``fire(Timing.CAPTAIN_LOAD, state, player_idx, ctx)`` is called ONCE per load
# (cargo ship OR wharf), AFTER the goods have moved and the base/chooser VP has
# been awarded. The phase exposes:
#   ctx.good           : Good — the kind just loaded.
#   ctx.count          : int  — how many goods were loaded this action.
#   ctx.ship           : CargoShip | None — the ship loaded, or None for a wharf
#         shipment to the supply.
#   ctx.extra["first"] : bool — whether this was the player's FIRST load this
#         phase (the chooser privilege is a PHASE rule applied directly; harbor
#         does not depend on this flag).
# The HARBOR handler (buildings-04) awards +1 VP via ``award_captain_vp`` so the
# VP-exhaustion trigger stays consistent. No-op until that handler registers.
#
# STORAGE SUB-PHASE (interactive windrose choice)
# -----------------------------------------------
# After the loading loop ends, the phase enters an interactive STORAGE sub-phase
# (still ``Phase.CAPTAIN``) before unloading ships and ending the role. Goods
# storage exposes the player's WINDROSE choice as a decision when it is genuinely
# ambiguous (more distinct held kinds than fit). Storage progress lives in
# ``phase_state.sub``:
#   sub["storage"]       : bool — True once the loading loop is done and we are in
#         the storage sub-phase (legal_actions/apply route to storage handling).
#   sub["storage_order"] : list[int] — the players to process, in ``order``.
#   sub["storage_pos"]   : int — index into ``storage_order`` of the player whose
#         windrose CHOOSE is pending (``current_player``).
# Capacity for a player = warehouse WHOLE-kind protection (CAPTAIN_STORAGE hook →
# ``keep_kinds``) PLUS exactly 1 single good kept on the windrose. If the player
# holds 0 or 1 UNPROTECTED kind, everything fits with no genuine choice — storage
# auto-resolves with NO decision node and that player is skipped. Only a player
# with >= 2 unprotected kinds gets a CHOOSE node: ``Action(CHOOSE, good=g)`` for
# each unprotected held kind ``g``, where choosing ``g`` keeps 1 of ``g`` on the
# windrose and discards every other unprotected good to ``goods_supply`` (warehouse
# kinds are kept in full). When all players are stored, ships unload and the role
# ends.
#
# CAPTAIN_STORAGE ctx contract (the WAREHOUSE handlers read/mutate)
# ----------------------------------------------------------------
# ``fire(Timing.CAPTAIN_STORAGE, state, player_idx, ctx)`` is called ONCE per
# player during goods storage, BEFORE the phase trims their goods. It exposes:
#   ctx.extra["keep_kinds"] : set[Good] — MUTABLE set of WHOLE kinds the player
#         keeps in addition to the single windrose good. The phase seeds it empty;
#         small/large warehouse handlers ADD kinds (small → 1 kind, large → 2,
#         stacked → 3). The phase then keeps ALL goods of every kind in
#         ``keep_kinds`` plus 1 single good of one other kind (the windrose),
#         returning the rest to ``goods_supply``.
# Until those handlers register, an in-phase fallback reads the player's OWNED
# warehouses directly so storage is correct without the buildings epic.

#: ``Action.load`` ``choice`` sentinel selecting the wharf shipment variant.
CAPTAIN_WHARF = 1


def captain_phase_enter(state: GameState) -> None:
    """Initialize captain scratch and seat the cursor on the first loader.

    Seeds ``phase_state.sub`` (wharf/first-load tracking) and ``captain_done``.
    Marks any player who cannot load at phase start as done, then positions the
    cursor on the first not-done player in ``order``. If NO player can load (no
    goods / no ship space), the chooser is left as current player with only a
    PASS available, which immediately ends the phase via the loop.
    """
    ps = state.phase_state
    ps.captain_done = set()
    ps.sub = {"wharf_used": set(), "first_load_done": set()}
    _captain_sub(state)

    for idx in ps.order:
        if not _can_load_cargo(state, idx) and not _wharf_kinds(state, idx):
            ps.captain_done.add(idx)

    for pos, idx in enumerate(ps.order):
        if idx not in ps.captain_done:
            ps.order_pos = pos
            state.current_player = idx
            return
    # Everyone stuck: leave cursor at order[0]; its only action is PASS, which
    # cascades to end_of_role.
    ps.order_pos = 0
    state.current_player = ps.order[0]


def _legal_ships_for_good(state: GameState, good: Good) -> list[int]:
    """Cargo-ship indices that can legally accept ``good`` right now.

    A ship is legal for ``good`` iff it already holds ``good`` and has space, OR
    it is empty AND ``good`` is held by no OTHER cargo ship. Single-kind-per-ship
    and no-duplicate-kind-across-ships are both enforced here. Returned in ship
    index order for determinism.
    """
    held_elsewhere = any(
        ship.good == good and ship.count > 0 for ship in state.cargo_ships
    )
    legal: list[int] = []
    for i, ship in enumerate(state.cargo_ships):
        remaining = ship.capacity - ship.count
        if remaining <= 0:
            continue
        if ship.good == good and ship.count > 0:
            legal.append(i)  # tops off the in-progress kind
        elif ship.count == 0 and not held_elsewhere:
            legal.append(i)  # empty ship, kind on no other ship
    return legal


def _loadable_pairs(state: GameState, player_idx: int) -> list[tuple[Good, int]]:
    """All legal (good, ship_idx) cargo loads for ``player_idx`` right now.

    One entry per held kind and per ship that can legally accept it. The amount
    loaded is always maximal (forced by the rules); only the GOOD and the SHIP are
    the player's choice. Ordered by good then ship index for determinism.
    """
    player = state.players[player_idx]
    pairs: list[tuple[Good, int]] = []
    for good in _PRODUCE_ORDER:
        if player.goods[good] <= 0:
            continue
        for ship_idx in _legal_ships_for_good(state, good):
            pairs.append((good, ship_idx))
    return pairs


def _can_load_cargo(state: GameState, player_idx: int) -> bool:
    """Whether ``player_idx`` can (compulsorily) load any cargo ship now."""
    return bool(_loadable_pairs(state, player_idx))


def _wharf_available(state: GameState, player_idx: int) -> bool:
    """Whether ``player_idx`` may still use the wharf this phase (occupied + unused)."""
    sub = state.phase_state.sub or {}
    used: set[int] = sub.get("wharf_used", set())
    if player_idx in used:
        return False
    return state.players[player_idx].occupied(BuildingId.WHARF)


def _wharf_kinds(state: GameState, player_idx: int) -> list[Good]:
    """Held good kinds the player could ship via the wharf (any held kind)."""
    if not _wharf_available(state, player_idx):
        return []
    player = state.players[player_idx]
    return [g for g in _PRODUCE_ORDER if player.goods[g] > 0]


def award_captain_vp(state: GameState, player_idx: int, amount: int) -> None:
    """Award ``amount`` VP, drawing from ``vp_chips_remaining`` (design/02).

    Awards ``min(amount, remaining)`` into the player's ``vp_chips`` and decrements
    the remaining pool. When the pool hits 0 the VP-exhaustion end trigger fires
    (``end_triggered = True``); further VP in the same phase is tracked on the
    player's chips but the pool stays at 0. Shared with the HARBOR handler so all
    captain VP flows through the same exhaustion accounting.
    """
    if amount <= 0:
        return
    granted = min(amount, state.vp_chips_remaining)
    state.players[player_idx].vp_chips += granted
    state.vp_chips_remaining -= granted
    if state.vp_chips_remaining <= 0:
        state.vp_chips_remaining = 0
        state.end_triggered = True


def _captain_sub(state: GameState) -> dict:
    """The captain phase's ``phase_state.sub`` bag, lazily initialized."""
    ps = state.phase_state
    if ps.sub is None:
        ps.sub = {}
    ps.sub.setdefault("wharf_used", set())
    ps.sub.setdefault("first_load_done", set())
    return ps.sub


def captain_legal_actions(state: GameState) -> list[Action]:
    """Legal loads/storage for the acting captain-phase player (design/02).

    LOADING sub-phase: one ``LOAD(good=g, target=ship_idx)`` per legal (good,
    ship) pair the player can load (the player chooses BOTH the good and the ship;
    the amount is forced maximal). Plus one ``LOAD(good=g, choice=CAPTAIN_WHARF)``
    per held kind if the player has an unused occupied wharf (optional). ``PASS``
    is legal ONLY when the player has no compulsory cargo-ship load (loading a
    cargo ship is mandatory; the wharf is optional and never blocks PASS).

    STORAGE sub-phase: the acting player's windrose choice —
    ``Action(CHOOSE, good=g)`` for each UNPROTECTED held kind (keeping 1 of ``g``
    on the windrose, discarding the rest). Storage only seats players with a
    genuine choice (>= 2 unprotected kinds), so this always has >= 2 actions.
    """
    sub = state.phase_state.sub or {}
    if sub.get("storage"):
        return _storage_legal_actions(state)

    player_idx = state.current_player
    actions: list[Action] = []
    cargo_pairs = _loadable_pairs(state, player_idx)
    for good, ship_idx in cargo_pairs:
        actions.append(Action.load(good, target=ship_idx))
    for g in _wharf_kinds(state, player_idx):
        actions.append(Action(DecisionType.LOAD, good=g, choice=CAPTAIN_WHARF))
    if not cargo_pairs:
        # No compulsory cargo load: PASS is permitted (wharf, if any, optional).
        actions.append(Action.passing())
    return actions


def _award_load_vp(state: GameState, player_idx: int, count: int) -> None:
    """Award per-load VP: +count, +1 chooser bonus on the player's FIRST load."""
    sub = _captain_sub(state)
    bonus = 0
    if player_idx == state.phase_state.role_chooser and player_idx not in sub["first_load_done"]:
        bonus = 1
    award_captain_vp(state, player_idx, count + bonus)


def captain_apply(state: GameState, action: Action) -> None:
    """Resolve one captain load (or PASS), then advance to the next loader.

    ``PASS``: the player cannot load a cargo ship; mark them done. ``LOAD`` onto a
    cargo ship: move ``min(holds, ship_remaining)`` of the chosen kind onto the
    CHOSEN ship (``action.target``), award VP (+count, chooser +1 on first load),
    fire the harbor hook. ``LOAD`` with ``choice=CAPTAIN_WHARF``: ship ALL of the
    chosen kind to the goods supply, mark the wharf used, award VP and fire the
    harbor hook. After any load, record the first-load flag and advance to the next
    not-done player.

    STORAGE sub-phase: routes ``CHOOSE`` to :func:`_storage_apply`.
    """
    sub = _captain_sub(state)
    if sub.get("storage"):
        _storage_apply(state, action)
        return

    player_idx = state.current_player
    player = state.players[player_idx]

    if action.type == DecisionType.PASS:
        state.phase_state.captain_done.add(player_idx)
        _captain_advance(state)
        return

    good = action.good
    is_first = (
        player_idx == state.phase_state.role_chooser
        and player_idx not in sub["first_load_done"]
    )

    if action.choice == CAPTAIN_WHARF:
        count = player.goods[good]
        player.goods[good] = 0
        state.goods_supply[good] += count
        sub["wharf_used"].add(player_idx)
        self_ship = None
    else:
        ship_idx = action.target
        ship = state.cargo_ships[ship_idx]
        count = min(player.goods[good], ship.capacity - ship.count)
        ship.good = good
        ship.count += count
        player.goods[good] -= count
        self_ship = ship

    _award_load_vp(state, player_idx, count)
    sub["first_load_done"].add(player_idx)

    ctx = Ctx(good=good)
    ctx.count = count
    ctx.ship = self_ship
    ctx.extra = {"first": is_first}
    buildings.fire(Timing.CAPTAIN_LOAD, state, player_idx, ctx)

    _captain_advance(state)


def _captain_advance(state: GameState) -> None:
    """Advance to the next player who can load; end the phase when all are done.

    Recomputes done status as we go: a player who cannot load any cargo ship is
    added to ``captain_done`` and skipped. The loading loop ends once every index
    in ``order`` is done, at which point we transition into the interactive STORAGE
    sub-phase (NOT directly to end_of_role). Cycles around ``order`` repeatedly
    (wrapping) since a player may take several turns.
    """
    ps = state.phase_state
    n = len(ps.order)
    done = ps.captain_done

    # Mark fully-stuck players done: they can neither load a cargo ship NOR use an
    # unused wharf. A player who can still wharf keeps a turn (to wharf or PASS).
    for idx in ps.order:
        if idx in done:
            continue
        if not _can_load_cargo(state, idx) and not _wharf_kinds(state, idx):
            done.add(idx)

    if len(done) >= n:
        _enter_storage(state)
        return

    # Find the next not-done player, scanning clockwise from after the current pos.
    for step in range(1, n + 1):
        nxt = (ps.order_pos + step) % n
        idx = ps.order[nxt]
        if idx not in done:
            ps.order_pos = nxt
            state.current_player = idx
            return

    # Unreachable: len(done) < n guaranteed a not-done player above.
    _enter_storage(state)


def _warehouse_keep_kinds(state: GameState, player_idx: int) -> set[Good]:
    """WHOLE kinds ``player_idx`` keeps via warehouses (the CAPTAIN_STORAGE hook).

    Fires Timing.CAPTAIN_STORAGE so the small/large warehouse handlers populate
    ``ctx.extra["keep_kinds"]`` (small -> 1 kind, large -> 2, stacked -> 3). These
    warehouse-protected kinds are kept in FULL and are NOT part of the windrose
    choice. The single source of truth for warehouse protection.
    """
    ctx = Ctx()
    ctx.extra = {"keep_kinds": set()}
    buildings.fire(Timing.CAPTAIN_STORAGE, state, player_idx, ctx)
    return set(ctx.extra.get("keep_kinds", set()))


def _unprotected_held_kinds(state: GameState, player_idx: int, keep_kinds: set[Good]) -> list[Good]:
    """Held good kinds NOT protected by a warehouse, in deterministic order."""
    player = state.players[player_idx]
    return [g for g in _PRODUCE_ORDER if player.goods[g] > 0 and g not in keep_kinds]


def _apply_storage(state: GameState, player_idx: int, keep_kinds: set[Good], windrose: Good | None) -> None:
    """Keep warehouse kinds in full + 1 windrose good; discard the rest to supply."""
    player = state.players[player_idx]
    for g in _PRODUCE_ORDER:
        held = player.goods[g]
        if held <= 0:
            continue
        if g in keep_kinds:
            kept = held
        elif g == windrose:
            kept = 1
        else:
            kept = 0
        excess = held - kept
        if excess > 0:
            player.goods[g] -= excess
            state.goods_supply[g] += excess


def _store_goods_for_player(state: GameState, player_idx: int) -> None:
    """Auto-resolve ``player_idx``'s goods storage (design/02 §Goods storage).

    Capacity = 1 single good on the windrose PLUS whole kinds protected by
    warehouses (the CAPTAIN_STORAGE hook). Deterministic auto-resolve used when
    there is NO genuine windrose choice and in unit tests: keep ALL goods of every
    protected kind, then keep 1 single good of the highest-count remaining kind
    (the windrose). Everything else returns to supply. The interactive sub-phase
    (:func:`_storage_apply`) uses the player's CHOOSE instead of this max-rule.
    """
    keep_kinds = _warehouse_keep_kinds(state, player_idx)
    player = state.players[player_idx]
    unprotected = _unprotected_held_kinds(state, player_idx, keep_kinds)
    windrose: Good | None = None
    if unprotected:
        windrose = max(unprotected, key=lambda g: (player.goods[g], -int(g)))
    _apply_storage(state, player_idx, keep_kinds, windrose)


# --------------------------------------------------------------------------- #
# CAPTAIN storage sub-phase (interactive windrose CHOOSE)                       #
# --------------------------------------------------------------------------- #


def _enter_storage(state: GameState) -> None:
    """Transition from the loading loop into the interactive storage sub-phase.

    Marks ``sub["storage"]`` and seats the cursor on the first player who has a
    genuine windrose choice (>= 2 unprotected held kinds). Players with 0 or 1
    unprotected kind are auto-resolved here with NO decision node. When no player
    needs a choice, storage finishes immediately (ships unload, role ends).
    """
    ps = state.phase_state
    sub = _captain_sub(state)
    sub["storage"] = True
    sub["storage_order"] = list(ps.order)
    sub["storage_pos"] = 0
    _advance_storage(state, start=True)


def _advance_storage(state: GameState, *, start: bool = False) -> None:
    """Seat the next storage player with a genuine choice, or finish storage.

    Walks ``storage_order`` from ``storage_pos``: any player with 0 or 1
    unprotected held kind is auto-stored (keep-all-that-fits, no decision) and
    skipped; the first player with >= 2 unprotected kinds becomes ``current_player``
    with a pending CHOOSE. When the order is exhausted, :func:`_finish_storage`
    runs (ship unload + end_of_role).
    """
    sub = _captain_sub(state)
    order: list[int] = sub["storage_order"]
    pos = sub["storage_pos"] if start else sub["storage_pos"] + 1

    while pos < len(order):
        player_idx = order[pos]
        keep_kinds = _warehouse_keep_kinds(state, player_idx)
        unprotected = _unprotected_held_kinds(state, player_idx, keep_kinds)
        if len(unprotected) >= 2:
            # Genuine windrose choice: seat this player.
            sub["storage_pos"] = pos
            state.current_player = player_idx
            return
        # No genuine choice (0 or 1 unprotected kind): auto-store, keep all that fits.
        windrose = unprotected[0] if unprotected else None
        _apply_storage(state, player_idx, keep_kinds, windrose)
        pos += 1

    sub["storage_pos"] = pos
    _finish_storage(state)


def _storage_legal_actions(state: GameState) -> list[Action]:
    """Windrose CHOOSE options for the seated storage player (>= 2 actions).

    One ``Action(CHOOSE, good=g)`` per UNPROTECTED held kind; choosing ``g`` keeps
    1 of ``g`` on the windrose and discards every other unprotected good to supply.
    """
    sub = state.phase_state.sub or {}
    player_idx = sub["storage_order"][sub["storage_pos"]]
    keep_kinds = _warehouse_keep_kinds(state, player_idx)
    unprotected = _unprotected_held_kinds(state, player_idx, keep_kinds)
    return [Action(DecisionType.CHOOSE, good=g) for g in unprotected]


def _storage_apply(state: GameState, action: Action) -> None:
    """Resolve the seated player's windrose CHOOSE, then advance storage.

    Keeps warehouse-protected kinds in full plus 1 of ``action.good`` on the
    windrose; discards the rest of that player's unprotected goods to supply.
    """
    sub = _captain_sub(state)
    player_idx = sub["storage_order"][sub["storage_pos"]]
    keep_kinds = _warehouse_keep_kinds(state, player_idx)
    _apply_storage(state, player_idx, keep_kinds, action.good)
    _advance_storage(state)


def _finish_storage(state: GameState) -> None:
    """End the storage sub-phase: unload full ships, then end the role.

    Every cargo ship that is FULL (count == capacity) empties to ``goods_supply``;
    partially-full ships KEEP their goods (carry over). Empty ships are untouched.
    Then :func:`end_of_role` returns to selection / ends the round.
    """
    _unload_full_ships(state)
    end_of_role(state)


def _unload_full_ships(state: GameState) -> None:
    """Unload every FULL cargo ship to supply; partial/empty ships are untouched."""
    for ship in state.cargo_ships:
        if ship.good is not None and ship.count >= ship.capacity:
            state.goods_supply[ship.good] += ship.count
            ship.good = None
            ship.count = 0


register_role_phase(
    Phase.CAPTAIN,
    RolePhase(
        legal_actions=captain_legal_actions,
        apply=captain_apply,
        last_duty=None,
    ),
)


# --------------------------------------------------------------------------- #
# dispatch — game.py delegates legal_actions()/apply() here                    #
# --------------------------------------------------------------------------- #


def dispatch_legal_actions(state: GameState) -> list[Action]:
    """Legal actions for the current decision (empty iff terminal).

    ROLE_SELECTION uses :func:`role_selection_legal_actions`; the role phases use
    their ``ROLE_PHASES`` entry; GAME_OVER has none.
    """
    if state.phase == Phase.ROLE_SELECTION:
        return role_selection_legal_actions(state)
    if state.phase == Phase.GAME_OVER:
        return []
    rp = ROLE_PHASES.get(state.phase)
    if rp is None:
        return []
    return rp.legal_actions(state)


def dispatch_apply(state: GameState, action: Action) -> None:
    """Apply ``action`` for the current decision.

    ROLE_SELECTION routes to :func:`apply_select_role`; the role phases route to
    their ``ROLE_PHASES`` entry's ``apply``.
    """
    if state.phase == Phase.ROLE_SELECTION:
        apply_select_role(state, action)
        return
    rp = ROLE_PHASES.get(state.phase)
    if rp is None:
        raise ValueError(f"no apply handler for phase {state.phase!r}")
    rp.apply(state, action)
