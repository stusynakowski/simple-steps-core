> Built by `scripts/core_handover.py` in Simple Steps. Files here:
> `plan.md` (1), `requests.md` (2), `words-and-rules.md` (3),
> `code-to-port/` (4), `probes/` (5), `CLAUDE.md` (6). Links below
> point into the Simple Steps repo.


# 011 — Handing the core update over to `simple-steps-core`

> Written 2026-10-26, app on the current core pin. The owner is making these
> changes in `simple-steps-core`; this repo still treats
> `external/simple-steps-core/` as read-only. This page lists what to carry
> over for context. It holds no new decisions; those are in the documents it
> points to.

**To copy it all at once:** `python scripts/core_handover.py` builds
`build/core-handover/` (git-ignored) from the current files: this page as its
README, plus `plan.md`, `requests.md`, `words-and-rules.md`, `code-to-port/`,
`probes/` and a `CLAUDE.md` of core's rules. Rebuild it after any of those
files change; don't edit the folder.

**The goal in one line.** Everything Simple Steps can do to a workflow can be
done on a kernel in a Python terminal. Core is the grid model and nothing
else; this repo adds transport, sessions, storage, concurrency, UI and the
agent.

## 1. The plan: start here

[`docs/system_design/12-core-and-app.md`](../system_design/12-core-and-app.md),
from **"The core update: what moves, what's fixed, what must work"** to the
end:

- the goal and the terminal test
- core's object model, with Kernel and Catalog
- one step, several forms
- spec and status, for every object
- what to migrate from this repo, what to fix in core, what to remove from core
- what stays in the app
- the acceptance session (each line marked *now* or *update*)

## 2. The requests, with what was run

[`008-core-changes.md`](008-core-changes.md):

| IDs | About |
|---|---|
| K17–K18 | keeping JSON v1 loadable; enforcing `timeout` |
| K19 | a column argument pairs per row by type; row id = the frame's index |
| K20 | kernel and run ids by hashing specs; tool hashes; seeds for tools that aren't deterministic |
| K21 | `extras` in each spec, namespaced, never hashed |
| K22 | outputs kept by data version while something reads them |
| K23 | progress and cancellation as modifiers |
| K24 | no state shared between workflows |
| K25 | resource defaults are literals; resources report a data version |
| K26 | size estimates (or `unknown`, with the reason), output in pages |
| K27 | return types: `unknown` until it runs, then observed or the union |
| K28 | cell-to-cell lineage stored in each output, multi-output cells included |
| K29 | renames: references follow; reading old data warns |
| R7–R9 | media handles; failed rows turning integers into floats; stages |
| C28–C32 | older open asks, including the pluggable output store (C32) |

## 3. The words and the rules

- [`docs/why-we-are-building-this.md`](../why-we-are-building-this.md):
  **"Words and what they mean"** (spec, status, kernel, catalog, …) and
  **"What is acceptable"** (how code enters, what the agent may do).
- [`docs/how-simple-steps-works.md`](../how-simple-steps-works.md) §1: the
  restriction table, what a formula may contain and why.

## 4. Code to port into core

| File | What to take |
|---|---|
| [`operation_formula.py`](../../src/SIMPLE_STEPS/operation_formula.py) | the whole file: the safe formula parser, which becomes `Formula.parse` beside `to_source()` |
| [`agent/proposals.py`](../../src/SIMPLE_STEPS/agent/proposals.py) | `check_step`, `check_proposal`, which become `validate` on a proposed formula |
| [`application.py`](../../src/SIMPLE_STEPS/application.py) | how the `App` limits tools: the start of the Catalog |
| [`kernels.py`](../../src/SIMPLE_STEPS/kernels.py) | `summary()`: the start of a readable `repr` |
| [`core_bridge.py`](../../src/SIMPLE_STEPS/core_bridge.py) | the shims core should close: C17, C18, G |

## 5. The scripts that ran each claim

In [`scripts/core_probes/`](../../scripts/core_probes/). Each runs against core
alone: `.venv/bin/python scripts/core_probes/<file>`.

| Script | Shows |
|---|---|
| `terminal_demo.py` | the terminal session: define, run, read, edit (stale), save, load |
| `probe_refs2.py` | the reference forms: selections, later steps, computed arguments |
| `probe_colarg.py`, `probe_colarg2.py` | a column as an argument, and the `zip_` route (K19) |
| `toolhash.py` | hashing a tool's source, and its cost (K20) |
| `probe_rename_lineage.py` | renames rewrite references; lineage through `expand` (K28, K29) |

## 6. Rules for core's own `CLAUDE.md`

- The grid is the only model.
- Verify a claim by running it, never by reading docs.
- No mutable state at module level (K24).
- An empty step is a 1×1 frame with one cell `"empty"`, never a placeholder.
- Extras live under a namespace and are never hashed (K21).
- Each behaviour change is confirmed in small pieces.

## 7. Bringing the update back here

1. Move the pin in `pyproject.toml` and the submodule commit together, then
   `python scripts/preflight.py`.
2. Before core deletes the older engine's names, move this repo off them:
   [`core_bridge.py`](../../src/SIMPLE_STEPS/core_bridge.py) (`register_tool`,
   `REGISTRY`, `ResourceSpec`) and [`main.py:139`](../../src/SIMPLE_STEPS/main.py)
   (`REGISTRY`), onto the catalog.
3. `ResourceSpec` is then reused for a resource's spec. `CLAUDE.md` and
   `docs/context.md` give `cannot import name 'ResourceSpec'` as the symptom of
   pin drift; change it to a name that is actually new.
4. Run the acceptance session in doc 12 and the probes above; every *update*
   line should now pass.
