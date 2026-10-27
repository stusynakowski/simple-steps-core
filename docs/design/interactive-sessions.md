# The grid model in an interactive session

> Proposed 2026-10-26. How a kernel behaves while someone builds a workflow
> step by step, in a terminal, a notebook or the app's UI. *Today* behaviour was
> run at `86170a3` on `grid.Workflow`, which is what the `Kernel` grows from.

## 1. The idea

An interactive session is a conversation with a kernel. You **declare** a
step and immediately see what it will produce. You **run** it when you choose.
You **edit** anything, and the kernel shows exactly what that made out of date,
without recomputing anything you didn't ask it to.

Four rules make that work:

1. **Status is reactive; computing is explicit.** Every edit updates, at once,
   every step's problems, plan, state and reasons. No tool runs unless asked
   (by a run, or, once it exists, by an autorun modifier on the step), because Python tools are messy, slow or costly, and the user decides when to
   pay for a run. What the kernel must do is make it obvious **what needs
   running, and why** (§6.1).
2. **Declaring is cheap and immediate.** A step is checked and planned the
   moment it is written: problems, the columns it will have, their types, how
   many rows (exactly, at most, or unknown and why). Nothing runs.
3. **Running is explicit unless a step opts in.** Only `run` and `run_all` call tools. Tools
   can be slow, costly or impure (an LLM call, a model, a database), so the
   kernel never runs one because something else changed, unless the step is
   written with an autorun modifier (§6.2, planned). *(Explicit running
   exists today.)*
4. **Nothing is thrown away, nothing is hidden.** After an edit, a step keeps
   its last output and is marked `stale`, with the reason. You can still read
   it, and see what it was computed from, until you re-run it.

The app is the same session with a UI on top: every action in the UI is one
kernel call (§8). Whatever the UI shows, a terminal can show.

## 2. What the kernel holds at any moment

For every step, always:

| | Before it runs | After it runs | After an edit |
|---|---|---|---|
| **spec** | what you declared | same | the new declaration |
| **state** | `staged`, or `invalid` | `completed` or `failed` | `stale` (or `invalid`) |
| **output** | the **plan**: columns, types, row count with certainty | the data, a state per cell, notes | the last data, kept and shown |
| **problems** | found when declared | same | re-checked against the new upstream |
| **reason** | — | — | why it's stale: `updated args`, `sick is stale`, `input sick changed`, `tool changed` |

## 3. A session, step by step

What core does today, run with the fever example (`p` → `sick` → `f`):

```python
k["p"]    = patients[mod.source()]()
k["sick"] = feverish[mod.filter()](wf["p"])
k["f"]    = to_f[mod.map()](wf["sick"])
```

| Moment | `p` | `sick` | `f` |
|---|---|---|---|
| **declared** | `staged`; rows unknown (not run) | `staged`; rows unknown (input unknown) | `staged`; columns `value: float` exact; rows unknown, *"run 'sick', or state it with mod.expect(rows=…)"* |
| **`run("p")`** | `completed`, 3×2 | `staged`; rows now **bounded** (at most 3) | `staged` |
| **`run_all()`** | `completed` | `completed`, 1×2 | `completed`, 1×1 |
| **edit `sick`** to `limit=37` | `completed` | **`stale`**: `updated args` (`limit` 38 → 37); still shows its 1 row | **`stale`**: `sick is stale` |
| **`run("sick")`** | | `completed`, 2×2 | still **`stale`**: `input sick changed`; still shows the 1 row it was computed from |
| **`run_all()`** | | | `completed`, 2×1 |

The plan **sharpens as upstream runs**: `sick`'s row count went from
`unknown` to `bounded` once `p` had run, and to `exact` once `sick` itself ran.

## 4. Declaring

`k["x"] = expression` does four things at once, and never runs a tool:

1. **Checks** the expression against the catalog (is every tool, modifier and
   combine in it?), the workflow (does every reference name an earlier step?),
   and the upstream's planned columns and types (does the tool find the
   columns it needs?). Each finding is a `Problem` on the step.
2. **Plans** the output: columns, types and rows, each with a certainty.
3. **Compares** with the step's previous spec, if it had one. The same spec
   changes nothing (*today*: re-declaring an identical step keeps it
   `completed`). A different spec makes it `stale`, with what changed
   (`k.arg_changes("sick")` → `limit: 38 → 37`).
4. **Re-checks the steps that read it.** Their problems and plans are worked
   out again against the new upstream, and if they had run, they're `stale`.

`k.check("x", expression)` does the first two without changing anything: what
a proposal (from the agent, or a form) would do before it's accepted.

An **empty step** is a line with no expression yet (`k["x"] = None`, a blank
row in the UI): it holds a place, its output is a 1×1 `"empty"`, and it
can't be read by later steps until it has an expression.

## 5. Running

| Call | Does |
|---|---|
| `k.run("f")` | runs `f` on **what its inputs show now**. A `stale` input passes through as it is, which is what you want while tinkering. An input that has **never run** has nothing to show, so it runs first (*today*: refused, *"Run 'p' then 'sick' first"*) |
| `k.run_all()` | runs every valid step that isn't `completed`, in order, each after what it reads. Stops at a failure nothing handles |
| `k.run("triage")` | runs a stage's steps in order |
| `k.run("f", observe=[…])` | attaches observing modifiers (progress) for this run |

When a step finishes, it records the version of every input it read. That is
what lets the kernel tell, later, that an input changed.

**A step computes from the data you can see** (decided 2026-10-26). `run("f")`
never refreshes a stale input behind your back: `f` runs on `sick`'s output as
displayed, so what the UI shows is always what was computed from. The result is
`completed`, with a mark that it **read a stale input**:

```
 2  f   to_f[mod.map()](wf["sick"])   completed · read stale 'sick' (updated args)
```

When `sick` is re-run later, `f` becomes `stale` (`input sick changed`) like any
other reader. To bring everything up to date, run upstream first, or
`k.run_all()`.

## 6. Editing

| Edit | Effect |
|---|---|
| **change a step** | it's `stale` (`updated args`, `updated tool`, …); later steps that read it are `stale` (`sick is stale`) and re-checked |
| **re-run a changed step** | it's `completed`; its readers stay `stale` with `input sick changed` until they re-run |
| **rename** `k.rename("sick", "fever")` | later references follow: `f` now reads `wf["fever"]`, and stays `completed` (*today*) |
| **remove** a step something reads | refused: *"cannot remove 'fever': 'f' reads it. Remove or rename it first"* (*today*) |
| **insert / move** | `k.insert(i, name, expr)`, `k.move(name, i)`; a move that puts a step before what it reads is refused |
| **change a source's data** | the step's next run gets a new data version; readers become `stale`, per row where it can tell (`k.stale_rows("s")`, *today*) |
| **change a tool's code** (new catalog) | steps that used it are `stale`: `tool changed` (K20) |

A stale step **keeps showing what it was computed from** (K22): `f` still shows
the one row it computed from the old `sick`, beside a mark that `sick` has
changed. Its version of `sick`'s output is kept as long as `f` reads it.

### 6.1 Knowing what needs running

| Call | Gives |
|---|---|
| `k.needs_run()` | every step that isn't up to date, in run order, with its reason: `staged`, `stale: updated args`, `stale: input sick changed`, `read stale 'sick'` |
| `k` | the same marks in the table, so one look shows what is out of date |
| `k.on_change(callback)` | calls the host on every change of state, problems or plan, with the steps affected. This is how the app's UI stays reactive without polling (C33) |

### 6.2 An autorun modifier (planned; to be designed)

Decided 2026-10-26: nothing re-runs on its own by default, but a step may opt
in with an **autorun modifier** (working name `mod.autorun(…)`). It is in the
development plan (phase 4); how it is defined is still open. What is settled:

- **Off unless written** on the step.
- **A scheduling modifier:** it decides *when* a step runs, never what it
  computes, so it is saved but not hashed.
- **It runs as `run(step)` does:** on what its inputs show.
- **The host can pause it** for a whole kernel (batch runs, tests).

What has to be designed before it is built:

| Question | Candidates |
|---|---|
| **What triggers it** | a step it reads re-ran; a step it reads changed state (e.g. became `completed`); its own spec was edited; any change it is told about through `on_change` |
| **How it's written** | one modifier with a trigger setting, `mod.autorun(on="input_ran")`, or one modifier per trigger |
| **Chains** | whether an autorun step's re-run can trigger autorun steps that read it, and how a failure stops the chain |
| **Cost guards** | whether a step whose tool is slow or costly may carry it, or only reshapes and combines; a limit on runs per change |
| **Pacing** | whether core waits for edits to settle (a UI sends one per keystroke) or the host decides when to hand an edit over. Leaning: the host decides; core reacts once per change it is told about |

## 7. Reading

| Call | Gives |
|---|---|
| `k` | a table: index, step, formula, state, shape, first problem |
| `k.step("f")`, `k.step(2)` | one step: formula, state, reason, problems, the first rows |
| `k.step("f").data` | its values, a DataFrame |
| `k.view("f", rows=(0, 50))` | a page of rows, as the UI shows them: row number `#`, row id, a state and type per cell, and how many rows there are in all (*today* `wf.preview`) |
| `k.cell("f", 1, "value")` | one cell: value, type, state, and the input cells it came from, with their values (*today*) |

Rows in `view` and `cell` are addressed by row number, as displayed; the
answer also gives the row id, which is what references and lineage use.

## 8. The same session in the app

| In the UI | Kernel call |
|---|---|
| type a formula and press enter | the app parses it, then `k[name] = op`, and shows problems and the plan |
| a form for a tool's arguments | builds the same `op`; `k.check` while typing |
| press run on a step / run all | `k.run(name)` / `k.run_all()` |
| edit, rename, delete, drag a step | `k[name] = op`, `k.rename`, `del k[name]`, `k.move` |
| scroll a table | `k.view(name, rows=…)` |
| click a cell | `k.cell(name, row, column)` |
| a progress bar | an observing modifier with the app's callback |
| the agent proposes a step | `k.check(name, op)`; the user accepts, then `k[name] = op` |
| save / open a workflow | `k.to_json()` / `Kernel.from_json(text, catalog)` |
| notes, colours, widgets | `extras`, which core keeps and ignores |

If the app needs a fact the kernel can't give, that is a gap in core, not
something the app works out.

## 9. Found while checking (to fix in phase 4)

| # | What |
|---|---|
| G13 | **Readers aren't re-checked against a changed upstream.** `sick` changed from a `filter` (keeping `temp_c`) to a `map` (only `value`): `f`, which needs `temp_c`, is only `stale`, `validate()` reports nothing, and running `f` fails every row with `TypeError: to_f() missing 1 required positional argument: 'temp_c'`. It should be a problem on `f` as soon as `sick` changes |
| G14 | `run("f")` refuses when an input hasn't run, instead of running it first (C33) |
| G15 | no `needs_run()`, no change callbacks, no "read a stale input" mark |

## 10. Open

1. **The autorun modifier's definition** (§6.2): its triggers, how it's
   written, chains, cost guards, pacing.
