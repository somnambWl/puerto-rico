"""Tests for the flat, immutable, hashable ``Action`` protocol."""

import dataclasses

import pytest

from puerto_rico.engine.actions import Action
from puerto_rico.engine.enums import BuildingId, DecisionType, Good, Role, TileType


def test_action_is_frozen():
    """Assigning to a field raises FrozenInstanceError."""
    a = Action(DecisionType.PASS)
    with pytest.raises(dataclasses.FrozenInstanceError):
        a.type = DecisionType.BUILD  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        a.role = Role.MAYOR  # type: ignore[misc]


def test_action_is_hashable():
    """Actions can be hashed and used as set members / dict keys."""
    a = Action.select_role(Role.SETTLER)
    assert isinstance(hash(a), int)

    s = {a, Action.passing()}
    assert a in s

    d = {a: "settler"}
    assert d[Action.select_role(Role.SETTLER)] == "settler"


def test_equality_by_value():
    """Two actions with identical fields are equal and hash equal."""
    a = Action(DecisionType.LOAD, good=Good.CORN, target=1)
    b = Action(DecisionType.LOAD, good=Good.CORN, target=1)
    assert a == b
    assert hash(a) == hash(b)

    # Differing in any field makes them unequal.
    assert a != Action(DecisionType.LOAD, good=Good.CORN, target=2)
    assert a != Action(DecisionType.LOAD, good=Good.INDIGO, target=1)
    assert a != Action(DecisionType.SELL, good=Good.CORN)


def test_distinct_actions_have_distinct_identity():
    """A set of varied distinct actions retains every member (stable ints)."""
    actions = [
        Action.select_role(Role.SETTLER),
        Action.select_role(Role.MAYOR),
        Action.take_tile(TileType.CORN),
        Action.take_tile(TileType.QUARRY),
        Action.place_colonist(0),
        Action.place_colonist(3),
        Action.build(BuildingId.SMALL_MARKET),
        Action.build(BuildingId.SMALL_INDIGO),
        Action.sell(Good.COFFEE),
        Action.load(Good.SUGAR, target=0),
        Action.load(Good.SUGAR, target=1),
        Action.choose(0),
        Action.choose(1),
        Action.passing(),
    ]
    # No accidental collisions: each distinct value survives the set.
    assert len(set(actions)) == len(actions)
    # Distinct hashes (no required but expected for these varied values).
    assert len({hash(a) for a in actions}) == len(actions)
    # Stable Action -> int mapping via enumerate.
    mapping = {a: i for i, a in enumerate(actions)}
    assert len(mapping) == len(actions)


def test_convenience_constructors_set_only_relevant_fields():
    """Each constructor sets its decision's field and leaves others None."""
    role = Action.select_role(Role.CAPTAIN)
    assert role == Action(DecisionType.SELECT_ROLE, role=Role.CAPTAIN)
    assert role.tile is None and role.target is None and role.good is None

    build = Action.build(BuildingId.SMALL_MARKET)
    assert build == Action(DecisionType.BUILD, building=BuildingId.SMALL_MARKET)

    load = Action.load(Good.TOBACCO, target=2)
    assert load == Action(DecisionType.LOAD, good=Good.TOBACCO, target=2)

    pass_ = Action.passing()
    assert pass_ == Action(DecisionType.PASS)
    assert pass_.role is None and pass_.good is None and pass_.choice is None
