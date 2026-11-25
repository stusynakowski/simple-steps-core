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

**Tests** (owner, 2026-11-23): "keep the tests for now, see where we land,
but expect the tests themselves to change drastically." Today's tests stay
and stay green while today's code is worked on (phase 2); the new set
brings its own (phase 3), and the old ones change or go with what they test
when it is switched over (phase 6). CLAUDE.md is unchanged.

**Extensions, later**: writing to databases or files, streaming, work
across machines, charts beyond a figure in a cell (closure.md §1): outside
the first closed core, added after it.

**Bugs in today's code:** the binding bugs (A4, H3's case b, G2) are
replaced by the new set's binding (by keyword; conditions.md R1–R8), so
they are **not patched**. The **data layer's** silent losses (F1, F2, I1,
I2) live under any instruction set, so they **are fixed**, in today's code.

## The phases

| Phase | What | Done when |
|---|---|---|
| **0. Consolidate** | this roadmap; blocks.md trimmed to its evidence (runs, findings, freezing, iterables, moves), the superseded parts cut to a short "how we got here"; the keep/toss inventory (below) reviewed; a note to the app (015) on the direction | the owner has reviewed the inventory |
| **1. Names** | the primitives' names first (decided 2026-11-23: take, nest, unnest, combine, convert, rename, pivot, unpivot, fill; names.md), then the canonical form's (the classes, the modifiers, the scopes, the levels); one naming page, candidates and reasons, the owner deciding each | every name in canonical.md is decided |
| **1b. The shorthand map** | once the primitives and their conditions are solid: **every current modifier and combine** (`map`, `filter`, `group`, `expand`, `collapse`, `table`, `sweep`, `source`, `select`, `drop`, `slice`, `sort`, `distinct`, `rename`, `copy`, `widen`, `pack`, `name`, `cast`, `expect`, `retry`, `timeout`, `breaker`, `try_except`, `auto`; `join`, `zip_`, `stack`) written as **how it is built from the primitives** in the canonical form, or marked tossed (owner, 2026-11-23: "after the solid primitives and conditions on them, I will want a mapping between the current shorthand modifiers and how they are built from primitives"). primitives.md §5 is its start | every current modifier is mapped or tossed |
| **2. The data layer's silent losses** | **F1 done** (2026-11-25: every gap in data given is absent; expand says a gap as it says `None`; `identity` of a row with no values is `None`, never `{}`), **F2 done** (a column keeps its dtype; a float column of whole numbers and gaps is warned, never turned into `Int64`; 008 C14's test and probe moved to `Int64`), I1 (`widen` opens a list, refuses what it can't open), **column names done** (2026-11-25: duplicates suffixed and said, MultiIndex flattened with `_`: tidy.md C2, C3); **widen's names done** (2026-11-25: W2, W5, W6, U12, U15–U20, U29: names as text, `#` dropped and said, collisions suffixed and said, the plan naming fields as the run does; extra and missing declared fields, 50+ fields, zero rows said); **I1 and widen's opening done** (2026-11-25: lists by position, ragged rows to the longest with gaps, a unit or a set fails its own row, the failures visible when nothing opens; widen.md U3–U5, U7, U11, U13); **I2 done** (2026-11-25: a placeholder row for no item, its id `"<parent>.-"`; no call made for it; nesting gives nothing for it; an empty list core packed from zero rows unnests to zero rows; expand.md §A.1): one at a time, each confirmed | each has its test, every check green |
| **3. The canonical core** | the new instruction set built: the five components as objects, the parser and the printer (one canonical text, printed back exactly), the resolver (written, implied, convention: grammar.md §1), the conditions (conditions.md) each with its problem text; tests written for it, and a property test that generates expressions from the grammar: each runs, or is refused naming its condition | every condition decided and tested |
| **4. The surface** | shorthands mapped into the canonical form, each opening into it exactly (presets; methods on picks; `auto`, writing the most likely and saying why). A spelling has no behaviour of its own (the principle, README.md): each is tested only for opening into the right combination of primitives | every shorthand round-trips |
| **5. What's new** | a locale-aware reading method, and data formats for structures as text (convert.md §E); pivot, fill, one call per column (in scope: closure.md §4); recursive expansion as a layer on widen and expand (widen.md, expand.md, *Later*); the outputs gathered into one list, a group as a table, unnesting a table cell (nest.md §E); `key(…, read=…)` (nest.md §A.1); opening a 1-D array like a list (expand.md, *Later*); the scopes of nesting (`"group"`, `group(by=…)`, `"all"`, `window(n)`); landing on every row of a group; execution's primitives at their levels (time limit, progress, on failure, cancel, pace: the app's K23); freezing; `k.block`, `k.accepts`, `k.fits` | each confirmed |
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
| the verbs **as they are built today**: each its own mechanism, mixing call, input and output (primitives.md §5) | the verbs themselves are kept as **shorthands, rebuilt on the primitives**: consolidating several primitives across components into one verb is the point (owner, 2026-11-23). Which are worth it: [shorthands.md](shorthands.md) |
| modifier order as written deciding meaning | O1: `[retry, map]` retries nothing |
| binding by position across a block, by a column's type, and a default silently beating a same-named column | A4, H3 case b, G2: guesses beyond a reasonable doubt |
| conversions decided at the call from the parameter's type (`_CONVERTS`) | A6, A7: the parameter's type chose the level |
| several spellings of one primitive **each with its own code** (five for "take rows" today) | they drift apart. The spellings are kept (people write the same thing differently: owner, 2026-11-23), each **defined only by its mapping** to the canonical form (shorthands.md) |
| `auto` deciding from the data at run (`compile_operation`'s run-time `auto`) | a step's meaning must be fixed when declared |
| the names `group` and `table` for those verbs | the ideas kept, renamed: they clash with "group" and "table" (shorthands.md) |

**`sweep`, `source`, `expect`, `breaker`:** proposed kept, in shorthands.md
(`breaker` as execution's "stop after n failures", per step).
