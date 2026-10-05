# Shape algebra — the target model

**Status: agreed design; partly built in the prototype, not in the engine.**
[object-model.md](object-model.md) describes what the engine holds today and
marks each object that is changing; [grid-model.md](grid-model.md) describes
what is built of this design in `grid.py`. Where they disagree, this document is
the intent, object-model is the engine's present, and grid-model is the
prototype's present.

The goal in one sentence: **a spreadsheet for expensive, impure, failable
Python functions.** Excel can recompute on every keystroke because its
functions are instant, pure and cannot fail. Transcription, LLM calls and model
inference are none of those, and every difference below follows from that.

---

## 1. Vocabulary

Two words were doing double duty and caused most of our confusion. The tidy
meanings win; the workflow concepts get new names.

| term | means |
|---|---|
| **tool** | a plain Python function the user wrote |
| **step** | a node in the workflow: a tool plus how to run it, plus what it produced |
| **grid** | the rows × columns output of an **orchestrated** step |
| **row** | a horizontal slice of the grid — an observation |
| **column** | a vertical slice — one variable about each observation |
| **cell** | one (row, column) intersection; holds any Python object |
| **unit** | **what one invocation of the tool covers** (§1.0) — a row, a column or a cell |
| **index** | a row's stable address, preserved across steps |
| **payload column** | the column holding the produced object (conventionally `value`) |
| **ledger** | the per-**unit** execution record |
| **shape** | a grid's rows × columns — what a verb changes, step to step (§3) |
| **alignment** | how `data` and `ledger` line up inside one Output (§5) |

Deliberately retired: calling a step "a column" (it clashes with a variable),
and calling a step's output box "a cell" (it clashes with a datum).

### 1.0 A row is not the same thing as a unit of work

These two coincide today and are not the same idea, so they get separate words.
**Unit** is the abstract one: what a single invocation of the tool covers, and
therefore what the ledger records one entry of. Which slice of the grid *serves*
as the unit is the verb's choice:

| unit | how many | the ledger is indexed by | status |
|---|---|---|---|
| **row** | n | the row index | the only one built |
| **column** | m | the column name | guarded — see §11 |
| **cell** | n × m | (row, column) | depends on 2-D grids — see §11 |

Saying "the row is the unit of work" is true of every verb that exists right
now, and it is the sentence that would quietly forbid `colmap`. Row-wise is a
**default**, not a definition.

Two consequences that follow immediately, and that the rest of this document
depends on:

- §5's alignment rule is *"one ledger entry per unit"*, **not** "per row". That
  is what already lets `filter` keep a ledger entry for a row it dropped.
- A column-wise verb does not merely have a different *number* of units; its
  ledger lives in a different **index space** (column names, not row positions).
  That is why it cannot be added as an `axis=` flag and nothing else — the join
  in `Output.view()` stops being meaningful.

The cell case is the least settled, because today every grid is flat: one row
per unit, with the produced object in one payload column. A cell only becomes a
distinct unit if grids become genuinely 2-D, which §11 leaves open.

### 1.1 Tool, Operation, Step, Output

These four were already defined in [object-model.md](object-model.md) §7–§9 and
[how-it-works.md](how-it-works.md). **Nothing here changes their meaning** —
this spec only changes what *Output* contains. Restated so we are aligned:

| term | is | lifetime |
|---|---|---|
| **Tool** | the registered capability — a plain Python function plus its `ToolDefinition` contract | declared once, at import |
| **Operation** | **one Tool + an ordered stack of modifiers** (higher-order functions), plus arguments | created when you wire a step |
| **ToolCall** | an Operation *compiled* to the executable form the engine runs | derived, `operation.to_tool_call()` |
| **Step** | one node of the workflow: **Operation + Output** | lives in the workflow |
| **Output** | what the Step produced — grid + ledger + meta | filled by running |

The pipeline, unchanged from the existing docs:

```
Tool  ──wrap it in HOFs──►  Operation  ──compile──►  ToolCall  ──run──►  Output
(a function)                (one tool +             (what the           (grid +
                             modifier stack          engine executes)    ledger)
                             + args)
```

> You *author* Operations; the engine *runs* ToolCalls; a Step *holds* the
> Operation and its Output.

#### An Operation is one tool wrapped by many modifiers

Not "a tool plus two config blobs" — **a tool with an ordered stack of
higher-order functions applied to it**, declared when you wire the step:

```python
wf["step2"] = score[mod.map(over="step1", concurrency=8),
                    mod.retry(times=3),
                    mod.timeout(seconds=30)]
```

**Order is semantics, not style.** These are different runs:

| composition | means |
|---|---|
| `map(retry(f))` | retry **each item** — 100 items, each may retry |
| `retry(map(f))` | retry **the whole fan-out** — one retry of all 100 |
| `map(timeout(f, 60))` | 60s **per item** |
| `timeout(map(f), 60)` | 60s for **the entire step** |

Today's flat `StepExecutionConfig` cannot express the second of each pair. Its
own docstring concedes it: *"`retries` means 'retry the unit' … the whole call
when `single`, one item when fanned out"* — the mode decides for you, and
"retry the whole fan-out" is simply unsayable. A stack makes it explicit.

#### Two classes of modifier

Shape verbs split again by whether they **run a tool** (§2.1), so the vocabulary
is really three tiers:

| class | modifiers | effect on shape |
|---|---|---|
| **shape verbs · run a tool** | `map` `filter` `group` `expand` `collapse` `sweep` | change rows/columns **and** can fail per unit (§3) |
| **shape verbs · no tool** | `source` `select` `drop` `rename` `widen` `slice` `sort` `distinct` | change rows/columns, nothing runs so nothing fails (§3) |
| **execution modifiers** | `retry` `timeout` `cache` `gate` `concurrency` | shape-preserving |

Staged shape is the **fold of the shape verbs in stack order** — still pure
structure, still computable before anything runs.

**At most one shape verb per step — proposed, not settled (§11).** Nothing in
the algebra forbids `filter(map(f))`, but a step is the unit the user sees,
addresses and re-drives. Two shape changes inside one step means an intermediate
grid that has no cell address and cannot be inspected or re-run. The argument
for keeping every shape change visible as its own column is strong.

Against it: the prototype permits several and folds them, and a spreadsheet
formula `=SUM(FILTER(...))` is the everyday counter-example — nesting inside one
cell is normal and readable. This gates how `inference.effective_output`
composes, so it needs deciding rather than assuming.

#### Modifiers are data

The stack is stored as an ordered list of descriptors, never as closures:

```python
Operation(
  tool="score",
  arguments={...},
  modifiers=[
    Modifier(kind="timeout", params={"seconds": 30}),
    Modifier(kind="retry",   params={"times": 3}),
    Modifier(kind="map",     params={"over": "step1", "concurrency": 8}),
  ],
)
```

**Stored innermost-first**, which is the order the layers are *applied* — you
must build the inside before the outside. The bracket list is written the other
way, outermost first, exactly as stacked `@` lines read:

```python
score[mod.map(over="step1"), mod.retry(times=2)]   # written: map, retry
#  →  modifiers == [retry, map]                    # stored:  retry, map
```

So the stored list `[retry, map]` means `retry` sits closest to the tool and
runs **per item**; `[map, retry]` would wrap the whole fan-out. Both orders are
named — `modifiers` (stored, what the engine folds) and `layers` (written, what
a user sees) — so a repr or an editor never shows the reverse of the source that
produced it.

Nothing attaches to the function declaration. That is the point, and it is why
brackets are safe where `@` is not: the same tool must be usable bare in one
step and mapped in another, which a decorator fixed at import cannot do (§6.4).

Keeping the stack as descriptors rather than closures is what keeps staging,
serialization and UI construction alive (§6). And it is what
`OrchestrationConfig` and `StepExecutionConfig` dissolve into: the former
becomes the single shape verb in the stack, the latter becomes execution
modifiers.

**Output is the only thing this spec redefines.** Today the second half of a
Step is called `Data` and holds `StepStatus` + `StepOutput` + `StepError`.
Those three collapse into one `Output` object (§5), because per-row state needs
somewhere to live.

| today | becomes |
|---|---|
| `Data` (the concept) | **`Output`** — the object, not just a concept |
| `StepOutput` (`ref`, `value`, `kind`) | `Output.ref`, `Output.data`, `Output.meta` |
| `StepStatus` (one per step) | `Output.status` — now a **rollup** of the ledger |
| `StepError` (one per step) | a column in `Output.ledger`, one per row |

### 1.2 A naming wart to fix while we are here

`ToolCall.operation_id` and `ToolDefinition.operation_id` **name a Tool, not an
Operation** — the existing docs already concede this ("also readable as
`.tool_id`"). Since these are the exact four words we are clarifying, the field
should be renamed `tool_id`, with `operation_id` kept as a deprecated alias.
Leaving it guarantees this conversation happens again.

---

## 2. The invariant

> **Equip a tool with any orchestration → its output is a grid.
> No orchestration → a single value.**

No exceptions, including `collapse`, which returns a one-row grid. A bare
`int` from an unorchestrated step stays a bare `int` — an integer should not
cost a DataFrame.

This is what makes the UI simple: **shape comes from the step's mode, never
from the payload.** A user-uploaded table is always *one cell*, however many
rows it has; it becomes many rows only when a verb explicitly fans out over it.
No component ever has to ask "is this one cell or many?" — it reads the mode,
which is written on the step before anything runs.

---

## 2.1 Tidy intent: the return type does not decide the shape — the verb does

The goal of the grid is a **tidy table**, in Wickham's exact sense:

1. **each column is a variable** — one attribute measured across every unit;
2. **each row is an observation** — all the values measured on one unit;
3. **each cell is a single value** — one discrete measurement.

A tool, though, is a plain Python function, and Python return types do not carry
tidy intent. `list_files` returns `["a.csv", "b.csv"]`; is that **two
observations of one variable** (two files) or **one observation holding a
vector** (a single value that happens to be a list)? `("SF", 18)` — one
observation with two variables, or two observations? The type alone cannot say.

The model's answer is the principle you are generalizing:

> **A tool invocation always produces exactly one cell** — one value, of any
> Python type. **Turning that cell into rows and columns is a separate
> declaration: the shape modifier.** The tool stays tidy-agnostic; the verb
> carries the tidy intent.

So `list_files` undecorated is *one cell* holding the list (rule 3 is not
violated — nobody asked for a table yet). It becomes a tidy column of files only
when a verb says what the list *means*. That is the whole job of the reshaping
verbs, and there are exactly **two directions** to unnest a cell, which is why
`expand` and `widen` are a pair:

| direction | tidyr | makes the grid | from a cell holding | verb |
|---|---|---|---|---|
| **longer** | `unnest_longer` | more **observations** (rows) | a collection of like things | `expand` |
| **wider** | `unnest_wider` | more **variables** (columns) | a record of named fields | `widen` |

### The return-type → tidy-grid map

Reading any Python return as a tidy shape, and the verb that declares it:

| a cell holds | tidy reading | declare with | result |
|---|---|---|---|
| a **scalar** (`18`, `"a.csv"`) | one value of one variable | — (already a cell) | stays 1 cell |
| a **list/tuple of like values** (`["a.csv", "b.csv"]`) | **n observations, one variable** | `expand` | n rows × `value` |
| a **dict / named record** (`{"city": "SF", "temp": 18}`) | **one observation, n variables** | `widen(columns=…)` | 1 row × `city, temp` |
| a **list of dicts** (`[{…}, {…}]`) | **n observations, n variables** — a table | `expand` **then** `widen` | n rows × those columns |
| a **DataFrame** | already tidy | `source` / pass through | n rows × m columns |

Three rules make this intuitive instead of guessy:

- **Name your variables, position your observations.** If the pieces are
  *different attributes* (a city **and** a temperature), return a **dict** so
  `widen` can give each a named column — rule 1. If they are *the same thing
  repeated* (many files), return a **list** so `expand` can give each its own
  row — rule 2. A bare `tuple` of heterogeneous values has no names, so it can
  only become positional rows; that is the signal to return a dict instead.

- **Longer and wider compose, one step each.** A `list of dicts` is both
  directions at once, so it is two steps: `expand` to one dict per row, then
  `widen` to spread each dict into columns. The one-shape-verb-per-step rule
  (§11) is what keeps each reshape a visible, addressable cell rather than a
  hidden nested frame — which is itself tidier than doing both at once.

- **Row identity follows the direction.** `expand` adds rows, so it cannot keep
  the input's index — it resets to positional and records each new row's origin
  in the ledger's `unit` column (§5). `widen` adds columns and keeps every row,
  so the observation keeps its address. This is the coercion table of §3's
  "n rows are" column, stated as intent.

A fourth, deliberate limit: the only thing that *starts* a grid from raw data is
`source`. It lifts a literal (a list, a dict, a frame) into the first grid using
the same coercion — a list becomes rows, a dict becomes rows keyed by its keys,
a scalar becomes one cell. `source` is `expand`'s counterpart at the head of a
chain: `expand` unnests an **upstream** step's cell, `source` unnests a
**literal** you hand it.

---

## 3. The shape algebra

*Shape* here means the **step-to-step** relationship: how one step's grid
becomes the next one's. The separate question of how `data` lines up with
`ledger` **inside** a single Output is *alignment*, covered in §5.

Every orchestration first coerces its input to **n rows**:

| input | n rows are |
|---|---|
| an upstream grid | its rows |
| a table | the table's rows |
| a list / `Collection` | its elements |
| a single object | 1 row |

Then the verb transforms. Output **columns are a function of input columns** —
that is the "shape of the output depends on the shape of the input" part. There
are **fourteen** verbs, in the two classes §2.1 draws: those that **run a tool**
(and so can fail per unit) and those that **purely reshape** (apply no tool, so
nothing can fail). A third column, **index**, tracks row identity — the address
a cell keeps across the step, which is what §5's ledger joins on.

Index legend: *preserved* = the row keeps its address (the index travels with
it); *reset* = output rows outnumber inputs, so a positional index replaces it
and the ledger's `unit` column records each row's origin; *from value* = taken
from the coerced literal (a list → positional, a dict → its keys); *new* = built
fresh because the rows are.

**Verbs that run a tool** — compute *and* reshape:

| verb | rows | columns | index | tidy name |
|---|---|---|---|---|
| `map` | n → n | input columns **+ payload** | preserved | `mutate` |
| `filter` | n → k ≤ n | input columns unchanged | preserved (dropped rows stay in the ledger) | `filter` |
| `group` | n → n | input columns **+ key column** | preserved | `group_by` |
| `expand` | n → m | input columns carried **+ payload** | **reset** — origin in `unit` | `unnest_longer` |
| `collapse` | n → 1 (or k with `by=`) | payload **+** group key | **new** — origin in `unit` | `summarise` |
| `sweep` | 1 → n×m | one column **per swept parameter + payload** | **new** — the parameter grid | `crossing` |

**Verbs that apply no tool** — purely reshape (§2.1):

| verb | rows | columns | index | tidy name |
|---|---|---|---|---|
| `source` | value → n | the value's own columns | **from value** | — (chain start) |
| `select` | n → n | the named columns, **in the order given** | preserved | `select` |
| `drop` | n → n | every column except the named ones | preserved | `select(-…)` |
| `rename` | n → n | same columns, renamed (order + values kept) | preserved | `rename` |
| `widen` | n → n | input columns **+ the lifted fields** | preserved | `unnest_wider` |
| `slice` | n → k ≤ n | unchanged | preserved (surviving rows) | `slice` |
| `sort` | n → n | unchanged | preserved (travels with the row) | `arrange` |
| `distinct` | n → k ≤ n | unchanged | preserved (first of each kept) | `distinct` |

The default payload column is `value`; the mapping verbs (`map`, `expand`,
`collapse`, `sweep`) and `group`'s key column accept `name=` to rename it.
`widen` is the one no-tool verb that still runs **per row** — it has a real
ledger, so a cell that is not a record, or is missing a declared field, is an
inspectable per-unit failure rather than a crash.

`select` and `drop` are the column-axis mirror of `filter`: filter chooses rows,
these choose columns. Two verbs rather than one with a `drop=` argument, because
each then does one thing, needs no mutually-exclusive arguments, and reads right
— "select drop" never did.

Both are **strict**: naming a column the input does not have is a typo, not a
no-op, and it is caught at declaration. And both apply **no tool**, which is
what makes them buildable while `colmap` is not — nothing executes, so nothing
can fail, so there are no per-column ledger entries and none of §5's
index-space problems arise.

You need it less often than you would expect *before* a `map`, because column
binding already hands a tool only the values it declares (§6.1). Its job is the
grid you carry **forward**: `map` passes every input column through, and
`select` is how you drop the ones downstream does not want.

`source` is the verb a chain starts with. Making it a verb rather than a
special case is what closes the algebra: **every** step is then (verb, tool,
arguments), the first one included, and its tool is `identity` (§6.3).

The rows column above is not prose — it is stored as `ROWS_RULE`, and staging
folds it. That is what lets a staged claim be honest: `map` can promise *n*
cells, `filter` only *at most n*, `collapse` exactly one, and `expand` cannot
know (§7).

Naming note: the tidy-name column borrows dplyr/tidyr where a verb matches one —
`filter`, `select`, `rename`, `distinct`, `slice`, `arrange`, `group_by`,
`summarise`, and the two unnests (`expand` = `unnest_longer`, `widen` =
`unnest_wider`, `sweep` = `crossing`). `map` is dplyr's `mutate`, and `drop` is
`select(-…)`. We keep our own names in the API; the column is only there to lend
each verb a one-word meaning a reader may already hold.

### Two consequences worth stating plainly

**`map` stops discarding the table.** Today `map` over a 3-row table returns a
`MapResult` of three values and the table is gone. Under `mutate` semantics it
returns the table plus a column:

```
   n  g  score
0  1  a     10
1  2  b     20
2  3  a     30
```

**`group` stops nesting.** It marks rows with a key column and keeps n rows;
reduction happens in `collapse(by=...)`. The "column of columns" problem
disappears rather than being solved:

```
group(over=step1, op=topic_of)        → step1's rows + a `topic` column   (n rows)
collapse(over=step2, by="topic", …)   → one row per topic                 (k rows)
```

---

## 4. The objects

### 4.0 The hierarchy, revised

Same notation as [object-model.md](object-model.md). **Bold** = new or changed.

```
App                         unchanged
├─ ToolRegistry             unchanged — tools, aliases, resource binding
│   └─ Tool                 a plain function + its ToolDefinition contract
├─ ResourceSpec*            unchanged — a resource and the tools bound to it
└─ Session
    └─ Workflow*
        ├─ graph()          **DERIVED, not stored** — edges from reference tokens
        └─ Step*            ordered steps
            ├─ Operation                 what to run — stays DATA
            │   ├─ tool                  ONE tool (by id)
            │   ├─ arguments             literals / references to earlier steps
            │   └─ **modifiers[]**       an ORDERED stack of higher-order fns
            │       ├─ shape verb        at most one: map | filter | expand
            │       │                    | collapse | group | **sweep**
            │       └─ execution mods    retry | timeout | cache | gate | concurrency
            │                            (order matters: retry(map(f)) ≠ map(retry(f)))
            └─ **Output**                what it produced
                ├─ **data**       DataFrame — the payload grid (immutable)
                │   ├─ index              stable cell address
                │   ├─ input columns      carried through
                │   ├─ payload column     the produced object (any type)
                │   └─ key / param cols   group keys, swept parameters
                ├─ **ledger**     DataFrame — per-row execution state (mutable)
                │   ├─ **status**         staged | running | completed | failed | **stale**
                │   ├─ error              per-row failure message
                │   ├─ attempts           retries used
                │   ├─ started_at/ended_at
                │   └─ **fingerprint**    what makes staleness computable
                └─ meta           dict — shape, tool id, run id
```

`*` = repeatable. `Output.view()` joins `data` and `ledger` on the index; that
join is the only thing the user sees.

Retired from the old hierarchy: `MapResult`, `Group`, `Groups`. `ItemOutcome`
survives only as an in-flight record during a run, materialized into `ledger`.

### 4.1 Unchanged

These are settled and stay as they are.

| object | role |
|---|---|
| tool (plain function) | the unit of work the user writes |
| `ToolDefinition` / `ToolParam` / `Guardrails` | a tool's public contract |
| `ToolRegistry` | tools by id, with aliases and resource binding |
| `ResourceSpec` / `ResourceContainer` / `Resource()` | injected runtime dependencies |
| `Collection` / `ListCollection` | lazy, versioned sources |
| `MediaAsset` / `MediaStore` | images and video held by handle |
| `ToolCall` | a durable, serialized invocation |
| `Workflow` / `SessionContext` / `CoreEngine` | ordered steps, payload store, execution |
| `Operation` | stays, and stays **data** — but now holds a modifier stack (§1.1) |

### 4.2 Changed

| object | change | why |
|---|---|---|
| `Step` | `Operation + Data` → **`Operation + Output`** | the ledger has to live somewhere |
| `StepOutput` | **absorbed into `Output`** — `ref` stays, `kind`/timings move to `Output.meta` | one object, not three |
| `StepStatus` | `PENDING` → `STAGED`; add `STALE` | the state already meant "staged"; staleness is new |
| `map` | returns a grid, not a `MapResult` | mutate semantics |
| `group` | adds a key column, no nesting | tidy semantics |
| `collapse` | gains `by=` | reduce within strata |
| `OrchestrationConfig` | dissolves into **the one shape verb** in `Operation.modifiers` | order-sensitive composition |
| `StepExecutionConfig` | dissolves into **execution modifiers** in the same stack | `retry(map(f))` vs `map(retry(f))` |

### 4.3 New

| object | role |
|---|---|
| **`Output`** | `data` + `ledger` + `meta`, with one merged `view()` — replaces `Data`/`StepOutput`/`StepError` |
| **`sweep`** | the cross-product verb: parameters in, a grid of cells out |
| **`Modifier`** | one entry in an Operation's stack: `kind` + `params`, ordered |
| **fingerprint** | a ledger column: what makes staleness computable |
| **graph derivation** | a *function*, not a stored object (§7) |
| **`ModifierKind`** | one entry in the modifier vocabulary: name, class, applier — the single place a kind is declared |
| **`Step`** | `Operation` + `Output`, both present from declaration (§7) |
| **`Workflow`** | ordered `Step`s, plus the payloads source steps read |
| **`check()`** | everything wrong with an Operation that is knowable without running it — returns problems, never raises |
| **`stage()`** | the `Output` a step has before it runs |
| **`identity`** | the default tool for the mapping verbs: what closes the algebra (§6.3) |
| **`gather`** | the default tool for `collapse` — the reduction that discards nothing |
| **builtin reducers** | `count`, `total`, `first`, `last` — so a `collapse` needs no bespoke tool |
| **`DEFAULT_TOOL`** | verb → the tool it applies when none is named |

### 4.4 Retired

| object | replaced by |
|---|---|
| `MapResult` | the grid (values) + the ledger (status/error) |
| `Group` / `Groups` | a key column produced by `group` |
| `ItemOutcome` | demoted to an **in-flight record** during a run, materialized into the ledger |

---

## 5. Output: one grid, two frames

The output is **one** dataframe. The ledger sits beside it on the Step — the
same way `Step.status` already sits beside `Step.output`.

```python
class Output:
    ref:    str | None     # key into the session store, where `data` actually lives
    data:   DataFrame      # payload grid — immutable, referenced by downstream steps
    ledger: DataFrame      # execution state — mutable, index-aligned, never referenced as data
    meta:   dict           # shape, tool id, run id, timings
    def view(self): return self.data.join(self.ledger)
```

### The alignment invariant

Two different relationships are easy to conflate, so they get different words:

| word | relates | changes? |
|---|---|---|
| **shape** (§3) | one step's grid to the **next step's** grid | yes — that is what a verb does |
| **alignment** (§5) | `data` to `ledger` **inside one Output** | no — always row-for-row |

This section is only about the second.

> **`data` and `ledger` are aligned by unit: one ledger entry per unit of work,
> sharing one index.**
>
> With row-wise verbs — every verb that exists today — a unit *is* a row, so
> this reads as row-for-row. It is stated in units because that is what makes it
> survive a column-wise verb (§1.0).

They differ only in *columns* — that is the whole point of the split. The index
is what joins them, and `view()` is always a clean 1:1 join.

This holds exactly for the verbs that are 1:1 — `map`, `group`, `sweep`. For
the three that are not, "one row per **unit of work**" and "one row per
**output row**" come apart:

| verb | units attempted | output rows | aligned? |
|---|---|---|---|
| `map` / `group` / `sweep` | n | n | **yes** |
| `filter` | n | k ≤ n | no — n−k units produced no row |
| `expand` | n | m | no — one unit may yield many rows |
| `collapse` | n | 1 | no |

**Resolution: the ledger has one row per *unit of work*, indexed by the
input's index.** That gives three tiers rather than a binary choice:

| verb | alignment |
|---|---|
| `map` / `group` / `sweep` | indexes **coincide** — the invariant holds exactly |
| `filter` | ledger **⊇** data, same index space — `join` still finds every data row |
| `expand` / `collapse` | different spaces — the ledger carries a **`unit`** column naming its source row |

`filter` is the case that decides it. Four predicates run, two rows survive;
a unit-of-work ledger still answers *what happened to the other two*:

```
      status   kept             error
1  completed  False               NaN      ← predicate said no
3     failed  False  predicate raised      ← predicate crashed
```

Mirroring output rows instead would buy strict 1:1 everywhere at the cost of
that record — for the one verb whose job is dropping things. `unit` is the
general link; for the 1:1 verbs it *is* the index, so it costs nothing there.
(It is named `unit`, not `source`, because `source` is now a verb.)

`Output` replaces `Data` and `StepOutput`, and absorbs `StepError`. The two-layer indirection survives unchanged:
`ref` points into `SessionContext.outputs`, and `data` is the inline copy —
exactly as `StepOutput.ref` / `.value` work today. An unorchestrated step has
`data` holding a single value and no `ledger`.

### Why not one frame

1. **Collisions.** Real tables already have columns named `value` and `status`.
   No prefix convention survives contact with scientific data.
2. **Mutability.** Status changes *while the step runs*; the payload must not.
   A downstream step referencing a payload that is being rewritten row by row
   is reading a moving target.
3. **Arrow.** The ledger is all scalar columns, so progress and error views
   always render natively. Only the payload column carries objects.

### What goes where

Rule of thumb: *would you ever group or filter your analysis by it?* → data.
*Does it describe how the run went?* → ledger.

| data (grid) | ledger |
|---|---|
| input columns carried through | `status` |
| the produced object | `error` |
| swept parameters | `attempts` |
| group keys | `started_at` / `ended_at` |
| | `unit` (which input row this records) |
| | `fingerprint` |

### Referencing

| reference | resolves to |
|---|---|
| `step2` | the payload grid |
| `step2.ok` | grid rows whose ledger says completed |
| `step2.failed` | ledger rows that failed — the re-drive set |
| `step2.ledger` | the full execution record |
| `step2[0]` / `step2['q1']` / `step2['east']['q1']` | accessor paths (already implemented) |

---

## 6. Authoring: functions outside, data inside

Tools are plain functions; **orchestration is declared when the step is wired,
never on the function.** The same tool must be usable `once` in one step and
`map` in another.

Decorating the tool at the wiring site gives this, with nothing attached to the
function:

```python
wf["step2"] = score[mod.map(over="step1", concurrency=8), mod.retry(times=2)]
```

Each layer appends one `Modifier` to the stack, so they compose and the stack
records the order you wrote. They return **data, not closures**. This is not
negotiable, because four things die with closures:

| | config as data | closure |
|---|---|---|
| reactive staging | reads `mode` → "one cell per item of step1" | opaque until it runs |
| `to_json()` / `from_json` | serializes | cannot serialize |
| dashboard building steps from dropdowns | constructs the data | cannot construct |
| fingerprinting | hashes resolved args | nothing stable to hash |

Reactive staging is the feature we care most about, and it is the one that
requires the orchestration to be readable before anything executes.

### 6.1 One surface: parens run, brackets decorate

The prototype (`simple_steps_core/grid.py`) went through three spellings of the
modifier stack — method chaining, a vertical `stack(...)` call, and the
brackets — and **kept only the brackets.** Three ways to write one thing meant
the verb list was spelled out in nine places; adding `sweep` had to touch most
of them. One spelling is the point, not a preference.

There are exactly two syntaxes, and one rule covers both:

```python
score({"n": 3})                                   # parens RUN — a plain call
score[mod.map(over=step1), mod.retry(times=2)]    # brackets DECORATE — data
score.bind(weight=2)[mod.map(over=step1)](rows)   # bind, decorate, run
```

The bracket list reads exactly like the stacked `@` lines it mimics — outermost
at the top, applied bottom-up — so the example above is `map(retry(score))` and
**retry runs per item**. The stored stack is `[retry, map]`, innermost-first as
§1.1 requires.

`bind` exists because literals are not modifiers: they are the arguments fixed
when the step was wired, applied *innermost* — inside every modifier, so a
retry re-runs the same call and a map passes them to every item.

Retired, deliberately: `Operation.map()`-style chaining, `stack(...)`, and a
`Pipeline` class. Also retired is `Output.map(fn)`, which *ran* a verb
immediately and so gave `.map` two opposite meanings depending on the receiver.
The eager form is just decorate-then-call: `score[mod.map()](grid(df))`.

### 6.3 `identity`: the tool that closes the algebra

Every step is a verb applied to a tool. Steps that only *reshape* have no tool
of their own, so they apply a verb to **`identity`** — and then need no special
case anywhere: `expand` over it flattens a level, `filter` over it keeps what is
already truthy, `source` over it lifts a literal.

It returns **the payload, not the row.** A tool receives a whole row
(`{"n": 1, "value": [2, 3]}`), but the reshaping verbs need the *cell* the
previous step produced. Returning the row would make `filter`+identity keep
everything (a non-empty dict is truthy) and `expand`+identity flatten nothing (a
dict is not unpacked) — both silently. So the payload is resolved by
convention: an explicit `column`, else `value`, else the only column, else the
whole row. The last case is the honest limit: after `map(name="score")` no
convention can know, so bind it — `op("identity", column="score")`.

`collapse` is the exception: it needs a two-argument reducer, so identity has
nothing to mean there.

`collapse` takes a two-argument reducer, so `identity` cannot be its default —
but a default exists: **`gather`**, which appends each payload to a list.
`identity` is the map that discards nothing; `gather` is the reduction that
discards nothing. Different arity, same principle, and it makes `expand` and
`collapse` exact inverses — a cell holding `[1, 2, 3]` expands to three rows,
and three rows gather back into that cell.

### 6.4 Brackets are decoration at run time

The right way to read `score[mod.map(...), mod.retry(...)]` is as a **runtime
decoration of the tool**: it changes what `score` does, before any data is
handed to it. That is genuinely a decorator — the objection in §6 is to **`@`
at definition time**, not to decorator-shaped syntax:

| | `@map(...)` above the `def` | `score[mod.map(...)]` |
|---|---|---|
| when it happens | import, once, forever | wiring, per step |
| the same tool `once` here and `map` there | ✗ pinned | ✓ |
| readable before anything runs | ✗ a closure | ✓ `Modifier` data |

So the two halves separate cleanly, and the second is where data arrives:

```python
decorated = score(threshold=5)[mod.map(over=videos), mod.retry(times=2)]
decorated                      # an Operation — data, serializable, stageable
decorated(videos_grid)         # now run it
```

Bound literals (`threshold=5`) are the **innermost** decoration, inside every
modifier — so a `retry` re-runs the same call and a `map` passes them to every
item. The row is the single positional unit of work and the literals arrive as
keywords, which is the same split the engine's `_run_item` already makes
between the item and its `shared` constants.

#### Three orders, one of them reversed

Order is semantics (§1.1), so it is worth being exact about which order is
which. For `score[mod.map(), mod.retry(times=1)]` over two rows:

| | order | why |
|---|---|---|
| **written** in the brackets | `map, retry` | outermost first, like stacked `@` lines |
| **stored** in `Operation.modifiers` | `retry, map` | innermost-first, per §1.1 |
| **wrapped** — when decoration happens | `retry, map` | the inside must be built before the outside |
| **entered** — when data arrives | `map, retry, retry` | outermost runs first; `retry` once per row |

So **written order = nesting order = run-time entry order**. That is the one
that carries meaning, and it is the one you type. The reversal is mechanical
and leaks into exactly one place: the stored list.

Because it leaks, both orders are named. `Operation.modifiers` is the stored,
innermost-first list the engine folds over; `Operation.layers` is the written,
outermost-first list. Anything showing a user their own stack — a repr, the
list editor, a diff of two steps — reads `layers`, so what is displayed matches
what was typed.

#### The one place the decorator idiom must change

The usual bracket-decorator recipe applies the decorators immediately and
hands back a wrapped function. Doing that here would cost all four rows of the
closure table above. Instead `__getitem__` returns an `Operation` — the stack
is only *appended as descriptors*, and application is deferred to
`compile_operation`, which builds exactly the object graph `@` would have.

Deferral is what makes this decoration *at run time* rather than at definition
time, and it is the whole reason the same syntax is safe here.

A layer that is not a `Modifier` is rejected at the bracket with a `TypeError`
saying so, precisely so a plain decorator cannot slip in and silently
un-serialize a step.

---

## 7. Lifecycle and reactivity

### A step is born staged

Defining a step **is** staging. There is no staging phase to add: a fresh step
has a spec (the template) and an empty output (the slot). Staging is a pure
read of structure — zero I/O — which is exactly why it can be reactive.

```
staged ──► running ──► completed
                   └─► failed
completed ──► stale        (an upstream input changed)
stale ──► running ──► …
```

`stale` is distinct from `staged` because there *is* an old value: the user can
look at last run's answer while knowing it is out of date.

### An invalid step is a single cell

A step whose Operation cannot work — a mistyped argument, a dangling or
circular `over`, an upstream that is itself invalid — still **exists**, carrying
its problems. Reactive editing needs that: you type a wrong argument and see it
flagged without the workflow rejecting the keystroke. Validity is a property of
the Step, not a precondition for building one, so `check()` returns problems and
never raises. `run()` is what refuses.

Such a step stages as **one cell**, status `invalid`: it has no shape, because
the thing that would have given it one is what is broken.

### Staging sharpens in three levels

| known | when | the preview can say |
|---|---|---|
| shape | always, from the mode | "one cell per item of step1" |
| cardinality | once upstream has a value | "4 cells" |
| addresses | once upstream has an index | cells `[0, 1, 2, 3]` |

At level three the **staged ledger can be materialized before the run** — rows
with `status="staged"`. Running flips statuses in place. The UI renders one
structure through all three phases, and progress is
`(ledger.status == "completed").sum() / len(ledger)`. No separate progress
mechanism exists or is needed.

### The graph is derived, never stored

Dependencies are already implicit in the reference tokens sitting in
`step.call.arguments` and `orchestration.over`. Extracting them is ~10 lines and
costs **1.4 ms for 2,000 steps** — measured. Storing the graph would mean
keeping it in sync; deriving it cannot go stale.

### Staleness is a fingerprint comparison

One more ledger column:

```
fingerprint = hash(tool_id, tool_version, resolved_args_for_this_cell,
                   fingerprints of the upstream cells consumed)
```

A cell is stale iff its recomputed fingerprint differs from the stored one.
The payoff is incremental recomputation:

> **Append 50 rows upstream → only 50 new cells stage downstream.** Existing
> cells' fingerprints are unchanged, so their values stay valid.

This only works because rows have stable identity — the index, preserved
through `filter` and `group` by `.iloc` selection.

### Push vs pull

Staleness propagates **automatically**; recomputation happens **only when the
user runs**. Auto-recalculation is wrong here: the functions are expensive.

---

## 8. Known hard parts

Stated up front so they are designed for, not discovered.

1. **Tool code changes.** A Python function's behaviour cannot be reliably
   hashed (closures, globals, imports). `inspect.getsource` catches most edits;
   a manual `version=` on the tool is the honest escape hatch. Pick one.
2. **Resource changes.** Swap the transcription model and every fingerprint
   should change though no argument did. Resources must contribute a version.
3. **Side effects.** A tool that writes to a database must not be skipped as
   "unchanged". Needs `always_run`, opt-out rather than opt-in.
4. **Fingerprinting large arguments.** Hash the *reference plus version stamp*,
   never the payload.
5. **Never write the ledger row by row.** Mutating a DataFrame per completed
   item is **69x slower** than accumulating plain records and building the
   frame once at the end (measured at 5,000 rows: 65 ms vs 0.9 ms), and it
   degrades worse than linearly. Live progress comes from a counter, not from
   frame writes.
6. **Pause.** Orchestrators currently dispatch all items to `asyncio.gather`
   at once. Pausing means halting new acquisition while in-flight items finish,
   plus recording the resume point in the ledger. Must be designed into
   `_gather_outcomes`, not bolted on.
7. **`collapse` returns a 1-row grid.** The price of the invariant. Give grids
   an `.item()` for the 1×1 case.
8. **Object columns are not Arrow-serializable.** `to_parquet` hard-fails;
   a client degrades to `repr` strings. Object payloads persist only when they
   are *handles* (`MediaAsset`, `Collection`) or have a `to_json` (plotly).

---

## 9. The pandas decision

**pandas becomes a core dependency.** Today it arrives only via the `dashboard`
extra, so a headless server pays ~30 MB it may not use. Taken deliberately:

- The **index** gives free, stable cell identity — the thing per-cell re-drive
  and incremental staleness both require.
- The **verbs** already exist and are correct.
- **Object dtype** holds plots, tables and media handles.

Writing our own `Frame` class means reimplementing `groupby`, `join` and
`explode` badly. Keeping the duck-typed `is_frame` check keeps the branching we
are trying to remove.

Be clear-eyed about what we are *not* buying: the payload column is `object`
dtype, so there is no vectorization over the values. We are using pandas as a
**ledger with typed metadata columns**, not as a numeric engine.

---

## 10. Sequence

Not a big-bang refactor. Each step leaves the system working.

1. ~~**This document.**~~ **Done.** Cheapest place to disagree.
2. ~~**`sweep`, tidy-native.**~~ **Done in the prototype** (`grid.py`), along
   with the rest of the verb table, the modifier stack, `Step`/`Workflow`,
   declaration-time staging and validation, and both export modes. Nothing in
   the engine has moved yet — that is step 3 onward. See
   [grid-model.md](grid-model.md) for what exists and how it is arranged.
3. **`map` → mutate**, with `MapResult` coexisting during migration.
4. **`group` / `collapse`** to key-column semantics.
5. **Ledger + fingerprints + `stale`**, once the graph derivation lands.
6. **Retire** `MapResult`, `Group`, `Groups` when nothing depends on them.
7. **`AppConfig`** — **designed, deferred.** Process-level settings and the
   ceilings a server needs to protect itself; deliberately holds no step
   behaviour. Fully specified in [app-config.md](app-config.md) and not yet
   implemented — it is pure pydantic with no server dependency, so it can land
   whenever the backend needs it.

If step 2 feels wrong in practice, we learned it cheaply and nothing is broken.

---

## 11. Open questions

- ~~The `Block` noun.~~ **Settled:** it is `Output`, the name the existing docs
  already gave that slot. No new noun.
- ~~Modifier application order in the stored list.~~ **Settled:**
  innermost-first, which is just nested-call evaluation order.
- ~~Ledger rows: units of work, or output rows?~~ **Settled:** one row per
  unit of work, indexed by the input's index; `expand`/`collapse` link back
  through a `source` column (§5).
- ~~Does `Step.status` remain a field, or become a rollup?~~ **Settled: a
  rollup, by precedence.** A stored field would have to be kept in sync with
  the ledger and could disagree with it; a rollup cannot. The rule is *the most
  alarming state wins*:

  ```
  invalid > failed > running > staged > completed
  ```

  So a step where 3 of 100 units failed reads **`failed`** — never "completed".
  There is deliberately no `partial` state: a client would still have to read
  the ledger for the counts, so a seventh word buys nothing that
  `(ledger.status == "completed").sum()` does not already give. `failed` means
  *at least one unit failed*; the ledger says how many.
- ~~Tool versioning: source hash or manual `version=`?~~ **Settled: both,
  layered.** `inspect.getsource` hashing is the default because it is free and
  catches the common case (someone edited the function). A manual `version=`
  overrides it when present, because the cases a source hash misses — a changed
  global, an upgraded dependency, a tweaked prompt file — are exactly the cases
  where a human knows and the machine cannot. Picking only one either burdens
  every tool author or silently misses real changes.

  Resources contribute their own version (§8.2), so the fingerprint is
  `hash(tool_version, resource_versions, resolved args, upstream fingerprints)`.
- ~~An `auto` modifier that picks the iteration for you.~~ **Settled: it is a
  resolver, not a modifier.** `score(wf["raw"])` infers the verb at wiring and
  stores it **concretely**. A stored `auto` would be the only modifier whose
  shape is unknowable before running — no rows rule, no staged claim, and a
  light export that could resolve differently on reload. Resolving once also
  means an inferred verb can never silently overwrite one the user chose.
- ~~Are shape verbs modifiers of the tool, or is the tool an argument of the
  orchestrator?~~ **Settled: modifiers of the tool.** Today's engine has it
  inverted — `orchestration-map` is the tool that runs and your function is a
  string argument — which is the mechanical reason `retry(map(f))` is
  unsayable: `retries` is an argument *of* map, and an argument cannot sit
  outside its own function.
- ~~One shape verb per step, or several?~~ **Settled: at most one.** The
  re-drive argument decides it. Two shape changes inside one step produce an
  intermediate grid with no cell address, so a unit that fails *there* cannot be
  inspected or re-run — and per-cell re-drive is the thing this whole model is
  built to provide.

  The spreadsheet analogy cuts the other way, which is worth saying because it
  looks like the strongest counter-argument: `=SUM(FILTER(...))` nests happily
  because Excel's functions are instant, pure and cannot fail. §0 opens by
  noting that ours are none of those — which is precisely why every intermediate
  has to be addressable.

  Enforced in `check()`, so the rule cannot quietly rot.
- **Still open: which slices can be units (§1.0).** `row` is built; `column`
  and `cell` are not.
  - **Column.** Note this is about `colmap` — running a tool *per column*. It
    is **not** about `select`/`drop`, which choose columns without running
    anything and are already built (§3). `colmap` and friends are wanted. The blocker is §5: a
    column-wise verb's ledger is indexed by column name while `data` is indexed
    by row — different index *spaces*, so `view()`'s join yields NaN rather than
    an error. `axis="columns"` raises today rather than shipping that silently.
    It also needs deciding whether a column reaches the tool as a **list** or as
    a dict keyed by the old row index; the half-built transpose did the latter,
    which is almost never what a column-wise tool wants.
  - ~~**Cell.**~~ **Settled by the flat-grid decision below: not a distinct
    unit.** One row is one unit, so a cell and a row coincide.
- ~~**Reference checking at declaration.**~~ **Half settled.** Once a tool
  declares the values it needs by name rather than taking a row dict, the
  *columns* an upstream must supply are checkable at declaration with no schema
  machinery at all — the prototype does this. What remains open is column
  *types*: matching dtypes to parameter annotations. `validation.py` (literals)
  and `inference.effective_output` (reference shapes) are both written and both
  still wired only to the engine's run path.
- ~~Does `sweep` take parameter lists, or a reference to a grid of parameter
  rows?~~ **Settled: lists — because the second option is not a sweep.** Running
  a tool once per row of an existing grid of parameters is exactly `map` with
  column binding; the parameters are columns and bind by name like any others.
  So the choice dissolves: `sweep` *generates* a cross product, `map` *consumes*
  a grid, and nothing is missing.
- ~~Nested fan-out: one flat grid, or a genuinely 2-D one?~~ **Settled: flat.**
  Four reasons, in order of weight:
  1. **Re-drive.** A cell's address is what lets a failed unit be re-run. A
     nested grid's inner cells have no address in the outer one.
  2. It costs nothing new: the ledger already links non-1:1 verbs through
     `unit`, which is the same mechanism.
  3. A 2-D grid of objects needs nested frames or a MultiIndex, reintroducing
     the "column of columns" problem §3 retired when `group` stopped nesting.
  4. The need is already expressible: `group` marks the stratum and
     `collapse(by=…)` reduces within it.

  **This also settles the cell question above.** If every grid is flat, one row
  *is* one unit and the produced object sits in one payload column — so a cell
  and a row coincide, and `cell` is not a distinct unit. The unit question
  reduces to row (built) versus column (open).
