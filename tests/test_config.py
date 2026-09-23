from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from press_sequencing.config import ConfigError, load_batches, load_capacity, load_config
from press_sequencing.model import Batch
from press_sequencing.rules import AlternationRule

REPO = Path(__file__).resolve().parents[1]


# --- the checked-in config --------------------------------------------------

def test_the_repository_config_loads():
    config = load_config(REPO / "config")
    assert config.classes and config.presses and config.pipeline


def test_the_sheet_budget_alternation_is_present_but_off():
    """The sheet-budget alternation is expressible in config and not live on
    lanes 2.1, 2.2 or 3.1, so it must not be enabled here. The 205-sheet
    behaviour that is live runs on lane 5.1 and alternates lifts, which this
    batch-level rule does not reproduce."""
    config = load_config(REPO / "config")
    ids = {r.rule_id for r in config.pipeline}
    assert "corner_alternation_batches" in ids
    assert "corner_alternation_sheets" not in ids

    text = (REPO / "config" / "rules.yml").read_text()
    assert "corner_alternation_sheets" in text
    assert "count: 205" in text
    assert "count: 204" not in text


def test_holiday_cards_are_not_excluded_from_press_5():
    """The exclusion was removed on 23 September: lane 5.1 runs holiday cards,
    cotton and pearlescent, and Jennifer confirmed the order it produces. This
    guards against the constraint being reinstated from the older context."""
    config = load_config(REPO / "config")
    assert not [c for c in config.eligibility if "holiday" in c.constraint_id]

    press_5 = config.press("press_5")
    cards = Batch("B-1", {"product": "holiday_card"}, 100, date(2026, 9, 23))
    assert all(c.permits(cards, press_5) for c in config.eligibility)


def test_lane_5_1_exists_on_press_5():
    assert "5.1" in load_config(REPO / "config").press("press_5").lanes


def test_corner_alternation_is_four_batches_on_the_three_lanes():
    config = load_config(REPO / "config")
    rule = next(r for r in config.pipeline if r.rule_id == "corner_alternation_batches")
    assert isinstance(rule, AlternationRule)
    assert (rule.count, rule.unit) == (4, "batches")
    assert set(rule.scope.lanes) == {"2.1", "2.2", "3.1"}


def test_lamination_is_grouped_and_never_alternated():
    """Gloss/matte alternation breaks delivery stacking, so lamination is a
    grouping rule. An alternation rule over gloss and matte would be a bug."""
    config = load_config(REPO / "config")
    for rule in config.pipeline:
        if isinstance(rule, AlternationRule):
            named = {rule.class_a, rule.class_b}
            assert named != {"gloss_laminated", "matte_laminated"}
    assert any(
        getattr(r, "attribute", None) == "lamination" for r in config.pipeline
    )


def test_the_example_files_load():
    batches = load_batches(REPO / "examples" / "batches.yml")
    capacity = load_capacity(REPO / "examples" / "capacity.yml")
    assert batches and capacity.availability


# --- validation -------------------------------------------------------------

def write(tmp_path: Path, name: str, text: str) -> Path:
    (tmp_path / name).write_text(text)
    return tmp_path


BASE_CLASSES = "product_classes:\n  a: {corner: rounded}\n  b: {corner: square}\n"
BASE_PRESSES = "presses:\n  - id: p1\n    sheets_per_hour: 100\n    lanes: ['1.1']\n"


@pytest.fixture
def base(tmp_path: Path) -> Path:
    write(tmp_path, "product_classes.yml", BASE_CLASSES)
    write(tmp_path, "presses.yml", BASE_PRESSES)
    return tmp_path


def test_a_rule_naming_an_unknown_class_is_rejected(base: Path):
    write(base, "rules.yml", "pipeline:\n  - id: r\n    type: ordering\n    class_order: [ghost]\n")
    with pytest.raises(ConfigError, match="unknown product class 'ghost'"):
        load_config(base)


def test_a_rule_naming_an_unknown_lane_is_rejected(base: Path):
    write(
        base,
        "rules.yml",
        "pipeline:\n  - id: r\n    type: grouping\n    attribute: size\n"
        "    applies_to:\n      lanes: ['9.9']\n",
    )
    with pytest.raises(ConfigError, match="unknown lane '9.9'"):
        load_config(base)


def test_a_constraint_naming_an_unknown_press_is_rejected(base: Path):
    write(
        base,
        "eligibility.yml",
        "eligibility:\n  - id: e\n    when:\n      attributes: {stock: cotton}\n"
        "    exclude_presses: [ghost_press]\n",
    )
    with pytest.raises(ConfigError, match="unknown press 'ghost_press'"):
        load_config(base)


def test_a_fourth_rule_type_is_rejected_by_name(base: Path):
    """The vocabulary is closed. An unknown type is a config error, and the
    message says why rather than just failing."""
    write(base, "rules.yml", "pipeline:\n  - id: r\n    type: constraint\n")
    with pytest.raises(ConfigError, match="vocabulary is closed"):
        load_config(base)


def test_bucket_shares_over_one_are_rejected(base: Path):
    write(
        base,
        "budget.yml",
        "time_budget:\n  buckets:\n"
        "    - id: a\n      share: 0.8\n      when: {attributes: {product: x}}\n"
        "    - id: b\n      share: 0.5\n      when: {attributes: {product: y}}\n",
    )
    with pytest.raises(ConfigError, match="exceeds 1.0"):
        load_config(base)


def test_every_problem_is_reported_not_just_the_first(base: Path):
    write(
        base,
        "rules.yml",
        "pipeline:\n  - id: r1\n    type: ordering\n    class_order: [ghost]\n"
        "  - id: r2\n    type: nonsense\n",
    )
    with pytest.raises(ConfigError) as exc:
        load_config(base)
    assert len(exc.value.problems) >= 2


def test_a_disabled_rule_is_skipped(base: Path):
    write(
        base,
        "rules.yml",
        "pipeline:\n  - id: r\n    type: grouping\n    attribute: size\n    enabled: false\n",
    )
    assert load_config(base).pipeline == ()


def test_missing_presses_or_classes_are_reported(tmp_path: Path):
    with pytest.raises(ConfigError) as exc:
        load_config(tmp_path)
    assert any("product class" in p for p in exc.value.problems)
    assert any("presses" in p for p in exc.value.problems)


# --- inputs -----------------------------------------------------------------

def test_capacity_requires_a_shift_date(tmp_path: Path):
    path = tmp_path / "cap.yml"
    path.write_text("presses:\n  - id: p1\n    hours: 8\n")
    with pytest.raises(ConfigError, match="shift_date"):
        load_capacity(path)


def test_capacity_parses_hours_and_operators(tmp_path: Path):
    path = tmp_path / "cap.yml"
    path.write_text(
        "shift_date: 2026-09-22\npresses:\n  - id: p1\n    hours: 6.5\n    operators: 2\n"
    )
    capacity = load_capacity(path)
    assert capacity.shift_date == date(2026, 9, 22)
    assert capacity.availability[0].minutes == 390


def test_duplicate_batch_ids_are_rejected(tmp_path: Path):
    path = tmp_path / "b.yml"
    path.write_text(
        "batches:\n"
        "  - {batch_id: B-1, sheets: 10, quoted_ship_date: 2026-09-22}\n"
        "  - {batch_id: B-1, sheets: 20, quoted_ship_date: 2026-09-22}\n"
    )
    with pytest.raises(ConfigError, match="duplicate batch ids: B-1"):
        load_batches(path)


def test_a_batch_without_an_id_is_rejected(tmp_path: Path):
    path = tmp_path / "b.yml"
    path.write_text("batches:\n  - {sheets: 10, quoted_ship_date: 2026-09-22}\n")
    with pytest.raises(ConfigError):
        load_batches(path)
