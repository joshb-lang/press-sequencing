# press-sequencing

Deciding the order in which batches are sent to presses at MOO's East
Providence site, given physical constraints and the presses and operators
actually available on a given shift.

Owner: Josh Barry, Data and Planning.

This repo is the **sequencing logic** — the rules that decide what comes next.
It is not the press queue app, it is not a portal, and it has no UI. See
[Where this fits](#where-this-fits).

## Status: nothing here is proven

The Press Queue app went to the floor in late August 2026. SLA deteriorated
over that period and recovered after the revert to manual scheduling on
8 September.

That period is confounded — short shifts, two scheduling paths running in
parallel, double-print incidents — so it is **not** proof the approach is
wrong. But nothing is proven to work either, and the SLA movement cannot yet
be explained in either direction, because print events are not being captured.

Nothing in this repo should be described, in code, docs or a deck, as a
proven win.

### Sequencing may not be the binding constraint

Before building further, three numbers from Aug–Sep:

1. Where time actually went on missed-SLA batches — queue wait vs press vs
   post-press vs reprint.
2. How many were reprints or double prints.
3. How press hours split between changeover, idle and unstaffed.

If changeover turns out to be a thin slice, the ceiling on any sequencing work
is low, and that is worth knowing before more of it is built. The scaffold
here is sized for that possibility: small, configurable, and cheap to abandon.

## What is in here

| Module | Does |
|---|---|
| `model.py` | Batches, presses, stated shift capacity |
| `rules.py` | The three rule primitives — ordering, alternation, grouping |
| `eligibility.py` | Where work may run at all. Not a rule type |
| `budget.py` | Press time windows per work type, and makeready |
| `sequencer.py` | Reference sequencer: whole-shift plan, or next-for-press |
| `sla.py` | What the plan stranded |
| `config.py` | Loading and validating configuration |
| `cli.py` | `press-seq validate` / `sequence` / `next` |

## Quick start

```bash
pip install -e ".[dev]"

press-seq validate --config config

press-seq sequence --config config \
    --batches examples/batches.yml \
    --capacity examples/capacity.yml
```

`sequence` exits 2 when the plan strands work that is due — see
[SLA argues back](#sla-argues-back).

## The four things this scaffold commits to

### Rules are configuration, not constants

The July logic layer holds its three rules as hardcoded constants. Here,
budget windows, the corner-alternation count, the lanes a rule applies to and
the press eligibility constraints are all config. If a number would be edited
by a supervisor, it is not a literal.

The planned change from four batches to 204 sheets on corner alternation is in
`config/rules.yml` already, expressible and switched off, because it is not
implemented on the floor. Turning it on is a config change.

### The rule vocabulary is closed

Ordering, alternation, grouping. Nothing else. Anything a planner asks for is
a template built from these. An unknown rule type is a config error whose
message says so.

Press eligibility is deliberately not a fourth primitive — most of the
pressure to add one turns out to be eligibility in disguise. See
[docs/rule-vocabulary.md](docs/rule-vocabulary.md).

### Capacity is an input

Supervisors state the presses and hours available at shift start and the
sequence recalculates. A press absent from the capacity file is not on shift;
a press with `operators: 0` is on shift but unstaffed. Those are different
facts, and unstaffed press hours are one of the three numbers above.

### SLA argues back

A capacity-first plan that hides what it stranded will make SLA worse while
looking more organised. So the plan states what it left behind:

```
This plan leaves 14 batches shipping 2026-09-22 or earlier unscheduled.
  DUE  B-1043  ships 2026-09-22  [no_capacity] eligible presses (press_2) have no time left
```

Every batch is either placed exactly once or reported as stranded with a
reason. Truncation never happens silently, and cycle 1 is laid down before
cycle 2 so overflow reaches work that is not yet due before it touches work
that ships today.

## Plan vs dispatch is not settled here

Two shapes are on the table, and this repo does not pick one.

- *Allocate-then-fill* — visible and plannable, but a plan made at 06:00 is
  stale by mid-morning, which is the failure mode we keep hitting.
- *Dispatch* — degrades gracefully under short staffing and self-heals after
  abandoned runs, but is myopic on changeover, makes pre-staging harder, and
  gives supervisors nothing to look at.

The current lean is a configuration layer feeding a dispatcher, with a
timeline kept as the surface for setting the standard and comparing plan
against actual rather than as the thing that assigns work.

So `sequencer.py` offers both over the same rules: `sequence_shift()` builds a
whole-shift plan, `next_for_press()` answers "what next?" from current state
by recomputing and taking the head. The configuration layer is the part worth
building now, because it survives either decision.

## What this repo deliberately does not do

**It does not write print events.** Execution lives in
`timw-moo/moo-press-queue`. Anything that does write events must honour
constraints that have each already caused a real defect:

- **The action log vocabulary is shared.** `operations_user_action_log` is
  written by other systems and read by the data team's flows. The action
  string changed from `printed` to `batch status is printed` once and silently
  dropped rows until the filter was widened. Agree any new action string with
  the data team first. Do not invent a third.
- **Writes must be additive.** If this became the only writer and only part of
  the floor used it, an absent event would be indistinguishable from absent
  work — worse than today, where the gaps are at least visible. Whatever
  WorkerBee writes keeps writing. Add press-level coverage flags or reconcile
  against HP logs so "nothing ran" is distinguishable from "ran elsewhere".
- **Every write needs a dedupe key.** Retries, resends and QC reprints all
  fire the writer. Key on batch ID + press + event type + run. Whether prod
  `markBatchesAsPrinted.do` is idempotent is still unconfirmed.
- **Two events, not one.** Sent-to-press and completed-per-JMF are different
  facts. Writing both also surfaces abandoned runs, which currently block
  queues invisibly.

**It does not parse batch IDs out of filenames.** Batch ID is a first-class
field. Filename prefix and extension inconsistencies break joins across
WorkerBee, HP and Snowflake. No helper for this exists here, and a test
asserts that none appears.

**It has no UI.** See below.

## Where this fits

| System | Role | Direction |
|---|---|---|
| WorkerBee | Order/batch system, the batch selection UI operators use today | Stays; upstream |
| Snowflake / dbt | Target for the sequencing model, DW-8440 | Growing |
| Tableau | Prep flow 450, workbook 6607 | Exit as pipeline, keep as reporting |
| `timw-moo/moo-press-queue` | Execution — JDF send, travelers, mark printed | Stays |
| `timw-moo/jdf-api` | JDF/JMF rules and docs | Stays |
| MOOsaic | Single manufacturing flow PoC, operator surfaces | Likely host for UI |
| Enfocus Switch | Workflow engine driving Phoenix | Being exited — do not build into it |
| tilia Phoenix | Imposition engine | Being replaced in-house (PPUR-1999) |
| PrintOS / Site Flow | Parallel print path | Source of double prints — needs a batch lock |

**Phase 0 needs no UI at all.** Sequencing as a dbt model in Snowflake (scoped
as DW-8440), press availability as a small table a supervisor edits, output as
a table any front end reads. The YAML in `config/` is the intended source of
truth for rules under that plan too: the dbt model consumes the same
configuration, and this package stays as the place rule semantics are
specified and tested.

**The UI probably lives in MOOsaic.** MOOsaic already has batch generation, a
station view and BFF contracts for operator views (PPUR-2180 / PPUR-2181).
What it lacks is the rules that decide what comes next. Treat this repo as the
sequencing brain behind MOOsaic's station view, not a competing portal. Adding
a fourth surface next to the Press Queue app and WorkerBee is how you get a
fourth thing nobody uses.

**Site Flow is not the answer and the question is closed.** It solves batch
formation, which MOO has already solved. It does not sequence work across
coupled finishing lines under physical constraints.

## Before you trust any output

Read [docs/open-questions.md](docs/open-questions.md). Press speeds, makeready
minutes and budget shares in `config/` are placeholders. Every physical
constraint is encoded `status: unverified` — the constraint is real, the
encoding is a first pass, and `press-seq validate` prints which ones. Nothing
here should be enforced on the floor while it says unverified.

## Conventions

- Do not present unproven work as proven. Flag confounders.
- Prefer configuration over constants.
- Any change touching the action log gets reviewed by the data team first.
- Phase small. The last rollout failed at 90% complete with no requirements
  and no QA; a small thing that works completely beats a large thing that
  mostly does.

## People

Timothy Wessman (press queue app, MOOsaic) · Jennifer Raposo (floor lead) ·
Rich Ives (Tableau and data, owns the action-log flows) · Andrew Smith and
Boris Janssen (ops) · Thomas Cornish (prepress).
