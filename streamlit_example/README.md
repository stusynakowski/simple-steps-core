# Streamlit dashboard example

A runnable tools file for the optional **Streamlit dashboard** — a local UI for
building and running workflows from the tools you register.

The dashboard itself lives in the package at
`simple_steps_core.streamlit.dashboard` and is exposed as the `Dashboard` class.
You write a tools file that imports `Dashboard` and calls `Dashboard().run()` at
the bottom; this folder ships one: [example_tools_and_resources.py](example_tools_and_resources.py).

## Run it

From the repository root:

```bash
python -m pip install -e ".[dashboard]"
python streamlit_example/example_tools_and_resources.py
```

That opens the dashboard in your browser. Add steps from the tool palette, wire
one step's output into a later step, then run step-by-step or by stage.

## What the example shows

Each tool in [example_tools_and_resources.py](example_tools_and_resources.py)
demonstrates one dashboard feature:

| Tool          | Demonstrates                                                        |
| ------------- | ------------------------------------------------------------------- |
| `make_list`   | A **custom Streamlit view** via `ui={"streamlit": fn}`.             |
| `scale`       | An **auto-generated form** built from the tool's schema (no `ui`).  |
| `pick_region` | A **multi-target `ui` map** — a hand-written prefab view *and* a Streamlit view in one tool. |
| `charge`      | **Guardrails** that shape the form (`min`/`max`) and gate the run (`requires_confirmation`). |
| `greet`       | A tool that consumes an **injected resource** (`Resource()`).       |

Two optional module-level settings are read by the dashboard:

- `CONFIG` — e.g. `{"title": "My Tools Dashboard"}`.
- `RESOURCES` — name → factory/instance, injected into tools that declare
  `Resource()` parameters (here, `names`).

## Write your own

Copy the example, edit the tools, and run your file directly:

```bash
python path/to/your_tools.py
```

The dashboard reads each tool's `ui.get("streamlit")` view when present and
otherwise auto-builds a form from the schema and guardrails — so a bare
`@register_tool` function already works.
