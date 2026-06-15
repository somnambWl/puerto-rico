"""Tests for engine serialization: lossless round-trip and public_view masking."""

from __future__ import annotations

import random

from .enums import BuildingId, Good, Phase, Role, TileType
from .phase_state import PhaseState
from .serialize import from_dict, public_view, to_dict
from .state import (
    CargoShip,
    CitySlot,
    GameConfig,
    GameState,
    IslandSlot,
    PlayerState,
    RolePlacard,
)

# Prefer the real setup if it exists; otherwise hand-build a fixture so this
# test runs standalone (setup.py is being created concurrently).
try:  # pragma: no cover - depends on concurrent work
    from .setup import new_game  # type: ignore
except Exception:  # pragma: no cover
    new_game = None


def _hand_built_state() -> GameState:
    """A small but non-trivial GameState exercising every field/enum/None."""
    rng = random.Random(1234)
    # advance the rng so its internal state isn't the freshly-seeded one
    for _ in range(7):
        rng.random()

    def mk_player(seed_doubloons: int, vp: int) -> PlayerState:
        island = [IslandSlot() for _ in range(12)]
        island[0] = IslandSlot(tile=TileType.INDIGO, colonist=True)
        island[1] = IslandSlot(tile=TileType.QUARRY, colonist=False)
        city = [CitySlot() for _ in range(12)]
        city[0] = CitySlot(building=BuildingId.SMALL_INDIGO, colonists=1)
        city[1] = CitySlot(building=BuildingId.SMALL_MARKET, colonists=0)
        goods = [0, 0, 0, 0, 0]
        goods[Good.CORN] = 2
        goods[Good.COFFEE] = 1
        return PlayerState(
            doubloons=seed_doubloons,
            island=island,
            city=city,
            goods=goods,
            stored_colonists=1,
            vp_chips=vp,
            roles_taken_this_round=0,
        )

    players = [mk_player(2 + i, 3 * i) for i in range(4)]

    placards = [RolePlacard(role=r, doubloons=0) for r in Role]
    placards[Role.SETTLER] = RolePlacard(
        role=Role.SETTLER, doubloons=1, taken_by=2
    )

    return GameState(
        config=GameConfig(num_players=4, seed=1234, ruleset="base", max_rounds=17),
        rng=rng,
        players=players,
        governor=0,
        current_player=1,
        phase=Phase.SETTLER,
        placards=placards,
        colonist_ship=4,
        colonist_supply=55,
        cargo_ships=[
            CargoShip(capacity=4, good=Good.CORN, count=2),
            CargoShip(capacity=5, good=None, count=0),
            CargoShip(capacity=6, good=Good.COFFEE, count=6),
        ],
        trading_house=[Good.INDIGO, Good.SUGAR],
        goods_supply=[10, 11, 11, 9, 9],
        plantation_faceup=[TileType.CORN, TileType.INDIGO, TileType.SUGAR],
        plantation_facedown=[TileType.TOBACCO, TileType.COFFEE, TileType.CORN],
        plantation_discard=[TileType.INDIGO],
        quarry_supply=8,
        vp_chips_remaining=100,
        buildings_supply={
            BuildingId.SMALL_INDIGO: 3,
            BuildingId.SMALL_MARKET: 1,
        },
        phase_state=PhaseState(
            role_chooser=0,
            active_role=Role.SETTLER,
            order=[1, 2, 3, 0],
            order_pos=1,
            colonists_to_place=0,
            captain_done={2, 3},
            sub={"foo": 1, "bar": [1, 2]},
        ),
        end_triggered=False,
    )


def _make_state() -> GameState:
    if new_game is not None:
        s = new_game(GameConfig(num_players=4, seed=1234, max_rounds=17))
    else:
        s = _hand_built_state()
    # Force non-default values so the round-trip test would FAIL if these fields
    # were dropped during (de)serialization.
    s.round_number = 5
    return s


def _assert_player_equal(a: PlayerState, b: PlayerState) -> None:
    assert a.doubloons == b.doubloons
    assert a.stored_colonists == b.stored_colonists
    assert a.vp_chips == b.vp_chips
    assert a.roles_taken_this_round == b.roles_taken_this_round
    assert a.goods == b.goods
    assert [(s.tile, s.colonist) for s in a.island] == [
        (s.tile, s.colonist) for s in b.island
    ]
    assert [(s.building, s.colonists) for s in a.city] == [
        (s.building, s.colonists) for s in b.city
    ]


def test_round_trip_lossless():
    s = _make_state()
    r = from_dict(to_dict(s))

    # config
    assert r.config == s.config
    assert r.config.max_rounds == s.config.max_rounds

    # scalars
    assert r.governor == s.governor
    assert r.current_player == s.current_player
    assert r.phase == s.phase
    assert r.colonist_ship == s.colonist_ship
    assert r.colonist_supply == s.colonist_supply
    assert r.quarry_supply == s.quarry_supply
    assert r.vp_chips_remaining == s.vp_chips_remaining
    assert r.end_triggered == s.end_triggered
    assert r.round_number == s.round_number

    # players
    assert len(r.players) == len(s.players)
    for a, b in zip(r.players, s.players):
        _assert_player_equal(a, b)

    # placards
    assert [(p.role, p.doubloons, p.taken_by) for p in r.placards] == [
        (p.role, p.doubloons, p.taken_by) for p in s.placards
    ]

    # ships
    assert [(c.capacity, c.good, c.count) for c in r.cargo_ships] == [
        (c.capacity, c.good, c.count) for c in s.cargo_ships
    ]

    # goods / plantations / supplies
    assert r.trading_house == s.trading_house
    assert r.goods_supply == s.goods_supply
    assert r.plantation_faceup == s.plantation_faceup
    assert r.plantation_facedown == s.plantation_facedown
    assert r.plantation_discard == s.plantation_discard
    assert r.buildings_supply == s.buildings_supply

    # phase_state
    assert r.phase_state == s.phase_state

    # enum types preserved (not bare ints)
    assert isinstance(r.phase, Phase)
    assert isinstance(r.placards[0].role, Role)
    for p in r.players:
        for slot in p.island:
            assert isinstance(slot.tile, TileType)

    # --- RNG round-trip: same next sequence proves state restored ---
    orig_seq = [s.rng.random() for _ in range(20)]
    restored_seq = [r.rng.random() for _ in range(20)]
    assert orig_seq == restored_seq


def test_to_dict_is_json_serializable():
    import json

    s = _make_state()
    # Should not raise: enums-as-ints, rng-as-nested-lists, dict keys as ints.
    json.dumps(to_dict(s))


def test_public_view_exposes_all_vp_and_score_and_hides_facedown():
    from . import scoring

    s = _make_state()
    pv = public_view(s, perspective=0)

    # VP is public: every player's vp_chips is shown (not None), plus a score.
    for i, p in enumerate(s.players):
        assert pv["players"][i]["vp_chips"] == p.vp_chips
        assert pv["players"][i]["vp_chips"] is not None
        assert pv["players"][i]["score"] == scoring.final_score(s, i)

    # facedown exposed as a count only, no tile list
    assert pv["plantation_facedown_count"] == len(s.plantation_facedown)
    assert "plantation_facedown" not in pv

    # face-up plantations still public
    assert pv["plantation_faceup"] == [int(t) for t in s.plantation_faceup]


def test_public_view_god_view_shows_all_vp_but_hides_facedown():
    s = _make_state()
    pv = public_view(s, perspective=None)

    for i, p in enumerate(s.players):
        assert pv["players"][i]["vp_chips"] == p.vp_chips

    assert pv["plantation_facedown_count"] == len(s.plantation_facedown)
    assert "plantation_facedown" not in pv
