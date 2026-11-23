# What could influence the distinctions

> **Draft, 2026-11-23, for the owner.** The distinctions in
> [grammar.md](grammar.md) §6 are meant to be clean. This page lists,
> frankly, **what could blur them or move a case from one class to
> another**, so each is decided on purpose rather than found later. Each
> item says which distinction it touches, how, and whether it was **run**
> (on `core-handover`, 2026-11-23) or is **reasoned** only.

The distinctions it is about:

| Axis (grammar.md §6) | Classes |
|---|---|
| **T-k. Whose function** | none · core's own (declared) · the user's (inferred) |
| **T-u. What it works on** | a whole table · cells |
| **K-n. How many calls** | zero · one · many |
| **declared or inferred**: how sure core can be | follows from T-k, and from how much the types say |

## 1. Whose function: none, core's, the user's

| # | What | How it influences | |
|---|---|---|---|
| **W1** | **Core's cell tools are called like a user's.** `op("total")[mod.collapse(by="k")]` makes one call per group; `op("identity")[mod.map()]` one per row | "core's" doesn't mean "one call". Whose function decides only *declared or inferred*; how many calls comes from what it works on and the call modifier | run |
| **W2** | **A call modifier with no tool gets core's default.** `collapse` alone runs `gather`; `expand` alone runs `identity` (`DEFAULT_TOOL`, system_tools.py) | The same expression's function moves from core's to the user's when a tool is named. The UI should show which: "gather (core's default)" | code read |
| **W3** | **A resource's method** (`res["llm"].summarize`) | It is the user's function, bound to an object: inferred like any user tool, plus the resource's settings. Execution matters most here (cost, rate limits, time) | reasoned |
| **W4** | **A condition in a pick** (`wf["p"][cols["x"] > 1]`) | Core evaluates a function inside the pick. It belongs to the **input** (which cells), not to the calls: a pick with a condition still makes no call of its own | reasoned |
| **W5** | **Data that started as output.** A frozen block (blocks.md §2), or a cell typed into (decisions.md CE) | It was a call's output; frozen, it is data: nothing applied, zero calls. Its history is not its class | reasoned |
| **W6** | **A plain Python function is refused**: it must be a tool in the catalog (EX9) | "The user's function" always means a catalog tool with a readable signature, so there is always something to infer from | code read |
| **W7** | **A future combine that takes a user function** (a join on a predicate; none today) | It would be core's function over tables with a user's part inside: two classes in one expression. Not today, but the grammar should leave room | reasoned |

## 2. What it works on: a whole table, or cells

| # | What | How it influences | |
|---|---|---|---|
| **U1** | **A user's tool typed `DataFrame → DataFrame`.** `auto` picks `table` for it (the rule in `checks.infer_verb`: a first parameter that is a `DataFrame` "wants the whole grid") | The type hint alone doesn't decide: the same tool under `map` would get a table **held in a cell** (blocks.md §1, two levels). What it works on comes from the call modifier, with the type as the default | code read |
| **U2** | **A source** (`load_csv[mod.source()]()`) | The user's function over no input, making a table: one call. It reads the outside world, so naming it always runs it again (`Kernel.run`: "a tool with no input reads the outside world"). That is execution, not its class | code read |
| **U3** | **A sweep** | The user's cell function, called once per combination of settings: many calls, with no input step. Its rows come from the settings, not from data | run 2026-11-22 (2 settings, 2 calls) |
| **U4** | **A whole-table function on one row** | A table function on a 1-row table is still one call over a table, not a cell function. The class is the function's, not the data's size | reasoned |

## 3. How many calls: zero, one, many

| # | What | How it influences | |
|---|---|---|---|
| **N1** | **The data's size.** Many calls over 0 rows make none; over 1 row, one | The class is written; the count is the data's. A step with many calls that ran on 0 rows still completes ("a step that ran to zero rows", `Step.state`) | code read |
| **N2** | **A step already current is skipped**: its kept output is reused, no calls (owner, 2026-11-16) | An outcome of a run, not a class (grammar.md §6.4) | code read |
| **N3** | **A cancelled run** stops part way (K23, to come; the app's shim today) | Fewer calls than the class says. An outcome | reasoned |
| **N4** | **One cell run in place**: `k.run_cell(step, row)` (P7r) | One call of a many-call step, the rest still pending. The class stays many; the run is partial | run (tests/unit/test_run_cell.py) |
| **N5** | **Retries** | Several attempts are still one call, with one output | run 2026-11-23 (order.py) |
| **N6** | **A breaker** stops after n failures | Fewer calls than rows: an outcome, from execution | code read |

## 4. Declared or inferred: how sure core can be

| # | What | How it influences | |
|---|---|---|---|
| **D1** | **A tool without type hints**, or `Any` | Little to infer from: the conventions fall back to their defaults, shown as assumed. `Catalog(strict=True)` requires hints and refuses a tool without them | code read |
| **D2** | **Hints written as strings** (`from __future__ import annotations`) | The same hints, read differently by Python. Core normalises them for the verb (`infer_verb`'s note); every rule that reads a type must too | code read |
| **D3** | **The input's types not known before a run** (a column from a tool with no return hint) | A rule may need a type it doesn't have yet. It decides with what it has, and writes it down once: never re-guessed after a run (grammar.md §1) | reasoned |
| **D4** | **A return type that says little**: `-> list` with no item type, `-> dict` | Where the output lands is known; its columns and their types only after a run | run 2026-11-22 (an expand's item type plans as `unknown`) |
| **D5** | **`async def` tools** (the app's C48) | A different kind of call: stored un-awaited today. Refuse at declaration, or await | run 2026-11-20 (`tool(async def …)` accepted) |
| **D6** | **Tools with side effects or randomness** (a write to a file, a random sample; S9 "volatile") | The same inputs may not give the same output: a kept output reused (N2), and a cell's recipe by value, can't be trusted to reproduce it. **Decided** (owner, 2026-11-23): **the user's responsibility.** A random tool takes a **seed** parameter, usually a literal argument, or `temperature=0` for a model; then the same inputs give the same output, and the seed is in the expression, the recipe and the kept output's key. Core declares nothing about volatility | decided |
| **D7** | **A tool's code changing** | Its steps go stale ("tool changed": core compares the code hash it ran with, today). Its hints may change too, so the classes written into its expressions may no longer fit: they would need checking again when the code changes. **Decided** (owner, 2026-11-23): good **versioning** is wanted, to know when a tool's code or a function's text changed since it was loaded, but it is **out of scope for now** | decided: later |

## 5. How the user sees it

| # | What | How it influences | |
|---|---|---|---|
| **V1** | **Whether core's table functions are shown as calls at all** | Proposed (grammar.md §6.3): shown as what they do, "drop columns x, y"; the calls question kept for the user's tools, where it needs an answer | reasoned |
| **V2** | **Shorthand against opened** (H1) | Every class a shorthand implies is shown when the expression is opened: "collapse: one call per group; xs packed per group; one row per group" | reasoned |
