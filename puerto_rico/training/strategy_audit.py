"""Strategy audit: do the trained RL AIs arrive at *dominant* Puerto Rico play?

This module instruments many full games and computes measurable "strong-play
signatures" drawn from Puerto Rico strategy analysis, then compares the trained
RL release policy against the :class:`HeuristicAgent` and :class:`RandomAgent`.

It is a *diagnostic*, not a trainer: it drives the engine manually (no env),
records every decision (acting seat, phase, action) plus board snapshots needed
to measure manning / production-chains, and at terminal records final scores,
winner and ranking. From those traces it computes the metrics enumerated in the
audit spec (outcome, win-rate-by-seat, role-pick distribution by game-third,
large-building ownership of winners, key/trap build rates, unmanned buildings,
production-chain mismatches, corn timing, empty builds, shipping behavior).

Entry points
------------
* :func:`run_audit` ``(num_games, seed) -> dict`` — play the four line-ups
  (4xRL self-play, 4xHeuristic, 4xRandom, 1xRL vs 3xHeuristic), rotating seats,
  and return every metric as a nested dict keyed by agent type.
* :func:`main` — run :func:`run_audit` and write a Markdown report with a
  per-metric section, RL-vs-Heuristic-vs-Random tables, and a VERDICT section
  grading each strong-play signature.

The release checkpoint is ``runs/release/final.pt``; if it is missing the RL
line-ups are skipped (so the audit still runs Heuristic/Random).
"""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from pathlib import Path

from ..agents.heuristic_agent import HeuristicAgent
from ..agents.random_agent import RandomAgent
from ..engine import scoring
from ..engine.buildings import CATALOG
from ..engine.enums import BuildingId, DecisionType, Good, Phase, Role, TileType
from ..engine.game import Game
from ..engine.state import GameConfig
from ..env import action_codec
from .evaluate import make_player

# Release checkpoint the audit loads the trained policy from.
RELEASE_CHECKPOINT = "runs/release/final.pt"
REPORT_PATH = "docs/rl-strategy-audit.md"

NUM_PLAYERS = 4

# Tile kind -> the good it produces; corn needs no production building.
_TILE_GOOD: dict[TileType, Good] = {
    TileType.CORN: Good.CORN,
    TileType.INDIGO: Good.INDIGO,
    TileType.SUGAR: Good.SUGAR,
    TileType.TOBACCO: Good.TOBACCO,
    TileType.COFFEE: Good.COFFEE,
}

# Buildings the strategy literature rates as strong/most-built.
_STRONG_BUILDINGS = (
    BuildingId.HARBOR,
    BuildingId.WHARF,
    BuildingId.FACTORY,
    BuildingId.SMALL_MARKET,
)
# Buildings considered traps (weak / situational; bad when built early).
_TRAP_BUILDINGS = (
    BuildingId.LARGE_WAREHOUSE,
    BuildingId.HOSPICE,
    BuildingId.UNIVERSITY,
    BuildingId.OFFICE,
)

# A build is "early" if it happens in the first third of the game (by round).
_EARLY_THIRD = 0


# --------------------------------------------------------------------------- #
# per-game instrumentation                                                    #
# --------------------------------------------------------------------------- #


def _large_buildings_owned(player) -> list[BuildingId]:
    out = []
    for slot in player.city:
        bid = slot.building
        if bid is None or bid == BuildingId.LARGE_CONT:
            continue
        if CATALOG[bid].is_large:
            out.append(bid)
    return out


def _owns(player, building_id: BuildingId) -> bool:
    return any(
        s.building == building_id for s in player.city
    )


def _manned_plantations(player, good: Good) -> int:
    tile = next(t for t, g in _TILE_GOOD.items() if g == good)
    return sum(1 for s in player.island if s.tile == tile and s.colonist)


def _manned_production_circles(player, good: Good) -> int:
    total = 0
    for slot in player.city:
        bid = slot.building
        if bid is None or bid == BuildingId.LARGE_CONT:
            continue
        spec = CATALOG[bid]
        if spec.is_production and spec.produces == good:
            total += min(slot.colonists, spec.capacity)
    return total


def _unmanned_capacity(player) -> int:
    """Free production/large-building circles (wasted manning)."""
    free = 0
    for slot in player.city:
        bid = slot.building
        if bid is None or bid == BuildingId.LARGE_CONT:
            continue
        spec = CATALOG[bid]
        if spec.is_production or spec.is_large:
            free += spec.capacity - slot.colonists
    return free


def _chain_mismatches(player) -> int:
    """Count manned-prod-no-plantation + manned-plantation-no-prod (excl. corn)."""
    mismatch = 0
    for good in Good:
        if good == Good.CORN:
            continue  # corn needs no building
        prod = _manned_production_circles(player, good)
        plant = _manned_plantations(player, good)
        if prod > 0 and plant == 0:
            mismatch += 1
        if plant > 0 and prod == 0:
            mismatch += 1
    return mismatch


def _ships_corn_no_engine(player, shipped_kinds: set[Good]) -> bool:
    """All-corn-no-engine: shipped corn but owns no Harbor/Wharf/large building."""
    if Good.CORN not in shipped_kinds:
        return False
    has_engine = (
        _owns(player, BuildingId.HARBOR)
        or _owns(player, BuildingId.WHARF)
        or len(_large_buildings_owned(player)) > 0
    )
    return not has_engine


def _play_game(seat_to_player_fn, seed: int) -> dict:
    """Drive one full game; return a per-seat instrumented record.

    ``seat_to_player_fn`` maps seat index -> a ``PlayerFn(game) -> int``.
    """
    game = Game(GameConfig(num_players=NUM_PLAYERS, seed=seed))

    # per-seat accumulators
    role_picks = [[] for _ in range(NUM_PLAYERS)]  # list of (Role, third)
    role_third = [[] for _ in range(NUM_PLAYERS)]
    first_ship_decision = [None] * NUM_PLAYERS  # decision index of first LOAD
    shipped_total = [0] * NUM_PLAYERS
    shipped_kinds = [set() for _ in range(NUM_PLAYERS)]
    empty_build_chances = [0] * NUM_PLAYERS
    empty_build_passes = [0] * NUM_PLAYERS
    corn_acquire_fracs = [[] for _ in range(NUM_PLAYERS)]
    prev_corn_count = [0] * NUM_PLAYERS

    # mayor-phase unmanned snapshots (averaged at end)
    unmanned_snapshots = [[] for _ in range(NUM_PLAYERS)]

    decision_idx = 0
    # We don't know total decisions ahead of time, so we estimate game progress
    # by completed rounds vs a typical max; thirds are computed post-hoc from the
    # final round count. We record the round_number at each role pick / corn buy.
    role_pick_rounds = [[] for _ in range(NUM_PLAYERS)]
    corn_buy_rounds = [[] for _ in range(NUM_PLAYERS)]

    last_phase = None

    while not game.is_terminal:
        state = game.state
        seat = game.current_player
        phase = state.phase
        player = state.players[seat]
        rnd = state.round_number

        legal = game.legal_actions()

        # --- pre-decision measurements that need the legal set ---
        if phase == Phase.BUILDER:
            builds = [a for a in legal if a.type == DecisionType.BUILD]
            has_pass = any(a.type == DecisionType.PASS for a in legal)
            if builds and has_pass:
                empty_build_chances[seat] += 1

        # --- the agent decides ---
        action_id = int(seat_to_player_fn(seat)(game))
        action = action_codec.from_int(action_id, state)

        # --- record the action ---
        if phase == Phase.ROLE_SELECTION and action.type == DecisionType.SELECT_ROLE:
            role_picks[seat].append(action.role)
            role_pick_rounds[seat].append(rnd)

        if phase == Phase.BUILDER and action.type == DecisionType.PASS:
            builds = [a for a in legal if a.type == DecisionType.BUILD]
            if builds:
                empty_build_passes[seat] += 1

        if phase == Phase.CAPTAIN and action.type == DecisionType.LOAD:
            if first_ship_decision[seat] is None:
                first_ship_decision[seat] = decision_idx
            # count goods actually shipped by this load
            held = player.goods[action.good]
            if action.choice == 1:  # wharf: ships the whole kind
                shipped = held
            elif action.target is not None and action.target < len(state.cargo_ships):
                ship = state.cargo_ships[action.target]
                shipped = min(held, ship.capacity - ship.count)
            else:
                shipped = 0
            shipped_total[seat] += max(0, shipped)
            if shipped > 0:
                shipped_kinds[seat].add(action.good)

        decision_idx += 1
        game.apply(action, validate=False)

        # --- post-apply board snapshots ---
        new_state = game.state
        # corn acquisition: detect a rise in corn plantation count
        for s in range(NUM_PLAYERS):
            corn_now = sum(
                1 for sl in new_state.players[s].island if sl.tile == TileType.CORN
            )
            if corn_now > prev_corn_count[s]:
                corn_buy_rounds[s].append(new_state.round_number)
            prev_corn_count[s] = corn_now

        # mayor-phase end: snapshot unmanned capacity when MAYOR just finished
        if last_phase == Phase.MAYOR and new_state.phase != Phase.MAYOR:
            for s in range(NUM_PLAYERS):
                unmanned_snapshots[s].append(_unmanned_capacity(new_state.players[s]))
        last_phase = new_state.phase

    # ---- terminal ----
    final_state = game.state
    scores = scoring.final_scores(final_state)
    order = scoring.rankings(final_state)  # best -> worst seats
    placement = [0] * NUM_PLAYERS
    for place, s in enumerate(order):
        placement[s] = place + 1
    winner_seat = order[0]

    total_rounds = max(1, final_state.round_number)

    def third_of_round(r: int) -> int:
        # 0 early, 1 mid, 2 late
        frac = r / total_rounds
        if frac < 1 / 3:
            return 0
        if frac < 2 / 3:
            return 1
        return 2

    # finalize per-seat records
    seats = []
    for s in range(NUM_PLAYERS):
        player = final_state.players[s]
        picks_by_third = {0: Counter(), 1: Counter(), 2: Counter()}
        for role, r in zip(role_picks[s], role_pick_rounds[s]):
            picks_by_third[third_of_round(r)][role] += 1

        corn_fracs = [r / total_rounds for r in corn_buy_rounds[s]]

        unmanned = unmanned_snapshots[s]
        # also include final-state unmanned capacity
        final_unmanned = _unmanned_capacity(player)

        seats.append(
            {
                "seat": s,
                "score": scores[s],
                "vp_chips": player.vp_chips,
                "placement": placement[s],
                "is_winner": s == winner_seat,
                "role_picks": list(role_picks[s]),
                "picks_by_third": {
                    t: dict(picks_by_third[t]) for t in (0, 1, 2)
                },
                "large_buildings": [int(b) for b in _large_buildings_owned(player)],
                "owns_guild_hall": _owns(player, BuildingId.GUILD_HALL),
                "owns_any_large": len(_large_buildings_owned(player)) > 0,
                "built_strong": {
                    int(b): _owns(player, b) for b in _STRONG_BUILDINGS
                },
                "built_trap": {
                    int(b): _owns(player, b) for b in _TRAP_BUILDINGS
                },
                "unmanned_mean": (
                    sum(unmanned) / len(unmanned) if unmanned else final_unmanned
                ),
                "unmanned_final": final_unmanned,
                "chain_mismatch_final": _chain_mismatches(player),
                "corn_fracs": corn_fracs,
                "all_corn_no_engine": _ships_corn_no_engine(player, shipped_kinds[s]),
                "empty_build_chances": empty_build_chances[s],
                "empty_build_passes": empty_build_passes[s],
                "first_ship_decision": first_ship_decision[s],
                "ships_at_all": shipped_total[s] > 0,
                "shipped_total": shipped_total[s],
            }
        )

    return {"seats": seats, "winner_seat": winner_seat, "total_rounds": total_rounds}


# --------------------------------------------------------------------------- #
# aggregation across games for one line-up                                    #
# --------------------------------------------------------------------------- #


def _new_accumulator() -> dict:
    return {
        "games": 0,
        "seat_decisions": 0,
        # outcome (winners only)
        "winner_vp": [],
        "winner_vp_chips": [],
        "winner_shipped": [],
        "winner_owns_large": 0,
        "winner_owns_guild_hall": 0,
        "winners": 0,
        # win rate by seat
        "wins_by_seat": [0, 0, 0, 0],
        "games_by_seat": [0, 0, 0, 0],
        # role picks by third
        "roles_by_third": {0: Counter(), 1: Counter(), 2: Counter()},
        "role_total": Counter(),
        # build rates (per seat-occurrence)
        "strong_built": Counter(),
        "trap_built": Counter(),
        # manning / chains
        "unmanned_mean_sum": 0.0,
        "chain_mismatch_sum": 0,
        # corn
        "corn_frac_sum": 0.0,
        "corn_frac_n": 0,
        "all_corn_no_engine": 0,
        # empty builds
        "empty_build_chances": 0,
        "empty_build_passes": 0,
        # shipping
        "ships_at_all": 0,
        "first_ship_sum": 0,
        "first_ship_n": 0,
        "winner_vp_hist": [],
    }


def _accumulate(acc: dict, seat_rec: dict, *, is_target: bool) -> None:
    """Fold one seat's record into ``acc`` (only seats driven by the target agent)."""
    if not is_target:
        return
    acc["seat_decisions"] += 1
    s = seat_rec["seat"]
    acc["games_by_seat"][s] += 1
    if seat_rec["is_winner"]:
        acc["wins_by_seat"][s] += 1
        acc["winners"] += 1
        acc["winner_vp"].append(seat_rec["score"])
        acc["winner_vp_chips"].append(seat_rec["vp_chips"])
        acc["winner_shipped"].append(seat_rec["shipped_total"])
        acc["winner_vp_hist"].append(seat_rec["score"])
        if seat_rec["owns_any_large"]:
            acc["winner_owns_large"] += 1
        if seat_rec["owns_guild_hall"]:
            acc["winner_owns_guild_hall"] += 1

    for t in (0, 1, 2):
        for role, n in seat_rec["picks_by_third"][t].items():
            acc["roles_by_third"][t][Role(role)] += n
            acc["role_total"][Role(role)] += n

    for b, built in seat_rec["built_strong"].items():
        if built:
            acc["strong_built"][b] += 1
    for b, built in seat_rec["built_trap"].items():
        if built:
            acc["trap_built"][b] += 1

    acc["unmanned_mean_sum"] += seat_rec["unmanned_mean"]
    acc["chain_mismatch_sum"] += seat_rec["chain_mismatch_final"]

    for f in seat_rec["corn_fracs"]:
        acc["corn_frac_sum"] += f
        acc["corn_frac_n"] += 1
    if seat_rec["all_corn_no_engine"]:
        acc["all_corn_no_engine"] += 1

    acc["empty_build_chances"] += seat_rec["empty_build_chances"]
    acc["empty_build_passes"] += seat_rec["empty_build_passes"]

    if seat_rec["ships_at_all"]:
        acc["ships_at_all"] += 1
    if seat_rec["first_ship_decision"] is not None:
        acc["first_ship_sum"] += seat_rec["first_ship_decision"]
        acc["first_ship_n"] += 1


def _safe_div(a, b):
    return a / b if b else 0.0


def _finalize(acc: dict) -> dict:
    n = max(1, acc["seat_decisions"])
    w = max(1, acc["winners"])
    out = {
        "games_as_target": acc["seat_decisions"],
        "winners": acc["winners"],
        "winner_mean_vp": _safe_div(sum(acc["winner_vp"]), acc["winners"]),
        "winner_mean_vp_chips": _safe_div(
            sum(acc["winner_vp_chips"]), acc["winners"]
        ),
        "winner_mean_shipped": _safe_div(
            sum(acc["winner_shipped"]), acc["winners"]
        ),
        "winner_vp_hist": sorted(acc["winner_vp_hist"]),
        "wins_by_seat": acc["wins_by_seat"],
        "games_by_seat": acc["games_by_seat"],
        "win_rate_by_seat": [
            _safe_div(acc["wins_by_seat"][s], acc["games_by_seat"][s])
            for s in range(NUM_PLAYERS)
        ],
        "winner_owns_large_rate": _safe_div(acc["winner_owns_large"], w),
        "winner_owns_guild_hall_rate": _safe_div(acc["winner_owns_guild_hall"], w),
        "role_total": {Role(r).name: c for r, c in acc["role_total"].items()},
        "roles_by_third": {
            t: {Role(r).name: c for r, c in acc["roles_by_third"][t].items()}
            for t in (0, 1, 2)
        },
        "strong_build_rate": {
            CATALOG[BuildingId(b)].name: _safe_div(acc["strong_built"][b], n)
            for b in (int(x) for x in _STRONG_BUILDINGS)
        },
        "trap_build_rate": {
            CATALOG[BuildingId(b)].name: _safe_div(acc["trap_built"][b], n)
            for b in (int(x) for x in _TRAP_BUILDINGS)
        },
        "mean_unmanned": _safe_div(acc["unmanned_mean_sum"], n),
        "mean_chain_mismatch": _safe_div(acc["chain_mismatch_sum"], n),
        "mean_corn_acquire_frac": _safe_div(
            acc["corn_frac_sum"], acc["corn_frac_n"]
        ),
        "all_corn_no_engine_rate": _safe_div(acc["all_corn_no_engine"], n),
        "empty_build_pass_rate": _safe_div(
            acc["empty_build_passes"], acc["empty_build_chances"]
        ),
        "ships_at_all_rate": _safe_div(acc["ships_at_all"], n),
        "mean_first_ship_decision": _safe_div(
            acc["first_ship_sum"], acc["first_ship_n"]
        ),
    }
    return out


# --------------------------------------------------------------------------- #
# line-up runner                                                              #
# --------------------------------------------------------------------------- #


def _run_lineup(
    agents: list, target_lineup_idx: set[int], num_games: int, seed: int
) -> dict:
    """Play ``num_games`` seat-rotated games; aggregate the TARGET agent's seats.

    ``agents`` is a list of length ``NUM_PLAYERS`` of agent objects (line-up
    order). ``target_lineup_idx`` is the set of line-up indices whose seats we
    accumulate (the agent type we are auditing in this line-up). Seat rotation
    matches the Arena: line-up index ``a`` sits at seat ``(a + g) % N``.
    """
    n = NUM_PLAYERS
    fns = [make_player(a) for a in agents]
    acc = _new_accumulator()

    for g in range(num_games):
        seat_to_lineup = [(s - g) % n for s in range(n)]

        def seat_player(seat, _map=seat_to_lineup):
            return fns[_map[seat]]

        rec = _play_game(seat_player, seed + g)
        acc["games"] += 1
        for seat_rec in rec["seats"]:
            lineup_idx = seat_to_lineup[seat_rec["seat"]]
            _accumulate(
                acc, seat_rec, is_target=lineup_idx in target_lineup_idx
            )

    return _finalize(acc)


# --------------------------------------------------------------------------- #
# public API                                                                  #
# --------------------------------------------------------------------------- #


def _load_rl():
    path = Path(RELEASE_CHECKPOINT)
    if not path.exists():
        return None
    try:
        from ..agents.rl_policy import RLPolicy

        return RLPolicy.from_checkpoint(str(path))
    except Exception:
        return None


def run_audit(num_games: int = 200, seed: int = 0) -> dict:
    """Play the audit line-ups and return all strong-play metrics.

    Returns a dict with keys:

    * ``agents`` — mapping agent-type name ("RL", "Heuristic", "Random") ->
      finalized metric dict (see :func:`_finalize`). Each type is audited in an
      all-same-type line-up (4xRL / 4xHeuristic / 4xRandom).
    * ``rl_vs_heuristic`` — RL's metrics when seated as 1 RL vs 3 Heuristic
      (a head-to-head check), or ``None`` if no checkpoint.
    * ``meta`` — ``num_games``, ``seed``, ``rl_available``.
    """
    rl = _load_rl()
    rl_available = rl is not None

    agents_metrics: dict[str, dict] = {}

    # 4x Heuristic
    heur = [HeuristicAgent(seed=100 + i) for i in range(NUM_PLAYERS)]
    agents_metrics["Heuristic"] = _run_lineup(
        heur, {0, 1, 2, 3}, num_games, seed
    )

    # 4x Random
    rand = [RandomAgent(seed=200 + i) for i in range(NUM_PLAYERS)]
    agents_metrics["Random"] = _run_lineup(
        rand, {0, 1, 2, 3}, num_games, seed
    )

    rl_vs_heuristic = None
    if rl_available:
        # 4x RL self-play (one shared stateless policy is fine; it is reused).
        rl_lineup = [rl, rl, rl, rl]
        agents_metrics["RL"] = _run_lineup(
            rl_lineup, {0, 1, 2, 3}, num_games, seed
        )

        # 1x RL vs 3x Heuristic (RL is line-up index 0).
        mixed = [rl] + [HeuristicAgent(seed=300 + i) for i in range(NUM_PLAYERS - 1)]
        rl_vs_heuristic = _run_lineup(mixed, {0}, num_games, seed)

    return {
        "agents": agents_metrics,
        "rl_vs_heuristic": rl_vs_heuristic,
        "meta": {
            "num_games": num_games,
            "seed": seed,
            "rl_available": rl_available,
        },
    }


# --------------------------------------------------------------------------- #
# report writer                                                               #
# --------------------------------------------------------------------------- #


def _fmt(x, nd=2):
    if isinstance(x, float):
        if math.isnan(x):
            return "nan"
        return f"{x:.{nd}f}"
    return str(x)


def _pct(x):
    return f"{100 * x:.1f}%"


def _table(header: list[str], rows: list[list[str]]) -> str:
    lines = ["| " + " | ".join(header) + " |"]
    lines.append("| " + " | ".join("---" for _ in header) + " |")
    for r in rows:
        lines.append("| " + " | ".join(str(c) for c in r) + " |")
    return "\n".join(lines)


def _verdict_symbol(strong: bool, partial: bool) -> str:
    if strong:
        return "✅"
    if partial:
        return "⚠️"
    return "❌"


def build_report(audit: dict) -> str:
    """Render the audit dict as a Markdown report string."""
    agents = audit["agents"]
    meta = audit["meta"]
    order = [a for a in ("RL", "Heuristic", "Random") if a in agents]

    lines: list[str] = []
    lines.append("# RL Strategy Audit — Puerto Rico\n")
    lines.append(
        f"Games per line-up: **{meta['num_games']}** (seed {meta['seed']}). "
        f"RL checkpoint: `{RELEASE_CHECKPOINT}` "
        f"({'loaded' if meta['rl_available'] else 'MISSING — RL rows omitted'}).\n"
    )
    lines.append(
        "Each agent type is audited in an all-same-type 4-player line-up "
        "(4xRL self-play / 4xHeuristic / 4xRandom), seats rotated so seat "
        "asymmetry averages out. Metrics for an agent are computed over the "
        "seats *it* drives, with extra focus on WINNERS.\n"
    )

    # ---- 1. Outcome ----
    lines.append("## 1. Outcome (winners)\n")
    rows = []
    for a in order:
        m = agents[a]
        rows.append(
            [
                a,
                _fmt(m["winner_mean_vp"], 1),
                _fmt(m["winner_mean_vp_chips"], 1),
                _fmt(m["winner_mean_shipped"], 1),
            ]
        )
    lines.append(
        _table(
            ["agent", "winner mean VP", "winner shipping VP (chips)", "winner goods shipped"],
            rows,
        )
    )
    lines.append("")
    for a in order:
        hist = agents[a]["winner_vp_hist"]
        if hist:
            lo, hi = hist[0], hist[-1]
            med = hist[len(hist) // 2]
            lines.append(
                f"- {a} winner VP distribution: min {lo}, median {med}, max {hi} "
                f"(n={len(hist)})."
            )
    lines.append("")

    # ---- 2. Win rate by seat ----
    lines.append("## 2. Win rate by seat (first-player disadvantage check)\n")
    lines.append(
        "Puerto Rico has a known FIRST-PLAYER DISADVANTAGE (seat 0 starts with "
        "indigo, the last seat with corn). In an all-same-type line-up every "
        "seat is played by the same policy, so a large seat-0 skew points at the "
        "engine/strategy, not at a stronger opponent.\n"
    )
    rows = []
    for a in order:
        m = agents[a]
        wr = m["win_rate_by_seat"]
        rows.append([a] + [_pct(x) for x in wr])
    lines.append(_table(["agent", "seat 0", "seat 1", "seat 2", "seat 3"], rows))
    lines.append("")

    # ---- 3. Role picks by third ----
    lines.append("## 3. Role-pick distribution by game-third\n")
    lines.append(
        "Strong play: Trader/Prospector early, Builder when cash-rich, Captain "
        "when holding goods, Craftsman mostly by the dominant producer.\n"
    )
    for a in order:
        m = agents[a]
        lines.append(f"### {a}\n")
        rows = []
        roles = [r.name for r in Role]
        for t, label in ((0, "early"), (1, "mid"), (2, "late")):
            d = m["roles_by_third"][t]
            total = sum(d.values()) or 1
            rows.append(
                [label] + [_pct(_safe_div(d.get(r, 0), total)) for r in roles]
            )
        lines.append(_table(["third"] + roles, rows))
        lines.append("")

    # ---- 4. Large-building ownership of winners ----
    lines.append("## 4. Large-building ownership of WINNERS\n")
    lines.append(
        "Guild Hall is generally rated the best large building. Strong play "
        "tends to land at least one large building.\n"
    )
    rows = []
    for a in order:
        m = agents[a]
        rows.append(
            [
                a,
                _pct(m["winner_owns_large_rate"]),
                _pct(m["winner_owns_guild_hall_rate"]),
            ]
        )
    lines.append(
        _table(["agent", "winners w/ >=1 large", "winners w/ Guild Hall"], rows)
    )
    lines.append("")

    # ---- 5. Key building build-rates ----
    lines.append("## 5. Key building build-rates (per seat played)\n")
    lines.append(
        "Each building has supply **1** in the 4-player base game, so the rate is "
        "computed per seat-occurrence and **ceils at 25%** (= built by exactly one "
        "of the four players every game). Read ~25% as *always built (by someone)* "
        "and ~0% as *almost never built*.\n"
    )
    lines.append("**Strong / most-built buildings:**\n")
    strong_names = [CATALOG[b].name for b in _STRONG_BUILDINGS]
    rows = []
    for a in order:
        m = agents[a]
        rows.append([a] + [_pct(m["strong_build_rate"][n]) for n in strong_names])
    lines.append(_table(["agent"] + strong_names, rows))
    lines.append("")
    lines.append("**Trap / weak buildings (high rate is a bad sign):**\n")
    trap_names = [CATALOG[b].name for b in _TRAP_BUILDINGS]
    rows = []
    for a in order:
        m = agents[a]
        rows.append([a] + [_pct(m["trap_build_rate"][n]) for n in trap_names])
    lines.append(_table(["agent"] + trap_names, rows))
    lines.append("")

    # ---- 6. Unmanned buildings ----
    lines.append("## 6. Unmanned-building rounds (wasted manning)\n")
    lines.append(
        "Mean free colonist circles across owned production+large buildings "
        "(measured at each Mayor-phase end). Strong play -> near zero.\n"
    )
    rows = [[a, _fmt(agents[a]["mean_unmanned"], 2)] for a in order]
    lines.append(_table(["agent", "mean unmanned circles"], rows))
    lines.append("")

    # ---- 7. Production-chain mismatches ----
    lines.append("## 7. Production-chain mismatches\n")
    lines.append(
        "Mean count (at game end) of manned production buildings with no manned "
        "matching plantation, plus manned plantations with no matching building "
        "(corn excluded). Strong play -> low.\n"
    )
    rows = [[a, _fmt(agents[a]["mean_chain_mismatch"], 2)] for a in order]
    lines.append(_table(["agent", "mean chain mismatch"], rows))
    lines.append("")

    # ---- 8. Corn timing ----
    lines.append("## 8. Corn timing\n")
    lines.append(
        "Mean game-fraction at which corn plantations are acquired, and the "
        "all-corn-no-engine rate (ships corn but never builds Harbor/Wharf/large).\n"
    )
    rows = []
    for a in order:
        m = agents[a]
        rows.append(
            [
                a,
                _fmt(m["mean_corn_acquire_frac"], 2),
                _pct(m["all_corn_no_engine_rate"]),
            ]
        )
    lines.append(
        _table(["agent", "mean corn-acquire frac", "all-corn-no-engine rate"], rows)
    )
    lines.append("")

    # ---- 9. Empty build phases ----
    lines.append("## 9. Empty build phases\n")
    lines.append(
        "Rate at which the agent PASSes on its builder turn while it could afford "
        ">=1 building. Strong play -> low.\n"
    )
    rows = [[a, _pct(agents[a]["empty_build_pass_rate"])] for a in order]
    lines.append(_table(["agent", "empty-build pass rate"], rows))
    lines.append("")

    # ---- 10. Shipping behavior ----
    lines.append("## 10. Shipping behavior\n")
    rows = []
    for a in order:
        m = agents[a]
        rows.append(
            [
                a,
                _pct(m["ships_at_all_rate"]),
                _fmt(m["mean_first_ship_decision"], 0),
            ]
        )
    lines.append(
        _table(
            ["agent", "ships at all", "mean first-ship decision idx (lower=earlier)"],
            rows,
        )
    )
    lines.append("")

    # ---- RL vs Heuristic head-to-head ----
    if audit["rl_vs_heuristic"] is not None:
        rvh = audit["rl_vs_heuristic"]
        lines.append("## RL vs 3x Heuristic (head-to-head)\n")
        lines.append(
            f"- RL win rate vs 3 Heuristic: "
            f"**{_pct(_safe_div(rvh['winners'], rvh['games_as_target']))}** "
            f"(chance = 25%).\n"
            f"- RL winner mean VP: {_fmt(rvh['winner_mean_vp'], 1)}; "
            f"mean unmanned: {_fmt(rvh['mean_unmanned'], 2)}; "
            f"empty-build pass rate: {_pct(rvh['empty_build_pass_rate'])}.\n"
        )

    # ---- VERDICT ----
    lines.append("## VERDICT — strong-play signatures\n")
    lines.append(_verdict_section(audit))

    return "\n".join(lines) + "\n"


def _verdict_section(audit: dict) -> str:
    agents = audit["agents"]
    if "RL" not in agents:
        return (
            "RL checkpoint missing — no RL verdict. Heuristic/Random metrics are "
            "reported above for reference."
        )
    rl = agents["RL"]
    heur = agents.get("Heuristic", {})
    rows = []
    weaknesses = []

    # Signature: seat-0 over-win
    wr = rl["win_rate_by_seat"]
    seat0 = wr[0]
    others = [wr[1], wr[2], wr[3]]
    mean_other = _safe_div(sum(others), len(others))
    # Strong: seat 0 NOT massively over-winning. Flag if seat0 > 1.5x others.
    over = seat0 > 1.5 * mean_other and seat0 > 0.30
    near = seat0 > 1.25 * mean_other
    sym = _verdict_symbol(not near, not over)
    note = (
        f"seat0 {_pct(seat0)} vs others ~{_pct(mean_other)}"
        + (" — seat-0 OVER-WINS" if over else "")
    )
    rows.append(("No first-player over-win", sym, note))
    if over:
        weaknesses.append(
            f"Over-wins from seat 0 ({_pct(seat0)} vs ~{_pct(mean_other)}): the "
            "policy exploits seat asymmetry. Lever: stronger seat balancing / "
            "seat-aware reward normalization in self-play."
        )

    # Signature: winners land a large building
    lr = rl["winner_owns_large_rate"]
    sym = _verdict_symbol(lr >= 0.5, lr >= 0.2)
    rows.append(("Winners build large buildings", sym, f"{_pct(lr)} of winners"))
    if lr < 0.2:
        weaknesses.append(
            f"Winners rarely own a large building ({_pct(lr)}). Lever: "
            "reward/curriculum shaping to value big buildings."
        )

    # Signature: Guild Hall usage
    gh = rl["winner_owns_guild_hall_rate"]
    sym = _verdict_symbol(gh >= 0.25, gh >= 0.1)
    rows.append(("Uses Guild Hall (best large)", sym, f"{_pct(gh)} of winners"))
    if gh < 0.1:
        weaknesses.append(
            f"Almost never builds Guild Hall ({_pct(gh)} of winners). Lever: "
            "encourage big-building lines via reward shaping or opponent curricula."
        )

    # Signature: strong buildings built. NB build-rate ceils at 25% (supply 1 of
    # 4 seats), so ~20%+ already means "almost always built by someone".
    harbor = rl["strong_build_rate"].get(CATALOG[BuildingId.HARBOR].name, 0)
    wharf = rl["strong_build_rate"].get(CATALOG[BuildingId.WHARF].name, 0)
    best_ship = max(harbor, wharf)
    sym = _verdict_symbol(best_ship >= 0.18, best_ship >= 0.08)
    rows.append(
        ("Builds shipping engine (Harbor/Wharf)", sym,
         f"Harbor {_pct(harbor)}, Wharf {_pct(wharf)} (max=25%)")
    )
    if best_ship < 0.08:
        weaknesses.append(
            f"Rarely builds Harbor/Wharf (best {_pct(best_ship)}): shipping-VP "
            "engine underused. Lever: reward shipping-VP accumulation."
        )

    # Signature: avoids traps. Compare RL vs Random per trap: a trap built at
    # (or below) Random's rate is not an RL preference. We flag only traps RL
    # builds NOTABLY MORE than Random. (Each ceils at 25% by supply.)
    trap_rates = rl["trap_build_rate"]
    rand_traps = agents.get("Random", {}).get("trap_build_rate", {})
    excess = {
        name: trap_rates[name] - rand_traps.get(name, 0.0) for name in trap_rates
    }
    worst_name = max(excess, key=excess.get) if excess else None
    worst_excess = excess.get(worst_name, 0.0) if worst_name else 0.0
    sym = _verdict_symbol(worst_excess < 0.03, worst_excess < 0.10)
    rows.append(
        ("Avoids trap buildings", sym,
         f"vs Random, worst excess {_pct(worst_excess)} ({worst_name})")
    )
    if worst_excess >= 0.10:
        weaknesses.append(
            f"Builds trap building '{worst_name}' "
            f"{_pct(trap_rates[worst_name])} vs Random {_pct(rand_traps.get(worst_name, 0.0))}. "
            "Lever: these add little; better lines exist."
        )

    # Signature: manning (low unmanned)
    um = rl["mean_unmanned"]
    sym = _verdict_symbol(um < 0.5, um < 1.5)
    rows.append(("Mans its buildings", sym, f"{_fmt(um, 2)} mean free circles"))
    if um >= 1.5:
        weaknesses.append(
            f"Leaves buildings unmanned ({_fmt(um, 2)} free circles on avg). "
            "Lever: penalize idle capacity or value Mayor more."
        )

    # Signature: production-chain coherence
    cm = rl["mean_chain_mismatch"]
    sym = _verdict_symbol(cm < 0.5, cm < 1.5)
    rows.append(("Coherent production chains", sym, f"{_fmt(cm, 2)} mean mismatch"))
    if cm >= 1.5:
        weaknesses.append(
            f"Production-chain mismatches ({_fmt(cm, 2)} on avg): mans buildings "
            "without plantations or vice-versa. Lever: chain-completion reward."
        )

    # Signature: doesn't over-rely on corn-without-engine
    acne = rl["all_corn_no_engine_rate"]
    sym = _verdict_symbol(acne < 0.1, acne < 0.3)
    rows.append(("Not all-corn-no-engine", sym, f"{_pct(acne)}"))
    if acne >= 0.3:
        weaknesses.append(
            f"Over-ships corn with no engine ({_pct(acne)}). Lever: reward "
            "building a real production/shipping engine."
        )

    # Signature: builds when able (low empty-build pass)
    eb = rl["empty_build_pass_rate"]
    sym = _verdict_symbol(eb < 0.2, eb < 0.5)
    rows.append(("Builds when affordable", sym, f"{_pct(eb)} pass rate"))
    if eb >= 0.5:
        weaknesses.append(
            f"Passes on affordable builds {_pct(eb)} of the time. Lever: "
            "tempo/build-progress reward."
        )

    # Signature: ships goods
    sar = rl["ships_at_all_rate"]
    sym = _verdict_symbol(sar >= 0.8, sar >= 0.5)
    rows.append(("Ships goods for VP", sym, f"{_pct(sar)} ship at all"))
    if sar < 0.5:
        weaknesses.append(
            f"Often never ships ({_pct(sar)} ship at all). Lever: shipping-VP reward."
        )

    out = [_table(["strong-play signature", "verdict", "evidence"],
                  [[r[0], r[1], r[2]] for r in rows])]

    # Strategy summary
    out.append("\n### Apparent RL strategy\n")
    top_roles = sorted(
        rl["role_total"].items(), key=lambda kv: kv[1], reverse=True
    )
    role_blurb = ", ".join(f"{name} ({c})" for name, c in top_roles[:4])
    out.append(
        f"Most-picked roles overall: {role_blurb}. "
        f"Winner mean VP {_fmt(rl['winner_mean_vp'], 1)} "
        f"(shipping-VP component {_fmt(rl['winner_mean_vp_chips'], 1)}). "
        f"Heuristic winner mean VP for reference: "
        f"{_fmt(heur.get('winner_mean_vp', float('nan')), 1)}.\n"
    )

    out.append("### Concrete weaknesses + improvement levers\n")
    if weaknesses:
        for w in weaknesses:
            out.append(f"- {w}")
    else:
        out.append("- None of the audited signatures fall in the FAIL band.")

    return "\n".join(out)


# --------------------------------------------------------------------------- #
# CLI                                                                         #
# --------------------------------------------------------------------------- #


def main(argv=None) -> None:
    import argparse

    # Cap CPU so the audit does not lag the machine (RLPolicy inference uses torch).
    try:
        from .ppo import limit_cpu_usage

        limit_cpu_usage()
    except Exception:
        pass

    parser = argparse.ArgumentParser(description="Puerto Rico RL strategy audit.")
    parser.add_argument("--games", type=int, default=200)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--out", default=REPORT_PATH)
    args = parser.parse_args(argv)

    audit = run_audit(num_games=args.games, seed=args.seed)
    report = build_report(audit)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(report)
    print(f"wrote {out_path}")
    print()
    print(_verdict_section(audit))


if __name__ == "__main__":  # pragma: no cover
    main()
