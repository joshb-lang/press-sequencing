from __future__ import annotations

import pytest

from conftest import batch
from press_sequencing.eligibility import (
    Condition,
    EligibilityConstraint,
    blocking_constraints,
    eligible_presses,
)
from press_sequencing.model import Press

PRESS_5 = Press("press_5", "Press 5", 3000)
RICOH = Press("ricoh", "Ricoh", 1200)
PRESS_2 = Press("press_2", "Press 2", 3000, lanes=("2.1",))
ALL = [PRESS_2, PRESS_5, RICOH]


def test_a_constraint_excludes_matching_work_from_a_press():
    # Illustrative only. The real holiday-cards/Press 5 exclusion was removed
    # on 23 September as incorrect - see config/eligibility.yml.
    c = EligibilityConstraint(
        "holiday_not_5", Condition({"product": "holiday_card"}), exclude_presses=("press_5",)
    )
    cards = batch("B-1", product="holiday_card")
    assert [p.press_id for p in eligible_presses(cards, ALL, [c])] == ["press_2", "ricoh"]


def test_an_unrelated_batch_is_unaffected_by_a_constraint():
    c = EligibilityConstraint(
        "holiday_not_5", Condition({"product": "holiday_card"}), exclude_presses=("press_5",)
    )
    cards = batch("B-1", product="business_card")
    assert len(eligible_presses(cards, ALL, [c])) == 3


def test_cotton_avoids_the_ricoh_only_after_qc_rejection():
    c = EligibilityConstraint(
        "cotton_not_ricoh",
        Condition({"stock": "cotton"}, qc_rejected=True),
        exclude_presses=("ricoh",),
    )
    rejected = batch("B-1", stock="cotton", qc_rejected=True)
    clean = batch("B-2", stock="cotton")

    assert "ricoh" not in [p.press_id for p in eligible_presses(rejected, ALL, [c])]
    assert "ricoh" in [p.press_id for p in eligible_presses(clean, ALL, [c])]


def test_allow_only_restricts_to_the_named_presses():
    c = EligibilityConstraint(
        "laminator_pairing",
        Condition({"lamination": "gloss"}),
        allow_only_presses=("press_2",),
    )
    gloss = batch("B-1", lamination="gloss")
    assert [p.press_id for p in eligible_presses(gloss, ALL, [c])] == ["press_2"]


def test_constraints_compose_and_can_leave_nothing_eligible():
    constraints = [
        EligibilityConstraint(
            "a", Condition({"product": "holiday_card"}), exclude_presses=("press_5",)
        ),
        EligibilityConstraint(
            "b", Condition({"product": "holiday_card"}), allow_only_presses=("press_5",)
        ),
    ]
    cards = batch("B-1", product="holiday_card")
    assert eligible_presses(cards, ALL, constraints) == []


def test_blocking_constraints_explain_why_a_press_was_refused():
    constraints = [
        EligibilityConstraint(
            "holiday_not_5", Condition({"product": "holiday_card"}), exclude_presses=("press_5",)
        )
    ]
    cards = batch("B-1", product="holiday_card")
    assert [c.constraint_id for c in blocking_constraints(cards, PRESS_5, constraints)] == [
        "holiday_not_5"
    ]
    assert blocking_constraints(cards, PRESS_2, constraints) == []


def test_a_constraint_must_actually_constrain_something():
    with pytest.raises(ValueError, match="exclude_presses or allow_only_presses"):
        EligibilityConstraint("empty", Condition({"a": "b"}))


def test_status_is_limited_to_verified_or_unverified():
    with pytest.raises(ValueError, match="status"):
        EligibilityConstraint(
            "x", Condition({"a": "b"}), exclude_presses=("p",), status="probably"
        )
