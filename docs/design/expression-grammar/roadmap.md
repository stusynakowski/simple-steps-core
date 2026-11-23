# Roadmap: a new instruction set

> **2026-11-23, for the owner.** The plan from the expression grammar to a
> built core. It replaces the pile of pieces in [blocks.md](../blocks.md)
> §6. Each piece is small, and each behaviour is confirmed with the owner
> before it lands (CLAUDE.md).

## The decisions it rests on

*Owner, 2026-11-23:* "I'm fine if the syntax breaks (it was already broken
anyway), like making a new instruction set (clean slate), but use as
inspiration what we have now. I really want to get it right. Now we don't
need any migration. Some things we might keep, but some things we might
want to just throw out. We should keep what we like, toss what we don't
and what certainly causes problems." And: "canonical names matter, and
primitives' names matter most."

| Decision | So |
|---|---|
| **a clean slate** | today's syntax doesn't have to keep working; it is inspiration, not a constraint |
| **no migration** | old saved sessions aren't carried over |
| **keep what we like, toss the rest** | an inventory, reviewed by the owner (below) |
| **names matter most** | naming comes **before** building, not last |

**Bugs in today's code:** the binding bugs (A4, H3's case b, G2) are
replaced by the new set's binding (by keyword; conditions.md R1–R8), so
they are **not patched**. The **data layer's** silent losses (F1, F2, I1,
I2) live under any instruction set, so they **are fixed**, in today's code.

## The phases

| Phase | What | Done when |
|---|---|---|
| **0. Consolidate** | this roadmap; blocks.md trimmed to its evidence (runs, findings, freezing, iterables, moves), the superseded parts cut to a short "how we got here"; the keep/toss inventory (below) reviewed; a note to the app (015) on the direction | the owner has reviewed the inventory |
| **1. Names** | the primitives' names first (primitives.md: take, nest, unnest, join together, convert, name, as placeholders), then the canonical form's (the classes, the modifiers, the scopes, the levels); one naming page, candidates and reasons, the owner deciding each | every name in canonical.md is decided |
| **2. The data layer's silent losses** | F1 (absent stays absent in a data step), F2 (a column keeps its type), I1 (`widen` opens a list, refuses what it can't open), I2 (`expand` keeps a row whose list is empty, its item absent): one at a time, each confirmed | each has its test, every check green |
| **3. The canonical core** | the new instruction set built: the five components as objects, the parser and the printer (one canonical text, printed back exactly), the resolver (written, implied, convention: grammar.md §1), the conditions (conditions.md) each with its problem text; tests written for it, and a property test that generates expressions from the grammar: each runs, or is refused naming its condition | every condition decided and tested |
| **4. The surface** | shorthands mapped into the canonical form, each opening into it exactly (presets; methods on picks; `auto`, writing the most likely and saying why) | every shorthand round-trips |
| **5. What's new** | the scopes of nesting (`"group"`, `group(by=…)`, `"all"`, `window(n)`); landing on every row of a group; execution's primitives at their levels (time limit, progress, on failure, cancel, pace: the app's K23); freezing; `k.block`, `k.accepts`, `k.fits` | each confirmed |
| **6. Switch over** | the new set replaces the old; model.md's words; the app's update guide (the app moves to the new set; no sessions carried over) | the app runs on it |

Open questions that don't block a phase are settled when their phase
reaches them (grammar.md §8, conditions.md's proposed conditions,
primitives.md §6, canonical.md §7).

## Keep, toss: a first inventory, for the owner to edit

**Proposed keep** (works, and fits the grammar):

| Keep | Why |
|---|---|
| the kernel, steps, the workflow; a step's name | the frame everything sits in |
| picks, `wf["p"][rows][columns]`, as live addresses | solid (grammar.md §0); they follow their rows (blocks.md §1) |
| row ids underneath, row numbers shown, lineage | how a pick follows its row, and how a cell traces back |
| cell states (absent, known, pending, failed, blocked, …) and step states | what the user sees of a run |
| staging: a plan before anything runs | "know what you get before you run it" |
| staleness, and reusing a kept output when nothing changed | slow work isn't redone |
| saving (a folder per step), spilling bulky cells to disk | works, and exact (blocks.md §2) |
| a cell's recipe (`formula`, `by_value`), `k.run_cell`, `k.clear` | built 2026-11-20, and they fit |
| the catalog: tools with type hints, resources with secrets | the source of the conventions |
| problems and warnings as objects | the conditions' messages |

**Proposed toss** (causes problems, or the grammar replaces it):

| Toss | Why |
|---|---|
| verbs as single modifiers that cross classes (`map`, `collapse`, `filter`, `group`, `expand`, `table` as they are) | each mixes call, input and output (primitives.md §5); they come back, if at all, as named presets of the canonical form |
| modifier order as written deciding meaning | O1: `[retry, map]` retries nothing |
| binding by position across a block, by a column's type, and a default silently beating a same-named column | A4, H3 case b, G2: guesses beyond a reasonable doubt |
| conversions decided at the call from the parameter's type (`_CONVERTS`) | A6, A7: the parameter's type chose the level |
| several spellings of one primitive (`filter` with a condition, `slice`, `select(rows=)`, a pick's row part) | primitives.md §3: up to five spellings of "take rows" |
| `copy` beside a pick declared as a step | the same thing twice |
| `auto` deciding from the data at run (`compile_operation`'s run-time `auto`) | a step's meaning must be fixed when declared |
| `mod.group`, `mod.table` as names | they clash with "group" and "table" |

**To decide:** `sweep` (keep as a call over combinations of settings?);
`source` (a tool with no input: keep as is?); `expect` (a check on the
output: keep as an output modifier?); `breaker` (becomes execution's
"stop after n failures", per step).
