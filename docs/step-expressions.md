# Step expressions — the rules, the syntax, and the reasons

A workflow is built one assignment at a time:

```python
wf["scored"] = score[mod.map()](wf["raw"])
```

The right-hand side is a **step expression**. This page is the complete set of
valid right-hand sides, the reference syntax they may contain, and *why* each
rule is the way it is. For the step lifecycle see
[object-model.md](object-model.md); for each verb's parameters see
[defining-operations.md](defining-operations.md) §10.

The whole design rests on one separation:

> **A modifier says *how* to orchestrate. A reference says *what* to read.**
> The two never mix. Data flows through one `input` slot and, when a value is
> needed, through `arguments` — never through a modifier.

---

## 1. The three shapes of a step expression

Everything you can assign to `wf[id]` is one of three things:

| expression | becomes | example |
|---|---|---|
| a **bare value** | a *source* step, born completed | `wf["raw"] = pd.DataFrame({"n": [1, 2]})` |
| an **Operation** | a computed step, staged at declaration | `wf["s"] = score[mod.map()](wf["raw"])` |
| a **bare shape modifier** | shorthand for the default-tool Operation | `wf["flat"] = mod.expand(over=wf["xs"])` |

- A bare value is the only expression with no tool: its data **is** its output,
  so there is nothing to run. A `DataFrame` is taken as-is; a `list`, `dict` or
  scalar becomes a one-cell grid.
- A bare *execution* modifier (`mod.retry(...)`) is **refused** — a
  pass-through that retries nothing is inert, and accepting it would hide a
  half-written step.

---

## 2. Building an Operation

An Operation is assembled from four optional parts, in this order:

```
tool handle  →  .bind(literals)  →  [mod.verb(...), …]  →  (input)
```

| piece | writes | form |
|---|---|---|
| **the tool** | `tool_id`, the function | `score` (a `@tool`) or `op("score")` (by id) |
| **bound literals** | `arguments` | `score.bind(weight=2)` or `op("score", weight=2)` |
| **decoration** | `modifiers` | `[mod.map(name="v"), mod.retry(times=3)]` |
| **the input** | `input` | the call position `(wf["raw"])`, or `over=wf["raw"]` |

These are all the **same** Operation — pick the form that reads best:

```python
score[mod.map()](wf["raw"])            # wire by the call position (canonical)
score[mod.map(over=wf["raw"])]         # wire with over= (identical data)
score(wf["raw"])                       # no verb written → one is inferred
```

Writing a bare tool on a reference **infers** the shape verb from the function's
return annotation (`-> bool` → `filter`, `-> list` → `expand`, else `map`) and
stores it concretely, so the step is complete and the chosen verb is visible.

---

## 3. References — the only two ways to name a step

A reference is produced **only** by subscripting the workflow:

```python
wf["raw"]      # by name  → StepRef("raw")
wf[0]          # by position → StepRef resolved to the id at that index
wf[-1]         # negative positions count from the end
```

- A `str` is **always** a name; an `int` is **always** a position. A step
  called `"0"` therefore stays reachable as `wf["0"]`.
- A position is resolved to the step's **id immediately** — a stored position
  would silently rewire the graph when an earlier step is inserted.
- The result is a `StepRef` **object**, not a string. That object carries the
  workflow it was read from, which is the whole provenance mechanism (rule 4).

A plain string (`"raw"`) is **not** a reference — it is a literal. The one
exception is `over="raw"`, which is coerced to a `StepRef` as authoring sugar.

---

## 4. Where a reference may appear

| position | holds | how many |
|---|---|---|
| the **data input** | the step whose grid this reads | **exactly one** |
| a **value argument** | another step's value, read at run (K10) | any number |
| a **modifier param** | — | **never** |

```python
# data input (call position or over=) — the grid this step iterates
wf["scored"] = score[mod.map()](wf["raw"])

# value reference in arguments — resolved to a value at run
wf["flag"]   = above[mod.map()](wf["raw"], k=wf["cutoff"])
```

A **value reference** resolves when the step runs: a one-cell step gives its
cell (a scalar flows in as a scalar); anything larger gives the whole grid. It
is still a real dependency — the graph runs `cutoff` before `flag`.

---

## 5. The rules, and why each one exists

1. **One data input per step.** A step reads exactly one grid. *Why:* the cell
   address `(step, row, column)` must stay unambiguous; combining two inputs is
   a real operation (a merge / `join`), not a free-for-all, so it gets its own
   verb rather than hiding in the wiring.

2. **Modifiers are literal-only.** A modifier's `params` are numbers, strings
   and lists — never a reference. *Why:* a modifier describes *how* to
   orchestrate (map, retry, widen), and mixing in *what* data it reads makes the
   two impossible to reason about separately. Keeping references out means the
   dependency graph is derivable from `input` + argument refs alone, and a stack
   of modifiers can be reordered or re-rendered without rewiring anything.

3. **At most one shape verb per step.** *Why:* the step is the unit a user sees,
   addresses and re-drives. Two shape changes inside one step produce an
   intermediate grid with no cell address — a unit that failed there could
   neither be inspected nor re-run.

4. **A reference should be a `StepRef`; a plain string is an unchecked
   template.** *Why:* a `StepRef` knows which workflow it came from, so reading
   a step from the *wrong* workflow is caught at declaration. A bare string
   carries no workflow and means "whatever `'x'` is in *this* workflow" — which
   is exactly what you want when reusing one operation across workflows, and is
   the only time to prefer it.

5. **A reference must name an earlier, valid, non-circular step in this
   workflow.** *Why:* staging predicts a step's shape from its upstream before
   anything runs, so the upstream has to exist and be valid; a cycle has no run
   order. A dangling, self- or cross-referencing input is a **problem**, not an
   exception — the editor can show it mid-keystroke, and `run()` refuses it.

6. **Declaring a step stages it.** `wf[id] = op` validates and stages
   immediately; nothing computes until `run()`. *Why:* a reactive editor must be
   able to show a step — valid or not, with its predicted shape — the moment it
   is written.

---

## 6. How it serializes

Every reference is one envelope — `{"$ref": id}` — distinct from a literal
string. An Operation is exactly four keys:

```python
scale.bind(weight=2)[mod.map(name="score")](wf["readings"]).to_dict()
# {
#   "tool_id":   "scale",
#   "input":     {"$ref": "readings"},   # the data — a reference
#   "arguments": {"weight": 2},          # literals; a value ref is {"$ref": …} too
#   "modifiers": [{"kind": "map", "params": {"name": "score"}}],   # literal-only
# }
```

A workflow is `{"version": 1, "steps": [{"step_id": …, "operation": {…}}]}`. The
DAG is **derived** from the `$ref`s, never stored separately. A legacy export
that kept `over` inside a modifier still loads — it is hoisted into `input`.

---

## 7. The grammar, in one block

```
step          := "wf[" step_id "] = " operand

operand       := operation                       # §1 computed step
               | literal                         # §1 source step
               | shape_modifier                  # §1 bare verb, default tool

operation     := tool_expr [ decoration ] [ wiring ]

tool_expr     := tool_handle                     # a @tool-decorated function
               | tool_handle ".bind(" literals ")"
               | "op(" tool_id [ "," literals ] ")"

decoration    := "[" modifier { "," modifier } "]"     # outermost-first

wiring        := "(" reference [ "," literals ] ")"    # the input — canonical

modifier      := "mod." shape_verb "(" [ literals ] [ "over=" reference ] ")"
               | "mod." exec_mod   "(" literals ")"    # literals only, no refs

literals      := name "=" value { "," name "=" value }   # value may be a reference
reference     := "wf[" step_id "]"               # preferred — a typo is a KeyError
               | string                          # unchecked template; same on disk
```

`shape_verb` is one of the 14 (`source`, `map`, `filter`, `select`, `drop`,
`widen`, `slice`, `rename`, `sort`, `distinct`, `group`, `expand`, `collapse`,
`sweep`); `exec_mod` is `retry` or `timeout`. `wiring` and `over=` are
alternatives — write both and the call position wins.

---

## 8. What is *not* a valid step expression

| mistake | what happens | do instead |
|---|---|---|
| a bare string as a reference — `score[mod.map()]("raw")` | `"raw"` is run as *data*, not a step | `score[mod.map()](wf["raw"])` |
| the data passed as an argument — `score.bind(input=wf["raw"])` | the input is the call position, not an argument | `score[mod.map()](wf["raw"])` |
| a reference inside a modifier param | never stored there — `over=` is hoisted to `input` | pass the input; use `over=` only as sugar |
| two shape verbs in one step | a problem: *"2 shape verbs in one step…"* | split into two steps |
| reading two steps at once | one input per step | a merge verb (`join`, designed — [status.md](status.md) D1) |
| subscripting a reference — `wf["s"].ok`, `wf["s"][0]` | not built in the grid model | read `wf.step("s").output` after it runs |
