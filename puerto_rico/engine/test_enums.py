"""Unit tests for the core engine enums."""

from puerto_rico.engine.enums import (
    BuildingId,
    DecisionType,
    Good,
    Phase,
    Role,
    TileType,
)

ALL_ENUMS = [Good, Role, TileType, Phase, DecisionType, BuildingId]


def test_members_hashable():
    """Every enum member must be usable as a dict key / set member."""
    for enum_cls in ALL_ENUMS:
        members = set(enum_cls)
        assert len(members) == len(list(enum_cls))
        # also usable as dict keys
        mapping = {member: i for i, member in enumerate(enum_cls)}
        assert len(mapping) == len(list(enum_cls))


def test_unique_values_within_each_enum():
    """Within each enum, all integer values are unique."""
    for enum_cls in ALL_ENUMS:
        values = [member.value for member in enum_cls]
        assert len(values) == len(set(values)), f"duplicate values in {enum_cls.__name__}"


def test_good_members():
    assert [(g.name, g.value) for g in Good] == [
        ("CORN", 0),
        ("INDIGO", 1),
        ("SUGAR", 2),
        ("TOBACCO", 3),
        ("COFFEE", 4),
    ]
    assert len(Good) == 5


def test_role_members():
    assert [(r.name, r.value) for r in Role] == [
        ("SETTLER", 0),
        ("MAYOR", 1),
        ("BUILDER", 2),
        ("CRAFTSMAN", 3),
        ("TRADER", 4),
        ("CAPTAIN", 5),
        ("PROSPECTOR", 6),
    ]
    assert len(Role) == 7


def test_tiletype_members():
    assert [(t.name, t.value) for t in TileType] == [
        ("EMPTY", 0),
        ("QUARRY", 1),
        ("CORN", 2),
        ("INDIGO", 3),
        ("SUGAR", 4),
        ("TOBACCO", 5),
        ("COFFEE", 6),
    ]
    assert len(TileType) == 7


def test_phase_members():
    assert [(p.name, p.value) for p in Phase] == [
        ("ROLE_SELECTION", 0),
        ("SETTLER", 1),
        ("MAYOR", 2),
        ("BUILDER", 3),
        ("CRAFTSMAN", 4),
        ("TRADER", 5),
        ("CAPTAIN", 6),
        ("GAME_OVER", 7),
    ]
    assert len(Phase) == 8


def test_decisiontype_members():
    assert [(d.name, d.value) for d in DecisionType] == [
        ("SELECT_ROLE", 0),
        ("TAKE_TILE", 1),
        ("PLACE_COLONIST", 2),
        ("BUILD", 3),
        ("SELL", 4),
        ("LOAD", 5),
        ("PASS", 6),
        ("CHOOSE", 7),
    ]
    assert len(DecisionType) == 8


def test_buildingid_has_large_cont_sentinel():
    assert hasattr(BuildingId, "LARGE_CONT")
    assert isinstance(BuildingId.LARGE_CONT, BuildingId)


def test_intenum_values_usable_as_indices():
    """IntEnum members compare equal to their ints and index sequences."""
    arr = [10, 11, 12, 13, 14]
    assert arr[Good.SUGAR] == 12
    assert Good.SUGAR == 2
