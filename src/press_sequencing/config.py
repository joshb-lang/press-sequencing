"""Configuration loading and validation.

If a number would be edited by a supervisor, it is not a literal. Everything
the July logic layer holds as a hardcoded constant — budget windows, the
corner-alternation count, the cycle boundary — is configuration here.

Config is a directory of YAML files. Each is optional except
`product_classes.yml` and `presses.yml`, which the rest refers to by name.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

import yaml

from .budget import Bucket, Makeready, TimeBudget
from .eligibility import Condition, EligibilityConstraint
from .model import Batch, Press, PressAvailability, ProductClass, ShiftCapacity
from .rules import AlternationRule, GroupingRule, OrderingRule, Rule, RuleScope


class ConfigError(Exception):
    """Raised with every problem found, not just the first."""

    def __init__(self, problems: list[str]) -> None:
        self.problems = problems
        super().__init__("\n".join(f"- {p}" for p in problems))


@dataclass(frozen=True)
class SequencingConfig:
    classes: dict[str, ProductClass]
    presses: tuple[Press, ...]
    pipeline: tuple[Rule, ...] = ()
    eligibility: tuple[EligibilityConstraint, ...] = ()
    budget: TimeBudget = field(default_factory=TimeBudget)
    makeready: Makeready = field(default_factory=Makeready)

    def press(self, press_id: str) -> Press | None:
        for p in self.presses:
            if p.press_id == press_id:
                return p
        return None


def _read_yaml(path: Path) -> Any:
    if not path.exists():
        return None
    with path.open() as fh:
        return yaml.safe_load(fh)


def _scope(raw: dict[str, Any] | None) -> RuleScope:
    raw = raw or {}
    return RuleScope(
        presses=tuple(raw.get("presses", ()) or ()),
        lanes=tuple(str(lane) for lane in (raw.get("lanes", ()) or ())),
    )


def _condition(raw: dict[str, Any] | None) -> Condition:
    raw = raw or {}
    return Condition(
        attributes=dict(raw.get("attributes", {}) or {}),
        qc_rejected=raw.get("qc_rejected"),
    )


def _build_rule(raw: dict[str, Any], problems: list[str]) -> Rule | None:
    rule_id = raw.get("id")
    if not rule_id:
        problems.append("rule without an id")
        return None
    if not raw.get("enabled", True):
        return None
    kind = raw.get("type")
    scope = _scope(raw.get("applies_to"))
    try:
        if kind == "ordering":
            return OrderingRule(rule_id, tuple(raw["class_order"]), scope)
        if kind == "grouping":
            return GroupingRule(rule_id, raw["attribute"], scope)
        if kind == "alternation":
            return AlternationRule(
                rule_id,
                raw["class_a"],
                raw["class_b"],
                int(raw["count"]),
                raw.get("unit", "batches"),
                scope,
            )
    except (KeyError, ValueError) as exc:
        problems.append(f"rule {rule_id}: {exc}")
        return None
    problems.append(
        f"rule {rule_id}: unknown type {kind!r}. The vocabulary is closed: "
        "ordering, alternation, grouping."
    )
    return None


def load_config(directory: str | Path) -> SequencingConfig:
    directory = Path(directory)
    problems: list[str] = []

    raw_classes = _read_yaml(directory / "product_classes.yml") or {}
    classes = {
        name: ProductClass(name, dict(attrs or {}))
        for name, attrs in (raw_classes.get("product_classes", {}) or {}).items()
    }
    if not classes:
        problems.append("no product classes defined in product_classes.yml")

    presses: list[Press] = []
    for raw in (_read_yaml(directory / "presses.yml") or {}).get("presses", []) or []:
        try:
            presses.append(
                Press(
                    press_id=raw["id"],
                    name=raw.get("name", raw["id"]),
                    sheets_per_hour=int(raw["sheets_per_hour"]),
                    lanes=tuple(str(lane) for lane in raw.get("lanes", ()) or ()),
                )
            )
        except (KeyError, ValueError) as exc:
            problems.append(f"press {raw.get('id', '<no id>')}: {exc}")
    if not presses:
        problems.append("no presses defined in presses.yml")

    pipeline: list[Rule] = []
    for raw in (_read_yaml(directory / "rules.yml") or {}).get("pipeline", []) or []:
        rule = _build_rule(raw, problems)
        if rule is not None:
            pipeline.append(rule)

    constraints: list[EligibilityConstraint] = []
    for raw in (_read_yaml(directory / "eligibility.yml") or {}).get("eligibility", []) or []:
        try:
            constraints.append(
                EligibilityConstraint(
                    constraint_id=raw["id"],
                    when=_condition(raw.get("when")),
                    exclude_presses=tuple(raw.get("exclude_presses", ()) or ()),
                    allow_only_presses=tuple(raw.get("allow_only_presses", ()) or ()),
                    status=raw.get("status", "unverified"),
                    note=raw.get("note", ""),
                )
            )
        except (KeyError, ValueError) as exc:
            problems.append(f"eligibility {raw.get('id', '<no id>')}: {exc}")

    raw_budget = _read_yaml(directory / "budget.yml") or {}
    buckets: list[Bucket] = []
    for raw in (raw_budget.get("time_budget", {}) or {}).get("buckets", []) or []:
        try:
            buckets.append(
                Bucket(
                    bucket_id=raw["id"],
                    when=_condition(raw.get("when")),
                    share=raw.get("share"),
                    minutes=raw.get("minutes"),
                )
            )
        except (KeyError, ValueError) as exc:
            problems.append(f"budget bucket {raw.get('id', '<no id>')}: {exc}")

    shares = [b.share for b in buckets if b.share is not None]
    if shares and sum(shares) > 1.0 + 1e-9:
        problems.append(f"budget bucket shares sum to {sum(shares):.2f}, which exceeds 1.0")

    budget = TimeBudget(
        buckets=tuple(buckets),
        allow_reallocation=bool(
            (raw_budget.get("time_budget", {}) or {}).get("allow_reallocation", True)
        ),
    )
    raw_makeready = raw_budget.get("makeready", {}) or {}
    makeready = Makeready(
        default_minutes=float(raw_makeready.get("default_minutes", 0.0)),
        changeover_minutes=float(raw_makeready.get("changeover_minutes", 0.0)),
        changeover_attributes=tuple(raw_makeready.get("changeover_attributes", ()) or ()),
    )

    problems.extend(_cross_check(classes, presses, pipeline, constraints))
    if problems:
        raise ConfigError(problems)

    return SequencingConfig(
        classes=classes,
        presses=tuple(presses),
        pipeline=tuple(pipeline),
        eligibility=tuple(constraints),
        budget=budget,
        makeready=makeready,
    )


def _cross_check(
    classes: dict[str, ProductClass],
    presses: list[Press],
    pipeline: list[Rule],
    constraints: list[EligibilityConstraint],
) -> list[str]:
    """Catch references to things that do not exist.

    A rule naming a class that was renamed, or a constraint naming a press
    that was retired, fails open otherwise: the rule quietly stops applying
    and nobody finds out until the floor does.
    """
    problems: list[str] = []
    press_ids = {p.press_id for p in presses}
    lane_ids = {lane for p in presses for lane in p.lanes}

    for rule in pipeline:
        named: list[str] = []
        if isinstance(rule, OrderingRule):
            named = list(rule.class_order)
        elif isinstance(rule, AlternationRule):
            named = [rule.class_a, rule.class_b]
        for name in named:
            if name not in classes:
                problems.append(f"rule {rule.rule_id}: unknown product class {name!r}")
        for press_id in rule.scope.presses:
            if press_id not in press_ids:
                problems.append(f"rule {rule.rule_id}: unknown press {press_id!r}")
        for lane in rule.scope.lanes:
            if lane not in lane_ids:
                problems.append(f"rule {rule.rule_id}: unknown lane {lane!r}")

    for c in constraints:
        for press_id in (*c.exclude_presses, *c.allow_only_presses):
            if press_id not in press_ids:
                problems.append(f"eligibility {c.constraint_id}: unknown press {press_id!r}")

    return problems


def load_capacity(path: str | Path) -> ShiftCapacity:
    """Load the presses and hours a supervisor states are available.

    Capacity is an input. A press absent from this file is not on shift.
    """
    raw = _read_yaml(Path(path)) or {}
    shift_date = raw.get("shift_date")
    if isinstance(shift_date, str):
        shift_date = date.fromisoformat(shift_date)
    if not isinstance(shift_date, date):
        raise ConfigError(["capacity: shift_date is required (YYYY-MM-DD)"])

    problems: list[str] = []
    availability: list[PressAvailability] = []
    for entry in raw.get("presses", []) or []:
        try:
            availability.append(
                PressAvailability(
                    press_id=entry["id"],
                    hours=float(entry["hours"]),
                    operators=int(entry.get("operators", 1)),
                )
            )
        except (KeyError, ValueError) as exc:
            problems.append(f"capacity for {entry.get('id', '<no id>')}: {exc}")
    if problems:
        raise ConfigError(problems)

    return ShiftCapacity(shift_date=shift_date, availability=tuple(availability))


def load_batches(path: str | Path) -> list[Batch]:
    """Load open batches.

    `batch_id` comes from the record. It is never recovered from a filename.
    """
    raw = _read_yaml(Path(path)) or {}
    entries = raw.get("batches", []) if isinstance(raw, dict) else raw
    problems: list[str] = []
    batches: list[Batch] = []
    for entry in entries or []:
        try:
            ship = entry["quoted_ship_date"]
            if isinstance(ship, str):
                ship = date.fromisoformat(ship)
            batches.append(
                Batch(
                    batch_id=str(entry["batch_id"]),
                    attributes={k: str(v) for k, v in (entry.get("attributes", {}) or {}).items()},
                    sheets=int(entry["sheets"]),
                    quoted_ship_date=ship,
                    qc_rejected=bool(entry.get("qc_rejected", False)),
                )
            )
        except (KeyError, ValueError, TypeError) as exc:
            problems.append(f"batch {entry.get('batch_id', '<no id>')}: {exc}")
    if problems:
        raise ConfigError(problems)

    seen: set[str] = set()
    duplicates = {b.batch_id for b in batches if b.batch_id in seen or seen.add(b.batch_id)}
    if duplicates:
        raise ConfigError([f"duplicate batch ids: {', '.join(sorted(duplicates))}"])
    return batches
