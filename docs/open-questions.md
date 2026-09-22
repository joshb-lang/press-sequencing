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
| Holiday cards excluded from Press 5 | Eligibility exclusion on `product: holiday_card` | Confirm the attribute name and whether the exclusion is absolute or conditional |
| Cotton must not route to the Ricoh after QC rejection | Eligibility exclusion conditional on `qc_rejected` | Confirm that clean cotton really is unaffected |
| Conveyor-to-laminator pairings | `allow_only_presses` for gloss work | The actual pairings. The press list in config is a guess |
| Gloss/matte and delivery stacking | Grouping rule on `lamination` | Confirm that grouping is sufficient, and whether matte or gloss should lead |
| Round-corner colour bands printing black | **Not encoded** | What the sequencing consequence is, if any. It may be a prepress or press-setup issue with no sequencing expression |

## Alternation block semantics

With `unit: sheets` and `count: 204`, does a block:

- **(a)** fill up to 204 without overshooting, leaving the next batch for the
  following block, or
- **(b)** fill until it reaches or exceeds 204?

These give different sequences. The code implements **(a)**, on the reasoning
that 204 is a physical stacking limit and overshooting a physical limit is
worse than undershooting it. A single batch larger than a whole block is
taken anyway, since batches are not split. If 204 is a target rather than a
ceiling, (b) is correct and `AlternationRule.apply` needs a one-line change.

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
