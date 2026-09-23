# Open questions

Nothing in this repo has been validated against the floor. This file is the
list of what a reader should not assume, kept next to the code that assumes
it.

## Encodings that need confirming

Each of these is a real constraint held today as operator knowledge. The
constraint is real; the encoding is a first pass. Everything listed here is
marked `status: unverified` in `config/eligibility.yml`, and `press-seq
validate` prints the list.

| What | Encoded as | Needs |
|---|---|---|
| Cotton must not route to the Ricoh after QC rejection | Eligibility exclusion conditional on `qc_rejected` | Confirm that clean cotton really is unaffected |
| Conveyor-to-laminator pairings | `allow_only_presses` for gloss work | The actual pairings. The press list in config is a guess |
| Gloss/matte and delivery stacking | Grouping rule on `lamination` | Confirm that grouping is sufficient, and whether matte or gloss should lead |
| Pearl runs last on Press 5 | **Not encoded** | Jennifer asked for this on 27 August. She has since confirmed she is fine with the order the lane 5.1 SQL produces, but that SQL's `print_sequence` has not been read here, so whether pearl is in fact last in it is unverified |
| Round-corner colour bands printing black | **Not encoded** | What the sequencing consequence is, if any. It may be a prepress or press-setup issue with no sequencing expression |

## Alternation: the unit, not the fill

**Resolved — the fill.** A block fills up to the cap without overshooting it.
The lane 5.1 cutter lifts are capped at **205 sheets** and the worked example
fills a lift to 204 from four 51-sheet batches. `config/rules.yml` now carries
205, and Jennifer has confirmed she is fine with the order that SQL produces.

**Open — the unit.** Lane 5.1 alternates whole *lifts*: it separates the A/B
rounded and square streams, builds lifts against the 205-sheet cap, then
alternates the lifts. `AlternationRule` alternates *batches* against a sheet
budget. The two produce similar sequences but are not the same computation, and
a lift is a real object in the 5.1 output — it carries a lift number and a lift
sheet total that Tableau reads back for validation. This package has no such
object.

Since the floor has now accepted the lift-level behaviour, the question is no
longer whether lifts are the right model but whether this package should
reproduce them. Doing so means a lift type and a rule that operates on lifts,
which is a change to the closed vocabulary, not a config edit.

## Placeholder numbers

These are invented and drive every duration the tool reports:

- `config/presses.yml` — press ids, names and `sheets_per_hour`
- `config/budget.yml` — `default_minutes`, `changeover_minutes`, and the
  bucket shares
- `config/budget.yml` — `changeover_attributes` assumes stock and lamination
  are what cost a changeover

They are configuration so that replacing them with measured values touches no
code. Until they are replaced, no output from this tool is a schedule.

## Attribute vocabulary

`config/product_classes.yml` invents attribute names (`stock`, `lamination`,
`corner`, `size`, `product`). These need reconciling with what WorkerBee and
Snowflake actually carry. A class that names an attribute nobody writes
matches nothing and fails silently — the cross-check in `config.py` catches
unknown *classes* and *presses*, not unknown *attributes*, because there is no
schema to check them against yet. Adding one is worth doing once the real
vocabulary is known.

## Assignment policy

`sequence_shift` assigns each batch to the least-loaded eligible press. This
is a placeholder and it is changeover-blind. A changeover-aware policy is the
obvious alternative and is exactly what the plan-vs-dispatch decision and the
Aug–Sep changeover measurement should settle. Deciding it before those is
guessing.

## Filler batches — cross-cycle pull-forward

Lane 5.1 pulls future-dated batches into a due-today lift to fill unused
capacity, consumes them once, and keeps them out of cycle 2. The worked
example: a 51-sheet due batch pulls three future 51-sheet batches to make a
204-sheet lift.

`cycle_of` here is a pure partition — cycle 2 never contributes to cycle 1.
This is accepted floor behaviour that the package does not implement, which
makes it a divergence rather than an open design question. It needs either a
pull-forward step or an explicit decision not to have one.

## Are lanes the presses?

Jennifer's conveyor pairings are per lane: 2.1 takes soft touch supers, 2.2
takes gloss then matte, 3 takes matte lam. `EligibilityConstraint` only has
`exclude_presses` and `allow_only_presses`, and in `config/presses.yml` lanes
2.1 and 2.2 both belong to `press_2` — so eligibility cannot tell them apart,
and the pairings cannot be encoded. Rules can already scope to lanes;
eligibility cannot.

Two ways out:

- **Add lane-level eligibility.** Smaller change, keeps presses as the unit of
  capacity.
- **Make lanes the presses.** Model 2.1, 2.2, 3.1 and 5.1 as presses in their
  own right. Closer to how the floor talks — the trial is described as being on
  "lane 5.1", and Jennifer's pairings name lanes, not presses. But it changes
  the domain model and means a supervisor states hours per lane.

This is why `laminated_work_conveyor_pairing` still carries a guessed press
list: encoding the real pairings twice, once per shape, is wasted work.

Note also that "gloss super, then gloss OG, then matte" on 2.2 is an *ordering*
rule, not eligibility. One sentence from Jennifer splits across two config
files.

## Carried over, not resolved here

From the wider programme, unchanged by this repo:

1. Is capacity-first the direction, or do we fix the current list in place?
2. Who owns product rules and templates? Proposal: central and versioned,
   with shift supervisors adjusting availability only.
3. Minimum operator count per shift, and the escalation path below it.
4. Does the last 10% of the press queue app get engineering time, and whose?
5. Go/no-go metrics for a stress test — agreed in writing before the run.

Parked since July: `markBatchesAsPrinted.do` idempotency; which WorkerBee
endpoint releases and transfers a chosen batch list; transfer status by
polling `getBatch.do` vs async push; ECO/Feltmark on Ricoh vs HP; whether to
keep the Ricoh.

Unresolved: the identity source for operator usernames. Shift-level claim via
badge or PIN, since shared floor terminals make username-and-password per
batch the friction that kills adoption. Login is also operator-to-press
assignment and the staffed-capacity signal — one mechanism, three payoffs.

**Operator-side requirements do not exist.** The admin side is well formed;
the operator side is not, and that is where most of the floor pain lives. It
needs a session with the floor lead and press operators before anything is
specified. Nothing in this repo substitutes for that.
