from __future__ import annotations

from datetime import date

import pytest

from conftest import SHIFT, batch
from press_sequencing.budget import Makeready, TimeBudget
from press_sequencing.config import ConfigError, SequencingConfig
from press_sequencing.eligibility import Condition, EligibilityConstraint
from press_sequencing.model import Press, PressAvailability, ProductClass, ShiftCapacity
from press_sequencing.rules import AlternationRule, GroupingRule, RuleScope
from press_sequencing.sequencer import (
    NO_CAPACITY,
    NO_ELIGIBLE_PRESS,
    TIME_BUDGET,
    cycle_of,
    next_for_press,
    sequence_shift,
)

PRESS_2 = Press("press_2", "Press 2", sheets_per_hour=3000, lanes=("2.1", "2.2"))
PRESS_5 = Press("press_5", "Press 5", sheets_per_hour=3000)

CLASSES = {
    "rounded": ProductClass("rounded", {"corner": "rounded"}),
    "square": ProductClass("square", {"corner": "square"}),
}


def config(**overrides) -> SequencingConfig:
    base = dict(
        classes=CLASSES,
        presses=(PRESS_2, PRESS_5),
        pipeline=(),
        eligibility=(),
        budget=TimeBudget(),
        makeready=Makeready(),
    )
    base.update(overrides)
    return SequencingConfig(**base)


def capacity(*entries, shift_date: date = SHIFT) -> ShiftCapacity:
    return ShiftCapacity(shift_date, tuple(entries))


ONE_PRESS = capacity(PressAvailability("press_2", hours=8))
TWO_PRESSES = capacity(PressAvailability("press_2", 8), PressAvailability("press_5", 8))


# --- cycles -----------------------------------------------------------------

def test_cycle_1_is_due_today_or_earlier():
    assert cycle_of(batch("B-1", ship=SHIFT), SHIFT) == 1
    assert cycle_of(batch("B-2", ship=date(2026, 9, 21)), SHIFT) == 1
    assert cycle_of(batch("B-3", ship=date(2026, 9, 23)), SHIFT) == 2


def test_cycle_1_is_laid_down_before_cycle_2():
    batches = [
        batch("LATER", ship=date(2026, 9, 30)),
        batch("TODAY", ship=SHIFT),
    ]
    plan = sequence_shift(batches, ONE_PRESS, config())
    assert [b.batch_id for b in plan.sequence_for("press_2")] == ["TODAY", "LATER"]


# --- rules are applied ------------------------------------------------------

def test_the_rule_pipeline_orders_each_press_run():
    rule = AlternationRule("corner", "rounded", "square", count=1, scope=RuleScope(lanes=("2.1",)))
    batches = [
        batch("R-1", corner="rounded"),
        batch("R-2", corner="rounded"),
        batch("S-1", corner="square"),
        batch("S-2", corner="square"),
    ]
    plan = sequence_shift(batches, ONE_PRESS, config(pipeline=(rule,)))
    assert [b.batch_id for b in plan.sequence_for("press_2")] == ["R-1", "S-1", "R-2", "S-2"]


def test_a_rule_scoped_to_lanes_leaves_other_presses_alone():
    """Corner alternation applies on lanes 2.1, 2.2 and 3.1. Press 5 has no
    lanes, so its run keeps the order it was assigned in."""
    rule = AlternationRule("corner", "rounded", "square", count=1, scope=RuleScope(lanes=("2.1",)))
    batches = [
        batch("R-1", sheets=3000, corner="rounded"),
        batch("R-2", sheets=3000, corner="rounded"),
        batch("S-1", sheets=3000, corner="square"),
        batch("S-2", sheets=3000, corner="square"),
    ]
    cap = capacity(
        PressAvailability("press_2", hours=0.1), PressAvailability("press_5", hours=8)
    )
    plan = sequence_shift(batches, cap, config(pipeline=(rule,)))
    assert [b.batch_id for b in plan.sequence_for("press_5")] == ["R-1", "R-2", "S-1", "S-2"]


def test_rules_run_in_pipeline_order_each_seeing_the_last_ones_output():
    """Grouping then alternation is not the same as alternation then grouping,
    so pipeline order is configuration, not an implementation detail."""
    group = GroupingRule("group", "size")
    alternate = AlternationRule("corner", "rounded", "square", count=1)
    batches = [
        batch("A-1", corner="rounded", size="big"),
        batch("A-2", corner="square", size="small"),
        batch("A-3", corner="rounded", size="small"),
        batch("A-4", corner="square", size="big"),
    ]
    forward = sequence_shift(batches, ONE_PRESS, config(pipeline=(group, alternate)))
    reverse = sequence_shift(batches, ONE_PRESS, config(pipeline=(alternate, group)))
    assert [b.batch_id for b in forward.sequence_for("press_2")] != [
        b.batch_id for b in reverse.sequence_for("press_2")
    ]


# --- capacity is an input ---------------------------------------------------

def test_a_press_absent_from_capacity_gets_no_work():
    plan = sequence_shift([batch("B-1")], ONE_PRESS, config())
    assert "press_5" not in plan.runs


def test_an_unstaffed_press_gets_no_work():
    cap = capacity(PressAvailability("press_2", 8), PressAvailability("press_5", 8, operators=0))
    plan = sequence_shift([batch("B-1")], cap, config())
    assert plan.sequence_for("press_5") == []
    assert plan.sequence_for("press_2") == [batch("B-1")]


def test_everything_strands_when_no_press_is_staffed():
    cap = capacity(PressAvailability("press_2", 8, operators=0))
    plan = sequence_shift([batch("B-1")], cap, config())
    assert plan.placed_count == 0
    assert [s.reason for s in plan.stranded] == [NO_CAPACITY]


def test_capacity_naming_an_unknown_press_is_a_config_error():
    cap = capacity(PressAvailability("press_99", 8))
    with pytest.raises(ConfigError, match="press_99"):
        sequence_shift([batch("B-1")], cap, config())


def test_a_shorter_shift_places_less_work():
    batches = [batch(f"B-{i}", sheets=3000) for i in range(8)]
    long_shift = sequence_shift(batches, capacity(PressAvailability("press_2", 8)), config())
    short_shift = sequence_shift(batches, capacity(PressAvailability("press_2", 2)), config())
    assert short_shift.placed_count < long_shift.placed_count


# --- eligibility ------------------------------------------------------------

def test_an_ineligible_batch_goes_to_another_press():
    # Illustrative constraint, not a live one - see config/eligibility.yml.
    constraint = EligibilityConstraint(
        "holiday_not_5", Condition({"product": "holiday_card"}), exclude_presses=("press_5",)
    )
    plan = sequence_shift(
        [batch("B-1", product="holiday_card")], TWO_PRESSES, config(eligibility=(constraint,))
    )
    assert plan.sequence_for("press_5") == []
    assert [b.batch_id for b in plan.sequence_for("press_2")] == ["B-1"]


def test_a_batch_no_press_accepts_is_stranded_with_the_constraint_named():
    constraint = EligibilityConstraint(
        "nowhere", Condition({"product": "holiday_card"}), allow_only_presses=("press_5",)
    )
    plan = sequence_shift(
        [batch("B-1", product="holiday_card")], ONE_PRESS, config(eligibility=(constraint,))
    )
    assert plan.placed_count == 0
    assert plan.stranded[0].reason == NO_ELIGIBLE_PRESS
    assert "nowhere" in plan.stranded[0].detail


# --- overflow ---------------------------------------------------------------

def test_overflow_is_stranded_rather_than_silently_dropped():
    batches = [batch(f"B-{i}", sheets=3000) for i in range(10)]
    plan = sequence_shift(batches, capacity(PressAvailability("press_2", 4)), config())
    assert plan.placed_count + len(plan.stranded) == len(batches)
    assert all(s.reason in (NO_CAPACITY, TIME_BUDGET) for s in plan.stranded)


def test_overflow_reaches_not_yet_due_work_before_due_work():
    due = [batch(f"DUE-{i}", sheets=3000, ship=SHIFT) for i in range(4)]
    later = [batch(f"LATER-{i}", sheets=3000, ship=date(2026, 9, 30)) for i in range(4)]
    plan = sequence_shift(due + later, capacity(PressAvailability("press_2", 4)), config())

    stranded_ids = {s.batch.batch_id for s in plan.stranded}
    assert all(i.startswith("LATER") for i in stranded_ids)


def test_makeready_can_truncate_a_sequence_that_fitted_before_sequencing():
    """Phase 1 reserves worst-case makeready, so this should be rare - but when
    it happens the batch is reported, not dropped."""
    makeready = Makeready(changeover_minutes=30, changeover_attributes=("stock",))
    batches = [batch(f"B-{i}", sheets=1500, stock=f"s{i}") for i in range(10)]
    plan = sequence_shift(
        batches, capacity(PressAvailability("press_2", 2)), config(makeready=makeready)
    )
    assert plan.placed_count + len(plan.stranded) == len(batches)


def test_every_batch_is_either_placed_once_or_stranded_once():
    batches = [batch(f"B-{i}", sheets=2000, ship=SHIFT) for i in range(12)]
    plan = sequence_shift(batches, TWO_PRESSES, config())
    placed = [p.batch.batch_id for run in plan.runs.values() for p in run.placed]
    stranded = [s.batch.batch_id for s in plan.stranded]

    assert len(placed) == len(set(placed))
    assert sorted(placed + stranded) == sorted(b.batch_id for b in batches)


def test_positions_are_contiguous_within_a_press_run():
    batches = [batch(f"B-{i}") for i in range(5)]
    plan = sequence_shift(batches, ONE_PRESS, config())
    assert [p.position for p in plan.runs["press_2"].placed] == [0, 1, 2, 3, 4]


def test_an_empty_batch_list_produces_an_empty_plan():
    plan = sequence_shift([], TWO_PRESSES, config())
    assert plan.placed_count == 0
    assert plan.stranded == []


# --- dispatch ---------------------------------------------------------------

def test_next_for_press_returns_the_head_of_the_sequence():
    batches = [batch("LATER", ship=date(2026, 9, 30)), batch("TODAY", ship=SHIFT)]
    assert next_for_press("press_2", batches, ONE_PRESS, config()).batch_id == "TODAY"


def test_next_for_press_skips_what_has_already_printed():
    batches = [batch("B-1", ship=SHIFT), batch("B-2", ship=date(2026, 9, 23))]
    nxt = next_for_press("press_2", batches, ONE_PRESS, config(), printed={"B-1"})
    assert nxt.batch_id == "B-2"


def test_next_for_press_returns_none_when_nothing_is_left():
    assert next_for_press("press_2", [], ONE_PRESS, config()) is None


def test_next_for_press_recomputes_rather_than_replaying_a_stale_plan():
    """Dispatch self-heals: work added mid-shift is considered immediately."""
    urgent = batch("URGENT", ship=date(2026, 9, 1))
    routine = batch("ROUTINE", ship=SHIFT)

    assert next_for_press("press_2", [routine], ONE_PRESS, config()).batch_id == "ROUTINE"
    assert next_for_press("press_2", [routine, urgent], ONE_PRESS, config()).batch_id == "URGENT"


def test_next_for_press_returns_none_for_a_press_not_on_shift():
    assert next_for_press("press_5", [batch("B-1")], ONE_PRESS, config()) is None
