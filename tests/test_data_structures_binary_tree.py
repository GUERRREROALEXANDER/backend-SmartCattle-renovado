"""Checks for the herd registry binary search tree.

The ordering rule is the whole structure: smaller tags left, larger right. So the
tests are about what that rule buys (search, sorted walks, pruned ranges) and
about deletion, the one operation that has to rebuild the rule by hand.
"""

import pytest

from data_structures.binary_search_tree_smartcattle import Animal, HerdRegistry, Node

TAGS = [50, 30, 70, 20, 40, 60, 80]


def animal(tag: int) -> Animal:
    return Animal(tag, f"Cow-{tag}", "Brahman", 400.0)


def filled(*tags: int) -> HerdRegistry:
    registry = HerdRegistry()
    for tag in tags:
        assert registry.insert(animal(tag)) is True
    return registry


def tags(animals: list[Animal]) -> list[int]:
    return [item.tag for item in animals]


def respects_the_rule(node: Node | None, low: float = float("-inf"), high: float = float("inf")) -> bool:
    """Every tag lies strictly between the bounds its ancestors set."""
    if node is None:
        return True
    tag = node.animal.tag
    return low < tag < high and respects_the_rule(node.left, low, tag) and respects_the_rule(node.right, tag, high)


def test_an_empty_registry_has_nothing():
    registry = HerdRegistry()
    assert registry.root is None
    assert len(registry) == 0
    assert registry.height() == 0
    assert registry.in_order() == []
    assert registry.by_level() == []
    assert registry.lowest() is None
    assert registry.highest() is None
    assert registry.search(1) is None


def test_insert_places_smaller_tags_left_and_larger_right():
    registry = filled(*TAGS)
    assert registry.by_level() == [[50], [30, 70], [20, 40, 60, 80]]
    assert respects_the_rule(registry.root)
    assert len(registry) == 7


def test_a_tag_cannot_be_registered_twice():
    registry = filled(*TAGS)
    assert registry.insert(Animal(40, "Otra", "Gyr", 300.0)) is False
    assert len(registry) == 7
    found = registry.search(40)
    assert found is not None and found.name == "Cow-40"


def test_search_finds_and_misses():
    registry = filled(*TAGS)
    found = registry.search(60)
    assert found is not None and found.tag == 60
    assert registry.search(65) is None
    assert 80 in registry
    assert 81 not in registry
    assert "80" not in registry


def test_in_order_is_sorted_whatever_the_insertion_order():
    assert tags(filled(*TAGS).in_order()) == [20, 30, 40, 50, 60, 70, 80]
    assert tags(filled(80, 20, 60, 40, 70, 30, 50).in_order()) == [20, 30, 40, 50, 60, 70, 80]


def test_pre_and_post_order():
    registry = filled(*TAGS)
    assert tags(registry.pre_order()) == [50, 30, 20, 40, 70, 60, 80]
    assert tags(registry.post_order()) == [20, 40, 30, 60, 80, 70, 50]


def test_re_inserting_the_pre_order_rebuilds_the_same_tree():
    original = filled(*TAGS)
    copy = filled(*tags(original.pre_order()))
    assert copy.by_level() == original.by_level()


@pytest.mark.parametrize(("low", "high", "expected"), [
    (35, 65, [40, 50, 60]),
    (20, 20, [20]),
    (0, 100, [20, 30, 40, 50, 60, 70, 80]),
    (81, 90, []),
    (41, 49, []),
])
def test_range_returns_the_tags_inside_in_order(low, high, expected):
    assert tags(filled(*TAGS).in_range(low, high)) == expected


def test_lowest_and_highest_are_the_outermost_nodes():
    registry = filled(*TAGS)
    lowest, highest = registry.lowest(), registry.highest()
    assert lowest is not None and lowest.tag == 20
    assert highest is not None and highest.tag == 80


def test_removing_a_leaf():
    registry = filled(*TAGS)
    assert registry.remove(20) is True
    assert registry.by_level() == [[50], [30, 70], [40, 60, 80]]
    assert respects_the_rule(registry.root)


def test_removing_a_node_with_one_child_lifts_the_child():
    registry = filled(*TAGS)
    registry.remove(20)
    assert registry.remove(30) is True
    assert registry.by_level() == [[50], [40, 70], [60, 80]]
    assert respects_the_rule(registry.root)


def test_removing_a_node_with_two_children_uses_the_successor():
    # The root: its successor is 60, the smallest tag on its right.
    registry = filled(*TAGS)
    assert registry.remove(50) is True
    assert registry.by_level() == [[60], [30, 70], [20, 40, 80]]
    assert respects_the_rule(registry.root)
    assert len(registry) == 6


def test_removing_a_missing_tag_reports_failure():
    registry = filled(*TAGS)
    assert registry.remove(99) is False
    assert len(registry) == 7
    assert HerdRegistry().remove(1) is False


@pytest.mark.parametrize("order", [TAGS, list(reversed(TAGS)), [40, 80, 20, 60, 50, 30, 70]])
def test_removing_everything_in_any_order_leaves_an_empty_valid_tree(order):
    registry = filled(*TAGS)
    for removed, tag in enumerate(order, start=1):
        assert registry.remove(tag) is True
        assert respects_the_rule(registry.root)
        assert len(registry) == len(TAGS) - removed
        assert tags(registry.in_order()) == sorted(set(TAGS) - set(order[:removed]))
    assert registry.root is None


def test_height_shows_balanced_versus_chained_shapes():
    # Seven tags in a good order fill three levels; the same tags sorted make a chain of seven.
    assert filled(*TAGS).height() == 3
    chain = filled(*sorted(TAGS))
    assert chain.height() == 7
    assert chain.by_level() == [[20], [30], [40], [50], [60], [70], [80]]
