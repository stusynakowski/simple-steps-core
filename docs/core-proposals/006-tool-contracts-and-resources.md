# 006 — Tool contracts and Resources in the grid model

**Status: note / early proposal.** A separate track from
[005](005-reshaping-merging-and-status-grids.md). Two related things the grid
model still owes: a stated **tool contract** (typing + docstrings), and
**Resources** — classes the user loads and that tools leverage to do their work.
The engine already implements Resources in full; the grid model dropped them on
the way over and needs them back.

---

## 1. The tool contract — typing and docstrings

A step's boundary is its tool's signature. We want that boundary to be the
*single source of truth* for validation, the palette, and (later) an LLM's view
of the tool. Most of this exists in `grid.py`; the note is to finish and state
it.

### 1.1 Typing (mostly built)

- `@tool(strict=True)` / `grid.STRICT_TYPES` refuses an under-annotated tool at
  import; `check` compares declared parameter types against upstream dtypes,
  and bound literals against their annotations ([004](004-grid-adoption.md) A1).
- **To settle:** make `strict` the default once the examples are annotated, so
  "a tool is fully typed" is the norm, not an opt-in. Untyped tools become the
  exception a user must ask for (`strict=False`).

### 1.2 Docstrings as the description surface (mostly built)

- `catalog()` already carries the summary and, per parameter, the `Args:` text
  (A1). The docstring is therefore **not decoration** — it is the human- and
  client-facing description of what the tool and each parameter mean.
- **To settle:** state the convention (summary line + `Args:` section +
  `Returns:`), and have `catalog()` publish `returns` text too. This is what a
  palette, a form, and eventually an agent read.

### 1.3 The contract, stated

> A tool is a **fully typed, self-describing** unit: every parameter and the
> return are annotated (the validation boundary), and the docstring describes
> the tool and each parameter (the presentation boundary). Nothing else in the
> model records intent, so the signature and docstring carry all of it.

---

## 2. Resources — capabilities a tool leverages

The piece the grid model is missing entirely. A **Resource** is a class the user
loads once — a database client, an HTTP/LLM client, a filesystem handle, config
— and that a tool *leverages* to do its work. It is **not** data, not a grid
value, not a reference, and not caller-supplied; it is a runtime **dependency
injected into the tool**.

### 2.1 What the engine already has (to port, not reinvent)

The retiring engine implements this fully — the design is settled, only the
grid port is owed:

- **`Resource()` marker as a default value** declares a dependency on the
  parameter:
  ```python
  @register_tool("load_orders")
  def load_orders(region: str, db: Database = Resource()) -> DataFrame: ...
  ```
  `region` comes from the grid; `db` is **injected**, never from a column or a
  bound literal. `Resource()` binds by parameter name; `Resource("other")` names
  a specific container key.
- **`ResourceContainer`** — a registry of injectable resources (factories or
  values, each with an optional health `check`).
- **`ResourceSpec`** — a *standard resource*: the runtime object plus how to
  build it and how to check it; `spec.tool(...)` registers a *bound* tool that
  may use only its own resource.
- **`App` owns default resources** seeded into every **`Session`**, and a session
  has its own container — isolation per user.
- Resources are **injected at run, invisible everywhere else**: schema.py says
  *"resources are injected, never part of the schema"*; validation.py says
  *"injected at run time, never caller-supplied"*. So they are not serialized,
  not validated as inputs, not shown as form fields.

### 2.2 Why they fit the grid model's invariants cleanly

A Resource is the one thing that enters a tool from *outside both the grid and
the arguments* — which is exactly consistent with the grid rules:

- it is **not a value** → never in `arguments`, never a `{"$ref": …}`;
- it is **not shape-bearing** → never affects columns or staging;
- it is **not serialized** → a workflow stays `{tool_id, inputs, arguments,
  modifiers}`; the resource is resolved at run from the session's container, by
  name;
- it is **injected at run** → it rides the same "needs the runtime, resolved
  when the step runs" timing as a value reference, but it comes from the
  container, not another step.

So Resources slot in as a **third input channel** to a tool, orthogonal to the
two the grid already has:

| channel | source | in the grid? | serialized? |
|---|---|---|---|
| grid columns | the input grid, by parameter name | yes | — (it's the data) |
| arguments | bound literals / value references | yes | yes (`$ref` or literal) |
| **resources** | the session container, by `Resource()` marker | **no** | **no** — resolved at run |

### 2.3 What to build in the grid model

- A `Resource()` marker recognized by `@tool`, excluded from the column bind,
  the arguments, `check`, staging, and serialization — exactly the engine's
  rule.
- A grid-side container (reuse `execution/resources.py`'s `ResourceContainer`
  and `resource_spec.py` if they can be lifted free of the engine) wired into
  whatever owns a session of workflows.
- `Workflow.run()` resolves a tool's `Resource()` parameters from the container
  at call time, alongside `_resolve_arguments`. A missing resource is a
  **run-time** problem with a clear message (the engine's
  `ResourceMissingError`), not a declaration error — a workflow is portable; its
  resources are environment.

### 2.4 Open questions

- Who owns the container in the grid world — a `Workflow`, or a `Session`/`App`
  layer above it (as the engine has)? The grid is currently a bare `Workflow`;
  resources may be the reason it grows a session owner.
- Do Resources appear in the status grid ([005](005-reshaping-merging-and-status-grids.md)
  §D) when missing — e.g., a step 🟠 "resource `db` not loaded"? Likely yes: a
  missing resource is a declared-but-unmet expectation, the same shape as a
  missing column.

### 2.5 Resources that ship their own tools (later — not yet designed)

The combine verbs in [005](005-reshaping-merging-and-status-grids.md) B (`join`,
`stack`, `zip`) are builtin operations that ship *with* the framework. That
motivates a broader pattern worth exploring once the basics land: **a Resource is
a class equipped with its own built-in tools** — it bundles state *and* the
operations that use that state, so loading the resource registers a related
family of tools at once.

The engine already gestures at this: `ResourceSpec.tool()` registers a *bound*
tool that may use only its own resource (and gets a prefixed id like
`file_system-list_files`). Generalizing it — a resource class whose methods
become tools, invoked through the resource — would make a resource a capability
*bundle*, not just an injected dependency. Deferred by request; captured here so
the connection to the builtin combine verbs is not lost.

---

## 3. Relationship to 005

Independent, but they meet at two points: the **status grid** (§005 D) is where a
missing resource would surface as a cell/step flag, and the **tool contract**
(§1) is what `check` and the palette already lean on. Build order is not coupled
— 005 (reshaping + status) can proceed first; Resources are the larger port and
can follow, reusing the engine's finished design.
