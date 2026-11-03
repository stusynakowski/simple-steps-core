# Capabilities

> Every capability the tutorial checks, with its expression, what it should
> do, and its status. Run 2026-11-03 at `2bd150e` by
> `.venv/bin/python tutorial/tutorial.py`: **89 ✓ · 17 ✗ · 3 ?**.
> ✓ does what we want · ✗ doesn't yet · ? not decided. The reasoning is in
> [README.md](README.md).
>
> Example data `v`: Ada (ward A, 37.0), Ben (B, 38.5), Cy (A, 36.9).

## Kernel and catalog

| # | Capability | Expression | Should do | Status | Notes |
|---|---|---|---|---|---|
| K1 | Catalog only | `to_f[mod.map()](wf["v"])` with `to_f` not in the catalog | `invalid`; never runs | ✓ | |
| K2 | Earlier steps only | `to_f[mod.map()](wf["later"])` | `invalid`: not an earlier step | ✓ | |

## Data in

| # | Capability | Expression | Should do | Status | Notes |
|---|---|---|---|---|---|
| D1 | Source tool | `k["v"] = patients[mod.source()]()` | its DataFrame becomes the rows | ✓ | |
| D2 | Literal | `k["lim"] = 38.0` | one cell; `completed` at once | ✓ | works as a control |
| D3 | List | `k["lst"] = [1, 2, 3]` | **one cell**, until a verb unpacks it | ✓ | never becomes rows by itself |
| D4 | Dict | `k["dct"] = {"x": 1, "y": 2}` | one cell | ✓ | |
| D5 | DataFrame | `k["df"] = pd.DataFrame(…)` | its rows | ✓ | |
| D6 | Empty step | `k["e"] = None` | 1×1 `"empty"`, `staged` | ✓ | |
| D7 | Reading an empty step | `to_f[mod.map()](wf["e"])` | `invalid`: give it an expression | ✓ | |
| D8 | Sweep | `label[mod.sweep(a=[1, 2], b=["x", "y"])]()` | one row per combination | ✓ | |
| D9 | Resource | `k.define("lab", Lab, scale=2.0)`; `res["lab"].adjust[mod.map()](wf["v"])` | a live object's method used per row | ✓ | |
| D10 | Resource change | `k.define("lab", Lab, scale=3.0)` | its readers go `stale` | ✓ | |
| D11 | A bare function | `k["fn"] = lambda temp: temp` | — | ? | stored as a value. Refuse it, pointing to `@tool`? |

## Picks

| # | Capability | Expression | Should do | Status | Notes |
|---|---|---|---|---|---|
| P1 | Row number | `wf["v"][1]` | Ben | ✓ | |
| P2 | From the end | `wf["v"][-1]` | Cy | ✓ | |
| P3 | Several rows | `wf["v"][[0, 2]]` | Ada, Cy | ✓ | double brackets |
| P4 | Range | `wf["v"][1:3]` | Ben, Cy | ✓ | |
| P5 | Out of range | `wf["v"][7]` | `invalid`: "has 3: 0–2" | ✓ | |
| P6 | Condition on data | `wf["v"][cols["temp"] > 37]` | Ben | ✓ | |
| P7 | Condition matching nothing | `wf["v"][cols["temp"] > 99]` | zero rows and a warning | ✓ | |
| P8 | Rows that must exist | `wf["v"][rows[cols["temp"] > 99]]` | `invalid`: the row is gone | ✓ | `rows[…]` is strict, a plain `[…]` filters |
| P9 | Condition on lineage | `wf["e"][row["v"] == 1]` | the rows that came from Ben | ✓ | |
| P9b | …with no position warning | same | no warning | ✗ | **new:** warns the rows "are positions"; they're lineage |
| P10 | Column | `wf["v"][cols["temp"]]` | the `temp` column | ✓ | |
| P11 | Column by string | `wf["v"]["temp"]` | the `temp` column | ✗ | refused: read as a row. Planned S3 (D2) |
| P12 | One cell | `wf["v"][1][cols["temp"]]` | 38.5 | ✓ | |
| P13 | Picking lineage | `wf["h"][cols["#v"]]` | refused, writing `mod.copy(…)` | ✓ | |
| P14 | A pick follows its row | `wf["srt"][1]`, then re-sort | still Ada; saved as `rows[row["v"] == 0]` | ✓ | |
| P15 | A pick into a source whose data is replaced | `wf["src"][0]`, then a row inserted at the top | still Ada | ✗ | **silent wrong answer:** gives Zed, `completed`, no warning. D-picks |
| P16 | A pick as a tool's input | `to_f[mod.map()](wf["v"][cols["temp"] > 37])` | runs on those rows | ✗ | refused: make the pick its own step. Planned S3 (D6) |

## Verbs

| # | Capability | Expression | Should do | Status | Notes |
|---|---|---|---|---|---|
| V1 | `map` | `to_f[mod.map()](wf["v"])` | one value per row | ✓ | |
| V1b | Output column name | same | column named `f`, after its step | ✗ | named `value`. Planned S4 (D9) |
| V2 | `filter` | `hot[mod.filter()](wf["v"])` | the rows the test approves, all their columns | ✓ | |
| V3 | `expand` | `two[mod.expand()](wf["v"])` | one row per item; lineage `#v`, `#v.idx` | ✓ | |
| V4 | `collapse(by=)` | `mean_t[mod.collapse(by="ward")](wf["v"])` | one row per ward, the key kept; `#v` lists the members | ✓ | |
| V5 | Accumulator | `add[mod.collapse(initial=0.0)](wf["v"])` | 112.4 | ✓ | the tool's first parameter is `acc` |
| V6 | `group` | `first_letter[mod.group()](wf["v"])` | adds a key column; rows unchanged | ✓ | |
| V7 | `table` | `describe[mod.table()](wf["v"])` | the whole grid to one call | ✓ | its rows don't trace back to the input |
| V8 | Inferred verb | `to_f(wf["v"])` | `map` | ✓ | |
| V8b | Inferred verb, `-> bool` | `hot(wf["v"])` | a map of bools: never drops rows | ✗ | **inferred as `filter`, so rows drop.** D20b decided otherwise, not built |
| V9 | One verb per step | `to_f[mod.map(), mod.filter()](…)` | `invalid` | ✓ | |
| V10 | A setting that does nothing | `to_f[mod.map(axis="columns")](…)` | refused | ✗ | **new:** accepted and ignored |
| V11 | `map(where=)` | `to_f[mod.map(where=cols["temp"] > 37)](…)` | — | ? | takes a tool, not a condition. Keep it? It overlaps `filter` + `join` |

## Reshapes (no tool)

| # | Capability | Expression | Should do | Status | Notes |
|---|---|---|---|---|---|
| R1 | `select` | `mod.select(columns=["name"])(wf["v"])` | only `name` | ✓ | |
| R2 | `drop` | `mod.drop(columns=["ward"])(wf["v"])` | `name`, `temp` | ✓ | |
| R3 | `rename` | `mod.rename(columns={"temp": "t"})(wf["v"])` | `temp` → `t` | ✓ | |
| R4 | `copy` lineage | `mod.copy(columns={"#v": "parent"})(wf["h"])` | lineage as data | ✓ | the only way to use lineage as data |
| R5 | `sort` | `mod.sort(by="temp")(wf["v"])` | Cy, Ada, Ben | ✓ | |
| R6 | `slice` | `mod.slice(stop=2)(wf["v"])` | Ada, Ben | ✓ | |
| R7 | `distinct` | `mod.distinct(columns=["ward"])(wf["v"])` | A, B; `#v` lists the duplicates | ✓ | |
| R8 | `pack` | `op("identity")[mod.pack(columns=["name", "temp"]), mod.name("rec")](wf["v"])` | one dict per row | ✓ | |
| R9 | `widen` | `mod.widen(column="rec")(wf["p"])` | the dict back into columns | ✓ | |
| R10 | `expand`, no tool | `mod.expand()(wf["lst"])` | a list cell into rows | ✓ | |
| R11 | A step where a setting belongs | `mod.widen(wf["i"])` | refused | ✗ | **new:** accepted; the step fails with `None` |
| R12 | A retired setting | `mod.pack(columns=[…], name="rec")` | refused, naming `mod.name` | ✓ | |

## Built-in tools

| # | Capability | Expression | Should do | Status | Notes |
|---|---|---|---|---|---|
| B1 | `count` | `op("count")[mod.collapse(by="ward")](wf["v"])` | 2, 1 | ✓ | |
| B2 | `total` | `op("total")[mod.collapse()](wf["t"])` | 112.4 | ✓ | the column keeps its name (`temp`) |
| B3 | `gather` | `op("gather")[mod.collapse(by="ward")](wf["v"])` | each group's values as lists | ✓ | |
| B4 | `first` | `op("first")[…]` | Ada, Ben | ✓ | |
| B5 | `last` | `op("last")[…]` | Cy, Ben | ✓ | |

## Arguments and binding

| # | Capability | Expression | Should do | Status | Notes |
|---|---|---|---|---|---|
| A1 | Bind by name | `to_f[mod.map()](wf["v"])` | `temp` → `temp` | ✓ | |
| A2 | A step's value | `hot[mod.filter()](wf["v"], limit=wf["lim"])` | one value for every row | ✓ | |
| A3 | A cell pick | `limit=wf["v"][0][cols["temp"]]` | one value for every row | ✓ | |
| A4 | Aligned column | `limit=wf["srt"][cols["temp"]]` | row with row, by identity | ✓ | |
| A4b | …a filter keeps its columns | same | `name`, `ward`, `temp` | ✗ | **new:** adds `limit` as a column |
| A5 | Column from a subset | `limit=wf["h"][cols["temp"]]` | refused, writing the join | ✓ | |
| A6 | Parent's column into its child | `to_f[mod.map()](wf["e"], temp=wf["v"][cols["temp"]])` | refused, writing the join | ✓ | D-child: keep the refusal |
| A7 | Unknown argument | `to_f[mod.map()](wf["v"], nope=1)` | names what it accepts: `temp` | ✗ | **new:** says "accepts (none)" |
| A8 | No matching column | `add_xy[mod.map()](wf["xy"])` | `invalid`, writing `a=wf[…][cols["x"]]` | ✗ | names the gap, not the fix. Planned S3 |
| A9 | Binding written out | `add_xy[…](wf["xy"], a=wf["xy"][cols["x"]], b=…)` | 3 | ✓ | |
| A10 | `map` after `map` | `to_f[mod.map()](wf["f2"])` | runs | ✗ | **most common friction:** the column is `value`, not `temp`. S3 + S4 |

## Combines

| # | Capability | Expression | Should do | Status | Notes |
|---|---|---|---|---|---|
| C1 | `zip_` | `zip_(wf["v"], wf["f"])` | each row beside its own result | ✓ | |
| C2 | `zip_` after a sort | `zip_(wf["v"], wf["fs"])` | pairs by identity, not position | ✓ | |
| C3 | `zip_` of a subset | `zip_(wf["v"], wf["h"])` | refused, writing the join | ✓ | |
| C4 | `zip_` of unrelated steps | `zip_(wf["v"], wf["n"])` | refused | ✓ | equal size isn't enough |
| C5 | Vouching | `zip_(wf["v"], wf["n"], match_ids=True)` | pairs by id | ✓ | the id sets must be equal |
| C6 | `join` on a value | `join(wf["v"], wf["df"], on="name", how="left")` | VLOOKUP; gaps `absent` | ✓ | |
| C7 | `join` on lineage | `join(wf["e"], wf["v"], on="#v")` | each child beside its parent | ✓ | |
| C8 | Group `join` | `join(wf["c"], wf["v"], on="#v")` | refused, writing the unpack | ✓ | |
| C9 | Unpack a group | `mod.expand(columns=["#v"])(wf["c"])` | one row per member | ✓ | |
| C10 | `stack` | `stack(wf["v"], wf["df"])` | rows one after another; gaps `absent` | ✓ | |
| C11 | Inline input | `zip_(wf["v"], to_f[mod.map()](wf["srt"]))` | — | ? | `invalid`. Must every input be a named step? |

## Wrappers

| # | Capability | Expression | Should do | Status | Notes |
|---|---|---|---|---|---|
| W1 | Failure per cell | `flaky[mod.map()](wf["v"])` | Ben's cell `failed`; the rest run | ✓ | |
| W2 | `run_all` stops | same, then `k.run_all()` | stops, naming `try_except` | ✓ | |
| W3 | `try_except` | `flaky[mod.map(), mod.try_except()](…)` | a `failed` cell; `run_all` goes on | ✓ | |
| W4 | `try_except(default=)` | `mod.try_except(default=-1.0)` | the default, and a warning | ✓ | |
| W5 | `breaker` | `mod.breaker(after=1)` | after one failure, the rest `blocked` | ✓ | |
| W6 | `retry`, `timeout` | `mod.retry(times=2), mod.timeout(seconds=2)` | wraps each call | ✓ | applied in the order written |
| W7 | `expect` kept | `two[mod.expand(), mod.expect(rows=6)](…)` | `completed` | ✓ | |
| W8 | `expect` broken | `mod.expect(rows=5)` | `failed`, loudly | ✓ | |

## Plans

| # | Capability | Expression | Should do | Status | Notes |
|---|---|---|---|---|---|
| L1 | Exact rows | a `map`, before it runs | rows `exact` | ✓ | |
| L2 | Unknown rows | an `expand`, before it runs | rows `unknown`, saying why | ✓ | |

## The session

| # | Capability | Do | Should do | Status | Notes |
|---|---|---|---|---|---|
| S1 | Declaring runs nothing | `k["f"] = …` | `staged` | ✓ | |
| S2 | The same value again | `k["lim"] = 38.0` twice | nothing goes `stale` | ✓ | |
| S3 | A change | `k["lim"] = 37.0` | readers `stale`, keeping their values | ✓ | |
| S4 | Why it's stale | `k.step("h").warnings` | the reason, among the warnings | ✗ | only in `needs_run()` and metadata. SS7 |
| S5 | Run one step | `k.run("f")`, `h` stale | runs `h` first | ✗ | `f` computed from old rows and shown `completed`; a warning names `h` and its version. SM |
| S6 | A value put back | 37 → 38 → 37 | `completed`, no re-run | ✓ | |
| S7 | An expression put back | change `f`, then restore it | `completed`, no re-run | ✗ | stays `stale`. SM |
| S8 | Column removed upstream | drop `temp` from `w` | `invalid`, keeping its last values | ✗ | values dropped. SM |
| S9 | Column put back | restore `temp` | `completed`, no re-run | ✗ | `staged`: must re-run. SM |
| S10 | Delete a step that's read | `del k["h"]` | refused, naming the reader | ✓ | no delete-anyway yet (SS7) |
| S11 | Rename | `k.rename("lim", "limit")` | rewrites every reference | ✓ | |
| S12 | Move | `k.move("f", 0)` | refused: `f` reads `h` | ✓ | |
| S13 | Check a proposal | `k.check("zz", …)` | its problems, nothing added | ✓ | |

## Save, load, provenance

| # | Capability | Do | Should do | Status | Notes |
|---|---|---|---|---|---|
| Y1 | Load | `Kernel.from_json(text, CATALOG)` | runs nothing; all `staged` | ✓ | |
| Y2 | Same result | load, then `run_all()` | same data, same id | ✓ | |
| Y3 | Extras | `step.extras["simple_steps.ui"]` | survive; never hashed | ✓ | |
| Y4 | Where a cell came from | `k.cell("f", 1)` | its inputs: `temp` 38.5 | ✓ | |

## Watch out for

- **Wrong answers:** P15 (a pick into a replaced source) is silent. S5 (running one step on a stale input) is `completed` with a warning naming the stale input.
- **Three spellings for one reshape:** `mod.sort(by=…)(wf[…])`, `op("identity")[mod.sort(by=…)](wf[…])` and `mod.sort(over=wf[…], by=…)` all work. Pick one (F7).
- **Inputs must be named steps:** a pick (P16) or an inline expression (C11) can't be an input yet.
- **Output columns are called `value`,** so chaining verbs needs a `mod.name` or a written binding (V1b, A10).
