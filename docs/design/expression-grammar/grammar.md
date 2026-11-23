# The step grammar

> **Draft, 2026-11-23, for the owner.** The start of the grammar that closes
> the system ([blocks.md](../blocks.md) §0, plan piece G0). It begins **top
> down**, with how a user should see an expression (§0); then **what must
> be resolved for any expression** (§1–§4), then **the owner's heuristics**
> for resolving it (§5), and **the classes each of the five components can
> be** (§6), which the rules will narrow. The shape (which words
> fill which component) and the numbered rules (how the components depend
> on each other) come next, on this page.

*Owner, 2026-11-23: "we now know exactly what needs to be satisfied for ANY
valid expression. When we specify a tool, modifiers, picks, or modifiers to
the pick, we converge on the components … everything needs to be obvious
and intuitive for how things are handled, but the conventions are clear. So
we can parse the expression to converge on the exact components."*

## 0. Top down: what the user sees

*Owner, 2026-11-23: "I usually start from a top-down perspective before
sorting out those specifics. Even if we have a system that is closed, if it
doesn't make sense to the user we defeat the purpose of why we are building
this. I find the 'stupider' the question, the more fundamental and
important the question is." And: "It's hard to think about multiple ideas
at once, but good compartmentalizing helps people perform complicated
things, if they can break things down into intuitive, isolated parts."*

**The goal:** a user writes an expression that is **really simple**, in
the style of functional programming, while the necessary details are still
there. They are handled in **isolated parts**, so the user thinks about one
at a time.

### What is solid: the inputs

Every expression has inputs, and **they are never fuzzy**:

| Input | Is | What the user writes |
|---|---|---|
| **a literal** | a value, written in the expression. It persists with it | `offset=1.0` |
| **a resource** | an object the tool needs, such as a model or a connection: **a literal, as far as the expression is concerned** | `res["llm"]` |
| **a reference** | data from a previous step, and **always structured**: a grid of cells | `wf["p"]` |

A reference is always structured, so it is always clear:

- **The step's name is always given**: `wf["p"]`.
- **Columns are named by strings**, one or a list: `["temp_c"]`, `[["x", "y"]]`.
- **Rows are indices**, and can be picked as they are today: a row, a list,
  a range, a condition.

(One difference between a literal and a resource, behind the scenes: a
literal is saved in the expression; a resource is saved as its settings,
and the object is built when the step runs, its secrets never saved.)

### What is fuzzy: the exact function, and how it runs

What is open is **which function the user wants, exactly, and how it is
run** over those inputs: how many calls, what each call is given, what
happens on an error, what comes out. That is where every finding so far
(A1–A7, O1, I1, I2) has been.

### What resolves it: three sources of information

| Source | Tells core | Example |
|---|---|---|
| **the data** | a consistent structure, and the types within it | `p` has a column `temp_c` of floats |
| **the tool** | the type hints on its inputs and its output | `to_f(temp_c: float) -> float` |
| **the modifiers** | what the user has said about how to run it | `mod.collapse(by="ward")` |

Together they converge on the exact function (§1, and §5's H9).

### The isolated parts, as plain questions

Each part is one plain question, so a user can think about one at a time.
They are the same as §5's classes of modifier (H7), in words:

| Plain question | Part | Answered by | Components (§2) |
|---|---|---|---|
| **What goes in?** | the inputs | the literals, resources and references written | C2, C3 |
| **What does it do?** | the tool | the tool's name | C1 |
| **How is each input handed over?** | input | input modifiers, or the types | C3, C4 |
| **How many times is it run?** | call | a call modifier, or the types | C5 |
| **What if a call goes wrong?** | execution, each call | execution modifiers | C6 |
| **How is the whole step run?** (progress, cancel, how many at once) | execution, the step | execution modifiers | C6 |
| **What comes out, and where does it go?** | output | output modifiers, or the return type | C7, C8, C9 |

*To check with the owner:* are these the questions a user would ask, in
their words?

### The levels of this page: abstractions of abstractions

*Owner, 2026-11-23: "they need to be connected to each other; we are making
a hierarchy of abstractions of abstractions. We're writing an expression →
what components are needed → what are the possible (general) states of those
components → how do those components influence the states of others, in
order to be a valid expression."*

Each level is built from the one above it. The breakdowns on this page and
in blocks.md are not rivals: each belongs to one level.

| Level | Asks | Here | Its parts |
|---|---|---|---|
| **L0. The expression** | what did the user write? | §0, §1 | a tool, its modifiers, its data: in full, **`tool[modifiers](data)`** (§5, H7), or a shorthand of it |
| **L1. The components** | what must be resolved? | §2, §6 | the **five**: tool, input, call, execution (at levels: each call, the step), output. Their contents are C1–C9 (§2); they are resolved **in a fixed order** (blocks.md §0, *The ordered components*); the user meets them as the **plain questions** above |
| **L2. The states** | what can each component be? | §6 | each component's axes, and the classes on each axis (`T-k.core`, `K-n.many`, …) |
| **L3. The rules** | how does one component's state limit the others', so the expression is valid? | §7 (next) | numbered rules: given these classes, those are impossible, or implied. Where more than one reading is left, the most likely is written and shown (H2) |

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
| C4 preparation | implied by the verb and the parameter's type, at the call, not written; four separate checks | A1–A7 ([blocks.md](../blocks.md) §3) |
| C6 and C5's order | the written order, which can change what a step does | O1 (blocks.md §0) |
| C7 landing | implied by the verb; "on every row of its scope" missing | §4's window and transform gaps |
| C2's block | checked against the input **step's** columns, not the pick's | A4; and H3's last row (two columns, two readings, accepted) |

## 5. The owner's heuristics

*Owner, 2026-11-23: "I think this has been the key problem in this project,
and it impacts everything else, so if I get this right everything else will
be much easier." Not in order of priority; heuristics, with exceptions
possible.*

### H1. Explicit beyond a reasonable doubt

A shorthand may be written, but **opening the expression shows exactly what
every component maps to**. If there is any potential for ambiguity, the
expression is explicit.

### H2. One reading may be left out; several must be written

If a component is missing from what is written, but **there is really only
one way to read the expression**, core fills it in (and writes it down,
§1). If there are **several valid readings**, the user writes it, or core
writes the reading it is fairly sure of and **shows it** as its choice. It
is never filled in silently.

### H3. Binding by name

- A tool's parameters can be given **by position**, with no names.
- When the data comes from a step's **columns**, the column names **match
  the parameter names** they bind to: a column `temp_c` binds to the
  parameter `temp_c`.
- **Naming a parameter's source explicitly overrides it**: `temp_c=wf["p"]["u"]`.

Run 2026-11-23, against today:

| Case | Today | Under H3 |
|---|---|---|
| `f(temp_c)` on `wf["p"]`, which has a column `temp_c` | bound by name, left short | ✓ |
| `f(temp_c)` on one column, `wf["p"]["t"]` | bound by type, written out: `temp_c=wf["p"][cols["t"]]` | ✓ by H2: one reading, written down |
| `f(temp_c)` on `wf["p"]`, `temp_c=wf["p"]["u"]` written | the written binding wins | ✓ |
| `g(a, b)` on columns `t`, `u` | refused: no column is named `a` or `b` | ✓ |
| `f(temp_c)` on columns `t` **and** `u`, both floats | **accepted; every row then fails, `TypeError: f() missing … 'temp_c'`** | ✗ two readings: refused, naming both (H2). It is A4: checked against the step `p`, which has a `temp_c`, not against the pick |

**Decided, 2026-11-23** (owner: "it goes beyond a reasonable doubt for
inference … I cannot have a user make a mistake because of ambiguities of
the tool"). Run, three cases that "by type" covered:

| Case | Today | Decided |
|---|---|---|
| **a.** One column picked, `to_f(wf["p"]["t"])` | bound to `temp_c`, written out | **stays**: by position, Python's own rule (`f(x)` gives `x` to the first parameter), not a guess |
| **b.** The whole step, `to_f(wf["p"])`, no column `temp_c`, exactly one float column `t` | core searches `p`'s columns and binds `t` by its type | **refused**, naming the fix `temp_c=wf["p"]["t"]`: a column found by its type may be the wrong one |
| **c.** A column named like a parameter that has a default: `q` has `offset`, `to_f` has `offset=0.0` | **the column is ignored, silently**; the tool gets `0.0` (**G2**) | **refused**, naming both: `offset=wf["q"]["offset"]` or `offset=0.0` |

### H4. The tool's types imply how it is called

The parameter types and the return type are where the conventions come
from (§1's third source).

### H5. Tidy tables: rows are samples, columns are variables

Rows are what is **iterated**: the calls go over them, and they are what
packs into a list. Columns are **keys**: they bind to parameters by name.

### H6. A list parameter given single values implies a collapse

A tool's parameter typed as a list of something, given a column of a
previous step whose cells each hold one such thing, **implies collapsing
that column into a list**. It can be written short, but **opening the
expression shows the collapse** (H1).

### H7. Everything can be written in the modifiers, in orthogonal classes

**The full form of every expression is `tool[modifiers](data)`** (owner,
2026-11-23: "under the hood I think it makes sense to have everything abide
by `=tool[modifiers](data)`, though we will be able to write shorthand
syntax to make everything easier to understand"). A `drop` is core's tool
with its modifiers over its data; a `join` is core's tool over several
data. **A shorthand is a soft link to a full form** (owner: "soft links to
the same thing, motivating primitives here, such that we can ultimately
perform things like that, to make shorthand writing easier"): it is
written for ease, and opened it shows the full form (H1). Two kinds of
shorthand:

| Shorthand | Is a soft link to | Example |
|---|---|---|
| **a preset modifier** | several modifiers, in several classes | `collapse(by="k")`: one call per group (call), each input argument packed per group (input), one row per group (output) |
| **a method on a pick** | an input modifier for that argument | `wf["p"]["y"].tolist(by="k")`: that argument packed per group. Helpful to read (owner: "helpful for me and to the user"), the same thing as the modifier |


Everything can be written as modifiers; today they are ambiguous (O1, and
blocks.md §0's modifiers that don't fit). **The tool's modifiers are
organized into classes, as orthogonal as possible**:

| Class | Decides | Components (§2) | Today's modifiers |
|---|---|---|---|
| **input** | how each argument's data is **prepared** and **bound** | C3 binding, C4 preparation | `select`, `slice` (pickers); `cast`; packing (to a list, per group, per window: to come) |
| **call** | **whether the call happens more than once**, and over what | C5 calls | `map`, `collapse`, `table`, `sweep`, `source`; `auto` writes one |
| **execution** | how the calls are run, **at a level**: each call, or the step | C6 | each call: `retry`, `timeout`, `try_except`; the step: `breaker`, progress and cancel (K23); how many at once, a rate: to come |
| **output** | the output's **structure** and **names** | C7 landing, C8 names | `expand`, `widen`, `filter`, `group`, `name`; and `expect` (C9) |

The rearrangements with no tool (`drop`, `rename`, `copy`, `sort`,
`distinct`, `pack`) are steps of their own, not a tool's modifiers.

**Where classes bleed into each other: the shorthands.** A shorthand
belongs to **one** class, and fills in the others' defaults (blocks.md §0,
*How the components depend*). `collapse(by="k")` is a **call** modifier;
it implies an **input** preparation (each input argument packed per group)
and an **output** landing (one row per group). Opened, the expression shows
all three (H1). *Open:* `filter`, `expand` and `group` are output
modifiers here, but each also implies calls per row. `cast` changes values,
which blocks.md §0's rule 2 says no modifier does: a conversion is a
preparation, if the owner agrees the rule allows it.

### H8. The pick conditions which modifiers apply

What the pick gives (a cell, a row, a column, a block; their types)
**decides which modifiers are valid**, and which are implied. A single cell
can't be collapsed by group; packing to a dict needs a row; a block given
to a parameter that takes one value has no single reading.

### H9. The parser: a conditional directed graph that converges

The parser takes the **pieces written** (a tool, picks, modifiers, the
pick's parts) and maps them onto **the components to resolve** (§2). Each
piece written **narrows** what the others can be, through the conditions
between them (H4, H6, H8, and the dependencies). When one valid reading is
left, it converges, and core writes it down. When several are left, core is
explicit: it writes the one it is fairly sure the user wants and shows it,
or asks.

```
 written:   tool ─┐      pick ─┐      modifiers ─┐      arguments ─┐
                  ▼            ▼                 ▼                 ▼
 resolve:   C1 signature ─► C2 block ─► C3 binding ─► C5 calls ─► C4 preparation ─► C7 landing ─► C8 names
                  │            │            ▲            ▲   │          ▲              ▲
                  └── types ───┴── shape ───┴────────────┴───┴──────────┴──────────────┘
                         (each arrow: a condition that narrows the next component)
 then:      C6 each call's run, C9 checks (as written)  ──►  one reading?  yes: written down
                                                                           no:  explicit (shown, or asked)
```

## 6. The five components, and the classes each can be

*Owner, 2026-11-23: "Given the 5 components of any tool expression, can we
start listing out some generic, isolated (orthogonal) classes each
component could be. Then we can define rules that, if they are specified,
remove the set of possible classes, such that ideally there is enough
information to converge on exactly one interpretation. If there isn't one
interpretation, we use the most likely interpretation based on that
information, and state that selection in the expression." And: "rules about
the data that help condition what is stated", "generic to any tool".*

The five components are **the tool** and §5's four classes of modifier
(H7): **input, call, execution, output**. Execution's primitives each name
their **level**, each call or the step (§6.4; owner, 2026-11-23). Each has a few **axes**; each
axis has a few **classes**. A class has a short id, so the rules can name
it. Each axis says which source fixes it (§0): **the data**, **the tool**'s
types, or **the modifiers** written. Every class here is generic: it names
a kind of thing, never a particular tool.

### 6.1 Tool: what kind of function it is, from its type hints

| Axis | Classes |
|---|---|
| **T-k. Whose function** | `T-k.none` nothing is applied (data, the empty step) · `T-k.core` core's own, **its classes declared** (`drop`, `sort`, `join`, a pick; `identity`, `gather`, `total`) · `T-k.user` the user's tool, **its classes inferred** from its type hints |
| **T-u. What it works on** | `T-u.table` a whole table, or tables (`drop`, `sort`, `join`, a pick; a user's tool under `table`; a source) · `T-u.cell` cells (`identity`, `gather`, `total`; a user's tool under `map` or `collapse`) |
| **T-a. How many parameters need a value** (no default) | `T-a0` none (it makes data) · `T-a1` one · `T-an` several |
| **T-p. What each parameter takes**, from its type | `T-p.unit` one value (`float`, `str`, `ndarray`, a class) · `T-p.seq` many values as one (`list[T]`, `tuple[T, …]`) · `T-p.map` named values (`dict`, a record) · `T-p.table` a table (`DataFrame`) · `T-p.acc` an accumulator (a first parameter named `acc`, `memo`, `carry`: a reducer) · `T-p.any` untyped, `Any` |
| **T-r. What it returns** | `T-r.unit` one value · `T-r.bool` a yes or no · `T-r.seq` many values · `T-r.rec` named fields (a record) · `T-r.map` a `dict` · `T-r.table` a table · `T-r.any` untyped |

Fixed by **the tool**, before any data is seen. **`T-k` decides whether
anything is inferred**: a core function's classes are declared, so core
never guesses about it; only a user's tool is converged on (owner,
2026-11-23: "yes this seems aligned"). Core's cell tools are called like a
user's (run 2026-11-23: `op("total")[mod.collapse(by="k")]` makes one call
per group, `op("identity")[mod.map()]` one per row), so `T-k` says nothing
about how many calls: `T-u` and the call modifier do.

### 6.2 Input: what goes in, and how it is handed over

Per argument:

| Axis | Classes | Fixed by |
|---|---|---|
| **I-s. Source** | `I-s.lit` a literal · `I-s.res` a resource (a literal, to the expression) · `I-s.ref` a reference · `I-s.none` no step is read (a tool that makes data, such as one that loads a file) | what is written |
| **I-g. What a reference gives** (its block's shape) | `I-g.cell` · `I-g.row` · `I-g.col` · `I-g.block` (rows × columns) | the pick |
| **I-c. What its cells hold** | `I-c.unit` · `I-c.seq` · `I-c.map` · `I-c.table` · `I-c.unknown` (types not known before the run) | the data, through the plan |
| **I-r. Whose rows** | `I-r.input` the input's own rows (it can go row by row with them) · `I-r.other` another step's rows (it can only be given whole, or as one fixed cell) | the data's lineage |
| **I-b. Binding** | `I-b.pos` by position · `I-b.name` a column named as the parameter · `I-b.type` the one column whose type fits · `I-b.given` written, `param=pick` | the data and the tool; or written |
| **I-h. Handover** | `I-h.cell` one cell per call, as it is · `I-h.pack` many cells packed into one; with its **scope**, `everything`, `group(key)`, `window(n)`, and its **form**, list, dict, table, array | the call, the types; or written |
| **I-v. Conversion** | `I-v.none` · `I-v.cast` each cell converted first (open, §8 question 3) | written |

### 6.3 Call: how many times the tool runs

*Owner, 2026-11-23: break calls into a single call or multiple; then
"calls have multiple states (zero, one or multiple)".*

| Axis | Classes |
|---|---|
| **K-n. How many** | `K-n.zero` no tool is called · `K-n.one` a single call · `K-n.many` multiple calls |
| **K-o. Over what** (only for `K-n.many`) | `K-o.row` each row · `K-o.group` each group, by a key · `K-o.combo` each combination of settings |

**Zero calls is only when nothing is applied**: a data step and the empty
step (`T-k.none`). A combine, a pick and the rearrangements (`drop`,
`sort`, `rename`, …) do apply a function, core's own (`T-k.core`): a whole
table's function makes **one** call (`T-u.table`), its classes declared, so
nothing about it is converged on (owner, 2026-11-23: "I look at a combine
or a drop requiring a call"). The converging (§1, H9) is for the user's
tools. The UI can show a core table function as what it does ("drop columns
x, y") rather than as calls.

Today: a single call is `source` (with `I-s.none`), `table`, or `collapse()`
with no `by`; multiple calls are `map`, `filter`, `expand`, `group` (each
row), `collapse(by=…)` (each group), `sweep` (each combination). Fixed by
**a call modifier**, or converged on from the tool and the input. (Each
column is a gap: blocks.md §5.)

**Zero calls at run time** is a count, apart from the class written:
multiple calls over zero rows make none (the data: the step completes, with no rows); a
step already current isn't run again, its kept output reused; a cancelled
run stops part way. The last two are execution's outcomes (§6.4).

### 6.4 Execution: one class, its primitives at levels

*Owner, 2026-11-23: "I would do inner, corresponding to each call, then
executional components to each step … think a long process where we might
want to know the progress of the step and the progress of each call"; then,
of one class whose primitives name their level: "that makes sense, let's do
that".*

**The step wraps its calls; each call wraps the tool.** The same few
controls repeat at each level, so execution is **one class of a few
primitives, each naming the level it applies to**: the pattern of the
restructurings, one primitive, several places (primitives.md).

| Primitive | Each call | The step | Later: a stage, a workflow run |
|---|---|---|---|
| **time limit** | this call (per attempt, or all its attempts) | the whole step | ✓ |
| **progress** | how far the tool is through its call: **needs the tool to report it** (a callable core passes in); core can't see inside a call | calls done of calls in all, failed, retrying, each call's time so far: **core can always measure it** | ✓ |
| **on failure** | retry up to n times · a default value (**a change of value**: written, and shown as one, like a conversion) · the cell fails, with its reason (the default) | stop after n failed calls (a breaker) | stop the run |
| **cancel** | — | the whole step can be stopped (K23) | ✓ |
| **pace** | — | up to n calls at once (one, today) · at most n calls a second (a model's API, a web service) | — |

Each axis is optional and independent; within a level, the written order
means something (`retry(3)` then `timeout(30)` per call: three attempts,
each with thirty seconds).

**The test that keeps execution its own class:** an execution modifier
**never changes the value of a cell that succeeds**. It decides only
whether, when and how fast cells are computed; input, call and output
decide *what* is computed. The one exception is a default on failure,
which puts a value into a failed cell: written, and shown as a change of
value.

**O1 was the levels mixed:** `[retry, map]` put `retry` at the step's level
("retry the whole step"), where nothing raised; `[map, retry]` put it at
each call's. A named level makes both meanings writable, and neither
accidental.

Fixed by **execution modifiers** only. The data and the tool never imply
them.

**Outcomes of a run**, not classes of the expression (nothing written
chooses them): run · **skipped**, already current (its kept output reused,
no calls) · **cancelled**, part way.

### 6.5 Output: what comes out, and where it goes

| Axis | Classes | Fixed by |
|---|---|---|
| **O-w. Which rows it lands on** | `O-w.own` its call's row · `O-w.new` one new row per call (a group's call gives one row) · `O-w.spread` every row of its scope (a group's output beside each of its rows) · `O-w.keep` it keeps or drops its call's row | the call; or written |
| **O-s. What shape** | `O-s.cell` one cell · `O-s.rows` spread into rows · `O-s.cols` spread into columns · `O-s.table` a table, its rows and columns | the return type; or written |
| **O-k. The input's columns** | `O-k.drop` not kept beside the output · `O-k.keep` kept beside it | written; a default per call |
| **O-n. Names** | `O-n.step` the step's name · `O-n.fields` a record's field names · `O-n.given` written (`mod.name`) | the return type; or written |
| **O-e. Checks** | `O-e.none` · `O-e.stated` rows or columns expected (`expect`) | written |

### 6.6 How rules remove classes: two examples

A **rule** says: given these classes, those are impossible (or implied).
Writing something, or knowing the data or the tool, removes classes until
one is left on each axis. When more than one is left, core picks the most
likely, **says why**, and **writes it into the expression** (H2).

**One reading.** `to_f(temp_c: float) -> float`, given `wf["p"]`, where `p`
has a float column `temp_c`:

| Axis | Known | Left |
|---|---|---|
| tool | `T-a1`, `T-p.unit`, `T-r.unit` | — |
| I-b | `p` has a column named `temp_c` | `I-b.name` |
| I-g, I-c, I-r | a column, floats, the input's rows | — |
| K | a one-value parameter and a column of single values, row by row: `K-n.many`, `K-o.row`. A single call, or one per group, would need packing, and nothing packs a single value | **each row**, the only reading |
| I-h | each row, and `T-p.unit` | `I-h.cell` |
| O-w, O-s, O-n | each row, and `T-r.unit` | `O-w.own`, `O-s.cell`, `O-n.step` |

Written down: `to_f[mod.map()](wf["p"])`.

**Several readings, the most likely written.** `sumup(xs: list[float]) ->
float`, given `wf["p"]["x"]`, a float column:

| Axis | Known | Left |
|---|---|---|
| tool | `T-a1`, `T-p.seq`, `T-r.unit` | — |
| I-h | a list of floats, from single floats: it must be packed (H6) | `I-h.pack`, form list |
| K, and the scope | `K-n.one` (one sum of the whole column); `K-o.group` (needs a key, and none is given); `K-o.row` with the whole column packed for every row (the same sum on every row: valid, unlikely) | `K-n.one` **most likely**; each row possible |
| O-w | from `K-n.one` | `O-w.new`: one row |

Written down, with the reason shown: `sumup[mod.collapse()](wf["p"],
xs=wf["p"]["x"])`: *"xs takes a list of floats; x holds single floats; so x
is packed into one list, one call."* Opening it shows the packing (H1).

Run 2026-11-23: that written form works today (`9.0`). The shorter
`sumup[mod.collapse()](wf["p"]["x"])` is **refused**: "sumup() needs 'xs',
which 'p' does not have". Binding by type compares a single float with
`list[float]`, before the packing is taken into account: `I-b.type` doesn't
yet see `I-h.pack`. Under these rules it has one reading, so it would be
accepted and written out as above (**G1**, a finding for the rules).

## 7. Next on this page

1. **The shape**: for each component, the words that fill it (the
   modifiers, the pick's parts, the literals), as a grammar.
2. **The rules**: every dependency between the components as a numbered
   rule, each with the problem it gives when broken. blocks.md §0's table
   of dependencies is the start.
3. **The conventions**: for each component, its default, written as one
   table, so "obvious and intuitive" is one place to look.

## 8. Open questions

**Decided in the consolidation review, 2026-11-23:**

- **`filter`, `expand`, `group`** (question 2 below): they could each be a
  step of its own, modify a tool's input, or modify its output (owner).
  **One primitive, three places**: as a step (core's tool over a table), as
  an input modifier (before the calls), as an output modifier (on the
  outputs). This is what the primitives are organized by.
- **Names** (`mod.group`, `mod.table`, the n×m shape): not renamed one by
  one. Names come once the modifiers are organized into their classes and
  the restructurings into primitives (owner: "we need good organizations of
  modifiers … and define good classes of restructuring data in the grid").
- **model.md** is updated once the rules (L3) settle; until then these pages
  are proposals.
- **A parameter typed `Block`** receives a block: useful for callables, and
  likely needed. Mixed-typed grids give errors that are handled in steps, as
  any spreadsheet or table library does. **Restructuring and casting
  methods are necessary components.**

**Areas not yet covered**, to settle (raised by core, 2026-11-23):

| # | Area | The question |
|---|---|---|
| **N1** | **Mixed types in a column** (floats and a stray string) | **Decided** (owner, 2026-11-23): when declared, core **says** it won't work where a type is wrong (a warning, not a refusal: "we can still run"). The cells with the right type run; the others fail, and **the error passes through, naming where the issue is** (the input cell), as a `blocked` cell names the failure it comes from |
| **N2** | **Missing values into a typed parameter** (absent, `None`, `NaN` into `x: float`) | **Decided, yes** (owner, 2026-11-23): the cell fails, unless the tool types the parameter `Optional[float]`, which gets `None`. *To clarify:* the owner added "it's good to probably return …": what is returned? |
| **N3** | **Data from several steps in one call**, row by row: `tool(a=wf["p"]["x"], b=wf["q"]["y"])` | their rows must be matched: the combines' *match*, needed inside `tool[modifiers](data)` when data comes from more than one step (refused today: join first) |
| **N4** | **Which form is stored**: the shorthand or the full form | and when the opened full form is edited, does the shorthand survive? |
| **N5** | **A preset and an explicit modifier that disagree** (`collapse(by="k")`, and an argument packed over everything) | which wins, or refused? |
| **N6** | **Output names that clash** with input columns kept beside them | a rule for the names |
| **N7** | **A parameter given twice**, by position and by name | refused |
| **N8** | **Where an error shows**: refused when declared, or a failed cell at run | one clear line between them, so a user knows where to look |
| **N9** | **Big data**: every convention decides from the plan's types, never by reading cells | so resolving a step costs nothing on a million rows |

**The silent-loss bugs** (A4, F1, F2, I1, I2, G2): **the biggest issue
now**, and **the first thing developed** once the abstractions and the
roadmap are right (owner, 2026-11-23: "we have the context now on what the
design problems are").

**Still open from before:**

Recorded 2026-11-23, to settle once the top-down view (§0) is agreed. The
owner works top down first, then these.

**From §5:**

1. **H3, binding by type.** When exactly one column fits a parameter
   whose name matches none, core binds it by type and writes it out
   (today). Does that stay (one reading, H2), or must every binding be by
   name or written?
2. **H7, `filter`, `expand`, `group`.** Each is an output modifier, but
   also implies one call per row. Output modifiers that fill in the call,
   or call modifiers?
3. ~~**H7, `cast`.**~~ **Settled, 2026-11-23:** a conversion is an **input
   modifier** (owner: "this motivates the need to classify the modifiers").
   blocks.md §0's rule "modifiers never change a value" reads: except a
   conversion, written as an input modifier.

**From §2 and §3:**

4. Are the nine **C1–C9** the right set? Anything missing (for example, the
   step's name as part of the expression), or anything that should be
   merged?
5. ~~**The empty step, data and pick**~~ **Settled, 2026-11-23:** every
   expression's full form is `tool[modifiers](data)` (H7); a pick, a drop, a
   join apply core's tool (§6.1, whose function); only data and the empty
   step apply nothing. *The question was:* should they be written as tool
   calls too (a pick as `identity` over a block, data as a `source`), so
   there is only one kind of expression? Core already stores a DataFrame
   step this way in some saved files (`identity[mod.source()]()`).
