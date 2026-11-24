# Previous terms, kept as future spellings

> **2026-11-24, for the owner**, who asked: "make sure to save the previous
> terms in a separate folder, as we are likely to have spellings for
> them." Every term used before the names were decided
> ([../names.md](../names.md)), mapped to its decided name. Under the
> principle (../README.md), a spelling is defined **only by its mapping**
> to the canonical form, never by code of its own; this folder is the start
> of those mappings.

**Two sources:** today's code (the 1.0.x modifiers and combines, what the
app's expressions are written in), and the design's own placeholders
(used on these pages before 2026-11-24).

## The primitives

| Previous term | From | Decided name | As a spelling |
|---|---|---|---|
| `select` (columns; `rows=`) | today's code | **take** | likely: the verb for those who think in verbs (shorthands.md) |
| `filter` (a condition) | today's code | **take** | likely |
| `slice` | today's code | **take** | likely |
| `sort` | today's code | **take** | likely: a shorthand of its own |
| `distinct` | today's code | **take** | likely: a shorthand of its own |
| `drop` | today's code | **take** | likely |
| `pack` (a row's columns into a dict) | today's code; model.md §2 | **nest** | likely: columns into a dict only (as tidyr's) |
| `pack`, `unpack` (as the primitive) | names.md's first draft | **nest**, **unnest** | — |
| `collapse` (with `gather`) | today's code | **nest** (with calls per group) | likely: the group-by preset |
| `gather` (a built-in tool) | today's code | **nest** | possible |
| `expand` | today's code | **unnest** `into="rows"` | likely |
| `widen` | today's code | **unnest** `into="columns"` | likely |
| `explode` | pandas | **unnest** `into="rows"` | possible |
| "join together" | the design's placeholder | **combine** | — |
| `stack` | today's code | **combine: append** | likely (but pandas' and R's `stack` mean wide to long) |
| `zip_` | today's code | **combine: align** | likely |
| `join` | today's code | **combine: join** | kept as the form's own name |
| `how="cross"` | pandas | **combine: cross** | possible |
| `vlookup` | Excel | **lookup** | possible |
| `cast` | today's code | **convert** | likely |
| `astype` | pandas | **convert** | possible |
| `name` (`mod.name`) | today's code; the design's placeholder | **rename** | likely: naming an output |
| `rename` (`mod.rename`) | today's code | **rename** | kept |
| `to_wide`, `to_long` | names.md's first draft | **pivot**, **unpivot** | — |
| `melt`, `pivot_longer` | pandas, tidyr | **unpivot** | likely |
| `pivot_wider` | tidyr | **pivot** | possible |
| `ffill`, `fill_down` | pandas | **fill** | possible |

## The canonical form's words

| Previous term (placeholder) | Decided |
|---|---|
| `mod.call.…` | `mod.calls.…` |
| `call.once()`, `call.each_row()`, `call.each_group(by=…)` | `calls.once()`, `calls.each_row()`, `calls.each_group(by=…)` |
| `call.each_combination()`, `calls.each_setting()` | `calls.each_combination()` |
| `mod.exec.…`, `mod.call_exec.…`, `mod.step_exec.…`, `mod.exec.each_call.…`, `mod.exec.step.…` | `mod.run.…`, with `per="call"` or `per="step"` |
| `exec.timeout(…)` | `run.time_limit(…)` |
| `exec.retry(…)`, `exec.on_failure(…)`, `exec.stop_after(…)` | `run.on_failure(retry=…, default=…, stop_after=…)` |
| `exec.at_once(…)`, `exec.rate(…)` | `run.pace(at_once=…, per_second=…)` |
| `mod.output.land("own_row" \| "new_row" \| "each_row_of_group")` | `mod.output.place("row" \| "new_row" \| "group_rows")` |
| `land=` (one call per column) | `place=` |
| `mod.output.keep_rows()` | `mod.output.keep_if()` |
| `mod.output.name(…)` | `mod.output.rename(…)` |
| `over="call"` | the scopes `"all"`, `"group"`, `group(by=…)`, `window(n)` |
| `spread` (a cell's parts as arguments) | `input.as_keywords`, `input.as_positions` |
| `.tolist()`, `.to_dict()`, `.to_frame()`, `.to_numpy()` on a pick | `mod.input.nest(…, form=…)`; the pick methods kept as spellings (grammar.md H7) |

## Today's verbs as presets

The verbs of today's code stay as **presets**, each a combination of
primitives (primitives.md §5): `map`, `filter`, `group` (to be renamed: it
clashes with "group"), `expand`, `collapse`, `table` (to be renamed: it
clashes with "table"), `sweep`, `source`, `auto` (the resolver). Their new
names are to be decided with the presets themselves.

## Retired, with no spelling

`copy` stays its own (lineage made data, shorthands.md). Retired words of
model.md §2 (*selection*, *formula*, *result*, *orchestration*, *shape
verb*, …) are never spellings.
