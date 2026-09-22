"""SLA argue-back.

A capacity-first plan that hides what it stranded will make SLA worse while
looking more organised. So the plan is required to state what it left behind:
"this plan leaves 14 batches shipping today unscheduled" is the output that
matters, not the tidy sequence above it.
"""

from __future__ import annotations

from dataclasses import dataclass

from .sequencer import ShiftPlan, Stranded


@dataclass(frozen=True)
class SLAReport:
    shift_date: object
    due_stranded: tuple[Stranded, ...]
    other_stranded: tuple[Stranded, ...]
    placed: int

    @property
    def is_clean(self) -> bool:
        return not self.due_stranded

    def headline(self) -> str:
        if self.is_clean and not self.other_stranded:
            return f"Plan places all {self.placed} batches. Nothing stranded."
        if self.is_clean:
            return (
                f"Plan places {self.placed} batches. "
                f"{len(self.other_stranded)} not-yet-due batches unscheduled."
            )
        return (
            f"This plan leaves {len(self.due_stranded)} batches shipping "
            f"{self.shift_date} or earlier unscheduled."
        )

    def lines(self) -> list[str]:
        out = [self.headline()]
        for s in self.due_stranded:
            out.append(
                f"  DUE  {s.batch.batch_id}  ships {s.batch.quoted_ship_date}  "
                f"[{s.reason}] {s.detail}".rstrip()
            )
        for s in self.other_stranded:
            out.append(
                f"       {s.batch.batch_id}  ships {s.batch.quoted_ship_date}  "
                f"[{s.reason}] {s.detail}".rstrip()
            )
        return out


def report(plan: ShiftPlan) -> SLAReport:
    due = tuple(
        s for s in plan.stranded if s.batch.quoted_ship_date <= plan.shift_date
    )
    other = tuple(
        s for s in plan.stranded if s.batch.quoted_ship_date > plan.shift_date
    )
    return SLAReport(
        shift_date=plan.shift_date,
        due_stranded=due,
        other_stranded=other,
        placed=plan.placed_count,
    )
