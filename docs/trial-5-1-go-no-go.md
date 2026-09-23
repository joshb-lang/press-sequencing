# Press 5.1 sequencing trial — go/no-go

Drafted 23 September 2026. **To be agreed by Jennifer Raposo and Josh Barry
before the first trial shift**, and not changed during the trial.

Placeholders in **[brackets]** are the figures to settle together. The point of
this document is that they are fixed in advance rather than interpreted
afterwards.

---

## What this trial tests

Whether a generated print sequence for lane 5.1 is correct, whether the floor
will run it as issued, and whether it improves sheet throughput and the time
lost between jobs.

Lane 5.1 runs holiday cards, cotton and pearlescent — three stock changes, and
work that does not split across presses. It was chosen for that stability.

## What it does not test

- **Adaptation to disruption.** The sequence is hardcoded and assumes 5.1 is
  running and staffed for the whole shift. Call-outs and press-downs are
  excluded by the guardrails below, by design. A clean result says nothing
  about how the approach behaves when an operator calls out or a press goes
  down, and must not be used to argue that it does.
- **SLA.** One lane over this sample cannot move SLA measurably, and print
  events with a username are still not captured, so cause could not be
  attributed. Throughput and downtime are measured instead, because they can
  be attributed.
- **Presses whose work splits across lanes.** 5.1 was chosen because its work
  does not.

## Duration

**[5]** qualifying shifts, consecutive where possible. Josh onsite for shift 1.

## A qualifying shift

A shift counts toward the trial only if all of these held:

- 5.1 was running and staffed for at least **[90%]** of the shift
- The 5.1 operator was not pulled to another press
- Volume was within **[50–150%]** of a normal 5.1 day
- No work was routed to 5.1 that does not normally run there

A shift failing any of these is **void** — recorded with its reason, and
counted neither for nor against. A call-out or a breakdown produces a void
shift, not a failed trial.

Void shifts are not wasted. Their causes are the most useful data this trial
produces, because they measure how often the static assumption stops holding.

## Performance — measured from press production records

**Baseline.** Lane 5.1 over the **[4 weeks]** before the trial, extracted by
**[named method]**, established and circulated before shift 1. The trial
measurement uses the identical extraction and the identical units.

> The units matter. A 10% improvement that turns out to be pages counted as
> sheets is worse than no measurement at all.

**Definitions, fixed in advance.**

- *Sheet throughput* — sheets printed per press-hour running. Void shifts
  excluded.
- *Between-job downtime* — minutes from the press reporting job N complete to
  job N+1 starting. Reported as total minutes per shift, with the stock-change
  count alongside, since sequencing acts on the count of changes rather than
  on how long each one takes.

**Pre-trial check, before shift 1.** Current average stock changes per shift on
5.1: **[ ]**. The sequence produces 3. Expected downtime reduction from that
alone: **[ ]%**.

If that figure is below the target, the target is revised now, not after the
trial. A target set above the achievable ceiling produces a no-go that says
nothing about the sequence.

**Targets.**

| Measure | Minimum | Target |
|---|---|---|
| Sheet throughput vs baseline | **+10%** | +20% |
| Between-job downtime vs baseline | **−40%** | — |

**Mix adjustment.** If trial product mix differs from baseline by more than
**[20%]** on any of holiday cards, cotton or pearlescent, throughput is
assessed per product class rather than in aggregate. Holiday card volume is
ramping seasonally and would otherwise move the aggregate on its own.

## Go — all of these must hold across the qualifying shifts

1. **The list was run as issued.** No more than **[2]** manual reorderings per
   shift, each with a recorded reason, and no shift where the operator
   abandoned the list.
2. **The list was complete and correct.** No batch missing that should have
   been on it; no batch present that should not have been.
3. **The lifts held.** 205-sheet cutter lifts and A/B alternation worked
   downstream. No lift had to be broken or rebuilt.
4. **Nothing due was buried.** No batch shipping today sat below future-dated
   work, and nothing due today was left unprinted at shift end.
5. **Filler batches behaved.** Batches pulled forward from future dates
   appeared once and did not reappear in cycle 2.
6. **No blocking defects.** No abandoned run blocking the queue, no send
   errors, no missing batch tags.
7. **Acceptance.** Jennifer and the 5.1 operator both say they would run it
   again the next day unchanged.
8. **Sheet throughput** at least +10% against baseline.
9. **Between-job downtime** at least 40% below baseline.

Criterion 7 is the one that matters most. Criteria 1–6 are hygiene.

Performance does not buy out a due-date failure: a shift that hits +20%
throughput while leaving due work unprinted fails on criterion 4. Having both
is the point.

## No-go

Any go criterion failing on **[2 or more]** qualifying shifts, or criterion 7
failing at all.

## Stop immediately

End the trial the same shift, regardless of everything above:

- Any double print traced to the trial
- Any batch printed that was not released to print
- A blocked queue that cannot be cleared within **[30 minutes]**

## Recording

Print events are not captured, so this is recorded by hand. One sheet per
shift, completed by the operator or Jennifer at shift end.

| Field | |
|---|---|
| Date / shift / operator | |
| Ran the list as given? If not — how many changes, and why | |
| Any batch missing from the list, or on it wrongly? | |
| Any lift broken or rebuilt? | |
| Anything due today unprinted at shift end? | |
| Errors, stuck screens, blocked queue? | |
| Stock changes this shift | |
| Press-hours running | |
| Sheets printed | |
| Partial lifts (under 205 sheets) sent to the cutter | |
| Would you run it again tomorrow? | |

Log every void shift and its cause on the same sheet.

## What a go authorises

Continued use on 5.1, and proceeding to **shift-start capacity input** as the
next piece of work.

It does **not** authorise a second lane, and specifically not a press whose
work splits across lanes. This trial excluded the conditions that make those
hard.

## What a no-go means

Stop sequencing on 5.1 and regroup on next steps. A no-go is a statement that
this sequence, as built, is not yet usable on this lane. It is not a verdict on
the approach.

## Decision

Jennifer Raposo and Josh Barry jointly, within **[2 working days]** of the
final qualifying shift, against these criteria as written. Result reported to
Andrew Smith and Boris Janssen.

---

## To settle before shift 1

- [ ] Baseline window, extraction method and units — the same for baseline and trial
- [ ] Current average stock changes per shift on 5.1, and the resulting achievable downtime reduction
- [ ] Is the 40% downtime figure a hard gate or a reported target?
- [ ] Number of qualifying shifts
- [ ] Thresholds in **[brackets]** throughout
- [ ] Who fills the recording sheet on shifts Josh is not onsite
