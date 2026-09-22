from __future__ import annotations

from datetime import date

import pytest

from conftest import batch
from press_sequencing.model import Batch, Press, PressAvailability, ProductClass, ShiftCapacity


def test_batch_id_is_required():
    with pytest.raises(ValueError, match="batch_id"):
        Batch("", {}, 10, date(2026, 9, 22))
    with pytest.raises(ValueError, match="batch_id"):
        Batch("   ", {}, 10, date(2026, 9, 22))


def test_sheets_must_be_positive():
    with pytest.raises(ValueError, match="sheets"):
        Batch("B-1", {}, 0, date(2026, 9, 22))


def test_no_filename_parsing_is_exposed():
    """Batch ids are never recovered from filenames, so no such helper exists."""
    import press_sequencing

    names = dir(press_sequencing) + dir(Batch)
    assert not [n for n in names if "filename" in n.lower() or "from_path" in n.lower()]


def test_product_class_matches_on_subset_of_attributes():
    pc = ProductClass("16pt_matte", {"stock": "16pt", "lamination": "matte"})
    assert pc.matches(batch("B-1", stock="16pt", lamination="matte", corner="rounded"))
    assert not pc.matches(batch("B-2", stock="16pt", lamination="gloss"))
    assert not pc.matches(batch("B-3", stock="16pt"))


def test_unstaffed_press_contributes_no_minutes():
    assert PressAvailability("press_2", hours=8, operators=1).minutes == 480
    assert PressAvailability("press_2", hours=8, operators=0).minutes == 0


def test_press_absent_from_capacity_is_not_on_shift():
    capacity = ShiftCapacity(date(2026, 9, 22), (PressAvailability("press_2", 8),))
    assert capacity.for_press("press_2") is not None
    assert capacity.for_press("press_5") is None


def test_press_speed_must_be_positive():
    with pytest.raises(ValueError, match="sheets_per_hour"):
        Press("p", "P", sheets_per_hour=0)
