# The step grammar

> **Draft, 2026-11-23, for the owner.** The start of the grammar that closes
> the system ([blocks.md](blocks.md) §0, plan piece G0). This page begins
> with **what must be resolved for any expression**. The shape (which words
> fill which component) and the numbered rules (how the components depend
> on each other) come next, on this page.

*Owner, 2026-11-23: "we now know exactly what needs to be satisfied for ANY
valid expression. When we specify a tool, modifiers, picks, or modifiers to
the pick, we converge on the components … everything needs to be obvious
and intuitive for how things are handled, but the conventions are clear. So
we can parse the expression to converge on the exact components."*

## 1. The idea: an expression converges on its components

What a user writes is **partial**. A tool, a pick and perhaps a modifier or
two. Core **resolves** it into a **complete** set of components, every one
with a value, and that complete set is what runs, what is saved and what
the UI shows. Resolving happens when the step is declared, before anything
runs.

```
what is written ──resolve──► every component has a value ──► checked ──► staged (a plan) ──► run
   (partial)                    (complete, written down)
```

**Each component's value comes from one of three places, in this order:**

| # | From | Example |
|---|---|---|
| 1 | **written**: the user wrote it | `mod.collapse(by="ward")` |
| 2 | **implied** by another component | under `collapse`, each input argument is packed per group |
| 3 | **a convention**: a default, from the tool's signature and the types | a tool returning one value lands as one cell |

What is written always wins. An implication or a convention never
overrides it. When two disagree (written per-row argument, implied per
group), the step is **refused when declared**, naming the components and
the fix. Every value that came from 2 or 3 **is written down**, so the
complete form is what is shown and saved, and it never changes after a run.
(Core does this for the verb and the binding today: `auto` is written as
the verb it chose, and a binding found by type is written into the
expression.)

## 2. The components every tool call must resolve

| # | Component | Must resolve to | Comes from, usually | Can't be resolved when |
|---|---|---|---|---|
| **C1** | **tool** | one tool in the catalog: its signature (each parameter's name, type and default; the return type), and its resource if it is a resource's method | written | it isn't in the catalog; its signature can't be read |
| **C2** | **input** | the pick the calls are made over: a step, its row part and its column part, and so **the block** (its rows, columns and their types). Or *none*, for a tool that reads no step (`source`, `sweep`) | written | the step doesn't exist or comes later; a column isn't there |
| **C3** | **binding** | for **every parameter**, exactly one source: a column of the input, another pick, a literal, a resource, or the tool's default. A parameter with no default must get one | written, or by name, or by type (written down) | a parameter needs a value and nothing fits; two sources claim one parameter |
| **C4** | **preparation**, per argument | its **scope** (its row, a window, its group, everything), its **packing** (the cell as it is, or packed: a list, a dict, a table, an array), and any **conversion** of each cell (`cast`) | its row's cell, unless written, or implied by C5 | a scope that disagrees with C5; a packed type that doesn't fit the parameter |
| **C5** | **calls** | exactly one: one per row, one per group (and its key), one in total, one per combination of settings, or one with no input | written, or from `auto` (written down) | two are written; it disagrees with C4 |
| **C6** | **each call's run** | the wrappers, in their order: `retry`, `timeout`, `breaker`, `try_except`. May be none | written | — |
| **C7** | **landing** | **where** each output goes (its row; one row per call; every row of its scope; or keep or drop its row) and **in what shape** (one cell; into rows; into columns) | implied by C5 and the return type | the return type can't land that way (keep needs a `bool`) |
| **C8** | **names** | a name for each output column | the step's name, a record's field names, or `mod.name` | two columns would get one name |
| **C9** | **checks** | what is expected of the output (`expect`): rows, columns. May be none | written | — |

**Worked out from the nine, never written** (they follow, so they are never
a choice): the **plan** (rows, columns and types, each with its certainty)
and the **row map** (for each output row, the input rows it came from:
lineage).

## 3. The other kinds of expression

Not every expression calls a tool. Each kind resolves fewer components:

| Kind | Example | Resolves |
|---|---|---|
| **empty step** | (a step with no expression yet) | nothing: a 1×1 output holding `"empty"` |
| **data** | `k["p"] = pd.DataFrame(…)`, `k["limit"] = 2.0` | the values, the column names (C8) and their types |
| **pick** | `k["cp"] = wf["f"]["x"]` | C2 (the block); it lands as the step's table, linked to `f` |
| **tool call** | `to_f[mod.map()](wf["p"], offset=1.0)` | C1–C9 (§2) |
| **combine** | `join(wf["a"], wf["b"], on="id")` | several inputs (C2 for each), **how their rows are matched** (by position, by row id, by key; inner or outer), and C8 (names, with suffixes on a clash) |

## 4. What core resolves today, in order

When a step is declared (`Workflow.__setitem__`), core already resolves
part of this, in this order:

| Order | Today | Component |
|---|---|---|
| 1 | a plain value becomes a **data** step; a Python function that isn't a tool is refused | the kind (§3) |
| 2 | a resource's method is attached to its resource | C1 |
| 3 | the tool is admitted from the catalog | C1 |
| 4 | arguments given by position to a resource are bound | C3 |
| 5 | a tool call with no input is refused, unless it is a `source`, `sweep` or combine | C2, C5 |
| 6 | picks are resolved: row numbers saved as lineage | C2 |
| 7 | `auto` is resolved into a verb, **written** | C5 |
| 8 | the binding by type, **written** | C3 |
| 9 | the problems are found | all |
| 10 | the plan is staged | the plan |

**Not resolved as components today**, and so where the findings are:

| Component | Today | Findings |
|---|---|---|
| C4 preparation | implied by the verb and the parameter's type, at the call, not written; four separate checks | A1–A7 ([blocks.md](blocks.md) §3) |
| C6 and C5's order | the written order, which can change what a step does | O1 (blocks.md §0) |
| C7 landing | implied by the verb; "on every row of its scope" missing | §4's window and transform gaps |
| C2's block | checked against the input **step's** columns, not the pick's | A4 |

## 5. Next on this page

1. **The shape**: for each component, the words that fill it (the
   modifiers, the pick's parts, the literals), as a grammar.
2. **The rules**: every dependency between the components as a numbered
   rule, each with the problem it gives when broken. blocks.md §0's table
   of dependencies is the start.
3. **The conventions**: for each component, its default, written as one
   table, so "obvious and intuitive" is one place to look.

To settle with the owner:

- Are the nine **C1–C9** the right set? Anything missing (for example, the
  step's name as part of the expression), or anything that should be
  merged?
- **The empty step, data and pick** (§3): should they be written as tool
  calls too (a pick as `identity` over a block, data as a `source`), so
  there is only one kind of expression? Core already stores a DataFrame
  step this way in some saved files (`identity[mod.source()]()`).
