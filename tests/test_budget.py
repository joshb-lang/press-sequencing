from __future__ import annotations

import pytest

from conftest import batch
from press_sequencing.budget import Bucket, BudgetLedger, Makeready, TimeBudget, run_minutes
from press_sequencing.eligibility import Condition
from press_sequencing.model import Press

PRESS = Press("press_2", "Press 2", sheets_per_hour=3000)

CARDS = Bucket("cards", Condition({"product": "business_card"}), share=0.5)
POSTCARDS = Bucket("postcards", Condition({"product": "postcard"}), share=0.5)


def test_run_minutes_comes_from_sheets_and_press_speed():
    assert run_minutes(batch("B-1", sheets=3000), PRESS) == 60.0
    assert run_minutes(batch("B-2", sheets=1500), PRESS) == 30.0


def test_makeready_charges_a_changeover_on_the_first_batch():
    mk = Makeready(default_minutes=2, changeover_minutes=15, changeover_attributes=("stock",))
    assert mk.minutes_for(batch("B-1", stock="16pt"), None) == 17


def test_makeready_charges_a_changeover_only_when_a_watched_attribute_changes():
    mk = Makeready(default_minutes=2, changeover_minutes=15, changeover_attributes=("stock",))
    first = batch("B-1", stock="16pt", lamination="matte")
    same = batch("B-2", stock="16pt", lamination="gloss")
    different = batch("B-3", stock="cotton")

    assert mk.minutes_for(same, first) == 2
    assert mk.minutes_for(different, first) == 17


def test_windows_split_available_time_by_share():
    budget = TimeBudget((CARDS, POSTCARDS))
    assert budget.windows(480) == {"cards": 240.0, "postcards": 240.0}


def test_a_bucket_caps_its_work_when_reallocation_is_off():
    budget = TimeBudget((CARDS, POSTCARDS), allow_reallocation=False)
    ledger = BudgetLedger(budget, 480)
    cards = batch("B-1", product="business_card")

    assert ledger.fits(cards, 240)
    assert not ledger.fits(cards, 241)


def test_a_bucket_borrows_headroom_from_a_quiet_bucket_when_reallocation_is_on():
    """Buckets readjust: a quiet work type does not hold minutes a busy one
    needs."""
    budget = TimeBudget((CARDS, POSTCARDS), allow_reallocation=True)
    ledger = BudgetLedger(budget, 480)
    cards = batch("B-1", product="business_card")

    assert ledger.fits(cards, 400)


def test_borrowing_never_exceeds_the_press_time_itself():
    budget = TimeBudget((CARDS, POSTCARDS), allow_reallocation=True)
    ledger = BudgetLedger(budget, 480)
    assert not ledger.fits(batch("B-1", product="business_card"), 481)


def test_charging_consumes_the_bucket_and_the_press_total():
    budget = TimeBudget((CARDS, POSTCARDS), allow_reallocation=False)
    ledger = BudgetLedger(budget, 480)
    ledger.charge(batch("B-1", product="business_card"), 100)

    assert ledger.headroom("cards") == 140
    assert ledger.remaining == 380


def test_work_no_bucket_claims_is_capped_only_by_press_time():
    budget = TimeBudget((CARDS,), allow_reallocation=False)
    ledger = BudgetLedger(budget, 480)
    other = batch("B-1", product="sticker")

    assert ledger.fits(other, 400)
    ledger.charge(other, 400)
    assert ledger.remaining == 80
    assert not ledger.fits(other, 100)


def test_an_explicit_minutes_bucket_ignores_available_time():
    fixed = Bucket("fixed", Condition({"product": "postcard"}), minutes=90)
    assert TimeBudget((fixed,)).windows(480) == {"fixed": 90}


def test_a_bucket_needs_exactly_one_of_share_or_minutes():
    with pytest.raises(ValueError, match="exactly one"):
        Bucket("b", Condition({}), share=0.5, minutes=90)
    with pytest.raises(ValueError, match="exactly one"):
        Bucket("b", Condition({}))


def test_a_share_outside_zero_to_one_is_rejected():
    with pytest.raises(ValueError, match="share"):
        Bucket("b", Condition({}), share=1.5)
