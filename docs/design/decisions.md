# Decisions

> **Every decision, in one place** (organised 2026-10-31). Open ones are
> grouped by the step of [phase4-plan.md](phase4-plan.md) that needs them, in
> the order the steps run, so the next one to make is always near the top.
> The design they decide is [syntax-review.md](syntax-review.md) (the model,
> the rules, the bugs, the tests). When a decision is made, its row moves to
> §3 with the date.

## 1. How to answer

Each row says what you have already said (*You said*), and what is
recommended. Where you've said something, it only needs a yes. "Yes to all
recommended in a group, except …" is a fine answer.

**Already answered in your own words, to confirm:** D1, D2, D3, D4, D6, D9, D11, D13, D14, D15, D16, D22, D23.

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
| D3 | Keys: strings only; identifiers only? | strings only | identifiers too (`temp_f`, not `temp f`), so every key can be typed | X-D3, Q3 |
| D27 | Refuse a `#` column as a tool argument (B3) | — | yes, pointing to D28 | — |
| D28 | `mod.rename(columns={"#": "row"})` makes the row id data | — | yes: one explicit way | — |
| D29 | Refuse `stack` of an ids-only step (B4) | — | yes | — |
| D31 | Fix `widen` (B1): name the column, `mod.widen("info")`; refused when it can't tell which | — | yes | — |
| D32 | `expand(columns=[…])` takes dicts as key/value rows (B2) | — | yes, so a melt keeps its keys | — |
| D17 | Tools get plain Python values | — | yes | X3, N12 |
| D57 | How an object's data version is computed (B10) | — | in order: the object's own `data_version()` (as resources have, K25); a dataclass, NamedTuple or plain object by its fields; a value pickle can hash; otherwise the step's plan says *"Scan has no stable version: readers look stale after each run; give it data_version()"*. Images and files get content hashes with media handles (R7, step E) | — |

### S3. The core change: brackets and what tools receive

The heart: once these land, the list-of-dicts model is true.

| | Decision | You said | Recommended | Was |
|---|---|---|---|---|
| D1 | The user's model is §2: a list of rows, each a dict | yes | yes | — |
| D2 | An integer is a row, a string a key; nothing else in brackets | yes | yes | N2, N3 |
| D5 | `wf[…]` takes step names only (`wf[0]` goes) | — | yes | Q10 |
| D6 | A key or row selection can be a step's input | (implied) | yes | X4 |
| D7 | `cols[…]` / `rows[…]` stay? | — | only for ranges of keys (`cols["a":"c"]`); otherwise plain brackets | X-D6, Q9 |
| D8 | `.header` → `.keys` | — | yes | X-D7 |
| D10 | `[i]` / `["k"]` never reach inside a cell | — | yes: `expand` / `widen` do | Q8 |
| D13 | §3's table: by type, a list to a value parameter iterates | yes ("a mapping is implied") | yes | N6 |
| D14 | Never choose a key when there is more than one | yes | yes | N7 |
| D15 | Binding by key name | only when explicitly defined | opt-in: `tool[mod.map(by_name=True)](wf["p"])`, refused when a name is missing | X-D2, Q2 |
| D16 | Keys, row numbers and `#` never reach a tool unless asked | yes | yes | N8 |
| D18 | A reference to a step whose shape is unknown until it runs | — | a warning when declared; decided when it runs; re-checked after | Q6 |
| D19 | `collapse(by="ward")` on a list of values: where is `ward`? | — | from that list's own step, for `by=` only | Q7 |

### S4. Broadcasting and naming

| | Decision | You said | Recommended | Was |
|---|---|---|---|---|
| D20b | May `auto` pick `filter` (a tool returning `bool`)? | — | no: broadcasting decides how many calls, not which rows stay; `filter` is written | — |
| D21 | Nothing added unseen (`breaker`) | — | shown in the formula, or not added | N11 |
| D9 | One key is named after its step, not `value` | (your "stepname is a variable") | yes; `mod.name` still wins | X-D5, N4 |
| D11 | A literal is one value | yes | yes | N5 |
| D12 | A source's return: rows or one value? | — | its declared type decides: `list[T]` is rows; `list` or no annotation is one value | X-D10 |

### G. The app moves

| | Decision | You said | Recommended | Was |
|---|---|---|---|---|
| D51 | **Order against the app's migration:** this cleanup's §7 phases 1–4 before the app moves, so its formulas change once | — | yes | X-D9, G-D1 |
| D52 | Older saved workspaces | — | refused with core's message | G-D2 |
| D53 | The app's own cleanups before it moves | — | yes | G-D3 |
| D50 | A resource with bound tools may also be passed to a free tool | — | yes, both | R-D1 |

### S5. Row numbers

The largest change: it can be deferred (keep row ids) without blocking anything before it.

| | Decision | You said | Recommended | Was |
|---|---|---|---|---|
| D4 | Rows: numbers `0…n-1` in each step's order, or stable ids? | integers | numbers; core keeps a hidden key per row for staleness and lineage; anything that must last is written by value | X-D1, Q1 |
| D30 | `sort` / `join` / `collapse` by `#` | — | no: under D4 `#` is a position; use the `#<step>` links | V5 |
| D35 | Collapse's group order | — | first appearance (today); sorting is a `sort` | — |
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
| E-D1 | The output store's interface | — | `save(version, output)`, `load(version)`, `keep(versions)`, content-addressed by data version: a folder or a bucket | phase4 E-D1 |

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
