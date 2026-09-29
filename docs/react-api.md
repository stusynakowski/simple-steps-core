# React API — the grid paradigm over HTTP

> **Status: a proposed contract for the target model.** It describes the API a
> React client should consume once the engine adopts the grid model
> ([shape-algebra.md](shape-algebra.md)); the shapes below are the ones
> `grid.py` actually emits today ([grid-model.md](grid-model.md)). For the API
> against the engine **as it is now**, see
> [integration.md §11](integration.md).

Every payload here was produced by running the prototype, not written by hand.
For the server side — how to write the tools this API exposes — see
[writing-tools.md](writing-tools.md); for how the process itself is configured,
[app-config.md](app-config.md).

---

## 1. The one idea the client has to absorb

**Declaring a step is not running it.** The server answers a declare request
with everything the UI needs to render the step — its shape, how many cells it
will produce, what is wrong with it — having executed nothing.

```
POST /steps        declare   → a staged step, no computation
POST /steps/{id}/run  run    → the same step, now holding data
GET  /workflow     inspect   → every step, current state
```

That split is the whole design. It is why a user can wire a 40-step workflow,
see it laid out with cell counts and errors, and only then decide what to
compute. Three consequences the client depends on:

| | |
|---|---|
| **an invalid step is a `200`, not a `422`** | it still exists, carrying `problems` — the editor must render a broken step while the user is still typing it |
| **the server never computes on its own** | staleness propagates, recomputation does not (§7's push/pull) |
| **a declared step already knows its shape** | render cell counts and progress skeletons before any run |

---

## 2. Resources

### `GET /tools`

The palette. One entry per registered tool.

```json
[
  {
    "tool_id": "score",
    "description": "Weight a count.",
    "params": [
      {"name": "n",      "type": "int", "required": true,  "default": null},
      {"name": "weight", "type": "int", "required": false, "default": 1}
    ],
    "returns": "int"
  }
]
```

`required: true` params are the ones a step must get **from a column**;
optional ones are candidates for `bind` (§4).

### `GET /modifiers`

The modifier vocabulary — everything the stack editor's dropdown needs. Serve
it from the server's one table so the client can never drift from it.

```json
{
  "source":   {"cls": "shape",     "rows": "same"},
  "map":      {"cls": "shape",     "rows": "same"},
  "filter":   {"cls": "shape",     "rows": "at_most"},
  "group":    {"cls": "shape",     "rows": "same"},
  "expand":   {"cls": "shape",     "rows": "unknown"},
  "collapse": {"cls": "shape",     "rows": "one"},
  "sweep":    {"cls": "shape",     "rows": "generated"},
  "retry":    {"cls": "execution", "rows": null},
  "timeout":  {"cls": "execution", "rows": null}
}
```

`cls` drives the UI directly:

- **`shape`** — changes rows or columns. At most one is the *outermost*, and it
  decides the step's shape. Render these as the step's "iteration" control.
- **`execution`** — shape-preserving. Render as step settings; they never
  affect the cell count, so the client can ignore them when drawing shape.

`rows` is what lets the client predict cardinality locally without a round trip
(§5).

---

## 3. An Operation is data

This is the entire definition of a step. It is small, JSON-native, and the
client may hold, diff and reorder it freely.

```json
{
  "tool_id": "score",
  "arguments": {"weight": 2},
  "modifiers": [{"kind": "map", "params": {"over": "raw"}}]
}
```

### Modifier order is semantics, not style

`modifiers` is stored **innermost-first**. The UI must display it
**outermost-first** — the reverse — because that is the order the user thinks
in and the order a decorator stack reads:

```js
const layers = [...operation.modifiers].reverse();   // what to render
```

Get this wrong and every stack appears backwards. `[retry, map]` stored means
`map(retry(f))`: retry runs **per item**. `[map, retry]` means retry wraps the
whole fan-out. They are different runs, so reordering in the UI is a real edit,
not a cosmetic one.

### `over` is a graph edge

`params.over` names the step this one reads. The dependency graph is **derived**
from these tokens, never stored separately — so the client can draw the DAG from
the workflow payload alone, with no `/dag` call.

---

## 4. Declaring a step

### `POST /steps`

```json
{"step_id": "scored", "operation": { ... }}
```

Responds `200` with the step (§5) whether or not it is valid.

### Literals vs. columns

A tool's parameters come from two places, and the client should present them
differently:

| | source | UI |
|---|---|---|
| `n` (required) | a **column** of the upstream grid | not an input — show which column feeds it |
| `weight` (optional) | a **bound literal** | a form field; goes in `arguments` |

A bound literal also *satisfies* a required parameter the grid cannot supply, so
the form should let a user fill a missing column by hand.

### Letting the server choose the iteration

### `POST /steps/infer`

```json
{"tool_id": "total", "over": "scored"}
```

```json
{"kind": "collapse",
 "reason": "'acc' is not a column but 'value' is, so this reads as a reducer"}
```

Use this to pre-select the iteration dropdown. Two rules matter to the client:

1. **The result is a concrete verb, never an `"auto"` value.** Write it into
   `modifiers` like any other. Nothing named `auto` should ever reach the
   server's stored data.
2. **Infer once, at creation.** Do not re-infer when an upstream changes, or you
   will silently overwrite a choice the user made.

Show `reason` as a caption under the dropdown. It is what makes the choice
editable rather than magic.

---

## 5. A Step: an Operation and an Output, always both

```json
{
  "step_id": "scored",
  "status": "staged",
  "valid": true,
  "problems": [],
  "describe": "map score · 3 cells",
  "operation": { ... },
  "output": {
    "meta": {
      "verb": "map", "form": "column", "payload": "value",
      "staged": true, "n_in": 3, "expected": 3, "rows_rule": "same"
    }
  }
}
```

`status` is one of `staged · running · completed · failed · invalid · stale`.
It is a **rollup** of the ledger: a step where 3 of 100 rows failed is neither
completed nor failed. (`stale` is in the enum but cannot occur yet — see §11.)

### Staged claims are honest — render them verbatim

`expected` is what the verb can *guarantee*, not a guess. Use `rows_rule` to
render the qualifier, and never round it up:

| `rows_rule` | render |
|---|---|
| `same` | "3 cells" |
| `at_most` | "at most 3 cells" |
| `one` | "1 cell" |
| `unknown` | "unknown count from 3 rows" |
| `generated` | from the sweep's own parameters |

`expected: null` means cardinality is not known yet — show the shape only
("one cell per upstream row"). It fills in as upstream steps run, so a step card
sharpens over the session without ever being wrong.

`describe` is the server's own one-line rendering. Prefer it for captions; it
already distinguishes a staged **prediction** from a completed **fact**.

### Invalid steps

```json
{"step_id": "oops", "status": "invalid", "valid": false,
 "problems": ["score() takes no argument 'wieght'; it accepts weight"],
 "describe": "invalid · score() takes no argument 'wieght'; it accepts weight"}
```

Still `200`. Still in the workflow. Render it inline on the step card, not as a
toast — the user is mid-edit, and the message names the fix.

Caught at declaration: unknown tool or modifier kind; an `over` that dangles,
self-references, is circular, or names an invalid step; a bound argument the
signature rejects; and **a required value the upstream cannot supply**
(`score() needs 'n', which 'raw' does not have (it has count)`).

---

## 6. Running

### `POST /steps/{id}/run` · `POST /workflow/run`

Running **replaces** the step's Output. The server refuses a step whose inputs
are not ready rather than computing something plausible and wrong:

```json
{"error": "step 'twice' reads 'scored', which has not run. Run 'scored' first, or run the workflow."}
```

`GET /steps/{id}/pending` returns what must run first, nearest last — use it to
enable or disable a Run button, and to offer "run these 3 first".

A **source step is never pending**: its data arrived with its declaration, so it
is born `completed` and running it is a no-op. Only computed steps can block.

### Progress

There is no separate progress mechanism and none is needed:

```js
const done = ledger.data.filter(r => r[statusCol] === "completed").length;
const progress = done / ledger.data.length;
```

A staged step already has a full ledger of `"staged"` rows when its addresses
are known, so the client can render the progress skeleton — one cell per row —
before anything starts.

---

## 7. Reading a grid

### `GET /steps/{id}/output`

**Send `data` and `ledger` as two frames, not one.** They share an index, so the
client joins them for display, but they must not be merged server-side:

- real tables already have columns named `value` and `status`;
- `ledger` changes *while* the step runs and `data` must not;
- `ledger` is all scalars, so it always renders — only `data` carries objects.

```json
{
  "data":   {"columns": ["n", "value"],
             "index": [0, 1, 2],
             "data": [[1, 20], [2, 40], [3, 60]]},
  "ledger": {"columns": ["status", "error", "attempts", "seconds", "unit"],
             "index": [0, 1, 2],
             "data": [["completed", null, 1, 0.000003, null],
                      ["completed", null, 1, 0.000001, null],
                      ["completed", null, 1, 0.000001, null]]}
}
```

That is pandas `orient="split"` — compact, order-preserving, and it keeps the
index, which is the cell address the client needs for per-cell re-drive.

| ledger column | means |
|---|---|
| `status` | this unit's state |
| `error` | why it failed, per row |
| `attempts` | retries used |
| `seconds` | how long it took |
| `unit` | which **input** unit produced this one (a row, in every verb built so far) |

A verb may add one: `filter` writes `kept`, so a dropped row is still in the
ledger with `kept: false`. Treat ledger columns as "these five, plus whatever
the verb added" rather than a fixed list.

One ledger entry per **unit of work** — not per output row. `unit` matters for
the verbs where the two do not line up. For `map`, `group` and
`sweep` the two frames share an index exactly. For `filter` the ledger is a
**superset** — it keeps the rows that were dropped, with a `kept` flag, so the
UI can answer *"what happened to the other two?"*. For `expand` and `collapse`
the indexes are different spaces and `unit` is the only link.

### Object payloads

`data` may hold plots, tables or media handles, which are not JSON. Send a
descriptor per cell rather than a `repr`:

```json
{"kind": "media", "ref": "asset://...", "preview": "..."}
```

Never send a `repr` string that cannot be read back — silent lossy encoding is
the failure mode this model is built to avoid.

---

## 8. Persisting: two modes, differing only in payloads

| | endpoint | carries | size, for the two-step example above |
|---|---|---|---|
| **light** | `GET /workflow` | the chain of Operations, nothing else | **294 B** |
| **full** | `GET /session` | that plus every payload | **727 B** |

The light export is the *recipe*. Use it for autosave on every keystroke — it is
a few strings per step, so it is cheap enough to send continuously.

```json
{"version": 1,
 "steps": [{"step_id": "scored", "operation": { ... }}]}
```

Staging is **derived**, so it is never stored. Reloading a light export lands
with shapes known and cardinality not, because cardinality came from data the
light export does not carry. That is correct, and the client should render it
the same way it renders any not-yet-known count.

A source step reloaded from a light export has no data and says so. Supply it
again by declaring it with a value; there is no separate "inputs" concept — a
literal is just a step's output.

---

## 9. Suggested endpoint map

| Method & path | Purpose |
|---|---|
| `GET /tools` | the palette |
| `GET /modifiers` | the vocabulary — dropdowns, `cls`, `rows` |
| `POST /steps` | declare or redeclare; `200` even when invalid |
| `DELETE /steps/{id}` | remove; re-check dependents |
| `POST /steps/infer` | pre-select an iteration, with a reason |
| `GET /steps/{id}` | one step (§5) |
| `GET /steps/{id}/pending` | what must run first |
| `GET /steps/{id}/output` | `data` + `ledger` |
| `POST /steps/{id}/run` | run one step |
| `POST /workflow/run` | run everything, in dependency order |
| `GET /workflow` | light export — autosave |
| `GET /session` | full export — save with results |
| `POST /session` | restore |

No `/dag` endpoint: the graph is derived from `over` tokens the client already
has.

---

## 10. Client patterns

**One step card, three phases.** Do not build separate staged/running/completed
components. A step always has both halves, so one component reads `status`,
`describe`, `expected` and the ledger throughout — which is exactly why staging
was designed to materialize the ledger early.

**Optimistic declare.** `POST /steps` runs no user code; it is a signature and
reference check. Render the response directly rather than maintaining a
client-side validity model that can disagree with the server.

**The modifier stack is a reorderable list**, not two config forms. Dragging
`retry` above `map` changes `map(retry(f))` into `retry(map(f))` — retry per
item becomes retry the whole fan-out. Surface that in the UI copy; it is the
capability the stack exists to provide.

**Reversing is the client's job.** Store order is innermost-first; display order
is its reverse. Do it once, at the boundary.

**Let the server phrase errors.** `problems` entries are written to be shown to
a user and name the fix. Do not re-map them to generic copy.

---

## 11. Open questions this API does not settle

- **Streaming progress.** The shapes above are poll-friendly. A long fan-out
  wants a websocket or SSE channel carrying ledger deltas keyed by index; the
  ledger's row-per-unit design supports it, but the transport is unspecified.
- **Per-cell re-drive.** The index is a stable cell address and the ledger knows
  which rows failed, so `POST /steps/{id}/run` with a row selection is the
  natural shape. Not specified here.
- **Staleness.** `stale` is in the status enum, but fingerprints are designed
  and unbuilt ([shape-algebra.md §7](shape-algebra.md)). Until they exist, no
  step will report `stale`.
- **Column verbs.** `colmap` and friends would index the ledger by column rather
  than row, which changes what `GET /steps/{id}/output` means. Deliberately not
  specified.
