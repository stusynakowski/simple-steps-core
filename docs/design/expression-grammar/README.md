# The expression grammar

*Owner, 2026-11-23: "I think this has been the key problem in this project,
and it impacts everything else, so if I get this right everything else will
be much easier."*

**The goal:** a user writes a really simple expression. Core converges, from
what is written, the data and the tool's types, on **exactly** what will run,
writes down every part it filled in, and shows it. Where there is more than
one reading, core writes the most likely and says so. The system is
**closed**: every expression is either a sentence of the grammar, or refused
when declared, naming the rule it breaks.

**The primitives' names** (decided 2026-11-23, names.md §1): **take;
nest, unnest; combine (append, align, join, cross, lookup); convert;
rename; pivot, unpivot; fill.** Other pages still use placeholders until
the canonical form's words are decided (names.md §2).

**The goal: reactive staging** (owner, 2026-11-23): know what a step will
give, quickly, before running it, so a solid workflow can be built without
running any step; and **arguments in the modifiers** to change any
convention (closure.md CL8, §6).

**The principle** (owner, 2026-11-23): **the same primitives, which need
to be tried and true and need to work; different spellings and syntaxes,
which mean different combinations of valid primitives in a valid syntax.**
All behaviour lives in the primitives; a spelling has none of its own.
And **where a convention could reasonably go either way, a reasonable
default, and an argument in the modifier or tool for the other way**
(owner, 2026-11-23: `undecided=`, `strict=`, `round=`, …). And **an error handled within the system is better than not knowing**
(owner, 2026-11-23): where no convention fits, the case is a visible error
(a failed cell, or a refusal, with its reason), never silence. So
the testing goes into the primitives and the conditions between them, and
a spelling is tested only for opening into the right combination.

| Page | What it holds | Read it for |
|---|---|---|
| [names.md](names.md) | **the names** (phase 1): what a good name is here (NM1–NM7), and candidates with a recommendation for each primitive and each word of the canonical form | deciding the names |
| [closure.md](closure.md) | **closed within the goals of the tool**: the goals (proposed), seven criteria each with its check, the coverage table (each kind of cell under each primitive), the catalogue of tasks, and where each part stands | whether the system is closed, and what's left |
| [grammar.md](grammar.md) | §0 top down: what the user sees, the inputs, the plain questions · §1–§4 the components every expression must resolve, and what core resolves today · §5 the owner's heuristics, H1–H9 · §6 **the five components and the classes each can be** · §8 open questions | the grammar itself |
| [primitives.md](primitives.md) | **one primitive, three places**: take, nest, unnest, join together, convert, name; each as a step, on a tool's input, or on its output; today's modifiers placed in that table, the gaps, and today's verbs as presets | organizing the modifiers, before naming them |
| [canonical.md](canonical.md) | **a proposed canonical form**: `tool[input…, call, execution…, output…](param=source, …)`, the class in each modifier's name, bindings always by keyword; the words by class; every kind of expression; surface examples opened into it; what it fixes | what is parsed, saved, run and shown |
| [conditions.md](conditions.md) | **L3, the conditions between components**: the two layers (canonical primitives, and the surface that maps to them), each component's own primitives, and R1–R26 (when, then, decided or proposed) | checking an expression is valid |
| [shorthands.md](shorthands.md) | **is each of today's verbs any good as a shorthand?** the tests (common, one reading, not redundant, clearly named), each verb judged with what it is built from, the useful ones missing | the start of the shorthand map (roadmap 1b) |
| [widen.md](widen.md) | **widen's conditions**: unnest into columns, every case pinned down (U1–U29: what it opens, which fields, uneven rows, names, depth, types, the plan, tidiness, the three places), today's behaviour and W1–W6 | the first primitive made robust |
| [expand.md](expand.md) | **expand's conditions**: unnest into rows, widen's mirror (V1–V20: what it opens, the rows, names, depth, types, the plan, the three places), beside pandas' `explode`, E1–E2 | the second primitive made robust |
| [nest.md](nest.md) | **nest's conditions**: many cells into one (rows into a list, columns into a dict, a block into a table), the reverse of widen and expand, chosen so nest and unnest undo each other (NS1–NS16, NF1–NF2) | the third primitive made robust |
| [joins.md](joins.md) | **join together's conditions**: stack, zip, join by key, cross, and lookup (another step's value per row, Excel's `VLOOKUP`: grammar.md N3); JN1–JN22, JF1–JF2 | the fourth primitive made robust |
| [take.md](take.md) | **take's conditions**: choosing and ordering rows and columns, no value changed (TK1–TK25: by position, by a condition, by a tool's test, sort, distinct, columns), TF1–TF2 | the fifth primitive made robust |
| [convert.md](convert.md) | **convert's conditions**: the one primitive that changes a value; a conversion keeps the value's meaning exactly or that cell fails (CV1–CV18, CF1–CF2) | the sixth primitive made robust |
| [pivot-fill-columns.md](pivot-fill-columns.md) | **pivot, fill, one call per column**: the catalogue's missing tasks, built from the primitives (PV1–PV9, FL1–FL7, PC1–PC7), beside pandas' conventions | the last of the catalogue |
| [tidy.md](tidy.md) | **tidy tables, enforced**: T1–T9 (names are strings, columns addressed by name or position, the canonical form stores the name, no meaningful row index, no hierarchical columns, …), today against them, and C1–C3 | the rules every table is held to |
| [roadmap.md](roadmap.md) | **the plan**: a clean slate (owner, 2026-11-23), no migration, names first; phases 0–6; a keep/toss inventory for the owner | what is built, in what order |
| [influences.md](influences.md) | what could blur the distinctions in §6 (whose function, what it works on, how many calls, how sure core can be), each run or reasoned | deciding each edge case on purpose |

**Background** (one level up): [blocks.md](../blocks.md), the runs and
findings behind this grammar (its §0 says how the grammar got here);
[grid.md](../grid.md), the grid and its moves.

**Status:** drafts, nothing built. The numbered rules have started in
conditions.md (R1–R26); next, going through the proposed ones, from §6's worked
examples; then the conventions, as one table.
