# Saving and loading a session

> **Draft, 2026-11-16, for the owner. Layers 1 and 2 built the same day**
> (`k.save(folder, outputs=True)`, `Kernel.load`, `saving.py`,
> `tests/unit/test_saving.py`): §2's `workflow.json`, `data/`, `outputs/` and
> `report.json`, §4's typed and tagged columns, §5 and §6. A data step keeps its
> rows' ids. **Media built too** (S-D1, S-D2, S-D3 as recommended): arrays,
> images in every mode and Plotly figures, exact, by content, the versions of
> images and figures taken from their content. Not yet: layer 3, and big steps
> kept on disk while you work (plan P7d). What a saved session holds, when
> something can be saved, and exactly when something can be lost. Every claim
> marked *run* was run on 2026-11-16 with pyarrow 25.0.1, numpy 2.5.3,
> Pillow 12.3.0 and plotly 7.1.0; the scripts are in
> [saving-probes/](saving-probes/). Where this is built is [plan.md](plan.md) P1c and P7d; the
> decisions are §8 here.

## 1. The promise

1. **A save is exact, or says where it isn't.** Every value is saved exactly,
   or is listed in the save's report with the reason. Never silently
   different.
2. **Core checks, it doesn't assume.** After writing a step, core reads it
   back and compares data versions (§6). Data versions are content-based for
   arrays, images and figures (*run*: values differing in one element, one
   pixel or one bar get different versions).
3. **Loading runs nothing.** A load builds objects from files, the workflow
   and the catalog. It imports nothing and unpickles nothing, so opening a
   session someone sent you is safe.
4. **What isn't saved can be re-made.** The workflow and its entered data
   are always saved, so a value that couldn't be saved is one re-run away,
   and the data version says whether the re-run gave the same value.

## 2. What a session is on disk

```
patients.simple-steps/          one session: one folder
  workflow.json                 steps in order, expressions, stages, resources'
                                settings (never a Secret), extras, each tool's
                                hash; per step, its files and data versions.
                                Format 5
  data/<step>.parquet           data typed, pasted or uploaded into a step
  outputs/<step>/               a step's output, when saved with outputs
    data.parquet                its grid: data columns and lineage, row ids
    states.parquet              a state per cell, the same shape
    meta.json                   run key, data version, verb, warnings, what it
                                read, and how each column was written (§4)
  media/<hash>.<ext>            arrays, images, figures: once each, by content
  report.json                   what the last save couldn't keep exactly (§7)
```

Any step's `data.parquet` opens in pandas, DuckDB, Polars or Excel without
core. A cell holding an array, image or figure shows there as its hash; the
file is in `media/`.

## 3. When you can save

**Always**, in any state, and the save says what it holds:

| Step state | What's saved |
|---|---|
| `staged` (never ran), the empty step | the expression; no output |
| `completed` | the expression and, with outputs, the output |
| `failed` | the same, failed cells and their notes included |
| `stale` | the expression and the output it shows, which loads `stale` with the same reason |
| `invalid` | the expression, its problems re-found on load, and the last output it shows |
| mid-run (the app's `running`) | **today**: what finished before the run started. **With layer 3** (P7d): each finished row too, so the run resumes |

A resource's settings are saved; a `Secret` never is. A loaded kernel asks for
the secret again, and the steps that use that resource wait for it.

## 4. What is kept, value by value

| A cell holds | Saved as | Kept exactly? | *Run* |
|---|---|---|---|
| a number, text, bool, `None` | typed Parquet | **yes**; `None` and `NaN` stay apart; an int column with a gap stays int | yes, through pyarrow (pandas' default read turns these into `NaN` and floats: core never reads that way) |
| *absent* (a key a record lacks, a join gap) | a null, and `absent` in `states.parquet` | **yes** | yes: a join gap is `absent` in the output's states |
| a list, a list of dicts, a dict | typed Parquet (`list<…>`, `struct`, `map<string, …>`) | **yes** when the column has one shape | yes |
| a datetime with a time zone, a `Decimal`, `bytes` | typed Parquet | **yes** | yes |
| a mixed column (`1`, `"a"`), tuples, dict keys that aren't strings, ints past 64 bits | tagged JSON: each value names its type | **yes** | Parquet refuses all four as typed columns; tagged JSON is to build |
| a numpy array (a tensor), any dtype but `object` | `media/<hash>.npy`, written without pickle | **yes**: dtype, shape, memory order, byte order, `NaN`s | yes: uint8 images, float16/32, bool, complex, datetime64, structured, Fortran order, 0-d, big-endian |
| a numpy array of `object` | tagged JSON when its items can be; else not saved | when its items are | `.npy` refuses it without pickle |
| a Pillow image, modes `1`, `L`, `LA`, `P`, `RGB`, `RGBA`, `I;16` | `media/<hash>.png` | **pixels yes** | yes |
| a Pillow image, modes `I`, `F`, `CMYK` | `media/<hash>.tiff` | **pixels yes** | yes. (PNG turns `I` into `I;16`, and refuses `F` and `CMYK`) |
| an image's file format and metadata (EXIF, `info`) | `meta.json`, when JSON can hold it | **no, today**: a JPEG saved as PNG keeps its pixels and loses `format` and `info` | yes: `format` JPEG→PNG, `info` four keys→none. S-D2 |
| a Plotly figure | `media/<hash>.json`, Plotly's JSON | **the figure yes**: every field the same, the JSON stable from the first reload on | yes. Two gaps, both to close: an array inside a figure loads as Plotly's encoded form `{'dtype', 'bdata'}`, not an array (core decodes it back); and the figure's data version changes on reload (core versions a figure by its canonical JSON). S-D3 |
| an object whose class gives `to_saved()` / `from_saved()` | what the class writes; the class found through the catalog | **yes**, as the class defines | to build |
| any other object | **not saved** | **no**: the step loads `stale`, *"column `c`: Thing can't be saved; give Thing to_saved(), or re-run"* | Parquet and `.npy` refuse it; pickle is never used |

**What is never saved, by design:** a tool's code (the workflow saves its
hash, and a changed tool makes its steps `stale`, *tool changed*); a
resource's live object (it's rebuilt from its settings); a `Secret`.

## 5. When a load can't give back what was saved

| On load | The step is | It says |
|---|---|---|
| a file in `data/` or `outputs/` is missing | `invalid` (entered data) or `staged` (an output) | which file |
| a file's data version isn't the one recorded | `invalid` (entered data) or `stale` (an output) | *"data/s.parquet changed since it was saved"* |
| a tool's code changed since the save | `stale` | *tool changed* |
| a column was marked not saved (§4) | `stale` | the column and the reason, from `report.json` |
| a value class's `from_saved` isn't in the catalog | `stale` | the class to add to the catalog |
| a `Secret` is needed | waiting on its resource, as today | the resource |
| the format is older than 5 | the load is refused | core's message (D52) |

Nothing on this list raises: each is a state and a reason, and the rest of
the session loads.

## 6. How core checks a save

For each step, after writing: read its files back, rebuild the grid, and
compare its data version with the one in memory. Equal: the step is exact.
Not equal: the columns that differ are written the next way down
(typed → tagged → media → the class's own → not saved) and checked again, and
anything still not equal is listed in the report. The data versions are
recorded in `workflow.json`, so a later load checks the files too (§5).

## 7. The save's report

`k.save(folder)` returns, and writes to `report.json`, every value it couldn't
keep exactly: the step, the column, the row count, the kind and the reason.
An empty report means the session is exact. The app shows it next to its save
button (*"Saved. 1 step will need a re-run: `fig` (3 cells: Model can't be
saved)"*).

## 8. Decisions

| | Decision | Recommended |
|---|---|---|
| **S-D1** | **Media kinds are built in, as optional codecs**: numpy arrays (`.npy`), Pillow images (PNG, or TIFF for `I`, `F`, `CMYK`), Plotly figures (JSON). Each is used only when its library is installed; core doesn't depend on Pillow or Plotly. More kinds come through the catalog (a codec: a type, `save(value) -> bytes`, `load(bytes) -> value`) | yes. **Tensors are numpy arrays** (owner, 2026-11-16): no torch or other tensor library in core; one would come as a catalog codec only when a user needs it |
| **S-D2** | **An image's format and metadata.** Keep `format` and JSON-able `info` in `meta.json` and put them back on load; or, for an image a tool read from a file and didn't change, keep the original file's bytes | keep `format` and `info`: the pixels are already exact, and it costs nothing |
| **S-D3** | **A Plotly figure's identity is its canonical JSON** (keys sorted, arrays decoded), for its data version and the save check; arrays inside it load as numpy arrays | yes: else every saved figure reports a false loss |
| **S-D4** | **The report**: `k.save` returns it and writes `report.json`; an empty report means exact | yes |
| **S-D5** | **Saving never blocks on a value it can't keep.** It saves the rest and reports | yes: refusing the whole save would lose more |

These go with plan.md P-D12–P-D17 (entered data saved, the folder, layer 3,
pyarrow, how a column is written, step names in file names).
