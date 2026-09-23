# Press sequencing — EP manufacturing

Context for working on press sequencing at MOO's East Providence site.
Owner: Josh Barry, Data and Planning. Last updated 21 September 2026.

## What this is

Deciding the order in which batches are sent to presses at EP, given physical
constraints (corner alternation, lamination pairings, delivery stacking) and the
presses and operators actually available on a given shift.

This repo is the sequencing logic. It is **not** the press queue app, and it is
probably not a portal — see "Where the UI lives" below.

## Read this before proposing anything

**The prior attempt made SLA worse.** The Press Queue app went to the floor in
late August 2026. SLA deteriorated over that period and recovered after we
reverted to manual scheduling on 8 September. The period is confounded — short
shifts, two scheduling paths running in parallel, double-print incidents — so it
is not proof the approach is wrong. But nothing here is proven to work, and we
cannot yet explain the SLA movement in either direction because print events are
not being captured.

Do not write code or docs that describe the tool as a proven win.

**Sequencing may not be the binding constraint.** Before building more, we want
three numbers from Aug–Sep: where time actually went on missed-SLA batches
(queue wait vs press vs post-press vs reprint), how many were reprints or double
prints, and how press hours split between changeover, idle and unstaffed. If
changeover is a thin slice, the ceiling on any sequencing work is low.

## Current state

**Logic layer — built, July 2026.** SQL over a Tableau Prep flow, output to
`dw_wf.print_sequencing`. Three rules, all hardcoded as constants:

- `press_time_budget` — each work type gets a time window from press speed and
  anticipated volume. Overflow truncates the list unless another bucket has room
  to absorb it, in which case buckets readjust.
- Corner alternation — lanes 2.1, 2.2, 3.1 alternate four batches rounded / four
  square. Planned change to 204 sheets (to handle small batches and group less
  efficient packing) is **not** implemented.
- Cycles — cycle 1 is a batch with earliest quoted ship date today or earlier;
  cycle 2 is the remainder.

**Execution layer — ~90% built, not in use.** `timw-moo/moo-press-queue`. Reads
the sequence, pulls batch PDFs from S3, renders EAN-13 batch-tag travelers and a
run manifest, sends over JDF in sequence, ingests JMF, calls
`markBatchesAsPrinted.do`. Shadow-verified against live data 13 July 2026.
Operators are currently on WorkerBee and batch selection; "live" means the app
can be used, not that it is doing anything.

## Hard constraints

These are non-negotiable and have each caused a real defect.

**Action log vocabulary is shared.** Print events go to
`operations_user_action_log`, which other systems write to and the data team's
flows read from. The action string changed from `printed` to
`batch status is printed` once and silently dropped rows until the filter was
widened. **Agree any new action string with the data team before writing it.**
Do not invent a third.

**Writes must be additive.** If this becomes the only writer of print events and
only part of the floor uses the tool, an absent event is indistinguishable from
absent work — data worse than today's, because today's gaps are visible. Whatever
WorkerBee already writes keeps writing. Add press-level coverage flags or
reconcile against HP logs so "nothing ran" is distinguishable from "ran
elsewhere".

**Every write needs a dedupe key.** Retries, resends and QC reprints all fire the
writer. Key on batch ID + press + event type + run. Related open question:
whether prod `markBatchesAsPrinted.do` is idempotent — unconfirmed.

**Batch ID is a first-class field.** Filename prefix and extension
inconsistencies break joins across WorkerBee, HP and Snowflake. Never recover a
batch ID from a filename.

**Two events, not one.** Sent-to-press and completed-per-JMF are different facts.
Writing both also surfaces abandoned runs, which currently block queues
invisibly.

## Rule vocabulary — closed set

Three primitives only. Anything else is a template built from these, not a new
rule type. Open-ended rules become a constraint solver; that is a six-month
project and out of scope.

1. **Ordering** — within a class, run A, then B, then C.
2. **Alternation** — alternate two product styles by a fixed count of batches or
   sheets.
3. **Grouping** — group by size or another attribute within a block.

A product class is an attribute combination, e.g. 16pt + matte lamination.

## Physical constraints to encode

Currently held as operator knowledge and routinely violated:

- Gloss/matte alternation breaks delivery stacking
- Conveyor-to-laminator pairings
- Cotton must not route to the Ricoh after QC rejection
- Holiday cards excluded from Press 5
- Round-corner colour bands printing black

## Architecture — decided and undecided

**Decided.** Capacity is an input. Supervisors state presses and hours available
at shift start and the sequence recalculates. Rules are configuration, not
constants. Tableau is dropped as the *pipeline* (direct SQL instead, removing the
5am–2pm refresh window and the manual 2pm flush) but kept as a *reporting
surface* — workbook 6607 has a real audience, point it at the same tables.

**Undecided: plan vs dispatch.** Two shapes on the table.

- *Allocate-then-fill* — admin lays product-class blocks on a per-press timeline;
  engine fills blocks from open batches. Visible and plannable, but a plan made at
  06:00 is stale by mid-morning, which is the failure mode we keep hitting.
- *Dispatch* — no global plan. Each press asks "what next?" and the engine answers
  from current state. Degrades gracefully under short staffing and self-heals
  after abandoned runs, but is myopic on changeover unless it looks ahead, makes
  material pre-staging harder, and gives supervisors nothing to look at.

Current lean: configuration layer feeding a dispatcher, with a timeline kept as
the surface for setting the standard and comparing plan against actual, rather
than as the thing that assigns work.

**SLA must argue back.** Whatever the shape, when a plan strands due-dated work
it has to say so — e.g. "this plan leaves 14 batches shipping today unscheduled".
A capacity-first plan that hides what it stranded will make SLA worse while
looking more organised.

## Where the UI lives

Probably not here. MOOsaic is an active time-boxed build-vs-buy PoC for a single
manufacturing flow, and its stated long-term vision is an operator walking up to
a press, loading the media it tells them to, and work flowing with no manual
batch manipulation. It already has batch generation (operator selects press and
station, sees available substrates), a station view, and BFF contracts for
operator views. See PPUR-2180 / PPUR-2181.

What MOOsaic lacks is the rules that decide what comes next. Treat this repo as
the sequencing brain behind MOOsaic's station view, not a competing portal.
Adding a fourth surface next to the Press Queue app and WorkerBee is how you get
a fourth thing nobody uses.

**Phase 0 needs no UI at all.** Sequencing as a dbt model in Snowflake
(scoped as DW-8440), press availability as a small table a supervisor edits,
output as a table any front end reads. Rules become dbt config.

## Systems

| System | Role | Direction |
|---|---|---|
| WorkerBee | Order/batch system, batch selection UI operators use today | Stays; upstream |
| Snowflake / dbt | Target for sequencing model, DW-8440 | Growing |
| Tableau | Prep flow 450, workbook 6607 | Exit as pipeline, keep as reporting |
| `timw-moo/moo-press-queue` | Execution — JDF send, travelers, mark printed | Stays |
| `timw-moo/jdf-api` | JDF/JMF rules and docs | Stays |
| MOOsaic | Single manufacturing flow PoC, operator surfaces | Likely host for UI |
| Enfocus Switch | Workflow engine driving Phoenix | Being exited for MOOsaic — do not build into it |
| tilia Phoenix | Imposition engine | Being replaced by in-house engine (PPUR-1999) |
| PrintOS / Site Flow | Parallel print path | Source of double prints — needs a batch lock |

**Site Flow is not the answer and the question is closed.** It solves batch
formation, which MOO has already solved. It does not sequence work across coupled
finishing lines under physical constraints. Do not reopen.

## Open decisions

1. Is capacity-first the direction, or do we fix the current list in place?
2. Who owns product rules and templates? Proposal: central and versioned, with
   shift supervisors adjusting availability only.
3. Minimum operator count per shift, and the escalation path below it.
4. Does the last 10% of the press queue app get engineering time, and whose?
5. Go/no-go metrics for a stress test — agreed in writing before the run.

Parked since July: `markBatchesAsPrinted.do` idempotency; which WorkerBee endpoint
releases and transfers a chosen batch list; transfer status by polling
`getBatch.do` vs async push; ECO/Feltmark on Ricoh vs HP; whether to keep the
Ricoh.

Unresolved: the identity source for operator usernames. Login should be
shift-level claim via badge or PIN — shared floor terminals mean
username-and-password per batch is the friction that kills adoption. Login is
also operator-to-press assignment and the staffed-capacity signal; one mechanism,
three payoffs.

**Operator-side requirements do not exist.** The admin side is well formed; the
operator side is not, and that is where most of the floor pain lives. Needs a
session with the floor lead and press operators before anything is specified.

## People

- Timothy Wessman — built the press queue app, MOOsaic
- Jennifer Raposo — floor lead, most of the operational feedback
- Rich Ives — Tableau and data, owns the action-log flows
- Andrew Smith, Boris Janssen — ops stakeholders
- Thomas Cornish — prepress

## Working conventions

- Do not present unproven work as proven. Flag confounders.
- Prefer configuration over constants. If a number would be edited by a
  supervisor, it is not a literal.
- Any change touching the action log gets reviewed by the data team first.
- Phase small. The last rollout failed at 90% complete with no requirements and
  no QA; a small thing that works completely beats a large thing that mostly does.

---

# Exec deck — 21 September 2026

`print-sequencing-exec.pptx`, 11 slides, by Josh Barry for Andrew Smith, Boris
Janssen and Timothy Wessman. Same date and author as the context above, and
framed in its speaker notes as "a proposal to argue with, not a status update".
Recorded here because it carries the phasing, the ask and the risk list, none
of which are in the document above.

Note that slide 6 repeats two claims the 23 September addendum below corrects:
"Holiday cards — Press 5 excluded", and corner alternation "every 204 sheets".

## The argument

**The root cause is a missing input, not a logic defect.** The sequencing logic
is not wrong; it has no input for how many presses and operators are actually
running, and no way to be told. That framing is the reason the fix is cheaper
than it looks.

The system assumes every press running and every station staffed, a full day of
available hours, rules fixed in SQL, and changeover minimisation as the thing to
optimise. The floor is short shifts with two operators common and no defined
minimum, presses down with work redistributed by hand, urgent batches buried,
and operators reverting to WorkerBee — taking the measurement with them.

**The shape of the change** is "derive then sort" becoming "allocate then
fill": presses and hours available this shift, plus rules as settings, produce a
timeline of product-class blocks per press, which are then filled from open
batches. The quiet win is that today's constants become configuration.

## Six things the floor keeps hitting

- **Double printing** — legacy and new paths can both send a batch. No
  cross-system lock.
- **Urgent work buried** — the queue optimises changeover, not due date, and
  never truncates for reality. One batch sat at the bottom of 130 batches and
  6,500 sheets.
- **Visibility gaps** — missing batches, cleared presses still showing sheets,
  abandoned runs blocking the queue.
- **5am–2pm only** — a Tableau refresh artefact. The 2pm flush is manual, and an
  outage stopped night-shift printing.
- **Constraints in people's heads** — gloss/matte stacking, lam pairings, cotton
  routing, Press 5 exclusions, encoded nowhere.
- **Measurement broken** — no print events with a username in the action log, so
  SLA movement cannot be explained in either direction.

Underneath all six: built as a proof of concept in one to two months, with no
requirements and no QA.

## Closing the data loop — the smaller half, and the one to do first

Operator signs in at the press → Press Queue app sends over JDF → press returns
JMF status → sent and completed events written with a username → warehouse model
DW-8440 → plan versus actual, and SLA.

The data team asked for this on 8 September. The write itself is about a day of
work; the event vocabulary, dedupe key, login UX and reconciliation against
non-app printing are the real scope.

## Phasing

- **Phase 0 — make it match the floor.** Shift capacity input, app writes print
  events, operator login, direct SQL, batch lock. Four weeks, no new UI.
- **Phase 1 — the admin surface.** Product classes, the press timeline, standard
  templates the floor follows by default. Needs Phase 0 data.
- **Phase 2 — the rule engine.** Ordering, alternation by batches or sheets,
  grouping. The 204-sheet change lands here as a setting.
- **Phase 3 — plan versus actual.** Only possible once Phase 0's event history
  has accumulated.

Phase 0 stands alone and everything else depends on it, which is the argument
for shipping it on its own rather than inside a bigger release. Alongside it: a
supervised stress test on one press with one operator, and written go/no-go
metrics agreed before the run — the shadow run skipped in August.

## The ask

Approve Phase 0 on its own, and give it a stress test with metrics agreed
beforehand:

- Shift capacity input, so the plan reflects the presses and people running
- Print events written with a username, so changes can be measured
- One press, one operator, written go/no-go — before anything wider

If capacity-first is approved, the next step is a requirements session on the
operator side with Jennifer Raposo and the press operators.

## Risks — each has already happened once, in some form

- **Shipping it all at once.** The timeline is the interesting part; capacity
  input is the valuable part. Together, the valuable part waits.
- **Partial adoption poisoning the data.** If the app is the only writer and half
  the floor uses it, zero events looks like zero work.
- **Rebuilding before we diagnose.** SLA fell while the tool was live. Until we
  know why, more build is a bet rather than a fix.
- **Due dates falling out of view.** A capacity plan that doesn't surface what it
  stranded will make SLA worse while looking more organised.
- Until there is a batch-level lock, double printing stays possible no matter how
  good the planner is.

---

# Addendum — 23 September 2026

The two sections above are the 21 September position, left unedited. This
section records what the #press-queue-dashboard Slack channel establishes since
then. Where they disagree, the disagreement is flagged here rather than resolved
by editing above — the corrections need Josh's and Jennifer Raposo's
confirmation before the earlier text changes.

## A single-press trial is in flight

Josh and Jennifer Raposo are re-trialing the print sequence on **one press:
5.1** (holiday cards, cotton, pearlescent). Announced 23 September. The portal
was never shut down — Timothy Wessman, 16 September: "live just means the app
can be used, it's not doing anything" — so there is nothing to redeploy.

Press 5.1 was chosen because it is three stock changes and work belonging to a
single press, rather than work that splits across presses (16pt BC). Dedicated
sequencing SQL deliberately **mimics current floor behaviour** — cycle 1 /
cycle 2 on `earliest_quoted_shipping_date`, then the configured `print_sequence`
grouping product sizes — because the goal is adoption and acceptance from the
floor, not better sequencing. Josh onsite with Jennifer at shift start on
24 September to document.

Josh's own stated limitation: the sequence is hardcoded and does not adapt to
press or operator availability. "When do we ever have 2 days of consistency
with presses."

Treat this trial as a behaviour-and-acceptance test. It is not evidence that
sequencing works, and nothing should describe it as such. It is also narrower
than the deck's Phase 0 — it adds no capacity input and no print events, so it
does not close the measurement gap.

## Corrections to "Physical constraints to encode"

**Holiday cards are NOT excluded from Press 5.** The document and the deck both
say they are. Jennifer asked on 26 August to have "holiday cards and cotton
added to press 5 sequence", chased it on 27 August ("still not seeing holiday
cards as part of press 5 sequence, only pearl and cotton"), and press 5.1 now
runs exactly that mix. Josh confirmed with Jennifer on 23 September that she is
fine with the order the lane 5.1 SQL produces. Whatever the original exclusion
referred to, it does not hold today. Do not reinstate it from the older text.

**Cotton and the Ricoh is probably unconditional.** The document makes it
conditional on QC rejection of the batch. Jennifer, 26 August: "Cotton is on the
list for ricoh however we do not print cotton there. QC rejected quality from
ricoh and it has been printing on hp." That reads as QC having rejected the
quality coming *off the Ricoh*, so cotton does not route there at all.

**Conveyor-to-laminator pairings are documented, not unknown.** Jennifer,
26 August, after the closing meeting:

- Press 2.1 — soft touch supers (conveyor to lam 2.1)
- Press 2.2 — gloss super, then gloss OG, then matte (so all gloss prints together)
- Press 3 — matte lam

This also confirms lamination is **grouped, not alternated**: gloss/matte
alternation is what breaks delivery stacking. Thomas Cornish modelled the
proposed sequencing in a spreadsheet linked in that thread.

**Pearl runs last on Press 5**, per Jennifer, 27 August ("can pearl be last
instead of first?"). An ordering rule, not captured above and still not
encoded: Jennifer's sign-off is on the order the 5.1 SQL produces, and that
SQL's `print_sequence` has not been read here, so whether pearl is actually
last in it is unverified.

## Corrections to the corner-alternation rule

The lift cap is **205 sheets, not 204**. Josh, 23 September: the SQL "builds
cutter lifts capped at 205 sheets", and the worked example — a 51-sheet
due-today batch pulling three future 51-sheet batches into a 204-sheet lift —
is filling *up to* a 205 cap without overshooting it. 204 is an outcome of
4 × 51, not the limit. This also settles the fill semantics the scaffold had to
guess at, and Jennifer's sign-off on the 5.1 order confirms the behaviour is
accepted on the floor.

## Two behaviours the closed rule set does not cover

Both come from the Press 5.1 SQL and neither is expressible as ordering,
alternation or grouping over a product class. They need a decision before the
rule vocabulary can be called complete.

**Filler batches — cross-cycle pull-forward.** Future-dated batches are pulled
into a due-today lift to fill unused capacity, are consumed once, and must not
reappear in cycle 2. Cycles as described above are a pure partition; this is
not.

**Alternation happens at lift level, not batch level.** The SQL separates the
A/B rounded and square corner streams, builds lifts capped at 205 sheets, then
alternates the *lifts*. A lift is a first-class object with a number and a
sheet total — the output carries `Roundedcorner`, lift number, lift sheet
total, cycle and final sequence row for validation in Tableau.

## Unresolved on the floor

Substrate-then-date ordering versus date ordering. Andrew Smith, 27 August:
sequencing by substrate then date minimises paper changes and helps achieve
total plan for the day, but "it does present issues if the queue isn't worked
when expected (3rd shift and 1st shift)". Jennifer: it "doesn't guarantee we
will get through all the colors in a shift", and Luxe in particular should go
by date, since Luxe is run third in the morning so it finishes and dispatches
within first shift. That thread never concluded.

## This repository

Scaffolded 22 September: the closed rule vocabulary, press eligibility as a
separate concept, capacity as an input, and SLA argue-back, with the July rules
expressed as configuration under `config/`. Press speeds, makeready minutes and
budget shares remain placeholders, and the constraints that are still guesses
carry `status: unverified`, which `press-seq validate` prints.

**Applied to `config/` on 23 September**, on the strength of Jennifer's
sign-off on the lane 5.1 order: the holiday-cards exclusion removed, the sheet
budget corrected to 205 with the fill semantics confirmed, and lane 5.1 added
to `press_5`.

**Not applied, and why:** the cotton/Ricoh rule still carries its
`qc_rejected` condition and the laminator pairings still carry a guessed press
list — neither is covered by a sign-off about lane 5.1, and the pairings are
additionally blocked on whether lanes should be modelled as presses. Pearl-last
is not encoded. `docs/open-questions.md` is the list of what a reader should
not assume.
