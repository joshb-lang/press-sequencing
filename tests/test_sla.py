from __future__ import annotations

from datetime import date

from conftest import SHIFT, batch
from press_sequencing.budget import Makeready, TimeBudget
from press_sequencing.config import SequencingConfig
from press_sequencing.model import Press, PressAvailability, ShiftCapacity
from press_sequencing.sequencer import sequence_shift
from press_sequencing.sla import report

PRESS_2 = Press("press_2", "Press 2", sheets_per_hour=3000)
CONFIG = SequencingConfig(
    classes={}, presses=(PRESS_2,), pipeline=(), eligibility=(),
    budget=TimeBudget(), makeready=Makeready(),
)


def cap(hours: float) -> ShiftCapacity:
    return ShiftCapacity(SHIFT, (PressAvailability("press_2", hours),))


def test_a_clean_plan_says_so():
    plan = sequence_shift([batch("B-1", sheets=300)], cap(8), CONFIG)
    sla = report(plan)
    assert sla.is_clean
    assert "Nothing stranded" in sla.headline()


def test_stranded_due_work_is_stated_up_front():
    """A capacity-first plan that hides what it stranded makes SLA worse while
    looking more organised, so the count of due work left behind is the
    headline."""
    batches = [batch(f"B-{i}", sheets=3000, ship=SHIFT) for i in range(10)]
    sla = report(sequence_shift(batches, cap(2), CONFIG))

    assert not sla.is_clean
    assert sla.headline().startswith("This plan leaves ")
    assert f"{len(sla.due_stranded)} batches" in sla.headline()
    assert "2026-09-22 or earlier unscheduled" in sla.headline()


def test_due_and_not_yet_due_stranded_work_are_counted_separately():
    batches = [
        *[batch(f"DUE-{i}", sheets=3000, ship=date(2026, 9, 20)) for i in range(3)],
        *[batch(f"LATER-{i}", sheets=3000, ship=date(2026, 9, 30)) for i in range(3)],
    ]
    sla = report(sequence_shift(batches, cap(1), CONFIG))

    assert {s.batch.batch_id for s in sla.due_stranded} <= {f"DUE-{i}" for i in range(3)}
    assert {s.batch.batch_id for s in sla.other_stranded} <= {f"LATER-{i}" for i in range(3)}
    assert len(sla.due_stranded) + len(sla.other_stranded) == len(
        sequence_shift(batches, cap(1), CONFIG).stranded
    )


def test_stranding_only_future_work_still_reads_as_clean_on_sla():
    batches = [
        batch("TODAY", sheets=1500, ship=SHIFT),
        *[batch(f"LATER-{i}", sheets=3000, ship=date(2026, 9, 30)) for i in range(5)],
    ]
    sla = report(sequence_shift(batches, cap(1), CONFIG))
    assert sla.is_clean
    assert "not-yet-due" in sla.headline()


def test_every_stranded_batch_appears_in_the_lines():
    batches = [batch(f"B-{i}", sheets=3000, ship=SHIFT) for i in range(6)]
    plan = sequence_shift(batches, cap(1), CONFIG)
    text = "\n".join(report(plan).lines())

    for s in plan.stranded:
        assert s.batch.batch_id in text
        assert s.reason in text


def test_due_lines_are_marked_so_they_read_differently():
    batches = [batch(f"B-{i}", sheets=3000, ship=SHIFT) for i in range(6)]
    lines = report(sequence_shift(batches, cap(1), CONFIG)).lines()
    assert any(line.strip().startswith("DUE") for line in lines[1:])
