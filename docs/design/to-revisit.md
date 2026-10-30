# To revisit

> The owner's list of design choices to reconsider in a later update
> (2026-10-29). Nothing here is decided or built: each entry says what core
> does today (each line was run at `adeda02`), why it's a concern, and the
> options. When one is taken up, it becomes a decision in
> [phase4-plan.md](phase4-plan.md) §5 and is confirmed before it lands.

The principles these are judged by (from the review of "several ways to do
the same thing"):

1. many spellings, one saved form;
2. the explicit form is the one that prints back;
3. a shortcut resolves when it is written, never later;
4. things that look alike but differ save differently, and say so;
5. a second way exists only for a different intent or a different surface;
6. a refusal names the one right way;
7. breaking an abstraction is one explicit, visible step.

## V1. `auto`: implicit, and ripe for error

**Owner:** auto selecting the right columns is implicit and invites mistakes.

**Today.** A tool called without a verb is wired as `mod.auto()`, and the
verb and the columns are chosen when it runs:

| Written | Saved and printed as | At run |
|---|---|---|
| `is_hot(wf["p"])` (`-> bool`) | `is_hot[mod.auto()](wf["p"])` | `filter`: *"it returns a bool per row, so keep the rows that pass"* |
| `to_f(wf["p"])` | `to_f[mod.auto()](wf["p"])` | `map`: *"'temp' comes from the input's columns"* |
| `mean(wf["p"])` (`temp: list[float]`) | `mean[mod.auto()](wf["p"])` | `map`, then **invalid**: *"declares temp: list, but 'p' has temp as float64"*. It doesn't infer `collapse` |

Two more implicit things come with it:
- **Columns bind by parameter name.** `label(name, ward)` reads the columns
  `name` and `ward` without saying so; a renamed column quietly stops
  matching (it becomes a problem, not a wrong value).
- **`auto` adds `breaker(after=5)`** to row-wise verbs, which the formula
  doesn't show.

**Why it's a concern.** It breaks principle 3. `infer_verb`'s docstring says
the verb resolves when wired, "never into a stored `auto`", but it is stored,
so two spellings of one step have different specs and ids. The verb can also
change after the step is written, if the input's columns change.

**Options.**
- (a) Resolve when wired: `is_hot(wf["p"])` saves and prints
  `is_hot[mod.filter()](wf["p"])`, with the reason shown once. *(Matches the
  docstring and principle 3.)*
- (b) Keep `auto`, but print what it chose, and the breaker it added.
- (c) Remove the shortcut: every step names its verb.

## V2. Modifiers that take data, or tools

**Owner:** modifiers accepting data to be processed by the tool; tools could
be used instead.

**Today.** Most modifier settings are literals (column names, counts,
flags). These take more:

| Modifier | Setting | Takes |
|---|---|---|
| `map`, others | `over=` | a step: the input, a second way to write `(wf["x"])` |
| `sweep` | each swept setting | lists of values the tool runs on |
| `collapse` | `initial=` | a value, or a reference to another step's cell |
| `try_except` | `default=` | a value written in place of a failure |
| `collapse` | `by=` | a column name, **or a tool** |
| `sort` | `by=` | a column name or list, **or a tool** |
| `select`, `distinct`, `rename` | `columns=` | names, **or a tool** (`columns=lambda c: …`) |

**Why it's a concern.** A modifier is meant to say *how a tool meets the
grid*. When it carries data or code, there are two places a step's inputs can
come from, and a tool inside a setting is a step that has no name, no output
and no lineage of its own (and a lambda can't be saved: such a step has no
id, K20).

**Options.**
- (a) Settings are literals and column names only. Data comes in as the
  tool's arguments or input; a computed key or column choice is its own step
  (a tool), then referenced by name.
- (b) Keep `sweep` (its lists are what it *is*) and `try_except(default=)`
  (a literal), and move the rest: `over=` goes (principle 5: it's the same as
  the call), tools in `by=` / `columns=` become steps.
- (c) Keep all, documented as the exceptions.

## V3. How arguments are passed: a column as a list, a row as a dict

**Owner:** unclear how arguments are passed and treated. Can a column
selection be treated as a list and a row as a dict, so that
`sum(wf["integers"])` works because it *is* a list, not because of `auto`?

**Today.** As an **argument**, a reference is passed by what the parameter
declares, and that already works:

| Argument | Parameter | The tool gets |
|---|---|---|
| `values=wf["p"][cols["temp"]]` | `values: list[float]` | the whole column as a list: `113.9` from one call |
| `row=wf["p"][1]` | `row: dict` | the row as a dict: `{'name': 'Ben', 'temp': 38.2, 'ward': 'A'}` (*but* `temp` arrives as `np.float64`, not `float`) |
| `t=wf["p"]` | `t: pd.DataFrame` | the table |
| `value=wf["p"][cols["temp"]]` | `value: float` | one value per row, paired by row id (K19) |

As the **input** (the first, unnamed reference), it's different: the step
runs once **per row**, and `auto` picks the verb.

| Written | Why it gives what it gives |
|---|---|
| `my_sum(wf["integers"])`, where `k["integers"] = [1, 2, 3]` | **6**, but only because a literal list is *one cell* (rule 1): `auto` → `map` over one row, whose value is the list |
| `my_sum(wf["ie"])`, `ie` = the list expanded into rows | **invalid**: `map` per row, and a row's `value` is an `int`, not a list |
| `my_sum[mod.source()](value=wf["ie"][cols["value"]])` | **6**: the column as an argument is a list |
| `my_sum[mod.collapse()](wf["ie"])` | 6: the explicit reduction |

**The gap.** The same reference means "each row" as the input, and "the
whole thing" as an argument. Nothing in the formula says which; it depends
on position and on the parameter's type.

**Options.**
- (a) Keep the two meanings and say them in the formula: the input is always
  per row under a verb; to hand a tool the whole column, pass it as an
  argument or use `collapse`. `auto` infers `collapse` when the parameter is
  a `list` (fixing the `mean` case in V1).
- (b) One meaning: a reference is a value (a column is a list, a row a dict,
  a table a DataFrame) wherever it appears, and only an explicit verb makes a
  step iterate.
- Also: hand tools plain Python values (`float`, not `np.float64`) in a
  row dict.

## V4. Row ids: integers, and the expand problem

**Owner:** likes rows being integers; the expand case needs a better
understanding.

**Today.** Sources and literals give integer ids `0…n-1` (or the tool's own
index). `expand` gives string ids, one level per expand: `0.1`, `0.2.1`.
Parent: drop the last part; the parent's id is also stored in `#<parent
step>`, which is what core follows. The dotted form keeps ids stable when a
parent's list grows (run: visit 0 gains a reading, every other row keeps its
id).

**Options for expand.**
- (a) Keep `parent.item` strings. Stable, readable, and the only non-integer
  ids; a string id is written `rows["0.1"]`.
- (b) Integers `0…N-1`, renumbered on each run, the parent in `#v`. Plain,
  but one added item renumbers every row after it: picks, lineage and
  per-row staleness point at other rows.
- (c) Integer pairs, `(0, 1)`, as a two-level index. Stable and not a string,
  but every id-taking place (`rows[…]`, `k.cell`, the app) must take tuples.
- (d) A stable integer per row (a hash of parent id and position). Stable,
  integer, unreadable.

## V5. `#` columns in modifiers: keep, and finish

**Owner:** likes index columns being accepted by modifiers such as the
reshapes.

**Today.**

| Works | Refused |
|---|---|
| `collapse(by="#s")`: back to step `s`'s rows | `collapse(by="#")`, `sort(by="#")`, `join(…, on="#")` |
| `select(columns=["#", "name"])`: shown beside the variables | `rename(columns={"#": "row"})`: `#` is the index, not a column |
| `rename(columns={"#p": "visit"})`: a lineage column becomes a variable (drops that trace, rule 8) | |
| `wf["s"][cols["#"]]`: the ids, to look at | |

**Gaps.** Whether `sort(by="#")` (back to the original order) and
`rename(columns={"#": …})` (the row id as data) should work; and one leak:

## Also open

| | | Recommended |
|---|---|---|
| a `#` column as a tool **argument** (`value=wf["p"][cols["#"]]`) | hands raw ids to the tool, breaking "tools see variables only" (principle 7) | refuse, pointing to `rename` |
| `stack` of an ids-only step | runs, and gives rows with nothing in them | refuse |
| a resource with bound tools, also passed to a free tool (R-D1) | both work today | keep both, unless each use should have one way |
| the seed recommendation (C-D2) | — | a tool with `seed` that isn't given warns |
