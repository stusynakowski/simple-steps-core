# The grid model — reading `grid.py`

**Status: a working prototype, standalone.** It imports nothing from the engine
and the engine imports nothing from it, so everything that works today keeps
working. [shape-algebra.md](shape-algebra.md) is the target design and the
authority on *why*; this document is the map of what is actually built and how
it is arranged. Where they disagree, that one is the intent and this one is the
present.

Tests: `tests/unit/test_grid.py`, organized by the same three layers as §2 below.

---

## 1. The vocabulary

One word, one meaning. This table is the contract; anything in the code that
drifts from it is a bug.

| word | means | kind |
|---|---|---|
| **Tool** | a plain Python function; the unit of work | `(Row, **literals) -> Any` |
| **ToolHandle** | what `@tool` returns: the function plus an id | object |
| **Row** | one unit of work, always a `dict` | data |
| **Modifier** | a descriptor: `kind` + `params` | data |
| **ModifierKind** | a vocabulary entry: name, class, applier | table entry |
| **Operation** | `tool_id` + ordered `Modifier`s + bound literals | data |
| **Output** | `data` + `ledger` + `meta` | data |
| **Step** | an `Operation` and an `Output`, always both | object |
| **Workflow** | ordered `Step`s, plus the payloads source steps read | object |
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
run       Operation × Data     ──► Output           the boundary
inspect   Output               ──► DataFrame        closed
```

**Build** is closed, which is why the stack is a flat ordered list rather than a
tree, and why any order composes. Every path — `__getitem__`, `bind`,
`from_dict` — lands back on `Operation`.

**Run** is the single boundary, crossed in `compile_operation`. That is the one
function where descriptors become behaviour.

### The calling rule

```python
score({"n": 3})                                   # parens RUN
score[mod.map(over=step1), mod.retry(times=2)]    # brackets DECORATE
score.bind(weight=2)[mod.map(over=rows)](rows)    # bind, decorate, run
```

Parens always mean run — a `@tool` function stays an ordinary callable.
Brackets always mean decorate and always return data. There is no third rule,
and no method whose meaning depends on its receiver.

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

wf.step("scored").describe()   # 'map score · 3 cells'   — before running
wf.step("scored").status       # 'staged'
wf.run_all()                   # now it computes
```

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

Caught at declaration today: unknown tool, unknown modifier kind, `over` that
dangles / self-references / is circular / names an invalid step, `source` with a
real tool, and bound literals the tool's signature does not accept. **Not** yet
caught: whether an upstream's output *type* fits its reader — that needs output
schemas (§11).

---

## 5. Two export modes

They differ only in payloads.

| | method | carries | typical size |
|---|---|---|---|
| **light** | `to_json()` / `from_json()` | the chain of Operations, nothing else | ~283 B |
| **full** | `to_session_json()` / `from_json()` | that plus inputs and outputs | ~1.3 KB |

This is what keeping modifiers as descriptors buys: a step's definition is a few
strings, so exporting a workflow is nearly free.

Source payloads live in `Workflow.inputs`, **beside** the Operations, never
inside them — otherwise a source step would drag its whole table into the light
export.

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
2. **Two unit conventions.** `grid.py` passes a tool one row *dict*; the engine
   binds one item to a *named parameter* and passes constants as kwargs. This
   already bit `identity` once — "return the input unchanged" is a silent no-op
   under the row convention. The two must be reconciled deliberately.
3. **`timeout` is a placeholder.** It records intent; real enforcement needs the
   async engine.
4. **Column verbs are guarded, not built.** `axis="columns"` raises. See §11.
5. **One shape verb per step is undecided.** The prototype permits several.
6. **No fingerprints, no `stale`.** Staleness (§7) and incremental recompute are
   designed but unbuilt; nothing is cached.
7. **`Output` has no `ref`.** [shape-algebra.md §5](shape-algebra.md) gives
   `Output` a `ref` into the session store, with `data` as the inline copy — the
   two-layer indirection the engine already has via `StepOutput.ref`. The
   prototype holds payloads inline and keeps source payloads in
   `Workflow.inputs` instead, which is enough to make both export modes work but
   is not the target. Adding `ref` is what lets a big grid live outside the
   model.
8. **`Operation.fn` is a prototype convenience.** It carries the callable so a
   decorated tool can run without a registry. In the engine a step stores an id
   and the function lives in `REGISTRY`, so "decorate then pass data" becomes
   `session.run(operation, data)`, not `operation(data)`.
