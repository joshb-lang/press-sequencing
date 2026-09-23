from __future__ import annotations

import pytest

from conftest import batch
from press_sequencing.model import Press
from press_sequencing.rules import AlternationRule, GroupingRule, OrderingRule, RuleScope


def ids(batches):
    return [b.batch_id for b in batches]


# --- ordering ---------------------------------------------------------------

def test_ordering_runs_classes_in_the_order_named(classes):
    rule = OrderingRule("r", ("square", "rounded"))
    batches = [
        batch("B-1", corner="rounded"),
        batch("B-2", corner="square"),
        batch("B-3", corner="rounded"),
        batch("B-4", corner="square"),
    ]
    assert ids(rule.apply(batches, classes)) == ["B-2", "B-4", "B-1", "B-3"]


def test_ordering_leaves_unnamed_classes_at_the_end_in_input_order(classes):
    rule = OrderingRule("r", ("gloss",))
    batches = [
        batch("B-1", lamination="matte"),
        batch("B-2", lamination="gloss"),
        batch("B-3", lamination="none"),
    ]
    assert ids(rule.apply(batches, classes)) == ["B-2", "B-1", "B-3"]


# --- grouping ---------------------------------------------------------------

def test_grouping_puts_like_with_like(classes):
    rule = GroupingRule("r", "size")
    batches = [
        batch("B-1", size="A"),
        batch("B-2", size="B"),
        batch("B-3", size="A"),
        batch("B-4", size="B"),
    ]
    assert ids(rule.apply(batches, classes)) == ["B-1", "B-3", "B-2", "B-4"]


def test_grouping_keeps_groups_in_first_appearance_order(classes):
    """Grouping must not silently reprioritise: the group whose first member
    came first still goes first."""
    rule = GroupingRule("r", "lamination")
    batches = [
        batch("B-1", lamination="matte"),
        batch("B-2", lamination="gloss"),
        batch("B-3", lamination="matte"),
    ]
    assert ids(rule.apply(batches, classes)) == ["B-1", "B-3", "B-2"]


def test_grouping_treats_a_missing_attribute_as_its_own_group(classes):
    rule = GroupingRule("r", "size")
    batches = [batch("B-1", size="A"), batch("B-2"), batch("B-3", size="A")]
    assert ids(rule.apply(batches, classes)) == ["B-1", "B-3", "B-2"]


# --- alternation ------------------------------------------------------------

def test_alternation_by_batch_count_is_four_and_four(classes):
    """Corner alternation as built in July: four rounded, four square."""
    rule = AlternationRule("r", "rounded", "square", count=4, unit="batches")
    batches = [batch(f"R-{i}", corner="rounded") for i in range(5)] + [
        batch(f"S-{i}", corner="square") for i in range(5)
    ]
    assert ids(rule.apply(batches, classes)) == [
        "R-0", "R-1", "R-2", "R-3",
        "S-0", "S-1", "S-2", "S-3",
        "R-4", "S-4",
    ]


def test_alternation_by_sheets_lets_small_batches_share_a_slot(classes):
    """The sheet budget: a slot is a sheet count, so several small batches fill
    one slot instead of each consuming a whole slot. 205 is the lane 5.1 cutter
    lift cap."""
    rule = AlternationRule("r", "rounded", "square", count=205, unit="sheets")
    batches = [
        batch("R-1", sheets=100, corner="rounded"),
        batch("R-2", sheets=100, corner="rounded"),
        batch("R-3", sheets=100, corner="rounded"),
        batch("S-1", sheets=100, corner="square"),
        batch("S-2", sheets=100, corner="square"),
        batch("S-3", sheets=100, corner="square"),
    ]
    assert ids(rule.apply(batches, classes)) == ["R-1", "R-2", "S-1", "S-2", "R-3", "S-3"]


def test_a_51_sheet_batch_pulls_three_more_into_a_204_sheet_block(classes):
    """The lane 5.1 worked example: under a 205-sheet cap, four 51-sheet
    batches make a 204-sheet lift and the fifth starts the next one. This is
    the case that settles fill-up-to over fill-until-reached - at 204 a fifth
    batch would overshoot, so the block closes."""
    rule = AlternationRule("r", "rounded", "square", count=205, unit="sheets")
    rounded = [batch(f"R-{i}", sheets=51, corner="rounded") for i in range(5)]
    square = [batch("S-1", sheets=51, corner="square")]

    result = ids(rule.apply(rounded + square, classes))
    assert result[:4] == ["R-0", "R-1", "R-2", "R-3"]
    assert result[4] == "S-1"


def test_alternation_by_sheets_switches_after_one_oversized_batch(classes):
    rule = AlternationRule("r", "rounded", "square", count=205, unit="sheets")
    batches = [
        batch("R-1", sheets=5000, corner="rounded"),
        batch("R-2", sheets=50, corner="rounded"),
        batch("S-1", sheets=50, corner="square"),
    ]
    assert ids(rule.apply(batches, classes)) == ["R-1", "S-1", "R-2"]


def test_alternation_continues_rather_than_stalling_when_one_side_runs_out(classes):
    rule = AlternationRule("r", "rounded", "square", count=2, unit="batches")
    batches = [batch(f"R-{i}", corner="rounded") for i in range(5)] + [
        batch("S-1", corner="square")
    ]
    assert ids(rule.apply(batches, classes)) == ["R-0", "R-1", "S-1", "R-2", "R-3", "R-4"]


def test_alternation_passes_other_classes_through_without_dropping_them(classes):
    rule = AlternationRule("r", "rounded", "square", count=1, unit="batches")
    batches = [
        batch("B-1", corner="rounded"),
        batch("B-2", corner="die-cut"),
        batch("B-3", corner="square"),
    ]
    result = rule.apply(batches, classes)
    assert ids(result) == ["B-1", "B-3", "B-2"]
    assert len(result) == len(batches)


def test_alternation_starts_on_the_side_that_has_work(classes):
    rule = AlternationRule("r", "rounded", "square", count=2, unit="batches")
    batches = [batch("S-1", corner="square"), batch("S-2", corner="square")]
    assert ids(rule.apply(batches, classes)) == ["S-1", "S-2"]


def test_alternation_rejects_an_unknown_unit():
    with pytest.raises(ValueError, match="unit"):
        AlternationRule("r", "a", "b", count=4, unit="metres")


def test_alternation_rejects_a_non_positive_count():
    with pytest.raises(ValueError, match="count"):
        AlternationRule("r", "a", "b", count=0)


# --- rules are total functions ---------------------------------------------

@pytest.mark.parametrize(
    "rule",
    [
        OrderingRule("r", ("rounded",)),
        GroupingRule("r", "corner"),
        AlternationRule("r", "rounded", "square", count=3),
    ],
)
def test_rules_never_drop_or_duplicate_a_batch(rule, classes):
    batches = [
        batch("B-1", corner="rounded"),
        batch("B-2", corner="square"),
        batch("B-3", corner="die-cut"),
        batch("B-4", corner="rounded"),
    ]
    result = rule.apply(batches, classes)
    assert sorted(ids(result)) == ["B-1", "B-2", "B-3", "B-4"]


@pytest.mark.parametrize(
    "rule",
    [
        OrderingRule("r", ("rounded",)),
        GroupingRule("r", "corner"),
        AlternationRule("r", "rounded", "square", count=3),
    ],
)
def test_rules_handle_an_empty_list(rule, classes):
    assert rule.apply([], classes) == []


# --- scope ------------------------------------------------------------------

def test_scope_matches_a_press_by_lane(press):
    assert RuleScope(lanes=("2.1",)).applies_to(press)
    assert RuleScope(lanes=("3.1",)).applies_to(press) is False


def test_scope_matches_a_press_by_id(press):
    assert RuleScope(presses=("press_2",)).applies_to(press)
    assert RuleScope(presses=("press_5",)).applies_to(press) is False


def test_empty_scope_applies_everywhere(press):
    assert RuleScope().applies_to(press)
    assert RuleScope().applies_to(Press("ricoh", "Ricoh", 1200))


def test_scope_requires_both_press_and_lane_to_match_when_both_given(press):
    assert RuleScope(presses=("press_2",), lanes=("2.1",)).applies_to(press)
    assert RuleScope(presses=("press_5",), lanes=("2.1",)).applies_to(press) is False
