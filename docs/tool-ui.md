# Tool UI developer contract

A tool UI may be declared for any renderer target. Prefer separate `input` and
`result` views: the host can then provide consistent execution, progress,
errors, layout, and accessibility around both views. Use `full` only when the
experience cannot be cleanly separated, such as a plot builder whose controls
and interactive visualization must share one coordinated surface.

## Declaration modes

Recommended composed declaration:

```python
@register_tool("plot", ui={
    "prefab": {
        "input": plot_input_document,
        "result": plot_result_document,
    },
    "streamlit": {
        "input": render_plot_input,
        "result": render_plot_result,
    },
})
def plot(data: list[dict], x: str, y: str) -> dict: ...
```

Advanced full declaration:

```python
@register_tool("plot", ui={
    "prefab": {"full": plot_builder_document},
})
def plot(data: list[dict], x: str, y: str) -> dict: ...
```

`full` is mutually exclusive with `input` and `result` for the same target. A
composed declaration must include `input`; `result` is optional and hosts may
fall back to a generic result renderer. Existing prefab documents and target
renderers are accepted unchanged and treated as input views.

## Full UI requirements

A developer providing `full` owns the complete presentation and interaction
lifecycle. The full UI must:

1. Keep editable operation arguments in host-recognizable state and submit an
   object matching the operation's `input_schema`.
2. Execute only through actions supplied by the host. It must not bypass core
   validation, guardrails, confirmation, resource injection, sessions, or the
   execution engine.
3. Render coherent idle, validating, running, completed, and failed states,
   including validation messages, retry behavior, and disabled duplicate
   submission while a run is active.
4. Treat execution results as read-only. Local interactions such as plot zoom,
   selected points, tabs, and table sorting belong in separate view state and
   must not mutate the stored result.
5. Handle both inline values and referenced results. Large or paginated data
   must be loaded through host data actions rather than copied wholesale into
   UI state.
6. Namespace local state with the host-provided instance or step key so two
   uses of the same tool do not share arguments, results, or interactions.
7. Use only values supported by its renderer. A serialized prefab declaration
   must be JSON-safe and cannot contain Python callables, JavaScript functions,
   clients, or non-serializable plotting objects.
8. Meet the host's accessibility and responsive-layout requirements, including
   labels, keyboard-operable actions, visible errors, and bounded dimensions
   for plots or other complex widgets.

## Host requirements for full UI

A host that supports `full` must provide a documented adapter exposing:

- Current arguments and a way to update them.
- Execution status and progress.
- The completed value or data reference, shape metadata, and structured error.
- Execute, cancel, reset, retry, and referenced-data loading actions as
  supported by that host.
- A stable instance key and isolated local view state.

The exact binding syntax is renderer-specific. For example, a prefab host uses
serializable state bindings and named actions, while a Python renderer may use
callable adapter methods. `simple-steps-core` declares and validates ownership;
the host remains responsible for implementing these bindings.

## Runtime access

```python
target_ui = operation.ui.for_target("prefab")
input_view = operation.ui.input("prefab")
result_view = operation.ui.result("prefab")
full_view = operation.ui.full("prefab")
```

`operation.ui.get(target)` and `operation.ui.prefab` remain compatibility APIs.
They return the input view for composed declarations and the full view for full
declarations. `ToolDefinition.ui` preserves a legacy input-only document,
but serializes new declarations as `{"input": ..., "result": ...}` or
`{"full": ...}` for frontend discovery.