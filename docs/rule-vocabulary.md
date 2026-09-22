# Rule vocabulary

Three primitives. The set is closed.

Anything a planner or operator asks for is a template built from these, not a
new rule type. This is a deliberate ceiling: open-ended rules become a
constraint solver, and a constraint solver is a six-month project that is out
of scope. Holding the line here is what keeps the sequencing layer small
enough to finish.

## 1. Ordering

Within a class, run A, then B, then C.

```yaml
- id: cotton_last
  type: ordering
  class_order: [16pt_matte, gloss_laminated, cotton]
```

Batches whose class is not named keep their relative position at the end of
the list. A class that disappears from the data does not reshuffle everything
else.

## 2. Alternation

Alternate two product styles by a fixed count of batches or sheets.

```yaml
- id: corner_alternation_batches
  type: alternation
  class_a: rounded_corner
  class_b: square_corner
  count: 4
  unit: batches
  applies_to:
    lanes: ["2.1", "2.2", "3.1"]
```

The `sheets` unit exists for the planned move to 204 sheets: with a batch
count, a 20-sheet batch consumes a whole slot. With a sheet budget it does
not. Both are expressible; which one is live is a config change, not a code
change.

Block-filling semantics are **unconfirmed** — see
[open-questions.md](open-questions.md).

## 3. Grouping

Group by size or another attribute within a block.

```yaml
- id: group_by_lamination
  type: grouping
  attribute: lamination
```

Groups appear in the order their first member appears, so grouping never
silently reprioritises work.

Note which primitive lamination uses. Gloss/matte **alternation** breaks
delivery stacking, so lamination is grouped. Writing that constraint as an
alternation rule would encode the opposite of what the floor needs.

## A product class

An attribute combination, e.g. 16pt + matte lamination:

```yaml
product_classes:
  16pt_matte:
    stock: 16pt
    lamination: matte
```

Classes may overlap. A rule tests the classes it names in the order it lists
them and takes the first match, so overlap stays predictable.

## What is not a rule

**Press eligibility.** "Holiday cards excluded from Press 5" and "cotton must
not route to the Ricoh after QC rejection" do not order, alternate or group
anything. They say where work may run at all. They live in
`config/eligibility.yml` and are applied before any rule runs.

Keeping these separate is what makes the closed set hold. Every constraint
that does not fit the three primitives is pressure to add a fourth; most of
that pressure is eligibility in disguise.

**Cycles.** Cycle 1 is a batch with earliest quoted ship date today or
earlier; cycle 2 is the remainder. This is a partition of the input, computed
from the shift date, not a configurable rule.

## Pipeline order

Rules run top to bottom and each sees the output of the one before it.
Grouping then alternating is not the same as alternating then grouping. The
order is therefore part of the configuration, and changing it changes the
sequence.

## Adding a rule

1. Can it be expressed with ordering, alternation or grouping over a product
   class? Then it is a template. Add it to `config/rules.yml`.
2. Is it really about which press may run the work? Then it is eligibility.
3. Neither? Do not add a rule type. Raise it — it is either a gap in the
   product-class model or the start of a constraint solver, and both are
   decisions, not implementation details.
