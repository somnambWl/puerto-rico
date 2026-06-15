# 02 — Phases, Turn Flow & Scoring

## Purpose

Specify the round/phase finite state machine: how role selection works, the "follow" turn order
within a phase, the exact legal actions and effects for every role, the end-game triggers, and final
scoring. This is where most rule edge cases live. Building special-functions are referenced here and
fully specified in design/03 via a hook interface.

Rules source: `docs/puerto-rico-rules.md` (Playing the Game, the seven roles, Game End, The Game for
Two).

## The phase cursor (`PhaseState`)

`phase_state` in `GameState` is the FSM cursor. It records, within the active phase, the player order
and where we are in it, plus any per-player sub-state.

```python
@dataclass(slots=True)
class PhaseState:
    role_chooser: int                 # ROLE_SELECTION: who is choosing a role next
    active_role: Role | None          # the role currently being executed (None during selection)
    order: list[int]                  # turn order for the active role (chooser first, then clockwise)
    order_pos: int                    # index into `order` = whose action turn it is
    # per-player scratch for the active phase:
    colonists_to_place: int           # MAYOR: colonists the current player still must place
    captain_done: set[int]            # CAPTAIN: players who can no longer load
    sub: dict                         # transient sub-decision state (e.g. pending hacienda tile)
```

A general principle: `legal_actions()` reads `phase`, `phase_state`, and the current player's
situation, and returns the atomic choices. `apply(action)` mutates state and advances the cursor:
either to the next player in `order`, or (when `order` is exhausted) ends the role phase and returns
to role selection or to the next round.

## Round structure & role selection

A **round** is: players take role placards until the round's selection budget is spent; each chosen
role is fully executed (the follow structure) before the next role is chosen.

- **4-player (primary):** each player takes **1** role per round; selection goes once around the table
  clockwise from the governor (4 of the 7 placards used). After the round, the governor places 1
  doubloon on **each of the 3** unused placards.
- **3-/5-player:** same one-role-per-round structure (3 or 5 placards used; the rest get a doubloon).
- **2-player:** each player takes **3** roles per round (6 of 7 used); selection alternates from the
  governor; the 1 remaining placard gets a doubloon.

Implement the selection budget generically: a round ends when every player has
`roles_taken_this_round == roles_per_round`, where `roles_per_round = 3 if num_players == 2 else 1`.

### ROLE_SELECTION decision node
- `current_player = phase_state.role_chooser`.
- Legal actions: one `SELECT_ROLE(role=r)` for each placard with `taken_by is None`.
  (Prospector is selectable; it just yields its privilege and no follow action.)
- `apply(SELECT_ROLE)`:
  1. Mark placard `taken_by = current_player`; transfer any accumulated `doubloons` to the player.
  2. `players[current_player].roles_taken_this_round += 1`.
  3. Set `phase = Phase(active role)`, `phase_state.active_role = role`.
  4. Build `phase_state.order = [chooser] + clockwise others` and `order_pos = 0`.
  5. Apply the **chooser's privilege** at the right time (per role below).
  6. Initialize per-player scratch (e.g. mayor's colonist counts) and set `current_player` to
     `order[0]`. (Prospector: no follow action — immediately resolve end-of-role, see below.)

### End of a role phase
When `order_pos` runs past the end of `order` (or the phase's own termination rule fires), run the
role's **last-duty** step (e.g. settler refills the row; mayor refills the ship; trader/captain
clear), then:
- If the round's selection budget remains, return to ROLE_SELECTION: advance `role_chooser` to the
  next player who still owes a role (alternating in 2-player), set `phase = ROLE_SELECTION`.
- Else end the round: place 1 doubloon on each untaken placard (3 in the 4-player game; 1 in 2-player),
  reset all `taken_by=None` and `roles_taken_this_round=0`, pass governor to the next player, set the
  new `role_chooser = governor`. Then **check end-of-game** (see Game End): if `end_triggered`, set
  `phase = GAME_OVER`.

## The Settler (Phase.SETTLER)

Per-player turn (`current_player = order[order_pos]`):
- **Privilege (chooser only, this player's turn):** may also take a **QUARRY** instead of/in addition
  per rules — specifically the settler may take a quarry *instead* of a plantation. Model the
  chooser's legal `TAKE_TILE` actions as: each face-up plantation `tile`, plus `tile=QUARRY` (if
  `quarry_supply > 0`). Non-choosers may only take a face-up plantation (not quarry) — **exception:**
  a player with an occupied **construction hut** may take a quarry instead (design/03).
- **Building sub-decisions (hooks, design/03):** an occupied **hacienda** lets this player first take
  an extra top face-down tile and place it; an occupied **hospice** places a free colonist on the
  tile they place. These fire as part of resolving this player's settler turn. The forest house is an
  expansion building (ignore for base).
- Legal actions for the player's turn:
  - `TAKE_TILE(tile=t, target=slot)` for each available tile `t` and each empty island slot. To keep
    the action space small, fix placement: since island position is irrelevant, **auto-place** into
    the lowest-index empty slot and drop `target` from settler actions entirely — the agent only
    chooses *which tile*. (Document this simplification; it is rules-equivalent.)
  - `PASS` (taking a tile is voluntary).
- `apply(TAKE_TILE)`: move the tile from `plantation_faceup` (or decrement `quarry_supply`) into the
  player's island; fire hacienda/hospice hooks. Then advance `order_pos`.
- **Last duty:** discard remaining face-up tiles to `plantation_discard`; draw `num_players+1` new
  tiles from `plantation_facedown` into `plantation_faceup`. If the draw stack empties, reshuffle the
  discard (via `rng`) to refill; if still short, the row is simply shorter that round.
- A player whose island is full takes no tile (only `PASS` is legal for them).

## The Mayor (Phase.MAYOR)

This phase is the main combinatorial one; we sequence colonist placement one colonist per decision.

- **Order & supply:** chooser takes 1 colonist from the **supply** (privilege) first; then, starting
  with the chooser and going clockwise, players draw colonists **one at a time from the ship** until it
  is empty. For the engine, compute each player's new colonists deterministically (rulebook example),
  add to their `stored_colonists`, then enter the **placement sub-phase**.
- **Placement sub-phase:** for each player in `order`, with `colonists_to_place` = (all their stored
  colonists; rulebook lets you rearrange every colonist each mayor phase), the player repeatedly makes
  `PLACE_COLONIST` decisions:
  - Legal actions: `PLACE_COLONIST(target=circle_id)` for each empty colonist circle the player owns
    (each empty plantation/quarry slot = 1 circle; each building = up to capacity circles), plus
    `PLACE_COLONIST(target=STORE)` **only if no empty circle exists** (rulebook: you may not store
    while empty circles remain). When all of a player's colonists are placed or stored, advance to the
    next player.
  - Rearrangement: at the start of a player's placement, **lift all their colonists back to
    `stored_colonists`** (island + city) so the agent can re-place from scratch — this matches "may
    move a colonist placed in an earlier round." Then place one at a time. (Implementation detail:
    lifting then re-placing is equivalent and keeps the decision uniform.)
- **Last duty (chooser):** refill the ship — for every empty **building** circle across all players
  (plantation/quarry circles do NOT count), add 1 colonist from `colonist_supply` to `colonist_ship`,
  but at least `num_players`. If `colonist_supply` is insufficient to meet the required count, this is
  the **colonist-shortage end trigger** (see Game End).
- **Building hooks:** university (builder phase), hospice (settler) are elsewhere; the mayor phase has
  no base-game building hooks beyond standard occupancy. (Expansion buildings villa/guest house: later.)

> Note: simultaneous placement in the physical game is modeled as sequential per-player here; it does
> not change outcomes because players place only on their own boards.

## The Builder (Phase.BUILDER)

Per-player turn:
- Legal actions: `BUILD(building=b, target=slot)` for each building `b` the player can afford and is
  available in `buildings_supply` and not already owned, where they have room (large building needs
  two adjacent empty city slots). As with settler, **auto-place** into the lowest available slot(s) and
  drop `target` — the agent chooses only *which building*. Plus `PASS`.
- **Cost:** printed cost − (1 if this player is the chooser, the builder privilege) − (quarry
  discount: 1 per occupied quarry, capped by the building's board column 1..4) − (any building-hook
  discounts, e.g. expansion black market — ignore for base). Floor at 0. Affordable iff
  `doubloons >= cost`.
- `apply(BUILD)`: pay to bank, place building (mark large-building second slot), decrement
  `buildings_supply`, fire build-time hooks (**university:** place a free colonist on the new
  building). If a player builds on their 12th city space, set the **12th-building end trigger**.
- No player builds more than one building per round (enforced by the one-turn-per-player structure).

## The Craftsman (Phase.CRAFTSMAN)

This phase has **no per-player choice in the base game except the chooser's bonus pick** — production
is deterministic given board state, so resolve it without decision nodes, then ask the chooser one
`CHOOSE` for the privilege good.
- For each player in `order`: compute production. For each good kind, output =
  `min(matching occupied production-building circles manned, occupied plantations of that kind,
  goods_supply[kind])`. Corn needs no building: output = `min(occupied corn plantations,
  supply)`. Add produced goods to the player's `goods`, decrement `goods_supply`.
  - Fire **factory** hook (chooser and any owner): +doubloons by number of distinct kinds produced
    (2→1,3→2,4→3,5→5). See design/03.
- **Privilege (chooser):** a `CHOOSE` decision selecting one extra good among the kinds they produced
  this turn (if supply remains). This is the only craftsman decision node. `PASS` if they produced
  nothing.
- If a good's supply is exhausted, production of that good is truncated (no substitute).

## The Trader (Phase.TRADER)

Per-player turn:
- Trading house holds up to 4 goods and (base rule) buys only **different** kinds. Legal `SELL(good=g)`
  for each good `g` the player holds such that the house has room AND (g not already in the house OR
  the player has an occupied **office**, which lifts the different-kind restriction). Plus `PASS`
  (selling is optional). A trading post (expansion) is ignored for base.
- **Price:** base good price by kind: corn 0, indigo 1, sugar 2, tobacco 3, coffee 4. Plus 1 if this
  player is the chooser (trader privilege). Plus market hooks: **small market** +1, **large market**
  +2 (stack to +3). `apply(SELL)`: remove the good from the player, add to `trading_house`, pay price
  from bank to player.
- **Last duty (chooser):** if `trading_house` has 4 goods, clear it to `goods_supply`; otherwise leave
  it (carries over, tightening the next trade phase).

## The Captain (Phase.CAPTAIN)

The only **mandatory** action phase, and the only one where a player gets multiple turns. The phase
loops around `order` repeatedly while at least one player can still load.

- A player **can load** if they hold a good that fits the loading rules:
  - each ship carries one kind; you cannot load a kind already on another ship; cannot load a full
    ship; when you load a kind you must load as many as fit, choosing the ship that takes the most.
- Legal actions for the current player's turn:
  - `LOAD(good=g, target=ship_idx)` for each legal (good, ship) pair. Because "load as many as fit /
    most-filling ship" is forced, you may reduce this to one `LOAD(good=g)` per loadable kind and let
    `apply` pick the forced ship/amount; document the rule that resolves ties (most free space).
  - **Wharf** (occupied): a `LOAD` variant `Action(type=LOAD, choice=WHARF, good=g)` that ships all of
    one kind to the supply (once per phase). The wharf is *optional*, so it is offered alongside cargo
    loads, but a player who can load a cargo ship **must** act (cannot `PASS`) unless their only option
    is the optional wharf. Encode this carefully: `PASS` is legal only when the player cannot load any
    cargo ship (they may still choose wharf if available, or pass).
  - If the player cannot load at all, they are added to `phase_state.captain_done` and skipped.
- **VP on load:** +1 VP per good loaded (all kinds equal here). Chooser (captain) gets +1 VP on their
  **first** load only. **Harbor** hook: +1 VP each load. **Lighthouse**/others are expansion.
  Increment the player's `vp_chips` and decrement `vp_chips_remaining`; if it hits 0, set the
  **VP-exhaustion end trigger** (game ends at end of round).
- Loop ends when every player is in `captain_done`. **Last duty (chooser):** unload all **full** ships
  to `goods_supply`; partial/empty ships remain.
- **Goods storage (end of captain phase):** for each player, they keep 1 good on the windrose; warehouse
  hooks (**small warehouse:** keep all of 1 chosen kind; **large warehouse:** 2 kinds; stack → 3) extend
  this. Remaining goods are returned to `goods_supply`. If a player must choose which goods to keep
  (capacity-limited and ambiguous), emit `CHOOSE` decisions; otherwise auto-resolve. Keep this minimal:
  in the 2-player base game, model storage as a small set of `CHOOSE` decisions only when the kept set
  is ambiguous, else resolve automatically (keep highest-count kinds).

## The Prospector (Phase ROLE_SELECTION resolves it inline)

No follow action. On selection, the chooser takes 1 doubloon from the bank (plus any accumulated
placard doubloons, already handled in SELECT_ROLE). Immediately run end-of-role and continue.

## Game End

Set `end_triggered = True` when any of these fires (the game then finishes the **current round**, then
`phase = GAME_OVER`):
1. End of a mayor phase: `colonist_supply` cannot meet the required ship refill.
2. Builder phase: a player builds on their 12th city space.
3. Captain phase: the last VP chip is taken (`vp_chips_remaining == 0`).

After the round in which a trigger fired, transition to `GAME_OVER`. `legal_actions()` returns `[]`
and `is_terminal` is true.

## Final Scoring (scoring.py)

For each player, total =
`vp_chips`
`+ printed VP of each building owned (occupied or not)`
`+ extra VP from each OCCUPIED large building`:
- **Guild hall:** +1 per small production building, +2 per large production building (occupied or not).
- **Residence:** +4/5/6/7 for ≤9 / 10 / 11 / 12 filled island spaces.
- **Fortress:** +1 per 3 colonists on the player's board (island + city + stored).
- **Customs house:** +1 per 4 VP **chips** (excludes building VP).
- **City hall:** +1 per beige building owned (city hall counts itself).

Winner = most total VP; tie-break = most (doubloons + goods) where 1 good = 1 doubloon; document a
final deterministic tie-break (e.g. lower player index) so `winner()` is total.

## Acceptance criteria (M2)

- A scripted 4-player game (fixed seed + fixed action list) reproduces an expected final score.
- The rulebook **captain worked example** (a 4-player scenario) is encoded as a test and matches the
  stated VP outcomes.
- Each end trigger has a dedicated test that ends the game in the correct round.
- Each building's effect has a unit test (cross-ref design/03).
- A full random-legal playthrough never produces an illegal state (invariant checks: counts
  non-negative, ship single-kind, ≤4 goods in trading house, ≤12 tiles/buildings per player).
