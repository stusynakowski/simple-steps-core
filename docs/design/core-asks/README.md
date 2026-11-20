# Core asks: references, selection and lineage

Everything `simple-steps-core` needs to know to build the reference, selection
and lineage model Simple Steps wants. **This folder is self-contained:** copy
it into the core repo (or point a core session at it) as the context for the
work. It's the source; the app's docs link here rather than copy it.

## What's here

| File | What it is | Read it for |
|---|---|---|
| [model.md](model.md) | The target: object model, definitions, hard and soft rules, naming, live-session behaviour, worked examples | what to build |
| [plan.md](plan.md) | The work: decisions (D1–D5, all settled), milestones M0–M6, changes L1–L43, a test for each with today's result | what to build first, and when it's done |
| [probe.py](probe.py) | Every test in plan.md, run against core alone: PASS / FAIL / SKIP | checking progress |
| [CLAUDE.md](CLAUDE.md) | Rules for an agent working on this in core | how to work |
| [012-formula-text.md](012-formula-text.md) | The app's asks of 2026-11-09 (C40–C44, C39/C36): `formula(text)` meaning what the Python means, and readable refusals. Core's plan step S12 | what the app needs before it drops its parser |
| [014-big-sessions.md](014-big-sessions.md) | The app's asks of 2026-11-17 at v1.0.3: big sessions (C48–C52) and housekeeping, with core's answers at the top. C50 and C52 done for 1.0.4 | what the app needs for large files |
| [015-editing-cells.md](015-editing-cells.md) | The app's asks of 2026-11-20 at v1.0.3: editing cells and runs (C53, C55–C59, K23), with core's answers at the top. C55's by-reference form and C57 done with P7r | what the app needs for cell editing |

Read in that order: model, then plan, then run the probe.

## Run the probe

From a checkout where `simple_steps_core` and `pandas` import:

```bash
python probe.py            # every milestone
python probe.py M0 M2      # some of them
```

It imports nothing from Simple Steps. A milestone is done when every test in
it passes; tests marked "keep green" in plan.md must stay passing throughout.

## Status

First run, 2026-11-02, at the app's current core pin: **16 pass, 49 fail,
1 skip.** After the owner's answers to core's review (the same day; core's
`docs/design/decisions.md` §4): **17 pass, 64 fail, 1 skip**; after the R8
fix for joins, **18 pass, 63 fail, 1 skip**; after S1, **24 pass, 60 fail,
1 skip**. Per milestone
in [plan.md §12](plan.md#12-the-script).

**Where this is edited.** Since 2026-11-02 the copy in core
(`docs/design/core-asks/`) leads; copy it back to the app's `docs/core-asks/`.

## Where this came from

| Source (in the Simple Steps repo) | What it holds |
|---|---|
| `docs/dev_plan/130-reference-selection.md` | the history: how each rule was reached, the evidence, the app-side work |
| `docs/core-proposals/008-core-changes.md` | the full list of older core asks (C, K, R IDs); plan.md §13 maps the ones this replaces |
| `scripts/ui_status/` workflows 06 and 07 | the same steps in the app's UI, with EXPECT / TODAY / VERDICT notes |
