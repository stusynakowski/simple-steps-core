# simple_steps server (minimal example)

Define a few tools, get a running API that lists, calls, and orchestrates them.
The session (data store + references between steps) is managed for you.

## Files

| File | What it is |
| --- | --- |
| [`tools.py`](tools.py) | The only file you edit — decorate plain functions with `@register_operation`. |
| [`server.py`](server.py) | Reusable `build_app(registry, engine)` FastAPI factory. |
| [`app.py`](app.py) | Wires tools + orchestrators into a running app. |

## Run

```bash
python -m pip install -e ".[api]"
uvicorn examples.simple_server.app:app --reload   # http://127.0.0.1:8000/docs
```

## Endpoints

| Method & path | Purpose |
| --- | --- |
| `GET /tools` | The tool palette: id, description, params, JSON Schema. |
| `POST /call` | Run one tool immediately: `{operation_id, arguments}`. |
| `POST /run` | Run a workflow of steps; later steps reference earlier outputs. |

## Examples

Call one tool:

```bash
curl -s localhost:8000/call -X POST -H 'content-type: application/json' -d '{
  "operation_id": "add",
  "arguments": {"a": 2, "b": 3}
}'
# {"value": 5}
```

Run a workflow — build a list, then **square every item** with an inline `map`
(orchestration is declared right on the step):

```bash
curl -s localhost:8000/run -X POST -H 'content-type: application/json' -d '{
  "steps": [
    {"step_id": "step_nums", "name": "make_list", "arguments": {"n": 4}},
    {"step_id": "step_squared", "name": "square",
     "orchestration": {"mode": "map", "over": "step_nums", "concurrency": 4}}
  ]
}'
# {"steps": [
#   {"step_id": "step_nums",    "status": "completed", "value": [0, 1, 2, 3], "error": null},
#   {"step_id": "step_squared", "status": "completed",
#    "value": {"outcomes": [...]}, "error": null}
# ]}
```

## The step shape

Each step in `/run` is a `StepSpec`:

```jsonc
{
  "step_id": "step_squared",
  "name": "square",                 // the tool to run
  "arguments": {},                   // constant data args (for single steps)
  "orchestration": {                 // how to apply the tool
    "mode": "map",                  // single | map | filter | expand | collapse
    "over": "step_nums",            // reference to the collection
    "concurrency": 4,
    "on_error": "collect"
  },
  "execution": {"mode": "sync", "run": "manual"}
}
```

To reference an earlier step's output as a **data** argument, pass its id as a
string. Referenceable step ids must start with `step` (e.g. `step_nums`), so
`"arguments": {"data": "step_nums"}` wires that step's output into `data`.
