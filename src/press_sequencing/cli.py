"""Command line entry points.

    press-seq validate --config config
    press-seq sequence --config config --batches examples/batches.yml \
        --capacity examples/capacity.yml

`sequence` exits 2 when the plan strands work that is due. That is the SLA
argue-back made operational: a plan that drops due-dated batches is not a
successful run, whatever the sequence looks like.
"""

from __future__ import annotations

import argparse
import json
import sys

from .config import ConfigError, load_batches, load_capacity, load_config
from .sequencer import next_for_press, sequence_shift
from .sla import report

EXIT_OK = 0
EXIT_CONFIG_ERROR = 1
EXIT_DUE_WORK_STRANDED = 2


def _add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--config", default="config", help="config directory")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="press-seq", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    validate = sub.add_parser("validate", help="check configuration and exit")
    _add_common(validate)

    sequence = sub.add_parser("sequence", help="produce a shift sequence")
    _add_common(sequence)
    sequence.add_argument("--batches", required=True)
    sequence.add_argument("--capacity", required=True)
    sequence.add_argument("--json", action="store_true", help="machine-readable output")
    sequence.add_argument(
        "--allow-stranded",
        action="store_true",
        help="exit 0 even when due-dated work is stranded",
    )

    nxt = sub.add_parser("next", help="ask what one press should run next")
    _add_common(nxt)
    nxt.add_argument("--batches", required=True)
    nxt.add_argument("--capacity", required=True)
    nxt.add_argument("--press", required=True)
    nxt.add_argument("--printed", nargs="*", default=[], help="batch ids already printed")

    return parser


def _plan_as_dict(plan, sla) -> dict:
    return {
        "shift_date": str(plan.shift_date),
        "runs": {
            press_id: [
                {
                    "position": p.position,
                    "batch_id": p.batch.batch_id,
                    "cycle": p.cycle,
                    "sheets": p.batch.sheets,
                    "run_minutes": round(p.run_minutes, 2),
                    "makeready_minutes": round(p.makeready_minutes, 2),
                }
                for p in run.placed
            ]
            for press_id, run in plan.runs.items()
        },
        "sla": {
            "headline": sla.headline(),
            "placed": sla.placed,
            "due_stranded": [
                {
                    "batch_id": s.batch.batch_id,
                    "quoted_ship_date": str(s.batch.quoted_ship_date),
                    "reason": s.reason,
                    "detail": s.detail,
                }
                for s in sla.due_stranded
            ],
            "other_stranded": [
                {
                    "batch_id": s.batch.batch_id,
                    "quoted_ship_date": str(s.batch.quoted_ship_date),
                    "reason": s.reason,
                    "detail": s.detail,
                }
                for s in sla.other_stranded
            ],
        },
    }


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        config = load_config(args.config)
        if args.command == "validate":
            print(
                f"Config OK: {len(config.classes)} product classes, "
                f"{len(config.presses)} presses, {len(config.pipeline)} rules, "
                f"{len(config.eligibility)} eligibility constraints."
            )
            unverified = [c.constraint_id for c in config.eligibility if c.status != "verified"]
            if unverified:
                print(
                    "Unverified constraints (encoding not yet confirmed with the floor): "
                    + ", ".join(unverified)
                )
            return EXIT_OK

        batches = load_batches(args.batches)
        capacity = load_capacity(args.capacity)
    except ConfigError as exc:
        print(f"Configuration problems:\n{exc}", file=sys.stderr)
        return EXIT_CONFIG_ERROR

    if args.command == "next":
        batch = next_for_press(args.press, batches, capacity, config, set(args.printed))
        print(batch.batch_id if batch else "")
        return EXIT_OK

    plan = sequence_shift(batches, capacity, config)
    sla = report(plan)

    if args.json:
        print(json.dumps(_plan_as_dict(plan, sla), indent=2))
    else:
        for press_id, run in plan.runs.items():
            print(f"{press_id} ({run.minutes_used:.0f} min)")
            for p in run.placed:
                print(
                    f"  {p.position:>3}  cycle {p.cycle}  {p.batch.batch_id:<12} "
                    f"{p.batch.sheets:>6} sheets  {p.total_minutes:>6.1f} min"
                )
        print()
        for line in sla.lines():
            print(line)

    if sla.due_stranded and not args.allow_stranded:
        return EXIT_DUE_WORK_STRANDED
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
