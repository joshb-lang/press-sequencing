from __future__ import annotations

import json
from pathlib import Path

import pytest

from press_sequencing.cli import EXIT_CONFIG_ERROR, EXIT_DUE_WORK_STRANDED, EXIT_OK, main

REPO = Path(__file__).resolve().parents[1]
CONFIG = str(REPO / "config")
BATCHES = str(REPO / "examples" / "batches.yml")
CAPACITY = str(REPO / "examples" / "capacity.yml")


def test_validate_reports_the_loaded_config(capsys):
    assert main(["validate", "--config", CONFIG]) == EXIT_OK
    assert "Config OK" in capsys.readouterr().out


def test_validate_names_constraints_that_are_not_yet_confirmed(capsys):
    """Nothing should be enforced on the floor while its encoding is
    unverified, so validate says which ones those are."""
    main(["validate", "--config", CONFIG])
    assert "Unverified constraints" in capsys.readouterr().out


def test_validate_fails_on_a_broken_config(tmp_path: Path, capsys):
    (tmp_path / "product_classes.yml").write_text("product_classes: {}\n")
    assert main(["validate", "--config", str(tmp_path)]) == EXIT_CONFIG_ERROR
    assert "Configuration problems" in capsys.readouterr().err


def test_sequence_prints_a_run_per_press(capsys):
    args = ["sequence", "--config", CONFIG, "--batches", BATCHES, "--capacity", CAPACITY]
    assert main(args) == EXIT_OK
    out = capsys.readouterr().out
    assert "press_2" in out
    assert "cycle 1" in out


def test_sequence_json_output_is_machine_readable(capsys):
    main(["sequence", "--config", CONFIG, "--batches", BATCHES, "--capacity", CAPACITY, "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert payload["shift_date"] == "2026-09-22"
    assert "sla" in payload and "headline" in payload["sla"]


def test_sequence_exits_nonzero_when_due_work_is_stranded(tmp_path: Path, capsys):
    """A plan that drops due-dated batches is not a successful run."""
    cap = tmp_path / "cap.yml"
    cap.write_text("shift_date: 2026-09-22\npresses:\n  - id: press_2\n    hours: 0.2\n")
    code = main(["sequence", "--config", CONFIG, "--batches", BATCHES, "--capacity", str(cap)])

    assert code == EXIT_DUE_WORK_STRANDED
    assert "This plan leaves" in capsys.readouterr().out


def test_allow_stranded_downgrades_that_to_a_warning(tmp_path: Path):
    cap = tmp_path / "cap.yml"
    cap.write_text("shift_date: 2026-09-22\npresses:\n  - id: press_2\n    hours: 0.2\n")
    code = main(
        ["sequence", "--config", CONFIG, "--batches", BATCHES,
         "--capacity", str(cap), "--allow-stranded"]
    )
    assert code == EXIT_OK


def test_next_answers_for_one_press(capsys):
    assert main(
        ["next", "--config", CONFIG, "--batches", BATCHES, "--capacity", CAPACITY,
         "--press", "press_2"]
    ) == EXIT_OK
    assert capsys.readouterr().out.strip()


def test_next_skips_what_has_already_printed(capsys):
    args = ["next", "--config", CONFIG, "--batches", BATCHES, "--capacity", CAPACITY,
            "--press", "press_2"]
    main(args)
    first = capsys.readouterr().out.strip()

    main([*args, "--printed", first])
    second = capsys.readouterr().out.strip()
    assert second and second != first


def test_next_is_empty_for_an_unstaffed_press(capsys):
    main(["next", "--config", CONFIG, "--batches", BATCHES, "--capacity", CAPACITY,
          "--press", "ricoh"])
    assert capsys.readouterr().out.strip() == ""


def test_a_command_is_required():
    with pytest.raises(SystemExit):
        main([])
