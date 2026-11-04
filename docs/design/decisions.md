# Decisions

> **Every decision, in one place** (organised 2026-10-31; the open ones
> brought to the top 2026-11-03). Open ones are grouped by the step of
> [plan.md](plan.md) that needs them, in the order the steps run, so the next
> one to make is always near the top. The design they decide is
> [model.md](model.md); the app's requirements are
> [core-asks/model.md](core-asks/model.md). When a decision is made, its row
> moves to §3 with the date.

## 0. Needed from you now

Opened by the 2026-11-03 review ([model.md §5, §8, §10](model.md#8-states-in-a-session);
the evidence is in [history/session-states.md](history/session-states.md)).
Each was run; each has a recommendation.

**States in a session.** Today a step's state is kept as flags, set by edits
and cleared by runs, so it remembers the order of events instead of saying
what the workflow is now.

| | Decision | Today (run 2026-11-03) | Recommended |
|---|---|---|---|
| **SM** | **The session model** ([model.md §8.1](model.md#81-the-proposed-session-model-sm)): the session keeps only the workflow and a store of results filed by **run key** (spec id + the data versions read). An edit changes the workflow and re-checks at once; a run adds the missing keys, `run(x)` making `x` current. Every state is derived: `completed` when the store holds its key now; `stale` when it holds an earlier one, saying what differs; `invalid` when it has problems now, still showing its last result. Replaces SS1–SS4 below (proposed earlier the same day); reverses **D40**'s *read stale* mark; brings K22 (several results per step) into S11 | flags: an expression put back stays `stale`; a reader made `invalid` loses its values; a run on a stale input says `completed` (with a warning naming the input); an `invalid` step carries a stale reason | **yes** |
| ~~SS1–SS4~~ | computed states; keep an `invalid` step's values; a run on a stale input is `stale`; no stale reason on `invalid` | — | → **SM** |
| SS5 | `needs_run()` leaves out empty steps, and failed steps whose spec and inputs haven't changed (relates to **D37**, an `empty` state) | lists an empty step as `staged`; leaves out a failed step | **yes**: owner, 2026-11-03 |
| SS6 | Core has no `running` state; it stays the app's | none in core | **yes**: owner, 2026-11-03 |
| SS7 | A stale step's reason is among its warnings, where the app reads it (core-asks L42); delete-anyway, `k.remove(name, force=True)` (L43d, **CA-6**) | the reason is in output metadata only; no delete-anyway | **yes**: owner, 2026-11-03 |

**Rows when a source's data changes** (model.md §10).

| | Decision | Today | Recommended |
|---|---|---|---|
| D-picks | A saved pick into a source's rows: when the source's data is replaced, core hashes its rows, gives rows it has seen their ids back, and **rewrites the pick's row number** in the expression when its row moves; a pick whose row's hash is gone (deleted, or a value edited) is `invalid`, naming it | the pick follows the position: a row inserted at the top makes it pick another row, silently | yes; a declared key column later, for value edits |

**How rows pair** (model.md §5). The older reshaping rules and the core asks
disagree; the code follows the core asks.

| | Decision | Reshaping rules (2026-10-27) | Core asks / code now | Recommended |
|---|---|---|---|---|
| D-child | A column argument from a parent into its child: each item takes its parent's value | allowed | refused, writing `join(…, on="#v")` (**CA-C**) | keep the code: one rule, a join. **yes**: owner, 2026-11-03 |
| D-subset | A column argument from a step missing some rows | blocks those rows, runs the rest | refused, writing the join | keep the code. **yes**: owner, 2026-11-03 |
| D-cell | A lineage cell shows the ancestor's row number as of the run, or now | — | now (S5-D4); core-asks model.md M3 says "as of the run" | now, and correct M3. **yes**: owner, 2026-11-03 |

**Expressions: simple and robust** (opened 2026-11-03 from the tutorial,
[tutorial/](../../tutorial/); lesson ids P…, V…, R…, A…, C… are in
[tutorial/capabilities.md](../../tutorial/capabilities.md)). Most of the
tutorial's ✗ share one cause: an expression can mean more than it shows. It
can be written several ways, it takes settings that do nothing, and core fills
in a verb, a binding or a name you didn't write. The aim: **one way to write
each thing, and a saved expression that says exactly what runs.** In the
order recommended: EX1–EX2 are small and close the five new findings; EX3–EX4
are removals; EX5–EX6 are S3's binding work.

| | Decision | Today (run 2026-11-03) | Recommended |
|---|---|---|---|
| **EX1** | **Every setting is checked, or refused.** Each modifier's settings come from one typed schema (`MODIFIERS`); an unknown setting, a setting that changes nothing, or a positional argument is refused when the step is declared, and the refusal writes the right form | `mod.map(axis="columns")` accepted and ignored (V10); `mod.widen(wf["i"])` accepted, the step fails with `None` (R11); an unknown argument says the tool "accepts (none)" (A7) | **yes** |
| **EX2** | **A verb owns its output columns.** A `filter` returns exactly its input's columns, a `map` exactly its named output; the plan lists them, and a test checks run against plan for every verb | a `filter` given a column argument adds it as a column (A4b) | **yes** |
| EX3 | **One grammar**: `tool[modifiers](input, arguments)`, `mod.reshape(settings)(input)`, `join`/`zip_`/`stack(…)`, `wf["s"][rows][cols]`. Retire `mod.x(over=…)` and `op("identity")[mod.reshape(…)]` | all three spellings of a reshape work (F7); `examples/all_orchestrations` uses `over=` | **yes**: owner, 2026-11-03; the old spellings removed, the examples and tests rewritten in the same piece |
| EX4 | **Remove what doesn't earn its place**: `axis` everywhere; `retries=` on verbs (`mod.retry` does it); `map(where=, replace=)` (overlaps `filter` + `join`, V11). Build verbs from a few primitives where possible (pack, unpack, choose, reorder, match), as grouping already is (H3) | all present | **yes**: owner, 2026-11-03: `axis`, `retries=` on verbs and `map(where=, replace=)` all removed |
| EX5 | **An input is a step or a pick, never a computation.** A pick may be a tool's input (D6, P16); an inline tool call or combine may not (C11), so every grid shown is a named step with a state | a pick as input refused (P16); an inline operation as a combine's input is `invalid` (C11) | open: not chosen on 2026-11-03 (picks as inputs are already yes under **D6** / core-asks L34; refusing an inline computation is what's open) |
| EX6 | **Inference is written into the expression at staging**, never decided again at run: the verb (`to_f(wf["v"])` saved as `to_f[mod.map()](…)`), the binding (`temp=wf["v"][cols["temp"]]`), the output name (after the step, **D9**). If core can't decide, the step is `invalid`, listing the candidates. `auto` chooses only verbs that can't change the row count | done for picks (P14); verb and binding inferred again at each run; `auto` chooses `filter` (V8b, against **D20b**) | yes; this is S3's binding (CA-A) and S4's naming, with **D20b** and **D21** |
| EX7 | **One printed form that round-trips**: `parse(print(x)) == x` for every expression; the saved form is the printed form. A property test generates expressions and checks it (beside L40) | expressions print; no round-trip test | **yes**: owner, 2026-11-03, with S3 |
| EX8 | **The tutorial is the contract.** `tutorial/tutorial.py` runs in the test suite; a decision that lands changes its lesson's `want` in the same commit | run by hand | **yes**: owner, 2026-11-03: both tutorials run in the test suite |
| EX9 | Assigning a bare Python function as a value is refused, pointing to `@tool` and the catalog (D11) | stored as a value, `completed` | **yes**: owner, 2026-11-03 |
| **EX10** | **`widen` applies only to a column of dicts** (owner, 2026-11-03: **decided**). Tuple and list cells no longer widen to `c0, c1, …`: a tool returns a dict for fields, `expand` unpacks a list. When the column's type is known and isn't a dict, the step is `invalid` at once; when it's unknown, a cell that isn't a dict fails, the other rows run; a `None` cell gives `absent` fields (with C6, one meaning of no value) | tuples and lists widen by position to `c0, c1, …`; a `None` cell fails | **decided**; lands as its own piece, with `examples/all_orchestrations` (`split`) and its tests |
| EX11 | **A return type is declared or unknown, never guessed.** No annotation, `Any` or `object` is *unknown*: the tool runs, its plan says the type is unknown and why (*"declare the return type"*), `auto` may only infer `map` for it, and checks that need the type (EX10) happen per cell at run. A declared type (`-> float`, `-> dict`, `-> list[str]`, a record class) gets every check at declaration | unannotated tools run; `auto` infers `map` for them; the plan states the type `unknown` before a run and the observed type after (K27, checked 2026-11-03 by tutorial/handover.py); per-cell checks at run and the plan's *"declare the return type"* are what's left | yes |
| EX12 | A lineage condition (`wf["e"][row["v"] == 1]`) gets no warning that its rows are positions: it isn't positional (P9b) | warns *"rows … are positions, and expand doesn't fix row order"* | **yes**: owner, 2026-11-03 |
| EX13 | **A string assigned to a step stays a string value; formula text is parsed only when asked**: `k["g"] = formula("to_f[mod.map()](wf['p'])")`. `formula(text)` returns an operation, checked against the kernel's catalog when it's assigned, like any other expression. It is the app's `operation_formula.py`, ported (plan S3): it reads the text as a syntax tree and never runs it (checked 2026-11-03: `__import__`, `open`, lambdas and `__subclasses__` all refused, nothing ran). The app's formula bar calls it | `k["g"] = "to_f[…]"` stores the text as a string; no parser in core; the app's parser still uses `grid` names (`shape_verbs`, …) | **yes**: owner, 2026-11-03 |

**Conditions that make every expression easier** (opened 2026-11-03).
Ten rules core enforces, each removing a group of the tutorial's findings.
With them, every error is either `invalid` at once, writing the fix, or one
`failed` or `absent` cell at run, the other rows running.

| | Condition | Fixes | Owner, 2026-11-03 |
|---|---|---|---|
| C1 | Anything that can be checked when a step is written is checked then; a run fails only on data, cell by cell | `widen` which column and the `key` collision, both failing at run with the reason only on a cell; R11; V10 | **yes**. First piece done 2026-11-03: `widen` (which column, a missing `column=`, a step for a column name) and the `key` collision are problems when written |
| C2 | A return type is declared or unknown, never guessed (EX11) | lets C1 work; safe inference; exact plans | **yes** |
| C3 | A step's columns are its input's, plus or minus what its verb says, and nothing else. Shown in full; stored as **ST** below, so carrying a column costs no memory | A4b; the melt a bare `expand()` makes on several columns | **yes, with ST**. A4b done 2026-11-03, and with it a silent wrong answer it hid: a column argument named like an input column replaced that column in a `filter` or `group` output |
| C4 | A step never replaces a column by accident: a name that exists already is refused unless replacing is written (`mod.rename` first, or `replace=True`) | `widen` silently overwriting `name` with a field of that name | **yes**. Done for `widen` 2026-11-03: a field named like a carried column is a problem when the fields are known, else fails at run; `widen(replace=True)` says it's meant |
| C5 | A reshape with no tool names the column it acts on (`widen(column=)`, `expand(columns=)`), unless only one column could be meant | the melt; `widen` guessing among dict columns | **yes** |
| C6 | No value means one thing in every verb: a missing input gives `absent`, and one warning per step with the count; `[]` gives no rows, no warning | three behaviours today: a tool's `expand` of `None` warns, `expand(columns=)` doesn't, `widen` fails the cell | **yes** |
| C7 | Each row of a source has an identity, from a key column or else from its content (**D-picks**) | P15 | **yes** |
| C8 | What core infers is written into the saved expression; only verbs that can't drop rows are inferred (EX6) | V8b; bindings decided again each run; `value` | **yes** |
| C9 | `run(x)` makes `x` current; a result computed from stale inputs is never `completed` (**SM**) | S5 | **yes** |
| C10 | One way to write each thing (EX3) | three spellings of a reshape | **yes** |

**Wiring rows between steps** (proposed 2026-11-03, from the tutorial):
what's asked of a user is to know how two steps' rows relate before writing
the expression that meets them; core already knows. Run 2026-11-03: a
refusal's fix is only text (a `Problem` has code, step, argument, row,
severity); `join(wf["v"], wf["h"])` with no `on=` is refused though core
knows `#v`; a join takes two inputs.

| | Decision | Today | Owner, 2026-11-03 |
|---|---|---|---|
| WR1 | One function answers how two steps' rows relate (same rows, subset, child, group, unrelated; the nearest shared ancestor; the join that meets them), used by every refusal, plan and view; it replaces the five helpers (observations F4, H2) | five partial helpers; a child and its parent described as "some would have no partner" | **yes** (with WR2) |
| WR2 | A refusal carries its fix as an operation, `Problem.fix`; `k.fix(name)` puts it in the step's place (a button in the app). Never applied unasked | the fix is in the message text only | **yes** |
| WR3 | `join(a, b)` with no `on=`, on related steps, joins on the nearest shared ancestor's lineage and writes `on="#v"` into the expression (EX6); unrelated steps still need `on=`. `zip_` becomes join's same-rows case | refused: "join needs on=" | **yes** |
| WR4 | One join for several tables, `join(a, b, c, on=[…])`, as one step | two steps; `join()` takes two inputs | open: not chosen |
| WR5 | A join that drops rows warns with the count | not checked | open: not chosen |
| PK3 | `k.trace(step, rows, to=ancestor)`: the pick of the rows behind them | `k.cell` shows one cell's inputs; no pick | open: not chosen |

**Storage** (opened 2026-11-03). Measured by allocation (`tracemalloc`) on a
200,000×10 source (16 MB), `sort` → `filter` → `rename` → `select` → `map`:
**211 MB** held, about 35 MB a step, `rename` included. Counting the data's
column buffers alone (8.2 MB on a 20,000-row copy; a first count, 11.4 MB,
counted a shared buffer once per step) missed the main cost: each
row-aligned step kept a fingerprint per input row for per-row staleness
(`meta["row_reads"]`) as a Python list `[row id, hex string]`, about 160 bytes
a row, twice the data. **Fixed 2026-11-03, no behaviour change:** kept as
one uint64 a row on the input's own index, saved in the same
`[[row id, hash], …]` form: **54 MB** held. What's left: `sort` copies every
row (16 MB), since without a row map reordering means copying; each step's
own fingerprints (1.6 MB). `select` and `drop` copied the columns they keep
(14 MB): **fixed 2026-11-03**, built from the input's own columns: **40 MB** held.
Images and files make a copy per step impossible.

| | Decision | Today | Recommended |
|---|---|---|---|
| **ST** | **A step stores only what it adds; everything is filed by content.** (1) Each output is a **row map** (for each row, the input row it came from: one integer; none when the rows are the input's in order) plus **the columns it makes**. A column it carries stays with the step that made it, read back through the row maps, and gathered into memory only for the columns a tool is bound to. (2) **Columns are filed by content hash**, so a column is stored once however many steps and runs hold it. (3) **A large value (an image, a file, a big array) is a media handle**: its content hash, type, size and a preview, the bytes kept once in a blob store (memory up to a limit, then a folder or a bucket) and loaded only when a tool reads it or the view shows it. Its data version is its hash (D57). (4) **A result is a run key → a row map and column hashes**, so keeping earlier results for SM (undo, stale values shown) costs little. (5) **A memory budget**: keep each step's current result and its last few; drop any column or blob nothing points to; the app sets its own budget. The view shows every carried column, as today; none of this appears in an expression or the UI. Is SM's store, and brings in **E-D1**, **K22** (several results per step) and **R7** (media handles); the row map is the one link back per row that lineage needs (observations F1, H3) | every step that keeps rows copies them all; one result per step; no media handles | **yes**: owner, 2026-11-03. Lands with SM (plan step S11) in pieces: compact row fingerprints (**done**, 211 → 54 MB above); `select` and `drop` sharing the columns they keep (**done**, 54 → 40 MB); row maps and carried columns (no behaviour change, the tests green); then the content store; then media handles |

The two wrong answers, **D-picks** (P15, silent) and **SM** (S5: `completed`
on a stale input, with a warning), come before all of these: neither depends
on grammar, and both break the rule that an expression means what it shows.

**Already answered on 2026-11-02:**

| | Decision | Owner, 2026-11-02 |
|---|---|---|
| N1 | The app waits for row numbers: S5 before G | **yes**: settled before more app development. **D51** decided |
| N2 | May an inferred verb be `filter`? | **no**. **D20b** decided |
| N3 | The modifiers core-asks left out | **all kept**; written order is applied order. *Squeeze*, the opposite of `widen`, is core's existing `mod.pack` |
| N4 | Where core-asks is edited | **the core copy leads** |

## 1. How to answer

Each row says what you have already said (*You said*), and what is
recommended. Where you've said something, it only needs a yes. "Yes to all
recommended in a group, except …" is a fine answer.

**Already answered in your own words, to confirm:** D1, D2, D3, D4, D6, D9, D11, D13, D14, D15, D16, D22, D23.

> **2026-11-02: the core asks ([core-asks/](core-asks/)) settle much of
> tiers 1–3.** What they decide, and which rows below they supersede, is in
> [§4](#4-core-asks-reconciled-2026-11-02). Where §4 and a row below
> disagree, §4 wins. Rows below that §4 settles are marked **→ CA-…**.
>
> §0 lists what was needed from you; it's empty now. Everything else open
> has a recommendation, and is confirmed when its step lands.

## 1b. By importance

Ranked (2026-10-31) by four things: **how much depends on it** (work and
other decisions that wait for it), **how hard it is to change later** (saved
formulas and the app bake it in), **whether something is silently wrong**
until it's made, and **how much of what a user sees** it changes. Importance
isn't urgency: the "when" column says when it's needed.

### Tier 1: the model itself. Decide these first; almost everything follows

| # | | Decision | Why it ranks here | When |
|---|---|---|---|---|
| 1 | **D13** | What a tool receives, by type (a list to a value parameter iterates) | It *is* the model: every formula's meaning, the binding code at the centre of running a step, about 200 test call sites and every app formula. D14–D19, D20b and D9 are details of it | S3 |
| 2 | **D2** | An integer is a row, a string a key | The grammar every reference is written in. Once formulas are saved and the app writes them, changing it means rewriting them all | S3 |
| 3 | **D15** | Binding by key name: opt-in only | Decides whether today's formulas keep working or are rewritten, and closes the silent wrong result B7 (a column replacing a default). The biggest single cost of the migration | S3 |
| 4 | **D14** | Never choose a key when there is more than one | Your core wish ("no implicit behaviour"). Without it D13 still guesses | S3 |
| 5 | **D51** | This cleanup before the app moves | Decides whether the app migrates once or twice. Nothing technical, all cost | before G |
| 6 | **D4** | Row numbers `0…n-1`, or stable ids | The largest piece of work, and it changes what identity means underneath lineage and staleness. Ranked below 1–5 only because it can be deferred without blocking them | S5 |

### Tier 2: settles what users write every day, or fixes silent errors

| # | | Decision | Why | When |
|---|---|---|---|---|
| 7 | **D57** | Objects' data versions | Silently wrong today: readers of any object column look stale after every run | S1 |
| 8 | **D31** | `widen` names its column | Silently wrong today: `None`s, no warning | S1 |
| 9 | **D16** | Keys, row numbers, `#` never reach a tool unless asked | The guarantee that keeps tools independent of the data's names; closes B3 | S3 |
| 10 | **D20b** | `auto` doesn't choose `filter` | Settles what `auto` is (how many calls, not which rows), and whether a bare call can drop rows | S4 |
| 11 | **D9** | A single key named after its step | Renames every unnamed output (`value` → the step's name): touches 126 test references and every downstream formula that says `"value"` | S4 |
| 12 | **D3** | Keys are identifiers | Cheap now, expensive once data with other names is saved | S1–S2 |
| 13 | **D17** | Tools get plain Python values | Tool authors will write against it; changing it later breaks their tools | S2 |
| 14 | **D21** | Nothing added unseen (`breaker`) | "The formula shows what runs" is false without it | S4 |
| 15 | **D6** | A selection can be a step's input | Without it the model's main form, `to_f(wf["p"]["temp"])`, is refused | S3 |

### Tier 3: grammar details; each follows from tier 1

| # | | Decision | Why | When |
|---|---|---|---|---|
| 16 | D5 | `wf[…]` by name only | Needed for D2 to be unambiguous (`wf[0]` is otherwise both) | S3 |
| 17 | D18 | References to steps whose shape isn't known yet | The one place D13 can't decide before running | S3 |
| 18 | D12 | A source's return: rows or one value | A consistency fix between sources and literals | S4 |
| 19 | D10 | Brackets never reach inside a cell | Keeps D2 airtight | S3 |
| 20 | D7, D8 | `cols[…]`/`rows[…]`; `.header` → `.keys` | Spelling; easy to revisit | S3 |
| 21 | D19 | `collapse(by=)` on one key of a step | An edge case of D13 | S3 |
| 22 | D1, D11 | The model; a literal is one value | Already your words; confirming | S3–S4 |

### Tier 4: features and fixes that add, without changing the model

| # | | Decisions | Why here | When |
|---|---|---|---|---|
| 23 | D-D1, D-D2, D42 | Autorun, the progress callback, re-running stale rows | Large features, but additive. Autorun has no design yet, which makes D-D1 the most important of these | D |
| 24 | E-D1 | The output store's interface | Additive; the interface is what the app will build on | E |
| 25 | D27, D28, D29, D30, D32 | `#` handling; `expand` of dicts | Small bug-level choices with an obvious answer | S1, S5 |
| 26 | D35, D47 | Collapse's group order; row classes | Follow from D4 | S5 |
| 27 | D22–D25, D56 | Modifiers take no data | Your rule; mostly moving three settings into the call | S6 |
| 28 | D41, D43–D46 | Cell-level staleness; volatility; the seed | Make staleness and reproducibility honest; none changes a formula | S9 |
| 29 | D33, D34, D36 | `melt`, `pivot`, `keep=`, the cheat sheet | Quick reshaping (goal 3); purely additive | S7 |
| 30 | D37–D40 | States | Naming and display | S8 |
| 31 | D48, D49 | `k.data`; the output UI | Convenience and app design | S10 |
| 32 | D50, D52, D53 | Bound tools as arguments; old workspaces; the app's cleanups | Carried over, each with a clear default | G |

**In short:** tier 1 (six decisions) settles the model and the cost of the
migration. Tier 2's first two fix things that are silently wrong today, so
they're worth making first even though they're small.

## 2. Open, by the step that needs them

### S1–S2. Bugs, values and keys

Needed first: phase S1 fixes what is wrong today.

| | Decision | You said | Recommended | Was |
|---|---|---|---|---|
| D3 | Keys: strings only; identifiers only? **→ CA-E: no** | strings only | identifiers too (`temp_f`, not `temp f`), so every key can be typed | X-D3, Q3 |
| D27 | Refuse a `#` column as a tool argument (B3) **→ core-asks rule 15: yes** | — | yes, pointing to D28 | — |
| D28 | `mod.rename(columns={"#": "row"})` makes the row id data **→ CA-D: rename and copy both copy, saved as `mod.copy`** | — | yes: one explicit way | — |
| D29 | Refuse `stack` of an ids-only step (B4) | — | yes | — |
| D31 | Fix `widen` (B1): name the column, `mod.widen("info")`; refused when it can't tell which | — | yes | — |
| D32 | `expand(columns=[…])` takes dicts as key/value rows (B2) | — | yes, so a melt keeps its keys | — |
| D17 | Tools get plain Python values | — | yes | X3, N12 |
| D57 | How an object's data version is computed (B10) | — | in order: the object's own `data_version()` (as resources have, K25); a dataclass, NamedTuple or plain object by its fields; a value pickle can hash; otherwise the step's plan says *"Scan has no stable version: readers look stale after each run; give it data_version()"*. Images and files get content hashes with media handles (R7, step E) | — |

### S3. The core change: brackets and what tools receive

The heart: once these land, the list-of-dicts model is true.

| | Decision | You said | Recommended | Was |
|---|---|---|---|---|
| D1 | The user's model is §2: a list of rows, each a dict **→ core-asks model.md** | yes | yes | — |
| D2 | An integer is a row, a string a key; nothing else in brackets **→ CA-B1: yes** | yes | yes | N2, N3 |
| D5 | `wf[…]` takes step names only (`wf[0]` goes) **→ core-asks rule 3: yes** | — | yes | Q10 |
| D6 | A key or row selection can be a step's input **→ core-asks L34: yes** | (implied) | yes | X4 |
| D7 | `cols[…]` / `rows[…]` stay? **→ core-asks: kept as the explicit spellings of any selector** | — | only for ranges of keys (`cols["a":"c"]`); otherwise plain brackets | X-D6, Q9 |
| D8 | `.header` → `.keys` | — | yes | X-D7 |
| D10 | `[i]` / `["k"]` never reach inside a cell | — | yes: `expand` / `widen` do | Q8 |
| D13 | §3's table: by type, a list to a value parameter iterates **→ CA-D1, CA-A: superseded** | yes ("a mapping is implied") | yes | N6 |
| D14 | Never choose a key when there is more than one **→ CA-A: yes** | yes | yes | N7 |
| D15 | Binding by key name **→ CA-A: superseded (by name is step 2, written out)** | only when explicitly defined | opt-in: `tool[mod.map(by_name=True)](wf["p"])`, refused when a name is missing | X-D2, Q2 |
| D16 | Keys, row numbers and `#` never reach a tool unless asked **→ core-asks rule 15: yes** | yes | yes | N8 |
| D18 | A reference to a step whose shape is unknown until it runs | — | a warning when declared; decided when it runs; re-checked after | Q6 |
| D19 | `collapse(by="ward")` on a list of values: where is `ward`? | — | from that list's own step, for `by=` only | Q7 |

### S4. Broadcasting and naming

| | Decision | You said | Recommended | Was |
|---|---|---|---|---|
| D20b | May `auto` pick `filter` (a tool returning `bool`)? **→ N2: no (decided)** | — | no: broadcasting decides how many calls, not which rows stay; `filter` is written | — |
| D21 | Nothing added unseen (`breaker`) | — | shown in the formula, or not added | N11 |
| D9 | One key is named after its step, not `value` **→ CA-D2: yes** | (your "stepname is a variable") | yes; `mod.name` still wins | X-D5, N4 |
| D11 | A literal is one value **→ core-asks: yes** | yes | yes | N5 |
| D12 | A source's return: rows or one value? | — | its declared type decides: `list[T]` is rows; `list` or no annotation is one value | X-D10 |

### G. The app moves

| | Decision | You said | Recommended | Was |
|---|---|---|---|---|
| D51 | **Order against the app's migration:** this cleanup's §7 phases 1–4 before the app moves, so its formulas change once **→ N1: yes, including S5 (decided)** | — | yes | X-D9, G-D1 |
| D52 | Older saved workspaces | — | refused with core's message | G-D2 |
| D53 | The app's own cleanups before it moves | — | yes | G-D3 |
| D50 | A resource with bound tools may also be passed to a free tool | — | yes, both | R-D1 |

### S5. Row numbers

The largest change: it can be deferred (keep row ids) without blocking anything before it.

| | Decision | You said | Recommended | Was |
|---|---|---|---|---|
| D4 | Rows: numbers `0…n-1` in each step's order, or stable ids? **→ CA-B1: numbers** | integers | numbers; core keeps a hidden key per row for staleness and lineage; anything that must last is written by value | X-D1, Q1 |
| D30 | `sort` / `join` / `collapse` by `#` **→ settled by CA-L1: settings may name lineage columns (D26); `#<step>`, the row number, is never a setting** | — | no: under D4 `#` is a position; use the `#<step>` links | V5 |
| D35 | Collapse's group order **→ CA-B2: first appearance** | — | first appearance (today); sorting is a `sort` | — |
| D47 | The plan carries the row class (aligned, subset, one→many, …) and a position into a step whose rows can shift warns | — | yes | — |

### D. Sessions

| | Decision | You said | Recommended | Was |
|---|---|---|---|---|
| D-D1 | **The autorun modifier**: triggers, chains, cost guards, pacing (interactive-sessions.md §6.2) | — | design it before step D starts | phase4 D-D1 |
| D-D2 | The progress callback | — | `k.run(…, observe=[progress(cb)])`, one call per cell: step, row id, state (grid-model.md §6) | phase4 D-D2 |
| D42 | Re-run only the stale rows | — | yes, with K15 (phase 4 step D) | — |

### E. Storage

| | Decision | You said | Recommended | Was |
|---|---|---|---|---|
| E-D1 | The output store's interface **→ ST (§0)** | — | `save(version, output)`, `load(version)`, `keep(versions)`, content-addressed by data version: a folder or a bucket | phase4 E-D1 |

### S6. Modifiers

| | Decision | You said | Recommended | Was |
|---|---|---|---|---|
| D22 | Modifiers: structure and execution only; tools in them are catalog tools or references, never lambdas | yes | yes | V2 |
| D23 | Move `initial=` (→ `acc=` in the call), `sweep`'s values (→ the call, `mod.sweep("x", "y")`), `over=` (goes) | yes | yes | X-D8 |
| D24 | `try_except(default=)` stays: the tool never sees it | — | yes | V2 |
| D25 | A key table in `collapse(by=)` | — | no: that's a `join` | V2 |
| D56 | A `where=` test that needs a setting (`above(temp, limit)`) | — | not possible yet: a tool in a setting gets the row only. Options: a test step written before (`k["hot"] = above(…, limit=…)`, then `where=` names it), or a bound test | — |

### S7. Reshaping

| | Decision | You said | Recommended | Was |
|---|---|---|---|---|
| D33 | `mod.melt(columns=[…], into=("key", "value"))`, `mod.pivot(by=, key=, value=)`, built from existing moves | — | yes; a pivot's columns are unknown until it runs, and must be identifiers (D3) | — |
| D34 | `collapse(by="ward", keep=[…])`: columns constant in a group stay one value, checked | — | yes | — |
| D36 | A reshaping cheat sheet in rules.md: "I have X, I want Y, write Z" | — | yes | — |

### S8. States

| | Decision | You said | Recommended | Was |
|---|---|---|---|---|
| D37 | The empty step gets its own state, `empty` (today `staged`) | — | yes, to match rule 9 | — |
| D38 | The `"empty"` cell: only the state says a step is empty, never the string | — | yes | — |
| D39 | `maybe` and `pending`: keep both (shown differently) or merge | — | keep, and document the difference | — |
| D40 | New conditions are marks on `completed`, not states (*as of 10:42*, *read stale*) | — | yes | T-D3 |

### S9. Staleness and time

| | Decision | You said | Recommended | Was |
|---|---|---|---|---|
| D41 | Track the exact cells an argument reads, so a cell argument is stale only when that cell changes | — | yes | — |
| D43 | Volatility classes: pure, seeded, versioned, volatile; a tool is pure unless it says `@tool(volatile=True)` | — | yes | T-D1 |
| D44 | A resource with no `data_version()` counts as volatile, with a note | — | yes | T-D2 |
| D45 | `run_id` includes *as of* for volatile steps | — | yes | T-D4 |
| D46 | A tool with `seed` that isn't given warns, and counts as volatile | — | yes | C-D2 |

### S10. Terminal and UI

| | Decision | You said | Recommended | Was |
|---|---|---|---|---|
| D48 | `k["p"]` stays a reference; `k.data("p")` gives the list of dicts, plain values | — | yes | — |
| D49 | The output UI (a value card, a list, a table, a lineage strip; headers select values, never names; `#` outside the selection) | — | yes, written in the app's dev plan | — |

Steps with no open decision: **F** (the workflow as a table: the draft of
2026-10-27 is the starting point) and **S0** (the tests).

## 3. Decided

| | Decision | Date |
|---|---|---|
| D20 | `auto` is kept, as broadcasting with clearly defined rules (syntax-review.md §3.1) | 2026-10-31 |
| D54 | `mod.map(where=test)`: apply a tool on a condition; built | 2026-10-31 |
| D55 | `first_present`: the else, a separate step; built | 2026-10-31 |
| D26 | `#` columns accepted by the reshaping modifiers (`collapse(by="#s")`): kept | 2026-10-29 |
| — | the combines (`zip_`, `stack`, `join`) stay as they are; no operators | 2026-10-30 |
| — | both orders of a cell reference (`[i]["k"]`, `["k"][i]`) are accepted and saved the same | 2026-10-30 |
| C-D1 | a resource's data version is an optional method, `data_version()`; built | 2026-10-27 |
| A-D1, A-D2, B-D1 | a fold's start value; `timeout` by a worker thread; pages of 50 rows; built | 2026-10-27 |
| R-D1 … R-D13, J-D1 … J-D6 | the reshaping decisions; built (reshaping-decisions.md) | 2026-10-27 |

## 4. Core asks, reconciled (2026-11-02)

The owner's answers to the review of [core-asks/](core-asks/) against this
register. IDs `CA-…` avoid core-asks' own D1–D5, which clash with D1–D5
here (core-asks D1 is CA-D1, and so on).

### Decided

| | Decision | Supersedes / settles |
|---|---|---|
| CA-D1 | What a column argument passes is decided by the **verb**, never the parameter's type: a row's cell under `map` / `filter` / `expand`, the whole column under one call, the group's values under `collapse`. The type checks the value; it never changes what is sent | **D13** superseded |
| CA-A | **Binding is decided at staging and saved explicitly.** For each parameter, the first that decides: (1) what the user wrote, a keyword or a one-column input; (2) a column with the parameter's name, only for a parameter without a default (closes B7); (3) the one unbound column whose type fits; (4) otherwise `invalid`, the message writing the fix, for ambiguity (*"r has two int columns, n and m: write `n=wf['r']['m']`"*) or for a type that doesn't fit (*"add `mod.cast(…)`"*). What staging decides is written into the saved expression, so the saved form says exactly what runs and nothing is guessed again; a binding that later breaks makes the step `invalid` with its reason. Types come from the return annotation before a run, observed types after; unknown types follow D18. Only lossless conversions are automatic (`int` → `float`); others need `mod.cast`, and a cast that fails fails the cell | **D15** superseded (by name is step 2, written out); **D14** decided (yes); syntax-review §3.1 rule 7 replaced. Needs: rule 13 allows `map` with keyword column picks and no positional input; a new `mod.cast` |
| CA-B1 | **Rows are shown and typed as row numbers** `0..n-1` in each step's current order (`#<step>`); a pick is **saved as the row's lineage**: back to its source row (`row['r'] == 2`), through an expand with `.idx`, through a collapse by its key (`cols['ward'] == 'A'`); into a source, sweep or table it stays a row number. Staging resolves `[3]` and writes the lineage into the expression, as it does a binding (CA-A). A pick follows its row; if the row is gone, the step fails saying so. Core's row ids, which already encode lineage (`0.1`, a group's key), stay its identity and are never shown or written. *Amended 2026-11-02 (owner): was "rows are row numbers, with a reference-moved warning"; this keeps core's identity and makes S5 a change of surface* | **D4** decided; **D2**, **D5** decided (core-asks rules 3, 6). Order: S5 before **G** |
| CA-D2 | One output value or column is named after the step; a dict's columns after its keys; unnamed parts `var0`, `var1`, … | **D9** decided |
| CA-D | `mod.rename` moves a data column; `mod.copy` duplicates one. On a `#` column both copy: the `#` column always stays. Both spellings are accepted and saved as `mod.copy` | **D28** replaced; core-asks D4 and TEST-L18b change (rename of lineage accepted, saved as copy) |
| CA-F | The word is **expression**; *formula* is retired. object-model.md §1 changes. Also proposed with it: *pick*, *picker* (for `select`, `slice`, `sort`, `distinct`), *row number* for `#<step>` (*placement* not a separate word), *lineage*, *aligned* (for *origin*) | object-model.md §1 |
| CA-L1 | **Every step carries its ancestors' lineage**, so every row says what it maps to all the way back. A step that isn't one-to-one also adds `#<parent>`; one-to-one steps add nothing. Filter, sort, pick: carried values follow the kept rows. Expand: repeated, plus `.idx`. Collapse, distinct: lists. Combines: each side's carried. The same ancestor by two paths: `#r`, `#r.2` | core-asks rule 21, L13, L14b, L12b change |
| CA-L2 | A lineage cell is an integer, a list of integers, or **empty** (stack, outer joins) | core-asks D5 |
| CA-L3 | A condition on a list cell: `row['r'] == 0` is true if the list contains 0; `.isin` if any item matches; `!=` is `~(==)`; `<`, `>` on a list cell refused; every test on an empty cell is false | core-asks TEST-L30b |
| CA-5 | A filter or condition that keeps nothing gives **zero rows** and a warning naming the condition, not a failure. A row number out of range (`[9]` of 4 rows) fails: a specific row was asked for. Zero rows is not the empty step (1×1 `"empty"`) | core-asks rules 11, 26, TEST-L31 change |
| CA-6 | Deleting a step that is read is refused, naming the readers (today). An explicit delete-anyway makes each reader `invalid`, naming the deleted step | core-asks M7, L43 |
| CA-7 | Two integers in one bracket (`wf['s'][0, 2]`) are refused, pointing to `[[0, 2]]` | core-asks rule 7 |
| CA-8 | Step names are identifiers: no `.` (so `#r.2`, `#r.idx` read one way) | core-asks M6 |
| CA-9 | Renaming a step rewrites everything core wrote: `wf['old']`, the column named after the step, staging's bindings, `#old` downstream and `row['old']`. Anything else that breaks is `invalid` with its reason; the user renames or redefines it | K29, core-asks M7 |
| CA-11 | **Strict alignment arrives with S5**, with joins on lineage, its replacement. Until then a column argument or `zip_` is refused only where a row would get no value (S1). **Amended 2026-11-02 (owner): pairing is by identity, not position.** Aligned means the same rows in any order (a sort is aligned); aligned steps pair each row with the same row, by row id; a filtered copy, or a child and its parent, still meet in a join on lineage | core-asks L1, L2 |
| CA-10 | Step and cell states stay core's; `running` and `empty` are decided with D37 | core-asks M7 |
| CA-B2 | **Three ways to pick rows:** by row number (what you see, `wf['s'][3]`), by value (a condition), by parent (`row['r'] == 3`). Clicking a cell writes a row number. Lineage shows under an expander, collapsed to "from r", nearest parent first; picking by parent is offered from a lineage cell, never written by a click. Default row order: sorted after `sort`; the parent's after filter, slice, pick; first appearance after collapse, distinct; parent then item after expand; the left side's after join; inputs in order after stack | **D35** decided |
| CA-C | **Merging a step with its ancestor is never implicit.** A column argument from a step that isn't aligned is refused (today it silently gives `None`), and the refusal writes the join: `join(wf['filtered'], wf['r'], on='#r')`, or `how='left'` for every row of `r` back, `absent` where the filter dropped one. A column passed through unchanged from the shared ancestor appears once, not as a clash | **K19** reversed for unaligned steps |
| CA-E | **Column names that aren't identifiers** (`'Patient ID'`) are kept as written, never renamed silently; picked by string; bound by keyword or type (CA-A), never by name. Numeric names still become `var<n>` | **D3** decided: no |

### S1, answered (2026-11-02)

| | Owner | As built |
|---|---|---|
| L5 | `total` needs a literal setting to ignore what isn't a number, like pandas' `numeric_only=True` | `total(…, numeric_only=False)`: by default a column that isn't numbers is a failed cell saying so and naming `numeric_only=True`; with `True` it's left out |
| D31 (B1) | `widen` names its column, or assumes the one dict column; one layer, never recursive | `mod.widen("info")`; with no name, the one column holding dicts; none or several: refused, naming them. Nested dicts stay values |
| D32 (B2) | `expand(columns=…)` of a dict: add a parameter for keeping the other columns | key/value rows; `keep=` (default: as a list column today) |
| D27 (B3) | yes: a `#` column never reaches a tool; it may still be used to pick | refused as an argument; settings and conditions may name it |
| D29 (B4) | yes, refused with its reason | refused |
| B9, D57 (B10), B11 | yes | — |

### S5, answered (2026-11-02)

S5-D1 to S5-D6 (phase4-plan §3, S5): **all as recommended** (owner). Conditions
move into S5; a range stays a range, a row or list of rows is saved as
lineage; a pick into a step that hasn't run is resolved when it has; a lineage
cell shows the parent row's current row number, empty when it's gone;
`step.output.data` keeps core's ids for code, everything shown uses row
numbers; a join row's empty side is `row["other"] == None`.
