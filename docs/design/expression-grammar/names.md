# The names

> **Draft, 2026-11-23, for the owner** (roadmap phase 1: "the primitives'
> names first, then the canonical form's"). For each: candidates, the
> reasons, and a recommendation. **The owner decides each.** Every name in
> the other pages is a placeholder until it is decided here.

## 0. What a good name is here

| # | A name is | Why |
|---|---|---|
| **NM1** | **plain English** a spreadsheet user understands | the goal: minimal cognitive load (closure.md §1) |
| **NM2** | **familiar** to pandas, dplyr, SQL or Excel users **where it means the same thing**, and avoided where it means something else | people think in different ways (shorthands.md); a familiar word with a different meaning misleads |
| **NM3** | **model.md's own word**, where there is one | CLAUDE.md: "use the words in model.md §2" |
| **NM4** | **not a retired word** (selection, formula, result, orchestration, shape verb, …) and **not a word with another meaning here** (group, table, block, pick, cell) | one word per idea (model.md §2) |
| **NM5** | **one name per primitive**; familiar words may be **spellings** of it (`select` for take) | the principle: one primitive, several spellings (README.md) |
| **NM6** | **pairs read as pairs** (in and out, wide and long) | they undo each other (nest.md NS1) |
| **NM7** | **short, and a valid Python name** | it is written in expressions |
| **NM8** | **primitives are verbs**; the classes of modifier are nouns; an argument says what it changes | a primitive is something done |

**The closest vocabulary is Excel's Power Query**: spreadsheet users
building a table in steps, as Simple Steps' users do. Its words (Append,
Merge, Expand, Group By, Pivot, Unpivot, Fill Down, Change Type, Rename,
Keep Rows) weigh most under NM2, then SQL, then tidyr and pandas.

## 1. The primitives

*Second look, 2026-11-23 (owner: "can you think harder … I need your help
with judgment").* Checked against what the words mean elsewhere, run where
it can be: pandas' `DataFrame.stack()` is **wide to long** (a reshape, not
rows appended); `DataFrame.align` pairs rows **by index**; numpy's `take`
with a permutation **is a sort** (`take([30, 10, 20], argsort)` → `[10, 20,
30]`).

| Primitive | Recommended | Why | Spellings that open into it |
|---|---|---|---|
| choose, reorder rows and columns | **`take`** | numpy's meaning exactly: these positions, in this order; a condition gives the positions, a sort is taking in sorted order. `keep` fails for sorting; `select` echoes the retired "selection" | `select`, `filter` (a condition), `slice`, `sort`, `distinct`, `drop`, a pick's parts |
| many cells into one | **`nest`** | **the design's word** (nest.md), and tidyr's for this move. *Changed from `pack`*: tidyr's `pack` is columns only, and Python's "unpacking" is `f(*args)`, the spread | `pack` (columns into a dict, as tidyr's), `collapse`, `gather` |
| one cell into many | **`unnest(into="rows" \| "columns")`** | tidyr's family (`unnest_longer`, `unnest_wider`); the direction an argument (NM5) | `expand`, `widen`, `explode` |
| tables made one | **`combine`** | **model.md's word** (NM3); pandas' `DataFrame.combine` is element-wise and obscure | — |
| … rows added under | **`append`** | Power Query's "Append Queries". *Changed from `stack`*: pandas' and R's `stack` are wide to long | `stack`, `concat`, `bind_rows` |
| … rows paired by identity | **`align`** | pandas' `align`, the same meaning: rows matched by index. *Changed from `zip`*: Python's `zip` pairs by position, which core never does | `zip_` |
| … rows matched by key | **`join`** | SQL; Power Query's "Merge" | `merge` |
| … every pair | **`cross`** | SQL's `CROSS JOIN` | — |
| … a value per row, from another step | **`lookup`** | Excel's `VLOOKUP` / `XLOOKUP` | `vlookup` |
| change a value's type | **`convert`** | plain; Power Query's "Change Type" | `cast`, `astype` |
| name columns | **`rename`** | *changed from `name`*: pandas, dplyr and Power Query all say `rename`; "name" is a noun everywhere else in core (a step's name, a column's name) | `name` |
| long to wide, and back | **`pivot` / `unpivot`** | *changed from `to_wide` / `to_long`*: Power Query's "Pivot Column", "Unpivot Columns", and SQL's `PIVOT` / `UNPIVOT`: the pair spreadsheet users know | `pivot_wider`, `pivot_longer`, `melt` |
| a gap from the nearest value | **`fill`** | tidyr's word; Power Query's "Fill Down" | `fill_down`, `ffill` |

**model.md's "pack, unpack"** become nest and unnest when model.md is
updated (roadmap phase 6), "pack" kept as the spelling for columns into a
dict.

## 2. The canonical form's words

### 2.1 The four classes of modifier

| Class (placeholder) | Candidates | Recommended | Why |
|---|---|---|---|
| input | `mod.input` · `mod.inputs` · `mod.args` | **`mod.input`** | plain; an attribute, so Python's builtin `input` doesn't clash |
| call | `mod.call` · `mod.calls` | **`mod.calls`** | "how many calls": plural reads as a count, and keeps it apart from "a call" |
| execution | `mod.exec` · `mod.run` · `mod.running` | **`mod.run`** | "how it runs": plain (NM1); `exec` is jargon, and Python's builtin |
| output | `mod.output` · `mod.out` | **`mod.output`** | plain |

### 2.2 Calls

| Placeholder | Recommended | Why |
|---|---|---|
| `call.once()` | **`calls.once()`** | — |
| `call.each_row()` | **`calls.each_row()`** | reads as English: "calls: each row" |
| `call.each_group(by=…)` | **`calls.each_group(by=…)`** | — |
| `call.each_combination()` | **`calls.each_setting()`** | a sweep's pieces are combinations of settings; "setting" is the word a user writes |
| one call per column | **`calls.each_column()`** | — |

### 2.3 Input

| Placeholder | Recommended | Why |
|---|---|---|
| `input.nest(param, over=…)` | **`input.nest(param, over=…)`** | the primitive's name (§1) |
| the scopes `"all"`, `"group"`, `group(by=…)`, `window(n)` | **the same** | each says what it is (canonical.md §3.1) |
| `input.convert(param, to=…)` | **`input.convert(param, to=…)`** | — |
| the spread (`f(**cell)`, `f(*cell)`) | **`input.as_keywords` / `input.as_positions`** (over `input.spread`, `input.kwargs`) | **`spread` means pivot-wider in older tidyr** (NM2); these say exactly what happens |
| `input.lookup(param, on=…)` | **`input.lookup(param, on=…)`** | Excel's word |
| `key(column, read=…)` | **the same** | — |

### 2.4 Execution (`mod.run`), each with `per="call"` or `"step"`

| Placeholder | Recommended | Why |
|---|---|---|
| `timeout(seconds=…)` | **`run.time_limit(seconds=…)`** | plain (NM1); `timeout` a spelling |
| `progress()` | **`run.progress()`** | — |
| `on_failure(retry=…, default=…, stop_after=…)` | **`run.on_failure(…)`** | — |
| `cancel()` | **`run.cancel()`** | — |
| `pace(at_once=…, per_second=…)` | **`run.pace(…)`** | — |

### 2.5 Output

| Placeholder | Candidates | Recommended | Why |
|---|---|---|---|
| `land("own_row" \| "new_row" \| "each_row_of_group")` | `land(…)` · `place(…)` · `onto(…)` | **`output.place("row" \| "new_row" \| "group_rows")`** | "place" is plain; the values shorter |
| `keep_rows()` (a filter's test) | `keep_rows()` · `keep_if()` | **`output.keep_if()`** | reads as English: "keep if the tool says yes" |
| `unnest(into=…)` | **`output.unnest(into=…)`** | the primitive's name |
| `keep_input()` | **`output.keep_input()`** | — |
| `name(…)` | **`output.rename(…)`** | the primitive's name (§1) |
| `expect(…)` | **`output.expect(…)`** | — |

### 2.6 Arguments, the other way (README.md's principle)

`undecided=`, `strict=`, `round=`, `lossy=`, `nonzero=`, `format=`,
`prefix=`, `agg=`, `only=`, `by=`, `limit=`, `land=` (→ `place=`),
`names=`, `missing_name=`, `direction=`, `expect=`: **recommended as
they are**; each says what it changes. `land=` follows §2.5.

### 2.7 Elsewhere

| Placeholder | Recommended | Why |
|---|---|---|
| `core.<name>` (core's own tools) | **`core.<name>`** | — |
| `k.freeze(name, pick)` | **`k.freeze`** | — |
| `k.block`, `k.accepts`, `k.fits` | **the same** | — |
| the n×m shape | **`rows × columns`** | blocks.md §1: "block" is the umbrella |

## 3. To decide

The owner, each name, in this order: **§1 the primitives** (take; nest,
unnest; combine and its forms append, align, join, cross, lookup; convert;
rename; pivot, unpivot; fill), then **§2**.
