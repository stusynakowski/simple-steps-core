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
