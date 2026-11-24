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

## 1. The primitives

| Primitive (placeholder) | Candidates | Recommended | Why |
|---|---|---|---|
| **take**: choose and reorder rows and columns | `take` · `keep` · `choose` · `select` · `subset` | **`take`** | short, plain (NM1, NM7). `select` echoes the retired "selection" and in SQL means columns only; it stays a **spelling** (NM5). `keep` reads oddly for sorting |
| **nest** / **unnest** | **`pack` / `unpack`** · `nest` / `unnest` · `collapse` / `expand` | **`pack` / `unpack`** | **model.md's own words** (NM3): "a column into a list, a row into a dict, and back". `nest` is tidyr's for data frames in cells, a narrower meaning (NM2) |
| unnest **into rows** / **into columns** | `unpack(into="rows")` / `unpack(into="columns")` · `unpack_rows` / `unpack_columns` · `expand` / `widen` | **`unpack(into=…)`** | one primitive, the direction an argument (NM5, the canonical form's style); `expand`, `widen` stay **spellings** |
| **join together** | **`combine`** · `join` · `merge` | **`combine`** | **model.md's word** (NM3) for "reads several steps"; `join` is one of its forms (by key), so it can't name them all |
| its forms | `stack` · `zip` · `join` · `cross` · `lookup` | **the same** | each familiar where it means the same (NM2): `stack` (rows), `join` (SQL, by key), `cross` (SQL's `CROSS JOIN`), `lookup` (Excel's `VLOOKUP`). `zip` is Python's (pairs by position), which core's isn't: **`zip` → `align`?** (it pairs the same rows, by identity) |
| **convert** | **`convert`** · `cast` · `as_type` | **`convert`** | plain (NM1); `cast` is programming jargon, kept as a **spelling** |
| **name** | **`name`** · `rename` | **`name`** | it names outputs as well as renaming columns; `rename` a **spelling** |
| **pivot** / **melt** | `pivot_wider` / `pivot_longer` · `to_wide` / `to_long` · `pivot` / `melt` | **`to_wide` / `to_long`** | a pair that reads as one (NM6), in plain words (NM1); tidyr's `pivot_wider` / `pivot_longer` are close; `pivot`, `melt` (pandas) are spellings |
| **fill** | `fill` · `fill_down` | **`fill`** | tidyr's word, the same meaning (NM2); the direction is an argument |

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
| `input.nest(param, over=…)` | **`input.pack(param, over=…)`** | the primitive's name (§1) |
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
| `unnest(into=…)` | **`output.unpack(into=…)`** | the primitive's name |
| `keep_input()` | **`output.keep_input()`** | — |
| `name(…)` | **`output.name(…)`** | — |
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

The owner, each name, in this order: **§1 the primitives** (`take`;
`pack`/`unpack`; `combine` and its forms, and whether `zip` becomes
`align`; `convert`; `name`; `to_wide`/`to_long`; `fill`), then **§2**.
