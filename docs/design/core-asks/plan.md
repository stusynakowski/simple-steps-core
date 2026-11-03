# Core development plan: references, selection and lineage

> Written 2026-11-02 against the current core pin; revised the same day
> with the owner's answers to core's review (core's `decisions.md` §4, IDs
> `CA-…`; core-asks D1 is CA-D1, and so on). The changes go into
> `simple-steps-core`; Simple Steps treats `external/simple-steps-core/` as
> read-only. Every "today" result below was **run**, not read (the script is
> in §12). The target model is [model.md](model.md).

**What this page is.** The core work behind the model, as ordered milestones.
Each change has an ID (`L1`, `L2`, …), what core does today, what it should
do, and the tests that prove it's done. The IDs are new: no `L` ID exists in
Simple Steps' `docs/core-proposals/008-core-changes.md`. Where an older ask
overlaps, it's named (§13).

**How to use it.** Do the milestones in order: each one's tests stay green
while the next is built. A milestone is done when every test in it passes
against core alone (no app code).

---

## 1. The target in one paragraph

Every output has three parts, told apart by name: **lineage** (`#<parent>`,
one per parent: the parent placement(s) each row came from), the **row
number** `#<step>` (`0..n-1`, the row's placement), and **data** (named
columns that never start with `#`). A pick reads like a list and a dict:
integers choose rows by placement, strings choose columns, a condition
chooses rows by value or by row number. A step's modifiers are any number of
**pickers** (narrow the input), at most one **verb** (how the tool is applied)
and execution wrappers. Tools receive data only. Rows from different steps
pair only where the formula says so. Nothing fails silently.

## 2. Decisions needed before core work starts

| # | Decision | Recommended | Blocks |
|---|---|---|---|
| D1 | **What a column argument passes: the verb decides, not the parameter's type** (owner, 2026-11-02; supersedes K19). Under `map` / `filter` / `expand`, each call gets **its row's cell**, whatever it holds (a list if the cell is a list). Under a single call (`source`, no input), the column arrives **whole, as a list**. Under `collapse`, each call gets **its group's values** as a list. The parameter's type only checks the value; it never changes what's sent. The verb is written in the formula, so the same text means the same data | Decided | L3 |
| D2 | Default name of a tool's output column | **Owner, 2026-11-02:** one value or one column → the **step's name**. Several named parts (a dict) → the keys. Unnamed parts (a tuple) → `var0`, `var1`, … unless renamed | L21, L23 |
| D3 | `mod.select(cols=…)` or core's `columns=` | Accept both; print `cols=` | L32 |
| D4 | Can lineage be renamed into data? | **Owner, 2026-11-02:** no. Lineage is never changed by the user; it can only be **copied** into a new data column: `mod.copy(columns={'#r': 'parent'})`. `mod.rename` on a `#` column copies too and is saved as `mod.copy`; on data, `rename` moves and `copy` duplicates (CA-D, 2026-11-02) | L18 |
| D5 | Lineage values | **Owner, 2026-11-02:** lineage cells are integers, lists of integers, or **empty** (stack, outer joins: CA-L2). A collapse gives a list. An expand gives **two** columns: `#r` (the parent placement) and `#r.idx` (the item's index within the parent's cell) | L12, L36 |
| D6 | Binding (CA-A) | **Owner, 2026-11-02:** decided at staging and saved explicitly. Per parameter, the first that decides: what the user wrote; a column with its name (only without a default); the one column whose type fits; otherwise `invalid`, writing the fix. Lossless conversions are automatic, others need `mod.cast` | L50, L51 |
| D7 | Lineage is recursive (CA-L1) | **Owner, 2026-11-02:** every step carries its ancestors' lineage; a step that isn't one-to-one also adds `#<parent>` | L44 |
| D8 | Merging a step with its ancestor (CA-C) | **Owner, 2026-11-02:** never implicit; `join(…, on='#r')`, columns passed through unchanged from the shared ancestor merge | L1, L45 |
| D9 | Names that aren't identifiers (CA-E) | **Owner, 2026-11-02:** kept as written, picked by string, bound by keyword or type | L46 |
| D10 | Matching nothing (CA-5) | **Owner, 2026-11-02:** zero rows and a warning; a row number out of range fails | L31 |
| D11 | Small rules | **Owner, 2026-11-02:** a list cell in a condition (CA-L3); `[0, 2]` refused (CA-7); no `.` in step names (CA-8); delete refused, or delete anyway (CA-6); a rename rewrites what core wrote (CA-9) | L43, L47–L49, L52 |

## 3. Shared fixture

Every test uses this, built in a plain `Kernel`:

```python
r      = {"ward": ["A", "B", "A", "C"], "n": [10, 20, 30, 40]}   # 4 rows
other  = {"ward": ["A", "C", "D"], "pop": [1, 2, 3]}              # 3 rows
third  = {"ward": ["A", "B", "C"], "area": [5, 6, 7]}             # 3 rows

double(n: int) -> int            # n * 2
is_big(n: int) -> bool           # n >= 20
split_in_two(n: int) -> list     # [n, n + 1]
add_up(n: list) -> int           # sum(n)
add_k(n: int, k: int) -> int     # n + k
add_all(n: int, k: list) -> int  # n + sum(k)
pair(n: int) -> dict             # {"a": n, "b": n + 1}

filtered  = is_big[mod.filter()](wf["r"])                        # n 20, 30, 40
sorted_   = identity[mod.sort(by="n", ascending=False)](wf["r"])  # n 40, 30, 20, 10
expanded  = split_in_two[mod.expand()](wf["r"])                  # 10, 11, 20, 21, …
per_ward  = add_up[mod.collapse(by="ward")](wf["r"])             # A 40, B 20, C 40
doubled   = double[mod.map()](wf["r"])                           # 20, 40, 60, 80
```

The same steps are in the app's `scripts/ui_status` workflows 06 and 07.

---

## 4. Milestones

| | Milestone | Why first |
|---|---|---|
| **M0** | Stop silent wrong results | Wrong answers with no error, under any syntax |
| **M1** | Rows are placements | Every pick, picker and lineage value is built on it |
| **M2** | Lineage | The link between steps, now that `#` is a placement |
| **M3** | Column names and output naming | The data part of the model |
| **M4** | Selection grammar | The user-facing syntax, on M1–M3 |
| **M5** | Arguments, binding and pairing across steps | Needs M1, M2, D1 and D6 |
| **M6** | Editing in a live session | Needs M1, M2 |

---

## 5. M0 — Stop silent wrong results

| ID | Change | Overlaps |
|---|---|---|
| L1 | A column argument from a step whose rows aren't aligned with the input is **refused**; the message writes the join (`on='#r'` when one descends from the other, L45) | K19, C20 |
| L2 | `zip_` of steps whose rows don't line up is **refused** | — |
| L3 | What a column argument passes depends on the verb, never on the parameter's type (D1). A type that doesn't fit what the verb sends is refused | **supersedes K19** |
| L4 | A source whose data has a key starting with `#` is refused | — |
| L5 | `total` over mixed columns sums what it can and fails the rest by name; never every column `None`. `total(…, numeric_only=True)` leaves out what isn't numbers, as in pandas (owner, 2026-11-02) | — |

| Test | Formula | Expected | Today |
|---|---|---|---|
| TEST-L1 | `add_k[mod.map()](wf["r"], k=wf["filtered"][cols["n"]])` | refused at declare; message writes the `join` | runs: `[None, 40.0, 60.0, 80.0]` |
| TEST-L2 | `zip_(wf["doubled"], wf["filtered"])` | refused: rows don't line up (4 vs 3, different lineage) | one row, value `None`, no error |
| TEST-L3a | `add_all[mod.map()](wf["r"], k=wf["r"][cols["n"]])` (`k: list`; each row's cell is an int) | refused: under `map`, `k` gets each row's cell, an int, not a list | runs: `110, 120, 130, 140` (whole column to each row) |
| TEST-L3b | `add_k[mod.map()](wf["r"], k=wf["r"][cols["n"]])` | `20, 40, 60, 80` | same (keep green) |
| TEST-L3c | `total_of[mod.source()](k=wf["r"][cols["n"]])` (`total_of(k: list)`: one call) | one cell, `100` | same (keep green) |
| TEST-L3d | `g = gather[mod.collapse(by="ward")](wf["r"])`; then `total_of[mod.map()](wf["g"], k=wf["g"][cols["n"]])` (cells hold lists) | `40, 20, 40`: each row's list summed | `None` in every row, no error (the whole column of lists was sent) |
| TEST-L3e | `g` with `n` renamed `k`; `total_of[mod.map()](wf["g2"])` (bound by name) | `40, 20, 40` | same (keep green) |
| TEST-L4 | a source with data `{"ward": ["A"], "#n": [1]}` | refused: `#` names are reserved | **core passes** (a DataFrame with a `#` key is refused). The app's `to_rows` tool gives one null row instead: an app bug, not core's |
| TEST-L5 | `op("total")[mod.collapse()]` over `{"t": ["x","y"], "a": [1,2], "b": [10,20]}` | `a` 3, `b` 30; `t` failed with its reason, naming `numeric_only=True` | every column `None` |
| TEST-L5b | the same, `numeric_only=True` | columns `a` 3, `b` 30; no `t` | every column `None` |

---

## 6. M1 — Rows are placements

| ID | Change | Overlaps |
|---|---|---|
| L6 | Every output shows its row number as `#<step>`, `0..n-1` (a translation in the view: core's row ids stay its identity, CA-B1) | C7 |
| L7 | Every plain integer row form selects by row number as typed: `[i]`, `[[i, k]]`, `[i:j]`, `[-1]`, and the same inside `rows[…]`. Staging saves the rows' lineage: back to the source row, `.idx` through an expand, the key through a collapse; into a source it stays a row number | C7 |
| L8 | Text row ids retired: `rows["A"]` refused with the row number to use | — |
| L9 | Row ids stay inside core, never in `#<step>`, never written by an expression | — |

| Test | Formula / check | Expected | Today |
|---|---|---|---|
| TEST-L6a | rows of `filtered` | `#filtered` = `0, 1, 2` | `#` = `1, 2, 3` |
| TEST-L6b | rows of `sorted_` | `#sorted_` = `0, 1, 2, 3` | `3, 2, 1, 0` |
| TEST-L6c | rows of `expanded` | `#expanded` = `0 … 7` | `0.0, 0.1, 1.0, …` |
| TEST-L6d | rows of `per_ward` | `#per_ward` = `0, 1, 2` | `A, B, C` |
| TEST-L7a | `wf["sorted_"][1]` | `n` = 30 | 20 (row id 1) |
| TEST-L7b | `wf["sorted_"][[0, 1]]` | `n` = 40, 30 | 10, 20 |
| TEST-L7c | `wf["sorted_"][1:3]` | `n` = 30, 20 | same (keep green) |
| TEST-L7d | `wf["sorted_"][-1]` and `wf["sorted_"][rows[-1]]` | `n` = 10 | refused |
| TEST-L7e | `wf["per_ward"][0]` | ward A | refused: *no row 0 (its row ids are A, B, C)* |
| TEST-L8 | `wf["per_ward"][rows["A"]]` | refused; message: use `wf["per_ward"][0]` | works |
| TEST-L7f | `wf["sorted_"][1]`, `wf["expanded"][2]`, `wf["per_ward"][0]`, `wf["r"][3]`: the saved expressions | `row["r"] == 2`; `row["r"] == 1` and `row["r"].idx == 0`; `cols["ward"] == "A"`; `wf["r"][3]` | saved as written |

---

## 7. M2 — Lineage

| ID | Change | Overlaps |
|---|---|---|
| L10 | Every step that isn't one-to-one has one `#<parent>` per parent, holding parent **placements** | K28 |
| L11 | Filter, slice, sort, pick: one placement. Collapse, distinct, gather: a list | K28 |
| L12 | Expand: two lineage columns, `#<parent>` (the parent placement) and `#<parent>.idx` (the item's index in the parent's cell), both integers (D5) | K28 |
| L13 | One-to-one steps (map, rename, select columns) add no lineage; they carry their input's unchanged (L44) | — |
| L14 | A combine (join, zip_, stack) has one `#<input>` per input, and carries each input's lineage (L44) | — |
| L15 | The same parent twice is numbered `#r`, `#r.2`. After the dot, a number is the occurrence and `idx` is the item index (`#r.2.idx`) | — |
| L16 | Lineage is not data: `k.view` returns it apart from `columns`; whole-step references and `select` exclude it; a tool never receives it | — |
| L17 | `join(child, parent, on="#parent")` matches the child's lineage to the parent's `#<parent>` | — |
| L18 | Lineage is read-only: it can't be dropped or edited. It can be **copied** into a new data column, `mod.copy(columns={"#r": "parent"})` (D4). `mod.rename` on a `#` column copies too, and is saved as `mod.copy` (CA-D) | — |
| L19 | Settings may name `#` columns (`collapse(by="#r")`, `sort(by="#r")`) | — |
| L44 | **Every step carries its ancestors' lineage** (D7). Filter, sort, pick: carried values follow the kept rows. Expand: repeated. Collapse, distinct: lists. The same ancestor by two paths: `#r`, `#r.2` | K28 |
| L45 | `join(a, b, on="#r")` works whenever one descends from the other; a column passed through unchanged from the shared ancestor appears once, not as a clash. `how="left"` gives every row back, `absent` where a step dropped it (D8) | — |

| Test | Formula / check | Expected | Today |
|---|---|---|---|
| TEST-L10 | `#r` of `filtered` | `1, 2, 3` | no `#r` |
| TEST-L11a | `#r` of `sorted_` | `3, 2, 1, 0` | no `#r` |
| TEST-L11b | `#r` of `per_ward` | `[0, 2], [1], [3]` | same values (keep), but in the data columns |
| TEST-L12 | lineage of `expanded` | `#r` = `0, 0, 1, 1, 2, 2, 3, 3`; `#r.idx` = `0, 1, 0, 1, 0, 1, 0, 1` | `#r` right; no `#r.idx`; `#` holds `0.0, 0.1, …` |
| TEST-L12b | `split_in_two[mod.expand()](wf["filtered"])`: `#filtered`, and `#r` carried | `0, 0, 1, 1, 2, 2`; `#r` = `1, 1, 2, 2, 3, 3` | `#filtered` = `1, 1, 2, 2, 3, 3` (r's ids, one hop too far) |
| TEST-L13 | lineage of `doubled`; of `identity[mod.rename(columns={"value": "n"})](wf["expanded"])` | none; `#r`, `#r.idx` (carried, nothing added) | none; `#r` only |
| TEST-L14a | `stack(wf["r"], wf["filtered"])`: `#filtered` | `None ×4, 0, 1, 2` | `None ×4, 1, 2, 3` |
| TEST-L14b | `j2 = join(wf["r"], wf["other"], on="ward")`; `join(wf["j2"], wf["third"], on="ward")` | lineage `#j2`, `#third`, and carried `#r`, `#other` | `#j2`, `#third` |
| TEST-L14c | `stack(wf["r"], wf["other"], wf["third"])` | `#r`, `#other`, `#third` | same (keep green) |
| TEST-L15 | `join(wf["r"], wf["r"], on="ward")` | lineage `#r`, `#r.2` | `#r_1`, `#r_2` (an underscore can't be told from a step named `r_1`) |
| TEST-L16a | `k.view("per_ward")` | `columns` = `ward, value`; lineage listed apart | `#r, ward, value` in `columns` |
| TEST-L16b | `identity[mod.select(columns=["#r"])](wf["expanded"])` | refused | works |
| TEST-L17 | `join(wf["expanded"], wf["r"], on="#r")` | 8 rows: `value`, `ward`, `n` | refused: *'r' does not have '#r'* |
| TEST-L18a | `identity[mod.copy(columns={"#r": "parent"})](wf["expanded"])` | data `parent`, `value`; lineage `#r`, `#r.idx` unchanged | no `copy` modifier |
| TEST-L18b | `identity[mod.rename(columns={"#r": "parent"})](wf["expanded"])` | data `parent`; `#r` unchanged; saved as `mod.copy` | `#r` replaced by `parent` |
| TEST-L19 | `add_up[mod.collapse(by="#r")]` over expanded renamed to `n` | `21, 41, 61, 81` | same (keep green) |
| TEST-L45a | `join(wf["filtered"], wf["r"], on="#r")` | 3 rows; `ward`, `n` once; `n` = `20, 30, 40` | refused: neither has `#r` |
| TEST-L45b | `fd = double[mod.map()](wf["filtered"])`; `join(wf["r"], wf["fd"], on="#r", how="left")` | 4 rows; `fd`'s column `absent` on row 0 | refused |

---

## 8. M3 — Column names and output naming

| ID | Change | Overlaps |
|---|---|---|
| L20 | Data names are unique text, never starting with `#` | C7 |
| L21 | Numeric names, and a tool's unnamed parts (a tuple), become `var0`, `var1`, … unless renamed; a clash is refused | C7 |
| L22 | A tool returning a dict gives one column per key | — |
| L23 | Default output name (D2): one value or one column is named after the step; a dict's columns after its keys. Renaming the step renames a column that took its name by default | — |
| L24 | An int column stays int when a value is missing | R8 |
| L46 | A data name that isn't an identifier is kept as written and picked by string (D9) | — |
| L47 | Step names are identifiers: no `.` (D11) | — |

| Test | Formula / check | Expected | Today |
|---|---|---|---|
| TEST-L20 | `identity[mod.rename(columns={"ward": "#x"})](wf["r"])` | refused | refused (keep green) |
| TEST-L21a | a source with data `{"0": [1, 2], "1": [3, 4]}` | columns `var0`, `var1` | `0`, `1` |
| TEST-L21b | a source with columns `0` and `var0` | refused, naming both | accepted |
| TEST-L22 | `pair[mod.map()](wf["r"])` | columns `a`, `b` | one `value` cell holding the dict |
| TEST-L23 | `double[mod.map()](wf["r"])` saved as step `doubled`; then rename the step to `twice` | column `doubled`, then `twice` | `value` |
| TEST-L24 | `join(wf["r"], wf["other"], on="ward", how="left")`: `pop` | int with a missing value | **passes** since 2026-11-02 (R8 fixed for joins) (keep green) |
| TEST-L46 | a source with `Patient ID`, `temp f`; then `wf["p"]["temp f"]` | names kept; `98, 99` | names kept; the pick refused (plain strings aren't columns yet, L25) |
| TEST-L47 | `k["a.b"] = …` | refused | accepted |

---

## 9. M4 — Selection grammar

| ID | Change | Overlaps |
|---|---|---|
| L25 | Plain strings choose columns: `wf["r"]["n"]`, `wf["r"]["ward", "n"]`, `wf["r"][["ward", "n"]]` | C7 (which refused it) |
| L26 | Rows and columns in either order, one bracket or two: `[1:3]["n"]`, `["n"][1:3]`, `[1:3, "n"]` | C7 |
| L27 | Columns by position: `cols[0]`, `cols[0:2]`, counting data columns only | C7 |
| L28 | A list mixing integers and strings is refused | — |
| L29 | Conditions in the row slot: `cols["x"]`, `row["s"]`, `==` `!=` `<` `<=` `>` `>=`, `.isin`, `&` `\|` `~`. Parsed, never evaluated as Python | — |
| L30 | `row["s"]` is the row's placement in `s`: its own `#s`, or its lineage `#s` | — |
| L31 | A condition that matches nothing gives zero rows and a warning naming it; a row number out of range fails (D10) | — |
| L32 | `mod.select(rows=…, cols=…)` takes every row form, including a condition and `slice(a, b)` | K9 |
| L33 | Pickers (`select`, `slice`, `sort`, `distinct`) may stand before a verb in one step, applied to the input in order | — |
| L34 | A pick as a tool's input: `double[mod.map()](wf["r"][0:2])`; lineage points at `r` | C20 |
| L35 | `row`, `rows`, `cols` reserved: no tool, resource or step may use them | C7 |
| L36 | `row["p"].idx` in a condition reads `#p.idx` (D5) | — |
| L48 | A list cell in a condition: `==` is "contains", `.isin` "any item", `!=` is `~(==)`; `<`, `>` refused; every test on an empty cell is false (D11) | — |
| L49 | Two integers in one bracket, `[0, 2]`, are refused, pointing to `[[0, 2]]` (D11) | — |

| Test | Formula | Expected | Today |
|---|---|---|---|
| TEST-L25a | `wf["r"]["n"]` | `10, 20, 30, 40` | refused |
| TEST-L25b | `wf["r"][0:2]["ward", "n"]` | `A 10`, `B 20` | refused |
| TEST-L26 | `wf["r"][1:3]["n"]`, `wf["r"]["n"][1:3]`, `wf["r"][1:3, "n"]`, `wf["r"][rows[1:3], cols["n"]]`, `identity[mod.select(rows=slice(1, 3), cols=["n"])](wf["r"])` | all `20, 30`, all the same saved spec | first two parts work with `cols[…]`; the rest refused |
| TEST-L27 | `wf["r"][cols[1]]` | `n` | **passes** in core (the app's parser refuses it) |
| TEST-L28 | `wf["r"][[0, "n"]]` | refused | passes (keep green) |
| TEST-L29a | `wf["r"][cols["n"] > 15]` | `20, 30, 40` | refused |
| TEST-L29b | `wf["r"][(cols["n"] > 15) & (cols["ward"] == "A")]` | `30` | refused |
| TEST-L29c | `wf["r"][len(cols["n"]) > 1]`, `wf["r"][__import__("os")]` | refused as you type, never run | refused |
| TEST-L30a | `wf["expanded"][row["r"] == 3]` | `40, 41` | refused |
| TEST-L30b | `wf["per_ward"][row["r"] == 0]` | ward A (its `#r` holds 0) | refused |
| TEST-L31 | `wf["r"][cols["n"] > 100]` | `completed`, zero rows, a warning naming `n > 100` | refused |
| TEST-L31b | `wf["r"][9]` (4 rows) | fails | passes (keep green) |
| TEST-L33 | `double[mod.select(rows=cols["n"] > 15), mod.map()](wf["r"])` | `40, 60, 80`; `#r` = `1, 2, 3` | refused: one shape verb per step |
| TEST-L34 | `double[mod.map()](wf["r"][0:2])` | `20, 40`; `#r` = `0, 1` | refused: *a selection can't be a tool's input* |
| TEST-L35 | register a tool named `row` | refused | registered |
| TEST-L36 | `wf["expanded"][row["r"].idx == 1]` | `11, 21, 31, 41` | refused |
| TEST-L48a | `wf["per_ward"][row["r"] != 0]` | wards `B`, `C` | refused |
| TEST-L48b | `wf["per_ward"][row["r"] < 1]` | refused | refused, but for lack of `row` |
| TEST-L49 | `wf["r"][0, 2]` | refused, suggesting `[[0, 2]]` | refused for another reason (*already has its rows*) |

---

## 10. M5 — Arguments, binding and pairing across steps

| ID | Change | Overlaps |
|---|---|---|
| L37 | A column argument from a step **aligned** with the input pairs each row with the same row (aligned = the same rows, in any order: connected only through steps that keep every row) | K19 |
| L38 | A block or whole step as an argument reaches only a `DataFrame` parameter | C7 table |
| L39 | Join variants: `how="left"` (exists), `"right"`, `"outer"`; and a merge. Lineage: one `#<input>` per side, empty where unmatched | — |
| L50 | **Binding at staging** (D6): what the user wrote, else a column with the parameter's name (only for a parameter without a default), else the one column whose type fits, else `invalid` naming the candidates and the fix. What staging decides is **saved in the expression** (`n=wf["doubled"]["doubled"]`), so nothing is guessed again; a binding that breaks later makes the step `invalid` | K19, B7, B8 |
| L51 | Types: only lossless conversions are automatic (`int` → `float`); others are refused, suggesting `mod.cast(column="type")`, which converts before binding; a failed cast fails the cell | — |

| Test | Formula | Expected | Today |
|---|---|---|---|
| TEST-L37 | `add_k[mod.map()](wf["r"], k=wf["doubled"])` | `30, 60, 90, 120` | refused: *join first* |
| TEST-L37b | `add_k[mod.map()](wf["r"], k=wf["sorted_"][0]["n"])` (one cell) | `50, 60, 70, 80` (k = 40, the first row on screen) | `20, 30, 40, 50` (row id 0) |
| TEST-L38 | a tool `(n: int, t: DataFrame)` with `t=wf["other"]` | each call gets the 3-row table | passes (keep green) |
| TEST-L50a | `double[mod.map()](wf["doubled"])` | `40, 80, 120, 160`; saved with `n=` | refused: *needs 'n'* |
| TEST-L50b | `double[mod.map()](wf["two"])`, `two` has int columns `a`, `b` | `invalid` at staging: two int columns, naming both | `invalid`, for a missing name |
| TEST-L50c | `scale(x: int, factor: int = 2)` over columns `x`, `factor` | `2, 4` (the default) | `10, 20` (the column replaced the default: B7) |
| TEST-L51a | `shout[mod.map()](wf["doubled"])` (`s: str`, an int column) | `invalid`, suggesting `mod.cast` | `invalid`, for a missing name |
| TEST-L51b | `shout[mod.cast(doubled="str"), mod.map()](wf["doubled"])` | `"20"`, `"40"`, … | no `mod.cast` |
| TEST-L51c | `half[mod.map()](wf["doubled"])` (`x: float`) | `10.0, 20.0, …` | refused: *needs 'x'* |
| TEST-L39 | `join(wf["r"], wf["other"], on="ward", how="right")` and `"outer"` | 4 and 5 rows; `#r`, `#other` empty where unmatched | passes (keep green). Merge: open. Note: `join` adds `_left` / `_right` suffixes to clashing names by default, against "a clash is refused" (130 M6) |

---

## 11. M6 — Editing in a live session

| ID | Change | Overlaps |
|---|---|---|
| L40 | An edit re-checks every step downstream at once: a step whose bound or picked column disappeared is `invalid`, naming it | — |
| L41 | A pick follows its row after an upstream change (it's saved as lineage); a pick whose row is gone fails, naming it (CA-B1) | — |
| L42 | Each stale step says which upstream step made it stale | — |
| L43 | Renames rewrite references and keep the output; deleting a step that is read is refused, naming the readers, and `k.remove(name, force=True)` deletes anyway, making each reader `invalid` (D11); a move that puts a reader before what it reads is refused | K29 |
| L52 | A rename rewrites everything core wrote: `wf["old"]`, the column named after the step, staging's bindings, `#old` downstream, `row["old"]`. Anything else that breaks is `invalid` with its reason (D11) | K29 |

| Test | Session | Expected | Today |
|---|---|---|---|
| TEST-L40 | run `doubled`; replace `r` with `{"m": [5]}` | `doubled` is `invalid`: *needs 'n'* | `stale`, no problem |
| TEST-L41a | `first = wf["filtered"][0]` (r's row 1, `n` 20); change `r`'s `n` to `[10, 25, 30, 40]`; run | `first` is still r's row 1: `n` 25 | blocked by M1: `[0]` is a row id, and `filtered` has no row 0 |
| TEST-L41b | the same; change `r`'s `n` to `[50, 10, 20, 30]` (r's row 1 is filtered out); run | `first` fails, saying r's row 1 isn't in `filtered` | as L41a |
| TEST-L42 | edit `r`; read `doubled`'s status | `stale`, reason names `r` | `stale` |
| TEST-L43a | rename `r` → `readings` | every `wf["r"]` reads `wf["readings"]`; outputs kept | passes (keep green) |
| TEST-L43b | delete `filtered` while a step reads it | refused naming the reader | passes: *cannot remove 'filtered': 'after' read it* (keep green) |
| TEST-L43d | `k.remove("filtered", force=True)` | removed; `after` is `invalid`, naming `filtered` | no `k.remove` |
| TEST-L52 | rename `r` → `readings`; lineage of `filtered` | `#readings` | no lineage column (lineage isn't shown apart yet, L16) |
| TEST-L43c | move `doubled` before `r` | refused | passes (keep green) |

---

## 12. The script

```bash
python probe.py          # every milestone
python probe.py M0 M2    # some of them
```

[`probe.py`](probe.py), beside this page,
builds the §3 fixture in a plain `Kernel` (no app code) and prints PASS / FAIL
/ SKIP for every test above, with what core did on a FAIL. A milestone is
done when all its tests pass; "keep green" tests must stay passing.

**First run, 2026-11-02:** 16 pass, 49 fail, 1 skip. **After the owner's
answers (same day, core at `11a7ca0`):** 17 pass, 64 fail, 1 skip. **After
the R8 fix for joins (L24):** 18 pass, 63 fail, 1 skip. **After S1, and
CA-B1 amended (L7f, L41a/b):** 24 pass, 60 fail, 1 skip. By milestone, before S1:

| | Pass | Fail | Skip |
|---|---|---|---|
| M0 | 4 (L3b, L3c, L3e, L4) | 5 | — |
| M1 | 1 (L7c) | 9 | — |
| M2 | 3 (L11b, L14c, L19) | 15 | — |
| M3 | 2 (L20, L24) | 6 | — |
| M4 | 3 (L27, L28, L31b) | 15 | 1 (L29c: needs core's formula parser) |
| M5 | 2 (L38, L39) | 8 | — |
| M6 | 3 (L43a, L43b, L43c) | 5 | — |

`scripts/ui_status/status.py` (sections 130 06 and 130 07) shows the same
steps through the app.

## 13. Where each older ask stands

| Older ask | Here |
|---|---|
| C7 (selection notation) | continued by L6–L8, L20–L21, L25–L28; **changed:** plain strings select columns (L25) |
| C20 (selection as input ignored in JSON) | replaced by L34 |
| K9 (select rows and columns) | extended by L32 |
| K19 (column argument by type) | **superseded by L3 and L37** (D1 decided 2026-11-02: the verb decides, not the type) |
| K28 (cell-to-cell lineage) | made concrete by L10–L16 |
| K29 (renames) | L43 |
| K30 (`wf[index]`) | unchanged; not part of this plan |
| R8 (failed rows turn ints to floats) | L24 |
