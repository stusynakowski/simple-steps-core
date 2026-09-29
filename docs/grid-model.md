# The grid model — reading `grid.py`

**Status: a working prototype, standalone.** It imports nothing from the engine
and the engine imports nothing from it, so everything that works today keeps
working. [shape-algebra.md](shape-algebra.md) is the target design and the
authority on *why*; this document is the map of what is actually built and how
it is arranged. Where they disagree, that one is the intent and this one is the
present.

Tests: `tests/unit/test_grid.py`, organized by the same three layers as §2 below.
To write tools against this model, see [writing-tools.md](writing-tools.md);
for the HTTP contract a React client would consume, see
[react-api.md](react-api.md).

---

## 1. The vocabulary

One word, one meaning. This table is the contract; anything in the code that
drifts from it is a bug.

| word | means | kind |
|---|---|---|
| **Tool** | a plain Python function declaring the values it needs | `(**values) -> Any` |
| **ToolHandle** | what `@tool` returns: the function plus an id | object |
| **Row** | one unit of work; its columns bind to a tool's parameters | data |
| **Modifier** | a descriptor: `kind` + `params` | data |
| **ModifierKind** | a vocabulary entry: name, class, applier | table entry |
| **Operation** | `tool_id` + ordered `Modifier`s + bound literals | data |
| **Output** | `data` + `ledger` + `meta` | data |
| **Step** | an `Operation` and an `Output`, always both | object |
| **Workflow** | ordered `Step`s — nothing else | object |
| **Grid** | the DataFrame in `Output.data` | data |
| **Ledger** | per-unit execution record, beside the grid | data |

Two distinctions that are easy to blur and cost real bugs when blurred:

- **`Modifier` vs. applying one.** `mod.map(over=x)` builds a *descriptor*. It
  is applying it — `op[mod.map(over=x)]` — that returns an `Operation`. The
  descriptor has to exist separately, or you could not name a modifier before
  you had a tool to put it on.
- **`Output.shape` vs. `Output.form`.** `shape` is `(rows, columns)`, exactly
  what pandas means by it. `form` is the cardinality class — `"scalar"`,
  `"column"`, `"grid"`. The form is what a step's mode *promises*; the shape is
  what it holds.

---

## 2. Three layers, one boundary

This is the whole structure. Two of the three are closed; there is exactly one
place where you leave the world of data and something executes.

```
build     Operation × Modifier ──► Operation        closed
          Operation × StepRef  ──► Operation        closed  (wiring)
run       Operation × Data     ──► Output           the boundary
inspect   Output               ──► DataFrame        closed
```

**Build** is closed, which is why the stack is a flat ordered list rather than a
tree, and why any order composes. Every path — `__getitem__`, `bind`,
`from_dict` — lands back on `Operation`.

**Run** is the single boundary, crossed in `compile_operation`. That is the one
function where descriptors become behaviour.

### Supplying rows is the modifier's job

A tool declares the **values** it needs. It never mentions a row:

```python
@tool
def score(n, weight=1):        # not  def score(row): return row["n"] * 10
    return n * 10 * weight
```

`map` binds each row's columns to those parameters by name — the same thing the
engine's `_run_item` does with `kwargs[arg] = item`. The alternative, passing
the whole row positionally, makes every tool name the row twice (once as a
parameter, once as a lookup), hard-codes the column name in the body, and makes
the tool unusable unmapped.

| rule | |
|---|---|
| columns bind **by name** | anything the tool does not declare is not passed |
| `**kwargs` gets the whole row | for the cases that want it — `identity` is the one |
| bound literals fill the rest | `score.bind(weight=2)` |
| a **column wins** a collision | the row is the unit of work — the engine's rule |
| a non-dict input is positional | an unorchestrated step over a bare value |

The payoff is bigger than the tidier signature: because the tool names what it
needs, **declaration can check the upstream actually has it** (§4).

### The calling rule

> **Brackets decorate. Parens apply — and a reference is an input you do not
> have yet.**

```python
score(3)                                    # data in hand      -> runs
score(wf["raw"])                            # a reference       -> wires a step
score[mod.map(over=step1)]                  # brackets          -> decorate
score.bind(weight=2)[mod.map()](wf["raw"])  # bind, decorate, wire
```

Applying to data runs it; applying to a reference has nothing to run, so it
builds the step that *will* run. One meaning, two times — not two meanings.
They cannot be confused, because a `StepRef` is never data.

`.run(...)` is the unambiguous half: it always executes, and refuses a
reference outright.

**Wiring is part of the build layer**, not an escape from it: it returns an
`Operation`, so `Operation × StepRef → Operation` is closed like everything
else there. What it writes is ordinary stored data — these are the same step:

```python
score[mod.map()](wf["raw"])
score[mod.map(over=wf["raw"])]
```

which is why everything reactive still works: `over` is in the Operation, where
`check`, staging, cycle detection and the light export all read it.

### Inferring the verb

With no shape verb to place, wiring picks one (`infer_verb`) and **stores it
concretely**:

```python
wf["scored"] = score(wf["raw"])      # -> map(over='raw') ∘ score
wf["sum"]    = total(wf["scored"])   # -> collapse(...)   total(acc, value)
wf["kept"]   = big(wf["scored"])     # -> filter(...)     big(value) -> bool
```

| signal | verb |
|---|---|
| `(acc, x)` — first value matches no column | `collapse` |
| return annotation is `bool` | `filter` |
| otherwise | `map` |

**What it can see depends on when you declare.** A step that has run knows its
columns exactly; a staged one predicts only the name of the payload column it
will write. Inference may use that prediction to *recognize* a pattern, but
`check` may not use it to *refuse* one — the prediction is a subset (a `map`
also carries its input's columns through), so rejecting against it would invent
errors.

Prediction covers the **whole column set**, not just the payload: `map`,
`filter`, `group` and `expand` carry their input's columns through, so a staged
step predicts those too, and `mod.map(name="score")` is predicted as `score`
rather than `value`. A test asserts the prediction equals the columns that
actually appear, for every step in a chain — predicting is not guessing.

What a staged step cannot predict is anything that depends on values rather than
structure: the column set of a `source` step you have not supplied yet, or how
many rows a `filter` will keep.

Two rules make this safe rather than magic:

**Nothing named `auto` ever reaches the data.** An `auto` modifier would be the
one whose shape is unknowable before running — no `ROWS_RULE` entry, no staged
claim, and a light export that could resolve differently on reload, breaking
the round-trip invariant. What is stored is an ordinary `map`, indistinguishable
from one you typed, so it shows up in a repr or a dropdown and you replace it by
writing the verb you wanted.

**It resolves once, at wiring.** An inferred verb is never silently re-inferred,
so a later change upstream cannot overwrite a choice you made. Same rule as
§7's push/pull: propagate staleness, never recompute behind the user.

`infer_verb` also returns its reason (*"'acc' is not a column but 'value' is, so
this reads as a reducer"*), which a UI can show as a caption. The reason is
derived, so it is recomputed rather than stored.

---

## 3. The modifier vocabulary is one table

`MODIFIERS` is the single place a modifier kind is declared. `SHAPE_VERBS`,
`DECORATORS`, `Modifier.cls`, `Modifier.is_shape` and `mod`'s validation all
derive from it, so adding a verb is one entry and a typo fails where it is
written.

`cls` is not taxonomy — it says what the modifier does to the signature it
wraps, and that is what makes reactive staging possible:

| class | does to the signature | staging |
|---|---|---|
| `shape` | **lifts** it: `(Row → b)` becomes `(source → Output)` | must fold it |
| `execution` | **preserves** it: `(Row → b)` stays `(Row → b)` | ignores it entirely |

Because execution modifiers cannot change shape, a step's shape is computable
from its stack without running anything. That is the whole reactive story in one
sentence.

Current vocabulary: `source`, `map`, `filter`, `group`, `expand`, `collapse`,
`sweep` (shape); `retry`, `timeout` (execution).

### Three orders, only one reversed

| | order | why |
|---|---|---|
| **written** in brackets | `map, retry` | outermost first, like stacked `@` |
| **stored** in `Operation.modifiers` | `retry, map` | innermost-first (§1.1) |
| **wrapped** — decoration happens | `retry, map` | inside before outside |
| **entered** — data arrives | `map, retry, retry…` | outermost first; retry per row |

Written order = nesting order = run-time entry order. The reversal is
mechanical and leaks into exactly one place, the stored list — so both orders
are named: `modifiers` (stored, what the engine folds) and `layers` (written,
what a user sees). Anything displaying a stack reads `layers`, or it shows the
reverse of the source that produced it.

---

## 4. A Step is born staged

Declaring a step **is** staging. A `Step` has both halves from the moment it
exists; running does not create the `Output`, it **replaces** it — never
mutates it, because writing a ledger row by row is 69× slower (§8.5).

```python
wf = Workflow()
wf["raw"]    = pd.DataFrame({"n": [1, 2, 3]})     # a bare value is a source step
wf["scored"] = score[mod.map(over=wf["raw"])]

wf.step("raw").status          # 'completed' — its data arrived with the declaration
wf.step("scored").status       # 'staged'
wf.step("scored").describe()   # 'map score · 3 cells'   — before running
wf.run_all()                   # now it computes
```

### The steps define the inputs

A **source step's data is its output.** It arrived with the declaration, so
there is nothing to stage and nothing to compute: that step is born
`completed`, and running it is a no-op.

This is why `vars(workflow) == ["steps"]`. An earlier version kept a parallel
`Workflow.inputs` map for literals, which was a mistake — it made source data a
second kind of thing with its own storage, its own branch in every resolver, and
its own key in the export. A literal was never anything but a step's output.
Removing it deleted the source branch from `_known_index` and `_input_for`, the
`step_id` threading through `stage()`, and the `inputs` key from the session
format.

Four functions carry this:

| function | answers |
|---|---|
| `check(operation, workflow, step_id)` | what is wrong, knowable without running |
| `stage(operation, …)` | what `Output` the step has before it runs |
| `Workflow.pending(step_id)` | which steps it reads that have not run |
| `Workflow.run(step_id)` / `run_all()` | execute, and replace the Output |

### Running refuses what it cannot do

`run(step_id)` will not run a step whose inputs are not there:

```python
wf.run("scored")
# ValueError: step 'scored' reads 'raw', which has not run.
#             Run 'raw' first, or call run_all().
```

This is worth the friction. Before the check existed, running against a staged
upstream coerced `None` into a one-row frame and returned a grid of `None` —
plausible-looking and wrong, which is the one outcome worth ruling out by
construction. `run_all()` orders a chain for you; it is still explicit, and
nothing ever recomputes on its own (§7's push/pull rule).

### Staged claims are honest

`ROWS_RULE` stores §3's rows column as data, and staging folds it. So a staged
step promises only what the verb can guarantee:

| verb | rule | staged claim |
|---|---|---|
| `map`, `group`, `source` | `same` | "3 cells" |
| `filter` | `at_most` | "at most 3 cells" |
| `collapse` | `one` | "1 cell" |
| `expand` | `unknown` | "unknown count from 3 rows" |
| `sweep` | `generated` | from its own parameters |

The staged ledger is materialized **only** when the addresses are genuinely
known (§7 level 3). An empty ledger is the honest answer otherwise.

`describe()` answers two different questions and must not blur them: a staged
step reports what staging can *promise*; a step that has run reports what it
actually *holds*. Only the first is a prediction.

### Invalid is a state, not an exception

`check()` never raises. A step with a mistyped argument, a dangling or circular
`over`, or an invalid upstream still exists, carrying its problems — reactive
editing needs to *show* a bad step mid-keystroke, not refuse to build it.

```python
wf["oops"] = score.bind(wieght=2)[mod.map(over=wf["raw"])]
wf.step("oops").problems[0]
# "score() takes no argument 'wieght'; it accepts weight"
```

An invalid Operation stages as **one cell**: it has no shape, because the thing
that would have given it one is what is broken. `run()` is what refuses.

Caught at declaration today:

| check | example |
|---|---|
| unknown tool / unknown modifier kind | |
| `over` dangles, self-references, is circular, or names an invalid step | |
| `source` applied to a real tool | |
| a bound literal the signature does not accept | `score.bind(wieght=2)` |
| **a required value the upstream cannot supply** | `score() needs 'n', which 'raw' does not have (it has count)` |

That last one is the payoff of binding by name — with a `def score(row)`
convention there is nothing to check against. It runs only against an upstream
that has **run**, because a staged Output holds placeholder rows rather than
real columns, so checking one would invent errors. The check therefore sharpens
as the workflow runs, the same way staging does — and a source step is born
completed, so the common case is covered from declaration.

**Not** yet caught: whether the upstream's column *types* fit the parameters.
Columns exist or they do not; matching dtypes to annotations is the next step.

---

## 5. Two export modes

They differ only in payloads.

| | method | carries | typical size |
|---|---|---|---|
| **light** | `to_json()` / `from_json()` | the chain of Operations, nothing else | ~283 B |
| **full** | `to_session_json()` / `from_json()` | that plus inputs and outputs | ~1.3 KB |

This is what keeping modifiers as descriptors buys: a step's definition is a few
strings, so exporting a workflow is nearly free.

There is **one payload map, not two**: a source step's literal serializes
through the same path as a computed output, because it *is* one. The light
export simply omits outputs, which is what keeps a literal out of it.

A light-reloaded source step therefore has no data, and says so rather than
computing something wrong:

```python
back = Workflow.from_json(wf.to_json(), tools)
back.run("raw")
# ValueError: source step 'raw' has no data. Assign it: wf['raw'] = <...>
back["raw"] = df        # supply it again, and the workflow runs
```

Staging is derived, so it is never stored. A light round-trip therefore lands at
§7's **level 1**: shape known, cardinality not, because cardinality came from
data the light export does not carry. That is by design, and it is the sharpest
test available that staging really is a function of structure:

```python
back = Workflow.from_dict(wf.to_session_dict(), tools)
assert back.step(sid).describe() == wf.step(sid).describe()   # for every step
```

Loading runs the same `check` and `stage` as declaring, so a load cannot smuggle
in a step that declaring would have rejected.

Payload codecs handle frames, scalars and lists, and **refuse** anything else.
This matters more than it looks: `DataFrame.to_json` does not fail on an object
column — it writes `{}` and reads back an empty dict. Silent loss is worse than
a refusal, so object columns are vetted per value before pandas sees the frame
(§8.8).

---

## 6. File map

`grid.py`, in order. Definitions precede use throughout.

| region | holds |
|---|---|
| `Output` | the payload grid, the ledger, `view()`, `form`, `shape` |
| `identity` / `BUILTIN_TOOLS` | the default tool, findable without a registry |
| `rows()` | input coercion — "what is a row?" (and the guarded column seam) |
| the verbs | `map_` `filter_` `group_` `collapse_` `expand_` `sweep_` `source_` |
| the appliers | `_d_retry` `_d_timeout` `_d_bind` `_lift` `_lift_generated` |
| **`MODIFIERS`** | the vocabulary table, and everything derived from it |
| `Modifier` / `Operation` | the deferred half — data, not closures |
| `StepRef` / `ToolHandle` / `@tool` | the authoring surface |
| payload codecs | `_encode` / `_decode`, only the full export needs them |
| `check` / `ROWS_RULE` / `stage` | declaration-time validation and staging |
| `Step` / `Workflow` | the two halves, and the ordered collection of them |
| `mod` | modifier constructors, validated against `MODIFIERS` |
| `compile_operation` | **the boundary**: data becomes behaviour |

---

## 7. Known gaps

Stated so they are not rediscovered as surprises.

1. **The engine has not moved.** `grid.py` is standalone. In the engine,
   `orchestration-map` is still the tool that runs and your function is a string
   argument — the inversion described in §11. The refactor that fixes it also
   deletes `ORCHESTRATORS`, `orchestrator_id`, `Tool.is_orchestrator`, and the
   engine's higher-order branches.
2. ~~**Two unit conventions.**~~ **Resolved.** `grid.py` now binds row columns
   to a tool's named parameters, matching the engine's `_run_item`
   (`kwargs[arg] = item`). The remaining difference is only breadth: the engine
   binds *one* item to *one* named parameter, while a grid row can fill several.
3. **`timeout` is a placeholder.** It records intent; real enforcement needs the
   async engine.
4. **Column verbs are guarded, not built.** `axis="columns"` raises. See §11.
5. **One shape verb per step is undecided.** The prototype permits several.
6. **No fingerprints, no `stale`.** Staleness (§7) and incremental recompute are
   designed but unbuilt; nothing is cached.
7. **`Output` has no `ref`.** [shape-algebra.md §5](shape-algebra.md) gives
   `Output` a `ref` into the session store, with `data` as the inline copy — the
   two-layer indirection the engine already has via `StepOutput.ref`. The
   prototype holds every payload inline on its Step, so two steps reading one
   grid each hold it, storage cannot be swapped for disk or Redis, and passing a
   Step passes its data. Both export modes work regardless; `ref` is what would
   let a large grid live outside the model.
8. **`Operation.fn` is a prototype convenience.** It carries the callable so a
   decorated tool can run without a registry. In the engine a step stores an id
   and the function lives in `REGISTRY`, so "decorate then pass data" becomes
   `session.run(operation, data)`, not `operation(data)`.
