<!-- from docs/why-we-are-building-this.md -->

## Words and what they mean

Decided by the owner on 2026-10-24. One meaning each, used everywhere: in
the code, the API and the docs.

| Word | Means | Retired words |
|---|---|---|
| **workflow** | a list of steps | *pipeline* |
| **step** | one entry in that list: a name and an expression. **Its position in the list is its id**. A step has several forms (the line you type, the operation it parses to, the saved recipe, the live step with its data). They are different things, but they all point to the same output ([one step, several forms](system_design/12-core-and-app.md#one-step-several-forms)) | — |
| **expression**, or **formula** | what's written in the formula bar: the right-hand side of `wf["name"] = …` in Python. The two words mean the same thing; scientists tend to say *formula*, programmers *expression* | — |
| **tool** | a function from the catalog | — |
| **operation** | what is actually executed: a tool with its modifiers, its arguments, and the data it runs on | *operation* for a plain tool |
| **modifier** | how a tool is applied: a shape verb (`map`, `filter`, …) or an execution modifier (`retry`, …) | — |
| **reference** | `wf["name"]`, or a selection of part of a step's output | `step1.col` |
| **kernel** | the live workflow on the server: every step as if it were a line of Python, run, with its output. **The kernel is the truth** about a workflow; the file is a saved copy of it, and the browser shows it. Its **`kernel.spec`** is the structure needed to reproduce the workflow with a particular set of tools: the workflow spec plus the catalog spec (2026-10-26) | — |
| **session** | an active construction of a workflow in the UI. The user adds steps, runs them, sees the data they produce, passes in new data, and sees what changes. Later it may include the chat with the agent, which will come as a layer on top | *session* for a browser connection |
| **workspace** | the folder the app serves | — |
| **spec** | the saved form of any object: everything needed to produce the same output, assuming what it references holds the same data. It never contains output data. Every object has one: `wf.spec`, `step.spec`, a resource's `ResourceSpec` (what's needed to load the right resource). The line `wf["x"] = …` is a step's spec written as text. Decided 2026-10-26. (`docs/spec/` is a different context: spec-driven development's requirements docs) | *saved step*, *declaration* |
| **status** | what is live about an object: a step's output, state and problems; a resource's loaded instance. A live object is its spec plus its status | — |
| **catalog** | everything a step can use (see [What is acceptable](#what-is-acceptable)) | *registry*, *pack* |


<!-- from docs/why-we-are-building-this.md -->

## What is acceptable

Decided by the owner on 2026-10-23.

**The rule: code enters only one way.** It comes in through the developer's
package, loaded by the maintainer's `app.py` when the server starts.
Everything a user or an agent sends while the app runs is data:
- formulas, in the grammar;
- literal arguments;
- resource settings;
- workflow files;
- the files in the workspace.

**Everything a step can use is in one catalog, fixed when the server
boots.** The catalog is the single list of what exists for this app. It's
used for running steps, for the palette and Environment panel, for checking
formulas, and for the agent. It holds:

| Part of the catalog | Examples | Who defines it |
|---|---|---|
| **System tools** | `identity`, `count`, `to_rows`, `load_csv` | the platform. They're on by default, and the maintainer can remove any of them |
| **Modifiers** | `mod.map()`, `mod.filter()`, `mod.retry()` | core. They're on by default, and the maintainer can remove any of them |
| **Combines** | `join`, `stack`, `zip_` | core. They're on by default, and the maintainer can remove any of them |
| **Literal types** | numbers, strings, lists, dicts, `True`/`None` | standard Python data types; the grammar allows them |
| **Reference forms** | `wf["step"]`, and selections of part of a step | the grammar; the user's manual selections write them |
| **Developer tools and resource types** | whole modules of decorated tools, single tools, `@simple_step_resource` classes | the maintainer's `app.py` |
| **Ready-made resources** | `Loaded(ClinicalDB, url=env("DB_URL"), locked=["url"])` | the maintainer's `app.py` |

Each entry also says **whether the agent may use it**. The default is yes;
the maintainer can withhold any entry. Changing the catalog should take one
line in `app.py`. ("Packs" was the old name for a module of tools. The idea
stays; the word is retired.)

**The workspace is the folder the app serves, for convenience.** It is
where `app.py` sits, or whatever folder the server was started in, or
`App(workspace=…)`. It holds:
- workflows, and their saved sessions;
- the examples the app ships;
- files users load, and files tools write, such as an output folder.

Users may read, load and edit everything there. **It is the maintainer's
responsibility not to expose a folder they don't want seen.** Finding files
in a folder is the job of a **resource** a step uses (like
`image_directory`), not a way of loading tools.

`app.py` is read once, at boot. While the server runs, **nothing in the
workspace is imported as code**, even if it's a `.py` file.

**The UI never executes Python.** All it can run is workflows (steps over the
registered tools) and resources.

| Who | Acceptable | Not acceptable |
|---|---|---|
| **User** | Write and edit formulas within the grammar, including its exceptions. Pass any literal argument. Create resources from the types the app offers, but not change locked settings. Run steps. Read, load and edit workspace files. Save, open and export workflows. Look at any cell. Accept or reject what the agent proposes | Run Python by any route: formula, console, settings, or a file the server imports. Add or change tools. Configure the agent. Change settings that affect other users |
| **Agent** | Read the tools, the resources, the workflow and its data. Propose adding, changing or removing steps, as formulas that have passed the checks | Apply its own changes, run steps, call anything that isn't a registered tool, or see tools the user can't use |
| **Developer** | Write any Python inside their tools and resources. They are trusted code, and they decide what each tool does with any argument | Reach into the server, the sessions or the storage, except through the decorators and `App` |
| **Maintainer** | Choose the libraries, the resource types, the ready-made resources with locked settings, the agent (model, temperature, prompt), where data is stored, and who can reach the server. All of it lives in `app.py` | — |

Decisions behind the table:

- **No eval mode.** No runtime path runs Python a user typed. The console
  stays, limited to calls to registered tools.
- **Tools come only from the catalog,** fixed at boot: the system set,
  minus whatever the maintainer removes, plus `App(tools=…)`. There is no
  loading tools from the workspace or from project folders while the server
  runs.
- **The workspace is chosen at boot**: `app.py`'s folder, the start-up
  folder, or `App(workspace=…)`. Exposing only what should be seen is the
  maintainer's job.
- **Users, groups and sessions will be completely isolated.** This isn't
  built yet, and building it is deployment work for the maintainer (for
  example, an extension that gives each user their own workspace). New code
  should assume it is coming: nothing global that should be per user or per
  session.
- **The agent is configured by the maintainer only, in `app.py`.** Users can
  see which model is in use, but not change it or the prompt.
- **Any argument is acceptable; what a tool does with it is the
  developer's responsibility.** The platform guarantees *which* code runs,
  not what that code does. For example, `list_files(folder)` can read any
  folder the server can. The maintainer's only lever is locking resource
  settings. A tool that should only see certain folders is written that way.


<!-- from docs/how-simple-steps-works.md -->

### The step expression: the general form and its exceptions

The general form is **`tool[modifiers](input, arguments)`**:

```
=with_tax[mod.map(name="total"), mod.retry(times=2)](wf["items"], rate=0.1)
 tool     one shape verb, then execution modifiers    input       arguments
```

| Part | Allowed |
|---|---|
| tool | a registered tool's name, `identity`, or a resource's method: `res["db"].lookup` |
| modifiers | at most one **shape verb**, plus any **execution modifiers** after it |
| input | at most one `wf["step"]`, naming an **earlier** step |
| arguments | literals only (`1`, `"a"`, `[1, 2]`, `{"k": "v"}`, `True`), or `res["name"]` |

The shape verbs are `source`, `map`, `filter`, `expand`, `collapse`, `group`,
`table`, `sweep` and `widen`. The verbs that run no tool are `select`,
`drop`, `rename`, `sort`, `slice` and `distinct`. The execution modifiers are
`retry`, `timeout` and `try_except`.

**The exceptions to the general form,** as the parser accepts them today:

| Exception | Example | Why it exists |
|---|---|---|
| No brackets: the verb is inferred | `=scale(wf["readings"])` | `-> bool` filters, `(acc, x)` collapses, `-> list` expands, anything else maps |
| No input: a source | `=to_rows[mod.source()](data='…')` | the first step makes a table from nothing |
| No input: a sweep | `=grid_cell[mod.sweep(model=["a","b"])]` | runs every combination of the settings |
| A bare literal | `=[3, 1, 2]`, `=7`, `={"x": 1}` | a one-cell source |
| `identity` as the tool | `=identity[mod.sort(by="n")](wf["x"])` | verbs that reshape without computing |
| Built-in reducers | `=count[mod.collapse()](wf["x"])` | `count`, `total`, `gather`, `first`, `last` |
| **Combines**, the only way to read several steps | `=join(wf["a"], wf["b"], on="city")`, `stack`, `zip_` | a normal step reads one input |
| A resource's method as the tool | `=res["sale"].sale_price[mod.map()](wf["items"])` | tools that live on a resource |
| `mod.auto()` | `=scale[mod.auto()](wf["x"])` | re-infer the verb on every run |

**What a formula can't contain today, and why.** Core was run on
2026-10-24 to check each of these (a probe on `simple-steps-core` `86170a3`).
Only one restriction is fundamental. The others are either a security
boundary or the app's parser lagging behind core.

| Restriction | Where it becomes a problem | Core (run) | Verdict |
|---|---|---|---|
| **A reference to a later step** | Steps run in order, so a later step has no output yet when this one runs. Allowing it would also allow cycles | refuses: "input 'later' comes after 's'; a step can only read earlier steps" | **Never.** Fundamental |
| **Part of a step**: rows, a column, or a cell. Core writes these as `wf["r"][0:2]`, `wf["r"][cols["n"]]` and `wf["r"][0][cols["w"]]` | Only in being stable: a position picks *whatever is now at that position*. After a re-sort, `wf["srt"][0]` picked a different row. That breaks "keeps pointing at the same data when it shifts" | **supports it**, as its own step (`wf["part"] = wf["r"][0:2]`) and as an argument (`weight=wf["r"][0][cols["w"]]`). As a tool's *input* it's refused: "make it its own step" | **Allowed (C1).** The app's parser refuses it today, so the gap is ours, not core's. **Decided (2026-10-25):** a selection picks rows by their id, and the id is the frame's index (the default index unless a tool sets one), so it follows the row through a sort. The owner is updating core for this ([008 K19](core-proposals/008-core-changes.md#k19-a-column-argument-pairs-per-row-by-type)) |
| **A whole column as an argument** (`weight=wf["r"][cols["w"]]`) | Should pair row *i* with row *i*: the tool runs on cells, and the parameter's type says how to feed it. An `int` parameter given a column gets one value per row; a `list` parameter gets the whole column | Doesn't do this today. Untyped, every row gets the whole list (`n * [10, 20, 30]` repeats the list). Typed `int`, it refuses with "join first", and the output is `None`. The working route is two steps: `zip_(wf["r"], wf["w"])`, then the tool | **Decided (2026-10-25): per-row by type.** Needs core: [008 K19](core-proposals/008-core-changes.md#k19-a-column-argument-pairs-per-row-by-type). Rows pair by their index (the row id), not by position, so a sort upstream doesn't mispair them. The owner is updating core |
| **A step as a modifier setting** (`mod.sort(by=wf["r"])`) | Modifier settings decide the output's *shape*. If they depend on data, a step's shape can't be known before it runs: no preview, no staging, and harder staleness | the form is accepted, but the value is type-checked: "by= … holds DataFrame; it must be str or list" | Possible later, if a selection yields the right type (a cell holding a column name). Not needed now |
| **A computed argument** (`weight=len("abc")`, `name=str.upper("ada")`) | In a Python script, Python works it out before core sees it, so it's harmless there. In the **formula bar**, working it out means *running code*: `str.upper` and `os.remove` have the same shape. This is the "UI never executes Python" boundary | fine in Python (core receives `3`) | **Not in the formula bar,** except for what the catalog provides. If something is worth computing, it should be a catalog tool, so its result is a step you can see |
| **A name that isn't `wf`, `res`, `mod`, a tool or `cols`** (`pd`, `np`, `math.pi`, `len`) | Each name is a door to code: `pd.read_csv` reads any file | — | The rule is really **"only names in the catalog"**. A constant or a safe function the maintainer wants becomes a catalog entry, not a hole in the grammar |

**Two forms are still accepted, but neither is an exception.** They are the
old syntax, `=ss_map(fn="op", url=step1.url)` and `=op(x=step2.col)`, and eval
mode's raw Python.

---
