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

| Page | What it holds | Read it for |
|---|---|---|
| [grammar.md](grammar.md) | §0 top down: what the user sees, the inputs, the plain questions · §1–§4 the components every expression must resolve, and what core resolves today · §5 the owner's heuristics, H1–H9 · §6 **the five components and the classes each can be** · §8 open questions | the grammar itself |
| [primitives.md](primitives.md) | **one primitive, three places**: take, nest, unnest, join together, convert, name; each as a step, on a tool's input, or on its output; today's modifiers placed in that table, the gaps, and today's verbs as presets | organizing the modifiers, before naming them |
| [canonical.md](canonical.md) | **a proposed canonical form**: `tool[input…, call, execution…, output…](param=source, …)`, the class in each modifier's name, bindings always by keyword; the words by class; every kind of expression; surface examples opened into it; what it fixes | what is parsed, saved, run and shown |
| [conditions.md](conditions.md) | **L3, the conditions between components**: the two layers (canonical primitives, and the surface that maps to them), each component's own primitives, and R1–R26 (when, then, decided or proposed) | checking an expression is valid |
| [roadmap.md](roadmap.md) | **the plan**: a clean slate (owner, 2026-11-23), no migration, names first; phases 0–6; a keep/toss inventory for the owner | what is built, in what order |
| [influences.md](influences.md) | what could blur the distinctions in §6 (whose function, what it works on, how many calls, how sure core can be), each run or reasoned | deciding each edge case on purpose |

**Background** (one level up): [blocks.md](../blocks.md), the runs and
findings behind this grammar (its §0 says how the grammar got here);
[grid.md](../grid.md), the grid and its moves.

**Status:** drafts, nothing built. The numbered rules have started in
conditions.md (R1–R26); next, going through the proposed ones, from §6's worked
examples; then the conventions, as one table.
