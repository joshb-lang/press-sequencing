from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from press_sequencing.model import Batch, Press, ProductClass  # noqa: E402

SHIFT = date(2026, 9, 22)


@pytest.fixture
def classes() -> dict[str, ProductClass]:
    return {
        "rounded": ProductClass("rounded", {"corner": "rounded"}),
        "square": ProductClass("square", {"corner": "square"}),
        "gloss": ProductClass("gloss", {"lamination": "gloss"}),
        "matte": ProductClass("matte", {"lamination": "matte"}),
    }


def batch(batch_id: str, sheets: int = 100, ship: date = SHIFT, **attrs) -> Batch:
    qc = attrs.pop("qc_rejected", False)
    return Batch(
        batch_id=batch_id,
        attributes={k: str(v) for k, v in attrs.items()},
        sheets=sheets,
        quoted_ship_date=ship,
        qc_rejected=qc,
    )


@pytest.fixture
def press() -> Press:
    return Press("press_2", "Press 2", sheets_per_hour=3000, lanes=("2.1", "2.2"))
