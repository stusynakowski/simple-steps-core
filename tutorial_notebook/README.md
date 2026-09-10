# Tutorial notebooks

Runnable, top-down tours of the Simple Steps object model. They build each layer
and print `info()` / `repr()` so you can *see* and *test* every object as you go.

| Notebook | What it covers |
|---|---|
| [`01_top_down_walkthrough.ipynb`](01_top_down_walkthrough.ipynb) | The whole hierarchy top-down: `App` \u2192 `AppConfig` / Tools / Resources / Sessions \u2192 `Workflow` \u2192 `Step` (= `Operation` + `Data`). Resource lifecycle (declare \u2192 load \u2192 check \u2192 use), `validate()` preflight, `map` orchestration, stages as views, per-step timing, and the three isolated execution configs. |

## Run it

```bash
pip install -e ".[api]"          # or just: pip install -e .
python -m pip install jupyter    # if you don't already have it
jupyter lab tutorial_notebook/01_top_down_walkthrough.ipynb
```

Every object exposes:

- `repr(obj)` \u2014 one dense line, safe for logs (no payloads).
- `obj.info()` \u2014 a rich `SummaryTable` (HTML in notebooks, aligned text in logs).

See [`docs/object-model.md`](../docs/object-model.md) and
[`docs/execution-model.md`](../docs/execution-model.md) for the full design.
