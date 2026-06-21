# Example API server

A runnable FastAPI app that exposes `simple-steps-core` to a frontend (e.g. a
React UI). It mirrors the patterns in [../../docs/integration.md](../../docs/integration.md)
with working code.

## Run

```bash
python -m pip install -e ".[api]"
uvicorn examples.api_server.app:app --reload
```

Open http://127.0.0.1:8000/docs for interactive Swagger docs.

## Endpoints

| Method & path | Purpose |
| --- | --- |
| `GET /operations` | Operation palette for the UI (id, description, params). |
| `POST /workflows` | Validate + create a workflow from `{step_id, formula}` steps. |
| `POST /workflows/{id}/run` | Execute the workflow asynchronously. |
| `GET /workflows/{id}` | Status + per-step results. |
| `GET /workflows/{id}/dag` | Nodes + edges derived from step references (for graph UIs). |

## Quick walkthrough (curl)

Create a workflow that builds a list, maps an async square over it (one item
fails to show partial-failure handling), then sums the successes:

```bash
curl -s localhost:8000/workflows -X POST -H 'content-type: application/json' -d '{
  "user_id": "alice",
  "workflow_id": "wf-001",
  "steps": [
    {"step_id": "step_nums",   "formula": "=make_list(n=10)"},
    {"step_id": "step_squared","formula": "=map(over=\"step_nums\", op=\"slow_square\", concurrency=4, on_error=\"collect\")"},
    {"step_id": "step_total",  "formula": "=total(data=\"step_squared.ok\")"}
  ]
}'

curl -s localhost:8000/workflows/wf-001/run -X POST
curl -s localhost:8000/workflows/wf-001
curl -s localhost:8000/workflows/wf-001/dag
```

## Frontend integration notes

- **Build the palette** from `GET /operations`. Each param has `name`,
  `type_name`, `required`, `default` — enough to render a form or node inspector.
- **Author steps** as `{step_id, formula}`. To reference an earlier step, name
  it `step_*` and pass its id as a **quoted string**, e.g.
  `data="step_nums"` or `data="step_squared.ok"`.
- **Render a graph** from `GET /workflows/{id}/dag` (`nodes` carry per-step
  `status`; `edges` are `{from, to}`).
- **Partial failures**: a `map` step returns a `MapResult`; the JSON exposes
  `ok` / `failed` so the UI can show which items succeeded.

## Production notes

- The in-memory `STORE` is for demonstration. Swap it for a database; the
  `save` / `load` surface is intentionally tiny.
- For long-running workflows, move `POST /run` onto a task queue (Celery / RQ /
  arq): persist `export_session_json()`, run `await wf.arun()` in the worker,
  store the new snapshot, and let the UI poll `GET /workflows/{id}`.
