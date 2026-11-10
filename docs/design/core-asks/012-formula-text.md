# 012 — The app's asks of core at `fed4d1a` (v1.0.1)

> **For simple-steps-core.** From the Simple Steps app, 2026-11-09, while
> planning to replace the app's formula parser with core's `formula(text)`
> (the app's `docs/dev_plan/core_migration.md` §6). Every result was produced
> by running core alone at `fed4d1a`: `formula(text)`, then the step assigned
> in a `Kernel` with a tool `dbl(n: int) -> int`, steps `s` (`n`, `city`) and
> `t` (`n`), and a resource `db`. The full side-by-side of 56 cases is the
> app's `docs/dev_plan/core_migration_L1_messages.md`; case numbers below are
> its numbers.
>
> **Re-run in core, 2026-11-09, at `fed4d1a`** (the work is step S12 of
> [../plan.md](../plan.md)). Where core's run differs from the app's:
>
> | # | The app saw | Core's run |
> |---|---|---|
> | C42.20 | assign: (empty message) | **hangs**: `checks.check` runs `list(on)` on a `StepRef`; with no `__iter__`, Python iterates `wf["s"][0]`, `[1]`, … forever (100 s at full CPU, stopped). Priority 1. **Fixed 2026-11-09**: a step reference isn't iterable, and `join(on=wf[…])` / `on=res[…]` are refused with #19 and #20's proposed text |
> | C41 | reading `step.formula` raises `PayloadError` | `step.formula` prints `mod.sort(by=<Operation n>)(wf["s"])`: no crash, still wrong |
> | C42.38 | assign: `'ResRef' object is not iterable` | accepted, printed `mod.sort(by=res["db"])(wf["s"])`: accepted wrongly (C43's kind) |
> | C40 | — | confirmed: the Python form saves as `summarize[mod.map()](wf["s"], llm=res["db"])`; the same text is refused by `formula()`. **Fixed 2026-11-09**: the text saves the same step |
>
> C42.7, C42.19, C42.21 and C43.6, 9, 15 reproduce as written. C44 and
> C39/C36 not re-run yet.

## Summary

| # | Ask | Kind | Priority |
|---|---|---|---|
| **C40** | `formula()` accepts a resource passed by position, as the Python API does | refuses valid text | **1** |
| **C41** | `formula()` turns an unquoted setting (`mod.sort(by=n)`) into a tool, and printing or saving the step raises | wrong, silently, then a crash | **1** |
| **C42** | Five refusals are raw Python errors or empty | crash text | **1** |
| **C43** | Three formulas that can't run are accepted | accepted wrongly | 2 |
| **C44** | Twenty-five refusals that are right but say less than they could | wording | 2 |
| C39, C36 | A source's, a literal's and the empty step's column is still `value`; `map`'s `name` still defaults to `'value'` | consistency (D9) | 3 |

What the app does meanwhile: it takes core's wording everywhere (C44 is not
shimmed), and keeps two shims, tagged `SHIM(core §C40)` and
`SHIM(core §C41)`, until those land.

---

## C40. A resource passed by position

**Run:** a tool `summarize(text: str, llm: LLM)`, a resource `tiny` of type `LLM`.

- Python: `k["p"] = summarize[mod.map()](wf["s"], res["tiny"])` is accepted and saved as
  `summarize[mod.map()](wf["s"], llm=res["tiny"])`.
- `formula('summarize[mod.map()](wf["s"], res["tiny"])')` raises *"a tool's input in a
  formula is a step or a pick, wf["…"]; values go in as name=value"*.

**Why it matters:** the app's shipped examples write this (`tiny_summaries`),
and the same line means one thing in Python and is refused as formula text.
**Ask:** read a positional `res["…"]` after the input the way the Python API
binds it.

## C41. An unquoted setting

**Run:** `formula('identity[mod.sort(by=n)](wf["s"])')`, assigned.

**Got:** no problem when assigned; `by` holds `op("n")`, and reading
`step.formula` raises `PayloadError: cannot save <Operation n>: a function is
saved by its tool id, so register it with @tool`.

**Ask:** refuse it while reading, as the app did: *"mod.sort(by=n): text needs
quotes, \"n\""*. A bare name in a setting is never a tool unless the setting
takes one.

## C42. Raw errors

| # | Formula | Core says | Proposed |
|---|---|---|---|
| 7 | `res["db"]` | assign: res['db'].data_version has no instance until the workflow runs. Wire it into a step: wf[...] = res['db'].data_version[mod.map()](wf[...]). | res["db"] on its own is a resource, not a step. Use one of its tools, res["db"].<tool>(…), or pass it to a tool |
| 19 | `join(wf["s"], wf["t"], on=res["db"])` | assign: 'ResRef' object is not iterable | join applies no tool, so it takes no resource |
| 20 | `join(wf["s"], wf["t"], on=wf["s"])` | assign: (empty message) | join(on=…) is a setting, and settings are literals. The steps it combines go first, as wf["…"] |
| 21 | `join(wf["s"], wf["t"], on=n)` | assign: a bracket layer must be a Modifier — mod.map(), mod.retry(times=...); got int. Modifiers are data; a plain decorator would not serialize. | join(on=n): text needs quotes, "n" |
| 38 | `identity[mod.sort(by=res["db"])](wf["s"])` | assign: 'ResRef' object is not iterable | mod.sort(by=…) is a setting, and settings are literals. A resource goes in the call: tool[…](wf["…"], name=res["…"]) |

## C43. Accepted, but can't run

| # | Formula | Core | Proposed |
|---|---|---|---|
| 6 | `res["db"].lookup[mod.map()]` | accepted | refuse: *map reads a step: res["db"].lookup[mod.map()](wf["…"])* |
| 9 | `dbl[mod.map()]` | accepted | refuse: *map reads a step: dbl[mod.map()](wf["…"])* |
| 15 | `dbl[mod.source()](wf["s"])` | accepted | refuse: *source takes no input: dbl[mod.source()](…)* |

If an unwired operation is meant to be assignable (a step to wire later),
say so in the plan and the app drops these.

## C44. Wording

Core refuses each of these rightly. The proposal is the app's own message,
which says what was probably meant and how to write it; several of core's
leak internals (`binop`, `got Modifier`, `<Operation s>`). Where the app's
text names the app or is out of date, the proposal is adjusted (1, 27, 32).

| # | Formula | Core says | Proposed |
|---|---|---|---|
| 1 | `res["db"] = DB(url="x")` | formula(): not a formula: invalid syntax | a step can use a resource but not create one; declare it in the workflow: k.define("db", DB, …) |
| 3 | `res["db"][mod.map()](wf["s"])` | formula(): res['db'] can't take […] in a formula | res['db'] is not a tool name |
| 4 | `wf["s"][mod.map()](wf["t"])` | formula(): rows are selected by row id, a list of row ids or a range of positions; got Modifier | wf['s'] is not a tool name |
| 5 | `os.system(wf["s"])` | formula(): os.system: a formula reads only mod.<modifier>, res[…].<tool>, .isin and .idx | os.system is not a tool |
| 10 | `1 + 2` | formula(): 1 + 2: a binop isn't allowed in a formula | expected tool[mod.verb(…)](wf["…"], …) — a tool, its modifiers in brackets, and a call with the step it reads |
| 12 | `dbl[mod.map()](wf["s"], wf["t"])` | formula(): dbl[mod.map()](wf['s'], wf['t']): dbl: pass these arguments by keyword — its parameters are not known here | a step reads one input; to combine steps use join(wf["a"], wf["b"], on=…), stack(wf["a"], wf["b"]) or zip_(wf["a"], wf["b"]) |
| 13 | `dbl[mod.map()](wf["s"], 3)` | formula(): dbl[mod.map()](wf['s'], 3): a tool's input in a formula is a step or a pick, wf["…"]; values go in as name=value | after the input, only resources go by position (res["…"]); give 3 a name: dbl(…, name=3) |
| 16 | `join()` | formula(): join(): join() missing 2 required positional arguments: 'left' and 'right' | join reads steps: join(wf["a"], wf["b"], …) |
| 18 | `join(wf["s"], "n")` | join needs on= — the key column(s) to merge on; input 2 'n', which is not an earlier step | join combines steps; each positional argument is wf["…"], not 'n'. Settings go by keyword, e.g. on="city" |
| 22 | `join(wf["s"], wf["t"], on=str(1))` | formula(): str(1): a tool's input in a formula is a step or a pick, wf["…"]; values go in as name=value | join(on=…) must be a literal, not str(1) |
| 23 | `dbl[map()](wf["s"])` | formula(): map(): map: pass the data to apply it to, or a step reference to wire it | map() isn't a modifier; write mod.map(…), mod.select(…), mod.retry(…), … |
| 27 | `dbl[mod.map()](dbl[mod.map()](wf["s"]))` | formula(): dbl[mod.map()](dbl[mod.map()](wf['s'])): a tool's input in a formula is a step or a pick, wf["…"]; values go in as name=value | an operation can't be an input; make it its own step and pass wf["…"] |
| 28 | `dbl[mod.map()](s)` | formula(): dbl[mod.map()](s): a tool's input in a formula is a step or a pick, wf["…"]; values go in as name=value | s is not defined. To use the step "s", write wf["s"] |
| 29 | `dbl[mod.map()]("s")` | formula(): dbl[mod.map()]('s'): a tool's input in a formula is a step or a pick, wf["…"]; values go in as name=value | the input must be a step reference; "s" is a string. Did you mean wf["s"]? |
| 30 | `dbl[mod.map()](3)` | formula(): dbl[mod.map()](3): a tool's input in a formula is a step or a pick, wf["…"]; values go in as name=value | the input must be a step reference, wf["…"], not 3 |
| 31 | `dbl[mod.map()](wf["s"], n=str(1))` | formula(): str(1): a tool's input in a formula is a step or a pick, wf["…"]; values go in as name=value | n: an operation can't be an argument; make it its own step and pass wf["…"] |
| 32 | `dbl[mod.map()](wf["s"], n=x)` | n: an Operation isn't a literal; a function belongs in a setting that takes a tool, as a registered @tool, or make it a step | n=x: x is not defined. A step is wf["x"]; text is "x" |
| 33 | `dbl[mod.map()](wf["s"], n=1+x)` | formula(): 1 + x: a binop isn't allowed in a formula | n must be a literal (text, a number, a list, …) or wf["…"], not 1 + x |
| 37 | `dbl[mod.sort(by="n")](wf["s"])` | sort applies no tool; use map to compute | sort applies no tool, so it runs on identity: identity[mod.sort(by='n')](wf["…"]). To compute with dbl, use map: dbl[mod.map()](wf["…"]) |
| 39 | `identity[mod.sort(by=wf["s"])](wf["s"])` | sort's by= reads 's', which holds DataFrame; it must be str or list or tuple | mod.sort(by=…) is a setting, and settings are literals. A step reference goes in the call |
| 41 | `identity[mod.sort(by=str(1))](wf["s"])` | formula(): str(1): a tool's input in a formula is a step or a pick, wf["…"]; values go in as name=value | mod.sort(by=…) must be a literal, not str(1) |
| 48 | `wf["s"][1.5]` | formula(): rows are selected by row id, a list of row ids or a range of positions; got float | wf["s"][…] takes rows ([1], [[0, 2]], [1:3], rows["0.1"]) or columns (cols["n"]) |
| 49 | `dbl[mod.map()](wf[s])` | formula(): 'a step reference takes a step id (a string), got <Operation s>' | wf[…] takes a step name in quotes: wf["readings"] |
| 50 | `dbl[mod.map()](wf["s"], db=res[db])` | formula(): 'a resource name must be an identifier, got <Operation db>' | res[…] takes a resource name in quotes: res["db"] |
| 51 | `wf[mod.map()](wf["s"])` | formula(): 'a step reference takes a step id (a string), got map()' | wf[…] takes a step name in quotes: wf["readings"] |

## C39, C36

In the app's `008-core-changes.md`, section *At core v1.0.1*: a source's, a
literal's and the empty step's one column is `value` while every other
verb's takes the step's name (D9); `describe()` gives `map`'s `name` a default
of `'value'`.
