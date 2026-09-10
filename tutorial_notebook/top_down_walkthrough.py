"""
Top-down walkthrough of the Simple Steps object model — as a plain script.

Run it::

    pip install -e .
    python tutorial_notebook/top_down_walkthrough.py

It builds the whole hierarchy from the top down and prints ``info()`` / ``repr``
at every layer. Mirrors tutorial_notebook/01_top_down_walkthrough.ipynb and
docs/object-model.md.

    App -> AppConfig, Tools, Resources, Sessions
      Session -> Workflows
        Workflow -> Steps (columns)
          Step = Operation (Tool + how) + Data (status/output)
"""

from simple_steps_core import (
    App,
    AppConfig,
    Operation,
    OrchestrationConfig,
    Resource,
    StageExecutionConfig,
    StepExecutionConfig,
    WorkflowExecutionConfig,
    register_tool,
)


def section(title: str) -> None:
    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)


# ── 0. Developers define Tools ───────────────────────────────────────────
@register_tool("make_list", description="Create the list [0, 1, ..., n-1].")
def make_list(n: int) -> list[int]:
    return list(range(n))


@register_tool("scale", description="Multiply a number by a factor.")
def scale(x: int, factor: int = 2) -> int:
    return x * factor


@register_tool("summarize", description="Count and total a list of numbers.")
def summarize(rows: list[int]) -> dict:
    return {"count": len(rows), "total": sum(rows)}


@register_tool("load_rows", description="Load n rows from the injected 'db' resource.")
def load_rows(n: int, db=Resource()) -> list[int]:
    return db.fetch(n)


class FakeDB:
    """Stand-in external resource (a 'database')."""

    def fetch(self, n: int) -> list[int]:
        return list(range(100, 100 + n))

    def close(self) -> None:
        pass


def make_db() -> FakeDB:
    return FakeDB()


def main() -> None:
    # ── 1. App + AppConfig ───────────────────────────────────────────────
    section("1. App + AppConfig — the whole system")
    app = App(AppConfig(title="Tutorial App", port=8123))
    print(repr(app))
    print(app.info())

    # ── 2. Tools ─────────────────────────────────────────────────────────
    section("2. Tools — the registered capabilities")
    print(app.tools_info())
    print()
    print(app.registry.get_definition("scale").info())

    # ── 3. Session ───────────────────────────────────────────────────────
    section("3. Session — one user's isolated area")
    session = app.session("alice")
    print(repr(session))

    # ── 4. Resources: declare -> load -> check -> use ────────────────────
    section("4. Resources — declare, check, use")
    session.resources.register("db", make_db, check=lambda db: db.fetch(1))
    print(session.resources.info())          # status: declared (lazy)
    print()
    print(session.resources.check_all())     # optional hello-world before a batch
    print()
    print(session.resources.info())          # now loaded

    # ── 5. Workflow: author Operations (Tool + how) ──────────────────────
    section("5. Workflow — author Operations")
    wf = session.workflow("demo")
    wf.add(Operation(step_id="step1", name="make_list", stage="load", arguments={"n": 5}))
    wf.add(Operation(step_id="step2", name="load_rows", stage="load", arguments={"n": 3}))
    wf.add(Operation(
        step_id="step3", name="scale", stage="transform",
        arguments={"factor": 10},
        orchestration=OrchestrationConfig(mode="map", over="step1", concurrency=4),
    ))
    wf.add(Operation(step_id="step4", name="summarize", stage="report",
                     arguments={"rows": "step3.ok"}))

    # Isolated, per-scope execution configs (no inheritance / overriding).
    wf.stage_config["transform"] = StageExecutionConfig(steps="parallel", concurrency=4)
    wf.execution = WorkflowExecutionConfig(on_stage_error="stop")
    print(repr(wf))
    print()
    print(wf.validate())                      # dry-run preflight
    print()
    print(wf.info())                          # spreadsheet view BEFORE running

    # ── Preflight catches a missing resource up front ────────────────────
    section("5b. Preflight catches a missing resource")
    bob = app.session("bob")                  # fresh session, no 'db'
    wf_bob = bob.workflow("demo")
    wf_bob.add(Operation(step_id="step1", name="load_rows", arguments={"n": 2}))
    print(wf_bob.validate())

    # ── 6. Run + inspect (timing lands on the Data) ──────────────────────
    section("6. Run + inspect")
    wf.run()
    print(wf.info())                          # completed, with durations
    print()
    print(repr(wf["step3"]))                  # Step repr: status + tool + duration
    print()
    print(wf.preview("step4"))                # payload-free output preview

    # ── Orchestrator output — partial-failure aware ──────────────────────
    section("6b. Orchestrator output (MapResult)")
    result = wf["step3"].output.value
    print(repr(result))
    print("ok     :", result.ok)
    print("failed :", result.failed)
    print("summary:", wf["step4"].output.value)

    # ── 7. Stages as views (a groupby over Steps) ────────────────────────
    section("7. Stages as views")
    for st in wf.stage_views():
        print(" ", repr(st))
    print()
    print(wf.stage("transform").info())

    # ── 8. Roll-up ───────────────────────────────────────────────────────
    section("8. Session & App overview after work")
    print(session.info())
    print()
    print(app.info())

    # ── 9. Isolated execution configs ────────────────────────────────────
    section("9. Execution configs are orthogonal & isolated")
    print("step    :", StepExecutionConfig(timeout=30, retries=2, cache=True))
    print("stage   :", StageExecutionConfig(steps="parallel", concurrency=8))
    print("workflow:", WorkflowExecutionConfig(on_stage_error="continue"))


if __name__ == "__main__":
    main()
