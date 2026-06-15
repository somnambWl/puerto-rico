"""Full-catalog integration test for end-game scoring (buildings-task-07).

Constructs deterministic player fixtures by DIRECT state construction (clearer
and more deterministic than playing a full game), gives a player a known set of
buildings + island/colonist/vp-chip configuration, and asserts
``scoring.final_score`` equals a HAND-COMPUTED total whose derivation is
documented inline against ``design/03-buildings-reference.md``.

Scoring model (scoring.py):

    final_score = vp_chips
                + printed VP of every owned building (each large counted once)
                + SCORE_END large-building extras (occupied only)

A single 12-slot city cannot hold all 23 buildings, so we use several focused
fixtures:

- ``test_five_large_plus_production_fixture`` — the 5 large buildings (10 slots)
  + 2 production buildings (2 slots), all occupied: exercises EVERY SCORE_END
  handler at once and asserts the exact total.
- ``test_unoccupied_large_scores_base_only`` — every large building UNoccupied:
  each contributes only its printed 4 VP, no extra.
- ``test_guild_hall_production_counting`` — guild-hall extra over a varied set of
  small/large production buildings.
- ``test_catalog_completeness`` — CATALOG has exactly 23 buildings and every
  SCORE_END handler is registered/reachable.
"""

from __future__ import annotations

from puerto_rico.engine import scoring
from puerto_rico.engine.buildings import CATALOG, HANDLERS, Timing
from puerto_rico.engine.enums import BuildingId, TileType
from puerto_rico.engine.game import Game
from puerto_rico.engine.state import GameConfig


def _new_state(num_players: int = 4, seed: int = 0):
    """A fully-built GameState (we only mutate one player's fixture fields)."""
    return Game(GameConfig(num_players=num_players, seed=seed)).state


def _place_building(player, bid: BuildingId, *, occupied: bool) -> None:
    """Place ``bid`` into the lowest empty city slot(s); large -> 2 slots.

    A large building occupies two adjacent slots: the real id in the first and
    ``LARGE_CONT`` in the second. ``occupied`` puts 1 colonist on the real slot.
    """
    spec = CATALOG[bid]
    for i in range(len(player.city) - (1 if spec.is_large else 0)):
        if player.city[i].building is None and (
            not spec.is_large or player.city[i + 1].building is None
        ):
            player.city[i].building = bid
            player.city[i].colonists = 1 if occupied else 0
            if spec.is_large:
                player.city[i + 1].building = BuildingId.LARGE_CONT
            return
    raise AssertionError(f"no room in city for {bid!r}")


def _clear_player(player) -> None:
    """Reset a player to an empty island/city with 0 chips/goods/colonists."""
    for slot in player.city:
        slot.building = None
        slot.colonists = 0
    for slot in player.island:
        slot.tile = TileType.EMPTY
        slot.colonist = False
    player.goods = [0, 0, 0, 0, 0]
    player.stored_colonists = 0
    player.vp_chips = 0


# --------------------------------------------------------------------------- #
# Main fixture: 5 large (occupied) + 2 production (occupied)                   #
# --------------------------------------------------------------------------- #


def test_five_large_plus_production_fixture():
    """All five SCORE_END handlers exercised at once; exact hand-computed total.

    City (12 slots, all occupied):
      - GUILD_HALL, RESIDENCE, FORTRESS, CUSTOMS_HOUSE, CITY_HALL  (5 large = 10 slots)
      - SMALL_INDIGO (production, vp 1), INDIGO_PLANT (production, vp 2)  (2 slots)

    Fixture knobs:
      - vp_chips = 8
      - island: 10 tiles placed (filled_island_spaces = 10), 4 of them manned
      - city colonists: 7 (each of the 7 real buildings manned with 1)
      - stored_colonists = 2

    Hand computation (design/03):

      BASE PRINTED VP (scoring sums catalog .vp for every owned real building):
        production: SMALL_INDIGO 1 + INDIGO_PLANT 2          = 3
        large beige: 5 x 4                                    = 20
        base printed                                          = 23

      vp_chips                                                = 8

      SCORE_END extras (each large is occupied, so all apply):
        guild_hall : +1 per small prod owned + +2 per large prod owned
                     small prod owned = 1 (SMALL_INDIGO)
                     large prod owned = 1 (INDIGO_PLANT)
                     = 1*1 + 1*2                              = 3
        residence  : filled island spaces = 10 -> +5          = 5
        fortress   : total_colonists // 3
                     island manned 4 + city 7 + stored 2 = 13
                     13 // 3                                  = 4
        customs    : vp_chips // 4 = 8 // 4                   = 2
        city_hall  : +1 per beige building owned (counts itself)
                     beige owned = 5 large buildings          = 5
        SCORE_END total                                       = 19

      FINAL = base 23 + chips 8 + score_end 19                = 50
    """
    st = _new_state()
    p = st.players[0]
    _clear_player(p)

    large = [
        BuildingId.GUILD_HALL,
        BuildingId.RESIDENCE,
        BuildingId.FORTRESS,
        BuildingId.CUSTOMS_HOUSE,
        BuildingId.CITY_HALL,
    ]
    production = [BuildingId.SMALL_INDIGO, BuildingId.INDIGO_PLANT]
    for bid in large + production:
        _place_building(p, bid, occupied=True)

    # Island: 10 tiles placed; 4 manned. (Tile kind is irrelevant to scoring.)
    for i in range(10):
        p.island[i].tile = TileType.CORN
    for i in range(4):
        p.island[i].colonist = True

    p.stored_colonists = 2
    p.vp_chips = 8

    # Sanity on the fixture's intermediate quantities.
    assert p.filled_island_spaces() == 10
    assert p.total_colonists() == 4 + 7 + 2  # island + city + stored == 13

    assert scoring.final_score(st, 0) == 50


# --------------------------------------------------------------------------- #
# Unoccupied large buildings: printed base only, no extra                      #
# --------------------------------------------------------------------------- #


def test_unoccupied_large_scores_base_only():
    """Five UNoccupied large buildings score only printed 4 VP each (no extra).

    No production buildings, vp_chips = 0, island holding tiles (so residence
    WOULD pay if occupied). Because every large is unmanned, each SCORE_END
    handler gates itself off and contributes nothing.

      base printed = 5 x 4 = 20 ; chips = 0 ; score_end extras = 0
      FINAL = 20
    """
    st = _new_state()
    p = st.players[0]
    _clear_player(p)

    for bid in (
        BuildingId.GUILD_HALL,
        BuildingId.RESIDENCE,
        BuildingId.FORTRESS,
        BuildingId.CUSTOMS_HOUSE,
        BuildingId.CITY_HALL,
    ):
        _place_building(p, bid, occupied=False)

    # Fill island + give chips: these WOULD trigger extras if buildings were
    # occupied, proving the per-handler occupancy gate.
    for i in range(12):
        p.island[i].tile = TileType.CORN
    p.vp_chips = 20

    # score_end bonus must be exactly 0 despite the residence/customs setup.
    ctx_bonus = scoring._score_end_bonus(st, 0)
    assert ctx_bonus == 0
    assert scoring.final_score(st, 0) == 20 + 20  # printed 20 + chips 20


# --------------------------------------------------------------------------- #
# Guild hall production-counting (targeted)                                    #
# --------------------------------------------------------------------------- #


def test_guild_hall_production_counting():
    """Guild hall extra over a mix of small/large production buildings.

    City: GUILD_HALL (occupied) + SMALL_INDIGO + SMALL_SUGAR (2 small prod)
          + SUGAR_MILL + TOBACCO_STORAGE (2 large prod).  (2 large slots + 5 = 7)

      base printed VP (CATALOG .vp values):
        guild hall                                           = 4
        SMALL_INDIGO 1 + SMALL_SUGAR 1                        = 2
        SUGAR_MILL 2 + TOBACCO_STORAGE 3                      = 5
        base printed                                          = 11
      chips = 0
      guild_hall extra: small prod 2 -> +2 ; large prod 2 -> +4 = 6
      FINAL = 11 + 6                                          = 17
    """
    st = _new_state()
    p = st.players[0]
    _clear_player(p)

    _place_building(p, BuildingId.GUILD_HALL, occupied=True)
    for bid in (
        BuildingId.SMALL_INDIGO,
        BuildingId.SMALL_SUGAR,
        BuildingId.SUGAR_MILL,
        BuildingId.TOBACCO_STORAGE,
    ):
        _place_building(p, bid, occupied=True)

    assert scoring.final_score(st, 0) == 17


# --------------------------------------------------------------------------- #
# Targeted residence / fortress / customs boundary checks                      #
# --------------------------------------------------------------------------- #


def test_residence_fortress_customs_boundaries():
    """Pin the bracket formulas at non-default points.

    City: RESIDENCE + FORTRESS + CUSTOMS_HOUSE, all occupied (6 slots).

      base printed = 3 x 4 = 12
      island: 11 tiles -> residence +6
      total colonists: island manned 0 + city 3 + stored 7 = 10 -> fortress +3
      vp_chips = 15 -> customs +3  (and chips themselves add 15)
      FINAL = 12 + 15 + (6 + 3 + 3) = 39
    """
    st = _new_state()
    p = st.players[0]
    _clear_player(p)

    for bid in (
        BuildingId.RESIDENCE,
        BuildingId.FORTRESS,
        BuildingId.CUSTOMS_HOUSE,
    ):
        _place_building(p, bid, occupied=True)

    for i in range(11):
        p.island[i].tile = TileType.CORN  # 11 filled -> residence +6
    p.stored_colonists = 7  # city 3 + stored 7 = 10 -> fortress +3
    p.vp_chips = 15  # customs +3

    assert p.filled_island_spaces() == 11
    assert p.total_colonists() == 10
    assert scoring.final_score(st, 0) == 39


# --------------------------------------------------------------------------- #
# Catalog completeness + handler reachability                                  #
# --------------------------------------------------------------------------- #


def test_catalog_completeness():
    """CATALOG has exactly 23 real buildings; LARGE_CONT excluded."""
    assert len(CATALOG) == 23
    assert BuildingId.LARGE_CONT not in CATALOG

    # 6 production + 12 small beige + 5 large beige.
    production = [b for b in CATALOG.values() if b.is_production]
    large = [b for b in CATALOG.values() if b.is_large]
    small_beige = [
        b for b in CATALOG.values() if not b.is_production and not b.is_large
    ]
    assert len(production) == 6
    assert len(large) == 5
    assert len(small_beige) == 12

    # Base printed VP breakdown from design/03 (task line 43).
    assert sum(b.vp for b in production) == 12
    assert sum(b.vp for b in small_beige) == 24
    assert sum(b.vp for b in large) == 20


def test_every_score_end_handler_registered_and_reachable():
    """Each large building declares SCORE_END and has a registered handler that
    fires when occupied (extra) and stays silent when unoccupied."""
    large_ids = [
        BuildingId.GUILD_HALL,
        BuildingId.RESIDENCE,
        BuildingId.FORTRESS,
        BuildingId.CUSTOMS_HOUSE,
        BuildingId.CITY_HALL,
    ]
    for bid in large_ids:
        assert Timing.SCORE_END in CATALOG[bid].timings
        assert (bid, Timing.SCORE_END) in HANDLERS

    # Each large building, in isolation, contributes a positive extra when
    # occupied under a setup that makes its formula non-zero -> handler reached.
    expected_extra = {
        BuildingId.GUILD_HALL: 2,  # 2 small production owned -> +2
        BuildingId.RESIDENCE: 4,  # <=9 filled island spaces -> +4
        BuildingId.FORTRESS: 1,  # 3 colonists -> +1
        BuildingId.CUSTOMS_HOUSE: 1,  # 4 vp chips -> +1
        BuildingId.CITY_HALL: 1,  # itself, 1 beige owned -> +1
    }
    for bid, want in expected_extra.items():
        st = _new_state()
        p = st.players[0]
        _clear_player(p)
        _place_building(p, bid, occupied=True)

        if bid == BuildingId.GUILD_HALL:
            _place_building(p, BuildingId.SMALL_INDIGO, occupied=False)
            _place_building(p, BuildingId.SMALL_SUGAR, occupied=False)
        elif bid == BuildingId.RESIDENCE:
            for i in range(3):
                p.island[i].tile = TileType.CORN
        elif bid == BuildingId.FORTRESS:
            p.stored_colonists = 2  # +1 city colonist = 3 total
        elif bid == BuildingId.CUSTOMS_HOUSE:
            p.vp_chips = 4

        assert scoring._score_end_bonus(st, 0) == want, bid

        # And the extra disappears when the SAME building is unoccupied.
        p.city[p.building_slot(bid)].colonists = 0
        assert scoring._score_end_bonus(st, 0) == 0, bid
